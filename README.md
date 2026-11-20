# StudioTrack AI

StudioTrack AI is an internal production and workforce platform for an AI film studio. It covers:
- artist attendance
- scene and episode assignments
- partial submissions with lead review
- notifications and email via a Gmail MCP server
- AI-assisted end-of-day production reports

**Status:** all six phases are complete, and every step of the Definition of Done passes end to end. The 17-step walkthrough was run in a real browser against both the development servers and the Docker production stack. See [docs/PLAN.md](docs/PLAN.md).

## Architecture

```
 browser ──▶ nginx (web)  ── static React app (Vite, Tailwind v4, shadcn/ui, React Query, Recharts)
               │  /api/*
               ▼
           FastAPI (api) ── SQLAlchemy ── PostgreSQL (db)
               │  ├─ Claude API (Anthropic SDK): narrative for EOD reports only
               │  └─ email outbox ──MCP (stdio)──▶ Gmail MCP server ──▶ Gmail API (OAuth 2.0)
               │                                   (bundled in the api image)  or mock .eml files
               └─ background loop: outbox dispatch + deadline reminders
```

| Path | What it holds |
|---|---|
| `backend/app/` | FastAPI app, organised as `core/`, `models/`, `schemas/`, `services/` (all business logic) and `api/routes/` (thin) |
| `backend/alembic/versions/` | Migrations 0001–0003 |
| `backend/tests/` | 139 pytest tests (SQLite or Postgres) |
| `mcp_servers/gmail_mcp/` | Standalone Gmail MCP server (Python MCP SDK) |
| `frontend/src/` | `pages/`, `components/`, `components/ui/` (shadcn primitives), `lib/` (API client, queries, types, formatting) |
| `docs/` | `PLAN.md` · `API.md` · `GMAIL_SETUP.md` · `SECURITY.md` |

## Quick start (Docker)

```bash
cp .env.example .env
# Generate the two secrets (each must be a long random value):
#   python -c "import secrets; print(secrets.token_urlsafe(48))"   -> JWT_SECRET_KEY, EMAIL_APPROVAL_SECRET

# First administrator (created on first start; remove ADMIN_PASSWORD from .env afterwards):
#   ADMIN_EMAIL=you@yourstudio.com  ADMIN_PASSWORD=<12+ chars>  ADMIN_NAME="Your Name"
# Gmail: set GMAIL_CREDENTIALS_FILE / GMAIL_TOKEN_FILE (docs/GMAIL_SETUP.md), APP_BASE_URL=http://localhost:8080
docker compose --profile app up -d --build
open http://localhost:8080          # set WEB_PORT=8090 if 8080 is taken
```

The API runs in production mode inside Docker. It **refuses to start** with placeholder secrets, mock email, or a localhost `APP_BASE_URL`. Gmail can be added later: until then emails stay queued, and API docs are disabled.

## Deploy (free): Vercel (web) + Render (API) + Neon (Postgres)

Step-by-step, copy-paste version: [docs/DEPLOY_STEPS.txt](docs/DEPLOY_STEPS.txt).

The web app is static and goes on Vercel. The API needs an always-on server (background email/reminder jobs, the bundled Gmail MCP process, persistent uploads), so it goes on Render, with the database on Neon. On the free plans it sleeps when idle and uploads are not kept across restarts; see `render.yaml` to upgrade.

1. **Neon** (free Postgres): create a project and copy its connection string.
2. **Render** (free plan): Dashboard → *New → Blueprint* → select this GitHub repo. `render.yaml` creates `studiotrack-api` (Docker). When prompted, fill in `DATABASE_URL` (the Neon string), `APP_BASE_URL` (your Vercel URL), `CORS_ORIGINS` (`["<your Vercel URL>"]`), `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and optionally `ANTHROPIC_API_KEY`. Gmail (`GMAIL_CREDENTIALS_JSON`, `GMAIL_TOKEN_JSON`) can be added later; until then emails stay queued. JWT and approval secrets are generated for you.
3. **Vercel**: *Add New → Project* → import this repo → **Root Directory: `frontend`** (framework Vite is detected; settings come from `frontend/vercel.json`). If your Render URL is not `https://studiotrack-api.onrender.com`, change the `/api` rewrite in `frontend/vercel.json`.
4. Sign in with `ADMIN_EMAIL`, change the password under **Settings**, then delete `ADMIN_PASSWORD` from Render's environment.

Vercel proxies `/api/*` to Render, so the browser only ever talks to one origin (no CORS, strict CSP intact).

## Local development (from source)

Prerequisites: Python 3.11–3.14, Node.js 20+. Docker is optional (the application runs out-of-the-box on SQLite with mock email outbox).

### One-Click Quick Start (Windows)
Double-click `run_local.bat` or run:
```powershell
.\run_local.ps1
```
This automatically applies migrations, seeds sample studio demo accounts, and starts both backend (port 8000) and frontend (port 5173).

