# Production deployment

> For the latest zero-cost provider comparison and current laptop service status, see [FREE_DEPLOYMENT_STATUS.md](../FREE_DEPLOYMENT_STATUS.md). The former paid Render Blueprint is intentionally disabled; do not apply a paid deployment for this project.

## Hosting recommendation

The Render Blueprint provisions a Docker web service, managed PostgreSQL, deploy-time Alembic migrations, HTTPS, and a persistent disk. It is configured for one instance and one Uvicorn worker. PostgreSQL stores the durable automation queue and audit history; resumes, generated documents, and browser profiles use the attached disk. This is a single-instance deployment footprint. Move documents to private shared object storage and introduce a dedicated worker/concurrency strategy before scaling horizontally.

Render plans in the Blueprint are paid. Applying the Blueprint creates billable resources; this repository has not been published or deployed.

## Prepare and deploy

1. Create a private GitHub, GitLab, or Bitbucket repository and push this project. Review `git status` first. Never push `.env`, `data/`, `uploads/`, `generated/`, `.venv/`, browser profiles, or logs.
2. In Render, choose **New → Blueprint**, connect the repository, inspect the services and prices, then apply `render.yaml`. This step creates paid resources and should be performed in the account owner’s Render workspace.
3. Render builds the Vite UI, installs Python requirements, installs Playwright Chromium and Linux dependencies, runs `alembic upgrade head`, then starts Uvicorn with one worker. The Blueprint health check uses `/api/health/ready`.
4. Wait for a successful deploy and note the `onrender.com` URL. No public URL exists until the owner applies the Blueprint.
5. Verify `/api/health`, `/api/health/ready`, `/api/health/worker`, account registration, candidate isolation, resume upload/version history, source health, live discovery, local test-form preparation, and Emergency STOP. Do not submit to real employers as part of deployment verification.

## Environment and secrets

`render.yaml` generates `JOBPILOT_SECRET_KEY`, gets `DATABASE_URL` from managed PostgreSQL, and mounts persistent storage at `/var/data`. Do not print or commit either secret. Rotating the session secret invalidates existing sessions. Production authentication requires 12-character passwords, secure HTTP-only session cookies, SameSite strict, CSRF validation, and exact-origin CORS. The bundled frontend and API use one origin, so `CORS_ORIGINS` is empty by default.

Environment variables:

- `APP_ENV=production`, `AUTH_ENABLED=true`, `JOBPILOT_SECRET_KEY`, `DATABASE_URL`
- `STORAGE_ROOT=/var/data`, `UPLOAD_DIR=/var/data/uploads`, `GENERATED_DIR=/var/data/generated`, `DATA_DIR=/var/data/cache`
- `JOBPILOT_OLLAMA_URL`, `JOBPILOT_OLLAMA_MODEL` (optional), `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` (optional)
- `JOBPILOT_GREENHOUSE_BOARDS`, `JOBPILOT_LEVER_SITES` (optional employer board handles)
- `ALLOW_REAL_SUBMISSIONS=false`, `AUTOMATION_ALLOWED_HOSTS=` (keep defaults until operator and platform-policy review)
- `CAPTURE_AUTOMATION_SCREENSHOTS=false` (screenshots can contain candidate PII)

Ollama is optional and is not bundled. There is no automatic switch to a cloud LLM. A reachable hosted Ollama endpoint receives resume/profile prompt contents; use only an endpoint whose privacy, retention, and access controls have been approved for candidate data. Without Ollama, parsing and exact observed-title search still work, but generated related roles are unavailable.

## Database migrations

Production schema changes are managed by Alembic. Render runs `alembic upgrade head` during pre-deploy. For an operator-managed deployment, use the same release image and run:

```sh
alembic upgrade head
```

before routing traffic to the new application. Do not point a local or test environment at a production `DATABASE_URL`. This checkout successfully rendered PostgreSQL migration SQL in Alembic offline mode; a live clean PostgreSQL server was unavailable locally, so execute and verify migrations against a private staging database before the first production release.

