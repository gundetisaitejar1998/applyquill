"""Production schema with accounts and candidate ownership."""
from alembic import op
import sqlalchemy as sa

revision = "20261118_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("session_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_expiry", "auth_sessions", ["user_id", "expires_at"])

    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("email", sa.String(320), server_default="", nullable=False),
        sa.Column("phone", sa.String(80), server_default="", nullable=False), sa.Column("location", sa.String(300), server_default="", nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False), sa.Column("profile_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("preferences_json", sa.Text(), server_default="{}", nullable=False), sa.Column("resume_path", sa.Text(), server_default="", nullable=False),
        sa.Column("resume_name", sa.String(255), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False), sa.Column("company", sa.Text(), server_default="", nullable=False),
        sa.Column("location", sa.Text(), server_default="", nullable=False), sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False), sa.Column("source", sa.Text(), server_default="", nullable=False),
        sa.Column("posted_at", sa.Text(), server_default="", nullable=False), sa.Column("salary", sa.Text(), server_default="", nullable=False),
        sa.Column("job_type", sa.Text(), server_default="", nullable=False), sa.Column("matched_role", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_run_id", sa.Integer()), sa.Column("work_mode", sa.Text(), server_default="", nullable=False),
        sa.UniqueConstraint("candidate_id", "url", name="uq_jobs_candidate_url"),
    )
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), server_default="Discovered", nullable=False), sa.Column("match_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "job_id", name="uq_applications_candidate_job"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="SET NULL")), sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "role_maps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.Text(), nullable=False), sa.Column("roles_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "source_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query_json", sa.Text(), nullable=False), sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "source_boards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False), sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), server_default="global", nullable=False), sa.Column("label", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "provider", "identifier", "region", name="uq_source_boards_user_provider_identifier_region"),
    )


def downgrade():
    for table in ("source_boards", "source_runs", "role_maps", "documents", "applications", "jobs", "candidates", "auth_sessions", "users"):
        op.drop_table(table)
