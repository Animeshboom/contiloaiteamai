# StudioTrack AI

Artist attendance, task assignment, quality review and AI-assisted end-of-day production reporting for an AI film studio.

> **Status:** Phases 1–2 complete (foundation, employees/teams, attendance, projects/episodes/scenes, assignments, role-based UI). See [docs/PLAN.md](docs/PLAN.md).

## Project structure

```
StudioTrack-AI/
├── docker-compose.yml         # Postgres (later: api, frontend, gmail-mcp)
├── .env.example               # all configuration, documented
├── docs/PLAN.md               # phased development checklist
├── backend/                   # FastAPI + SQLAlchemy + Alembic
│   ├── app/
│   │   ├── core/              # config, database, security (JWT/bcrypt), RBAC deps, errors, time utils
│   │   ├── models/            # SQLAlchemy models (19 tables)
│   │   ├── schemas/           # Pydantic request/response models
│   │   ├── services/          # business logic (routers stay thin)
│   │   ├── api/routes/        # HTTP endpoints
│   │   └── main.py            # app, CORS, error handlers, rate limiter
│   ├── alembic/versions/      # migrations
│   ├── scripts/seed.py        # demo data
│   └── tests/                 # pytest
├── frontend/                  # React + TS + Vite + Tailwind v4 + shadcn/ui + React Query + Recharts
│   └── src/{pages, components, components/ui, lib}
└── mcp_servers/gmail/         # Gmail MCP server (Python MCP SDK)           (Phase 4)
```

## Prerequisites

- Python 3.11 (the `py -3.11` launcher on Windows)
- Node.js 20+
- Docker Desktop (for Postgres)

## Local setup

```bash
cp .env.example .env                     # then set JWT_SECRET_KEY
docker compose up -d db                  # Postgres on localhost:5434

cd backend
py -3.11 -m venv .venv                   # macOS/Linux: python3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m scripts.seed     # demo accounts + demo projects
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

You can find the interactive API docs at http://localhost:8000/docs.

In a second terminal, start the frontend (it proxies `/api` to port 8000):

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

> **OneDrive note:** this folder is inside OneDrive. OneDrive can lock files in `node_modules`/`.venv` while syncing
> (seen as `EPERM` during `npm install`). If that happens, pause syncing or exclude those folders.

### Tests

```bash
cd backend
.venv/Scripts/python -m pytest                           # SQLite (fast, no setup)
TEST_DATABASE_URL=postgresql+psycopg://studiotrack:studiotrack@localhost:5434/studiotrack_test \
  .venv/Scripts/python -m pytest                         # same suite on Postgres

cd ../frontend && npm test                               # Vitest: timezone helpers, login flow
```

## Demo accounts (demo data only)

| Role | Email | Password |
|---|---|---|
| Admin | admin@studiotrack.demo | `Admin@12345` |
| Team Lead (Animation) | lead.anim@studiotrack.demo | `Lead@12345` |
| Team Lead (Compositing) | lead.comp@studiotrack.demo | `Lead@12345` |
| Artist (Animation) | artist.arjun@ / artist.sara@ / artist.leo@studiotrack.demo | `Artist@12345` |
| Artist (Compositing) | artist.nina@ / artist.dev@studiotrack.demo | `Artist@12345` |

Demo projects: **Neon Monsoon (Demo)**, a series with 2 episodes and 11 scenes, and **The Last Letter (Demo)**, a short film with 1 episode and 8 scenes.

## API

The full endpoint reference is in [docs/API.md](docs/API.md). The OpenAPI UI is at `/docs` while the API is running.

## Security model

- Passwords hashed with bcrypt. Responses for failed logins are generic and use timing-safe dummy hashing.
- JWTs carry a `token_version`. Changing a password, or deactivating or re-roling a user, invalidates existing tokens.
- **Roles are always read from the database**, never trusted from the token. This is covered by a test that forges a valid "admin" claim.
- Errors return `{error, detail}`. Stack traces go only to server logs.
- Every login, failed login and password change is written to `audit_logs`.
- Every service call is scoped: team leads only see and act on their own teams' people and projects; artists only their own work. Out-of-scope IDs return 404.
- The frontend's role checks are UX only; every permission is enforced by the API and covered by tests.
- The JWT is kept in `localStorage` for this prototype. For production, consider httpOnly cookies plus CSRF protection.
