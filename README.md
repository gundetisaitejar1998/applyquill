# JobPilot AI

JobPilot AI is a multi-candidate job discovery and application-preparation platform built on the existing React/Vite and FastAPI project. SQLite supports local use; PostgreSQL and Alembic are configured for production. Candidate-owned resumes, profiles, jobs, documents, application records, automation queues, and audit events are isolated by authenticated account.

## What works

- PDF and DOCX resume upload and extraction, version history, editable candidate facts, and candidate verification.
- Ollama role discovery with resume evidence, alternatives, synonyms, and search terms. Ollama is optional; when unavailable the app only uses exact observed resume titles.
- Live job search through Greenhouse, Lever, Arbeitnow, Remotive, Jobicy, Remote OK, and optional Adzuna. Jobicy, Remotive, and Remote OK feeds are cached. Source errors, rate limits, source health, publication time, discovery time, and original listing URLs are kept separately.
- Date filters for 24 hours, 3 days, 7 days, older, and unknown publication dates.
- Explainable score components and conservative eligibility checks. Unknown facts remain unknown; only source-confirmed live vacancies are stored.
- Candidate profile/preferences editor, active resume versions, job/application history, profile-specific ownership checks, and generated document drafts.
- Playwright form preparation for HTTPS application pages. It fills only known candidate facts and explicitly verified screening answers, uploads the active resume, and stops at unknown required fields or verification challenges.
- Durable PostgreSQL/SQLite queue records, recovery leases, daily scheduling in Asia/Kolkata, per-day and per-company submission limits, run history, and Emergency STOP. Submission is disabled by default and requires the server kill switch, explicit candidate opt-in, verified profile, hard eligibility, score threshold, active resume, and an explicitly allow-listed host.

## Platform access boundaries

LinkedIn and Indeed are shown as partner-required integrations; this app does not scrape their pages or bypass sign-in restrictions. Wellfound harvesting is not integrated. The public Remote OK feed requires source credit and direct links, which the connector retains. Review each provider’s current terms before enabling automated applications for any host.

## Local setup

Requirements: Python 3.12+ (Python 3.14 is used in this checkout), Node.js 22+, and Windows, macOS, or Linux. Ollama is optional and is not needed for the application to start.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location frontend
npm ci
Set-Location ..
```

Copy `.env.example` to `.env` and adjust local paths only if needed. `START.bat` launches the local dashboard and API. `CHECK_SETUP.bat` checks installed services and `STOP.bat` stops the processes started by the launcher. The UI defaults to `http://localhost:5173`; the API is `http://127.0.0.1:8000`.

## Tests and build

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend\app backend\tests
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
Set-Location frontend; npm run build; Set-Location ..
```

Connector tests use mocked provider responses. Browser tests use local loopback test forms. They do not submit real job applications. For a permitted live discovery check, use the dashboard and inspect the source report and eligibility reasons.

## Deployment

The repository includes a Render Blueprint and Docker image. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for environment variables, migrations, storage, worker behavior, backups, troubleshooting, and deployment checks. Production uses one disk-backed Uvicorn process: the job queue is database-backed and survives process restarts, while a single worker process claims the queued tasks. Do not scale this disk-backed service horizontally; move resumes and generated files to private shared object storage first.

No public deployment has been created from this checkout. Publishing requires the owner to push the repository to a Git remote and apply the Render Blueprint in their account. That step can incur hosting charges and remains outside this local implementation.

## Data and privacy

Local SQLite is at `data/jobpilot.sqlite3`; source resumes are in `uploads/`, generated files in `generated/`, and local feed caches in `data/`. All are excluded from Git. This task created a local pre-upgrade backup under `data/backups/20261118_before_full_autonomy/`. Keep backups private and encrypted at rest.

No cloud AI provider is configured. The default Ollama integration is local. Pointing `JOBPILOT_OLLAMA_URL` to a hosted endpoint sends resume/profile prompt content to that endpoint; use only a provider and endpoint authorized for candidate data. If Ollama is absent in production, role generation reports the limitation and uses only titles observed in resumes.