Open **http://localhost:5173** to sign in. The login page has quick-autofill buttons for:
- **Admin:** `admin@studiotrack.demo` / `Admin@12345`
- **Lead:** `lead.anim@studiotrack.demo` / `Lead@12345`
- **Artist:** `artist.arjun@studiotrack.demo` / `Artist@12345`

### Manual Start (Terminal)

```bash
# Backend:
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# Frontend:
cd frontend
npm run dev                              # http://localhost:5173
```

> **OneDrive note:** this folder is inside OneDrive, which can lock files in `node_modules` or `.venv` while syncing (`EPERM` during installs). If that happens, pause syncing or exclude those folders.

### Tests

```bash
cd backend
.venv/Scripts/python -m pytest                           # 139 tests on SQLite
TEST_DATABASE_URL=postgresql+psycopg://studiotrack:studiotrack@localhost:5434/studiotrack_test \
  .venv/Scripts/python -m pytest                         # same suite on Postgres

cd ../frontend
npm test                                                 # Vitest: timezone, login, review panel, report approval
```

The backend suite covers authentication, RBAC and scoping, attendance, assignments, partial submissions, approval, rejection and revisions, notifications and deduplication, the email outbox and duplicate prevention, the Gmail MCP server (in-memory protocol and a spawned subprocess), EOD metric arithmetic, the AI safeguards, report approval and sending, and production config checks.

## Definition of Done walkthrough

1. Sign in as **admin**. Under **Employees**, add a team lead and an artist. Under **Teams**, create a team led by the new lead. Under **Projects**, create a project for that team, then **Add episode** with generated scenes.
2. Sign in as the **lead**. Under **Assignments → New assignment**, pick the project, episode and two scenes, and the artist. The deadline defaults to today's end of day.
3. Sign in as the **artist**. **Check in**. Open the assignment, choose **Submit work**, select the scenes, then add a description, links, comments and optional files.
4. Sign in as the **lead**. Under **Reviews**, approve all scenes, approve some, or request a revision with feedback. The artist is notified in-app and by email.
5. As the **lead**, open **EOD Reports → Generate report**. Use **Preview**, edit if needed, then **Approve & send…**. The report is delivered through the Gmail MCP server and listed in **Report history**.

## Configuration

Every setting is documented in [`.env.example`](.env.example). The main ones:

| Setting | Purpose |
|---|---|
| `JWT_SECRET_KEY`, `EMAIL_APPROVAL_SECRET` | Long random secrets. Production refuses placeholders |
| `STUDIO_TIMEZONE`, `EOD_DEADLINE_HOUR` | All dates and deadlines use studio time |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Optional Claude narrative (default `claude-opus-5-5`). Without a key, a template is used |
| `EMAIL_PROVIDER`, `GMAIL_BACKEND` | `mcp` + `gmail` (real delivery). `mock` exists only for the automated tests |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Bootstrap the first administrator at container start |
| `GMAIL_CREDENTIALS_FILE`, `GMAIL_TOKEN_FILE` | Gmail OAuth files — see [docs/GMAIL_SETUP.md](docs/GMAIL_SETUP.md) |

### What needs configuring for production
- **Gmail:** an OAuth client and a one-time authorization, using the `gmail.compose` scope only. See [docs/GMAIL_SETUP.md](docs/GMAIL_SETUP.md). Mount the files into `./secrets` and set `DOCKER_GMAIL_CREDENTIALS_FILE=/app/secrets/client_secret.json` and `DOCKER_GMAIL_TOKEN_FILE=/app/secrets/gmail_token.json`.
- **Claude:** `ANTHROPIC_API_KEY`.
- **Infrastructure:** TLS in front of nginx, a strong `POSTGRES_PASSWORD`, and a read-only DB role for the MCP server. See [docs/SECURITY.md](docs/SECURITY.md).

## AI and email safeguards (summary)

- **Numbers never come from the AI.** EOD figures are SQL-computed and snapshotted. Claude writes only the narrative, from that snapshot. A number guard discards any text containing a figure not in the records.
- **The AI can't send email.** Sending requires a lead's explicit approval. The approval issues an HMAC token over the report, approver, time and exact recipients, and the Gmail MCP server verifies it before sending the database-stored content.
- **The MCP server enforces its own policy:** active artists only, authorized recipients only, and each idempotency key delivered at most once.

## Docs

- [docs/API.md](docs/API.md): every endpoint, with roles and rules. Interactive docs are at `/docs` in development.
- [docs/GMAIL_SETUP.md](docs/GMAIL_SETUP.md): the Gmail MCP architecture, its tools, and production OAuth setup.
- [docs/SECURITY.md](docs/SECURITY.md): review findings and fixes, controls, and known limitations.
- [docs/PLAN.md](docs/PLAN.md): phased checklist and design decisions.
