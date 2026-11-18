"""Small DB-API compatibility layer for local SQLite and production PostgreSQL.

Application queries remain parameterized and use ``?`` placeholders. PostgreSQL
schema changes are managed by Alembic; SQLite is initialized for local development.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", str(ROOT))).resolve()
DATA = Path(os.getenv("DATA_DIR", str(STORAGE_ROOT / "data"))).resolve()
UPLOADS = Path(os.getenv("UPLOAD_DIR", str(STORAGE_ROOT / "uploads"))).resolve()
GENERATED = Path(os.getenv("GENERATED_DIR", str(STORAGE_ROOT / "generated"))).resolve()
DB_PATH = DATA / "jobpilot.sqlite3"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))

for folder in (DATA, UPLOADS, GENERATED):
    folder.mkdir(parents=True, exist_ok=True)


class PostgresConnection:
    """Translate the project's SQLite-style parameter syntax for psycopg."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql, params=()):
        ignore = bool(re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\s", sql, re.I))
        if ignore:
            sql = re.sub(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\s", "INSERT INTO ", sql, count=1, flags=re.I)
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        sql = sql.replace("?", "%s")
        return self._connection.execute(sql, params)


@contextmanager
def connect():
    if USE_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        url = DATABASE_URL.replace("postgres://", "postgresql://", 1).replace("postgresql+psycopg://", "postgresql://", 1)
        db = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
        try:
            yield PostgresConnection(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return

    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    if USE_POSTGRES:
        # Render runs ``alembic upgrade head`` before starting the web process.
        with connect() as db:
            db.execute("SELECT 1")
        return

    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            session_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            csrf_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, email TEXT DEFAULT '', phone TEXT DEFAULT '', location TEXT DEFAULT '', summary TEXT DEFAULT '',
            profile_json TEXT NOT NULL DEFAULT '{}', preferences_json TEXT NOT NULL DEFAULT '{}',
            resume_path TEXT DEFAULT '', resume_name TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            title TEXT NOT NULL, company TEXT DEFAULT '', location TEXT DEFAULT '', url TEXT NOT NULL,
            description TEXT DEFAULT '', source TEXT DEFAULT '', posted_at TEXT DEFAULT '', salary TEXT DEFAULT '', job_type TEXT DEFAULT '', matched_role TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen_run_id INTEGER DEFAULT NULL, work_mode TEXT DEFAULT '', discovered_at TEXT, expires_at TEXT, expired INTEGER,
            external_id TEXT, canonical_url TEXT, employment_type TEXT, salary_min REAL, salary_max REAL, salary_currency TEXT,
            experience_min REAL, experience_max REAL, match_score INTEGER, eligibility_status TEXT DEFAULT 'unknown',
            eligibility_reasons TEXT DEFAULT '[]', last_checked_at TEXT,
            UNIQUE(candidate_id, url)
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'Discovered',
            match_score INTEGER DEFAULT 0, notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, normalized_job_url TEXT, company_key TEXT, job_key TEXT,
            resume_version_id INTEGER, application_date TEXT, submission_status TEXT DEFAULT 'not_started',
            confirmation_details TEXT DEFAULT '', failure_reason TEXT DEFAULT '', last_activity_at TEXT,
            UNIQUE(candidate_id, job_id)
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL, kind TEXT NOT NULL, path TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS role_maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            model TEXT NOT NULL, roles_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS source_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            query_json TEXT NOT NULL, report_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS source_boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL, identifier TEXT NOT NULL, region TEXT DEFAULT 'global', label TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(provider,identifier,region)
        );
        CREATE TABLE IF NOT EXISTS resume_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL, file_name TEXT NOT NULL, profile_json TEXT NOT NULL DEFAULT '{}',
            sha256 TEXT DEFAULT '', is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(candidate_id,file_path)
        );
        CREATE TABLE IF NOT EXISTS source_health (
            source TEXT PRIMARY KEY, status TEXT NOT NULL, checked_at TEXT NOT NULL, duration_ms INTEGER DEFAULT 0,
            http_status INTEGER, success_count INTEGER DEFAULT 0, error_count INTEGER DEFAULT 0, last_error TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS automation_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL UNIQUE REFERENCES candidates(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, config_json TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 0, submissions_enabled INTEGER NOT NULL DEFAULT 0,
            schedule_enabled INTEGER NOT NULL DEFAULT 0, schedule_time TEXT DEFAULT '09:00', timezone TEXT DEFAULT 'UTC',
            last_scheduled_date TEXT DEFAULT '', updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS automation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'queued',
            stop_requested INTEGER NOT NULL DEFAULT 0, config_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT, completed_at TEXT, last_error TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS automation_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL REFERENCES automation_runs(id) ON DELETE CASCADE,
            candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
            task_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
            available_at TEXT DEFAULT CURRENT_TIMESTAMP, lease_until TEXT, last_error TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS automation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER REFERENCES automation_runs(id) ON DELETE SET NULL,
            candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        columns={row[1] for row in db.execute("PRAGMA table_info(jobs)")}
        definitions={"salary":"TEXT DEFAULT ''","job_type":"TEXT DEFAULT ''","matched_role":"TEXT DEFAULT ''","last_seen_run_id":"INTEGER","work_mode":"TEXT DEFAULT ''","discovered_at":"TEXT","expires_at":"TEXT","expired":"INTEGER","external_id":"TEXT","canonical_url":"TEXT","employment_type":"TEXT","salary_min":"REAL","salary_max":"REAL","salary_currency":"TEXT","experience_min":"REAL","experience_max":"REAL","match_score":"INTEGER","eligibility_status":"TEXT DEFAULT 'unknown'","eligibility_reasons":"TEXT DEFAULT '[]'","last_checked_at":"TEXT"}
        for name,definition in definitions.items():
            if name not in columns: db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        db.execute("UPDATE jobs SET discovered_at=COALESCE(discovered_at,created_at) WHERE discovered_at IS NULL")
        app_columns={row[1] for row in db.execute("PRAGMA table_info(applications)")}
        app_definitions={"normalized_job_url":"TEXT","company_key":"TEXT","job_key":"TEXT","resume_version_id":"INTEGER","application_date":"TEXT","submission_status":"TEXT DEFAULT 'not_started'","confirmation_details":"TEXT DEFAULT ''","failure_reason":"TEXT DEFAULT ''","last_activity_at":"TEXT"}
        for name,definition in app_definitions.items():
            if name not in app_columns: db.execute(f"ALTER TABLE applications ADD COLUMN {name} {definition}")
        candidate_columns={row[1] for row in db.execute("PRAGMA table_info(candidates)")}
        if "user_id" not in candidate_columns:
            db.execute("ALTER TABLE candidates ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        board_columns={row[1] for row in db.execute("PRAGMA table_info(source_boards)")}
        if "user_id" not in board_columns:
            db.execute("ALTER TABLE source_boards ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_app_candidate_normalized_url ON applications(candidate_id,normalized_job_url) WHERE normalized_job_url IS NOT NULL AND normalized_job_url!=''")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_app_candidate_company_job ON applications(candidate_id,company_key,job_key) WHERE company_key IS NOT NULL AND company_key!='' AND job_key IS NOT NULL AND job_key!=''")
        db.execute("CREATE INDEX IF NOT EXISTS ix_automation_queue_pending ON automation_queue(status,available_at,id)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_automation_queue_active_candidate_job ON automation_queue(candidate_id,job_id,task_type) WHERE job_id IS NOT NULL AND status IN ('queued','processing')")
        db.execute("CREATE INDEX IF NOT EXISTS ix_automation_events_candidate_created ON automation_events(candidate_id,created_at)")
        # Preserve existing uploaded resumes as the first version when upgrading a local database.
        for row in db.execute("SELECT id,resume_path,resume_name,profile_json FROM candidates WHERE COALESCE(resume_path,'')!=''").fetchall():
            db.execute("INSERT OR IGNORE INTO resume_versions(candidate_id,file_path,file_name,profile_json,is_active) VALUES(?,?,?,?,1)",(row[0],row[1],row[2] or Path(row[1]).name,row[3] or '{}'))


def rowdict(row):
    return dict(row) if row else None
