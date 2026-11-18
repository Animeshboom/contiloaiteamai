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

# Demo stack with seeded demo accounts:
SEED_DEMO_DATA=true docker compose --profile app up -d --build
open http://localhost:8080          # set WEB_PORT=8090 if 8080 is taken
```

The API runs in production mode inside Docker. It **refuses to start** with placeholder secrets or the mock email provider, and API docs are disabled.

For a **real deployment**, leave `SEED_DEMO_DATA` unset and create the first administrator:

```bash
docker compose --profile app run --rm api python -m scripts.create_admin --email ops@yourstudio.com --name "Studio Ops"
```

## Local development (from source)

Prerequisites: Python 3.11, Node.js 20+, Docker (for Postgres).

```bash
cp .env.example .env                     # dev defaults work as-is
docker compose up -d db                  # Postgres on localhost:5434

cd backend
py -3.11 -m venv .venv                   # macOS/Linux: python3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m scripts.seed     # demo accounts + demo projects
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000     # API docs: http://localhost:8000/docs

cd ../frontend
npm install
npm run dev                              # http://localhost:5173 (proxies /api to :8000)
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

## Demo accounts (demo data only, never in production)

| Role | Email | Password |
|---|---|---|
| Admin | admin@studiotrack.demo | `Admin@12345` |
| Team Lead (Animation) | lead.anim@studiotrack.demo | `Lead@12345` |
| Team Lead (Compositing) | lead.comp@studiotrack.demo | `Lead@12345` |
| Artist (Animation) | artist.arjun@ / artist.sara@ / artist.leo@studiotrack.demo | `Artist@12345` |
| Artist (Compositing) | artist.nina@ / artist.dev@studiotrack.demo | `Artist@12345` |

Demo projects: **Neon Monsoon (Demo)** (a series: 2 episodes, 11 scenes) and **The Last Letter (Demo)** (a short film: 1 episode, 8 scenes). Two authorized report recipients are configured: producer@ and studio.head@studiotrack.demo.

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
| `EMAIL_PROVIDER` | `mcp` (default) or `mock` (tests) |
| `GMAIL_BACKEND` | `mock` (writes `.eml` files) or `gmail` |
| `GMAIL_CREDENTIALS_FILE`, `GMAIL_TOKEN_FILE` | Gmail OAuth files — see [docs/GMAIL_SETUP.md](docs/GMAIL_SETUP.md) |
| `SEED_DEMO_DATA` | Docker only; `true` seeds demo accounts. Never use it for real deployments |

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