Local SQLite initialization is additive. A pre-upgrade snapshot of this workspace’s database and documents is in `data/backups/20261118_before_full_autonomy/` and remains Git-ignored. Do not use that candidate data in a public deployment. Production should start with a fresh database unless a separate consented migration is planned.

## Browser automation and background execution

The Docker build installs Playwright Chromium and system libraries. The service uses a per-candidate persistent browser profile under `STORAGE_ROOT/browser-profiles`. Public application pages must use HTTPS. Configure explicit hostnames in `AUTOMATION_ALLOWED_HOSTS` only after confirming that automated application actions are permitted by the specific platform and employer.

The queue, worker leases, schedules, and activity events are stored in PostgreSQL. The FastAPI lifespan starts one queue/scheduler loop, and the Render command pins Uvicorn to one worker for single-claim behavior. The database survives process restarts: expired preparation tasks can requeue; interrupted submission tasks transition to **Verification required** and are never automatically retried. Schedules use the candidate-configured timezone, defaulting to Asia/Kolkata.

Real submissions require both `ALLOW_REAL_SUBMISSIONS=true` and an explicit per-candidate submission opt-in. The daily limit is at most 10, company limit at most 2, and the default minimum score is 75. The pipeline also requires explicit profile verification, hard eligibility, an active resume, a configured allow-listed host, no duplicate/in-flight attempt, valid form controls, and known required answers. CAPTCHA, OTP, MFA, identity checks, and unknown mandatory questions stop the task. A submit action is recorded as **Submitted** only after a recognized confirmation appears; otherwise it is marked for manual verification. Keep the process kill switch off until policy review and staged local testing are complete.

Emergency STOP flags the run, cancels queued tasks, and is checked again by the worker immediately before submission. Preparation and submission activity is available in the dashboard. `/api/health/worker` reports the worker heartbeat separately from database readiness.

Do not scale the disk-backed service to multiple instances. Multi-instance deployment needs shared object storage and a separately operated worker service with an explicit distributed queue lease/locking plan.

## File storage and backups

- `/var/data/uploads` stores uploaded resumes; `/var/data/generated` stores generated candidate documents; `/var/data/browser-profiles` stores persistent browser state. These are not baked into the image or served as static files.
- Back up PostgreSQL and the persistent disk independently. Browser profiles can contain session data; include them only if policy permits and protect backups with encryption and strict access control.
- Test database and disk restore procedures in private staging. Verify candidate ownership and document paths before restoring service. Never run automation against a restored test environment.
- The local SQLite database and `uploads/`/`generated/` directories are Git-ignored. Back up SQLite using its online backup API before schema work and preserve its linked documents.

## Monitoring and troubleshooting

- `/api/health`: process liveness.
- `/api/health/ready`: database readiness and Render health check.
- `/api/health/worker`: worker heartbeat; a stale status means the queue loop is not running.
- `/api/job-sources/health`: last provider status, response code, duration, and sanitized error.
- Dashboard source diagnostics distinguish empty feeds, provider errors, missing credentials, and location/role filters.
- Logs go to stdout/stderr. HTTPX request URLs are suppressed to avoid credential-bearing query strings. API errors include request IDs without serializing exception response bodies.
- If a provider is unconfigured, supply only its documented credentials/board handles. Do not scrape restricted job boards or bypass anti-bot/authentication controls.
- If Playwright cannot launch in a hosting environment, check Chromium installation and system libraries during image build; do not assume a local browser test proves the container runtime is healthy.

## Other hosting providers

Build the Dockerfile and provide PostgreSQL, HTTPS, secret storage, a persistent volume mounted at `/var/data`, Alembic pre-start migrations, and a single Uvicorn process. Keep `PORT` set to the platform-provided port. A split frontend must set `VITE_API_BASE` at build time and configure exact CORS and same-site cookie/CSRF settings; same-origin frontend and API are preferred.

## Deployment blockers in this workspace

There is no Git remote or connected Render account here, and Docker Desktop’s Linux engine is not running. No paid service was created. The app is prepared for deployment, but a public URL and Docker image build require the owner to push the repo and apply the Blueprint in an authorized hosting account. A live PostgreSQL migration run must also be verified in staging before production.
