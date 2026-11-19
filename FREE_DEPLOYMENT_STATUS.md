# Free Deployment Status

Last checked: 2026-11-19 (Asia/Kolkata)

## Decision

**Selected architecture: local-first hybrid, with no cloud services enabled.** The complete app runs on the laptop. This is the only verified zero-cost option that keeps resumes, browser profiles, SQLite data, Ollama prompts, the durable queue, and Playwright together without a public endpoint or expiring cloud database. No public URL has been created.

The app is currently reachable on this laptop at `http://localhost:5173`; its FastAPI backend is bound to `127.0.0.1:8000`, and Ollama is available on `127.0.0.1:11434`. These are local URLs, not public deployment URLs. The current worker health endpoint reports ready.

## Provider evaluation

| Provider | Current free capability verified from official docs | Decision |
| --- | --- | --- |
| Cloudflare Pages | Free static asset hosting; free plan allows up to 20,000 files per site. It does not run this FastAPI service, local Ollama, Playwright browser sessions, or the durable worker. | Not selected alone: a static hosted UI cannot safely operate this local backend. Connecting a public UI to a laptop API would expose the laptop and candidate data. [Pages limits](https://developers.cloudflare.com/pages/platform/limits/) |
| GitHub Pages | Available on GitHub Free for public repositories; recommended source repository limit is 1 GB. It hosts static sites only. | Not selected: the project is a private candidate-data application with an API, authentication, and file storage. Publishing the full source repository would not host those services. [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) |
| Vercel Hobby | $0 plan for personal/non-commercial projects; included usage pauses at plan limits in many cases. Hobby is restricted to personal, non-commercial use. | Not selected: static hosting does not provide this persistent FastAPI + Playwright worker stack. No Vercel account was used. [Hobby plan](https://vercel.com/docs/plans/hobby), [Terms](https://vercel.com/legal/terms) |
| Render Free | Free web instances sleep after 15 minutes idle; their filesystem is ephemeral; free Postgres expires after 30 days and is limited to 1 GB. Free services may restart, and excess bandwidth can be billed. | Not selected: uploads, SQLite, browser profiles and continuous automation require durable storage and an always-running worker. Existing paid Render Blueprint was removed to prevent accidental paid provisioning. [Free services](https://render.com/docs/free) |

Free-plan limits can change. No provider account was connected, no payment information was entered, and no cloud resource was provisioned.

## Running locally

- Dashboard: `http://localhost:5173`
- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/health`
- Readiness: `http://127.0.0.1:8000/api/health/ready`
- Worker: `http://127.0.0.1:8000/api/health/worker`
- Ollama: `http://127.0.0.1:11434`; installed models include `qwen2.5:3b` and `qwen2.5:1.5b`.

`START.bat` starts the dashboard and API. `.env.example` documents optional settings. Ollama remains local; do not configure a public Ollama endpoint with private resumes unless its data handling is reviewed.

## Working features

Resume extraction, AI role generation through local Ollama, live job-source discovery, transparent matching and eligibility checks, candidate profile and resume management, authenticated local API, source diagnostics, job/application tracking, Playwright form preparation, verified-answer safeguards, durable local queue, Asia/Kolkata scheduling, crash recovery, and Emergency STOP are implemented. Real submission remains disabled by default. No real applications were submitted.

Latest audit (2026-11-19): backend suite **41 passed**; frontend production build **passed**; Vite `/api` proxy reaches FastAPI; **37 OpenAPI operations** were route-smoke-tested with no 405 or 5xx responses; an isolated clean SQLite schema includes all expected tables. The current local worker is ready. A scheduler smoke test created a scheduled prepare run and queued work in a temporary database. The latest persisted live discovery run checked **23 listings** across Greenhouse (7), Lever (1), Arbeitnow (3), Remotive cached (1), Jobicy cached (10), and Remote OK cached (1); duplicate count was 0. Adzuna needs credentials. Docker image build is blocked because the Docker Linux engine is not running. PostgreSQL Alembic SQL was rendered successfully in offline mode; there is no live PostgreSQL staging server here. The local SQLite database is in use.

Security checks in this audit: npm audit reported **0 vulnerabilities**; pip-audit reported **no known vulnerabilities**; targeted scans of the three Git commits found no common secret/token/private-key patterns; tracked-file review found no resume, document, or database files. These scans do not prove that every possible secret format is absent. Authentication, CSRF, and candidate-isolation behavior are covered by backend tests.

## What free cloud hosting cannot safely run for this app

The reviewed free static or sleeping services cannot guarantee continuous browser automation, persistent browser profiles, private resume/document storage, durable queue processing, or a non-expiring database. A public static UI without its API would be incomplete. A public tunnel to the laptop would expose a personal computer and is not configured. Cloud AI APIs are not configured or used.

## GitHub/deployment authorization still needed

- GitHub CLI is not installed, there is no Git remote, and no GitHub account authorization is configured in the terminal. A Vercel tab open in Chrome belongs to an unrelated financial workspace; it was not touched or used.
- Before a source push, choose a repository under the user’s GitHub account and authenticate through the official GitHub flow. Do not put resumes, `.env`, database files, generated documents, or browser profiles into Git. Credential-pattern scanning of both existing commits found no common token/private-key patterns; the tracked-file review found no candidate resume or database. This is a targeted scan, not a guarantee against every secret format.
- For a cloud UI, the backend would first need a genuinely free, persistent, private API/database/filestore arrangement compatible with FastAPI and a laptop-based automation agent. No currently configured free provider meets those requirements. Do not connect a public frontend until its API, CORS, authentication, storage and data-isolation design are verified.
- No account was created, no legal terms were accepted, and no public site was published during this work.

## Cost statement

**No money was spent.** No payment details were entered, no paid subscription/trial was started, no paid API was used, and no cloud resource was created.
