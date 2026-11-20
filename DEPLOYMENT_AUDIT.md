# StudioTrack AI — Deployment Audit

Audit date: 2026-11-20 · Branch audited: `main` @ `bbb7937` · Auditor: Claude Code (with repository owner)

This records the state of the repository and the previous deployment **before** the clean redeploy. Nothing was deleted; the old configuration is kept for reference.

## 1. Executive summary

The application code is in good shape: 143 backend tests and 12 frontend tests passed at baseline, the production build succeeds, migrations apply cleanly to Postgres 16, and models and migrations are in sync (`alembic check`). **The login failures and 404s come from the deployment, not the code.** Two independent faults were confirmed by probing the live old deployment (read-only HTTP requests):

| Probe | Result | Meaning |
|---|---|---|
| `GET https://studiotrack-api.onrender.com/api/health` | **404**, header `x-render-routing: no-server` | No Render service exists at the hostname the frontend proxies to. Every API call, including login, returns 404. |
| `GET https://studiosrackai.vercel.app/` | 200 | Static page is served |
| `GET https://studiosrackai.vercel.app/login` | **404** | The deployed Vercel project has no SPA fallback, so refreshing or deep-linking any route 404s. This points to the wrong repo or Root Directory still being connected (`docs/DEPLOY_STEPS.txt` mentions an old `studiosrackai` repo). |
| `GET https://studiosrackai.vercel.app/api/health` | **404** | Proxy rewrite isn't active, or its target doesn't exist (see first row) |

A deployment that relies on a hardcoded proxy hostname in two `vercel.json` files is fragile. If the Render service isn't created, is renamed or gets a suffix, login breaks with no clear error.

## 2. Repository inventory

| Area | Location | Notes |
|---|---|---|
| Frontend | `frontend/` | React 19, Vite 8 (rolldown), TypeScript 5.8, Tailwind 4, React Router 7, TanStack Query. Vitest tests. |
| Backend | `backend/app/` | FastAPI 0.163, SQLAlchemy 2.0, Pydantic 2, Python 3.11. Layers: `core/`, `models/`, `schemas/`, `services/`, `api/routes/`. |
| Database models | `backend/app/models/` | 19 tables: Role, User, Team, AuthorizedRecipient, Project, Episode, Scene, Assignment, AssignmentScene, AssignmentAssignee, Attendance, Submission, SubmissionDeliverable, SubmissionAttachment, Review, Notification, EmailLog, DailyReport, AuditLog |
| Migrations | `backend/alembic/versions/0001–0003` | Additive only. Run automatically at container start (`docker-entrypoint.sh`). Verified on Postgres 16, no drift. |
| Authentication | `core/security.py`, `core/deps.py`, `services/auth_service.py` | bcrypt (12 rounds), HS256 JWT (8 h), `token_version` revocation, role re-read from DB on every request, generic login errors, timing-safe for unknown emails |
| RBAC | `core/deps.py` (`require_roles`), `services/scope.py` | admin / team_lead / artist; leads scoped to own teams, artists to own records |
| API | `/api/v1/*` (68 routes in 11 routers) + `/api/health` | Documented in `docs/API.md`. OpenAPI docs disabled in production. |
| Rate limiting | `core/rate_limit.py` (slowapi) | Login 10/min/IP, change-password 5/min, report generation and sending 10/min |
| File storage | `services/files.py` → `UPLOAD_DIR` (`/app/data/uploads` in Docker) | Local disk. Extension allow-list, signature check, size cap, path-traversal guard. **Ephemeral on Render free.** |
| Email | Gmail MCP server (`mcp_servers/gmail_mcp`), outbox pattern | Optional. Without Gmail OAuth, emails stay queued. In-app notifications still work. |
| AI | `services/report_ai.py` | Optional `ANTHROPIC_API_KEY`. Without it, a deterministic template is used. |
| Docker | `Dockerfile` (API, repo root), `frontend/Dockerfile` (nginx), `docker-compose.yml` | Non-root user, healthcheck, migrations and bootstrap in entrypoint |
| Deploy config (old) | `vercel.json`, `frontend/vercel.json`, `render.yaml`, `docs/DEPLOY_STEPS.txt` | Vercel proxies `/api/*` to a hardcoded Render URL |
| CI/CD | **none** | No `.github/` directory. Nothing stopped broken commits from deploying (`autoDeploy: true`). |
| Tests | `backend/tests/` (143), `frontend/src/**/*.test.tsx` (12) | All passing at baseline |
| Env templates | `.env.example` (root) | No frontend template |
| Git | `main`, clean, remote `github.com/srinivaspatnaik52-svg/StudioTrack-AI` | Last 5 commits by the teammate were all deployment changes (Vercel/Render/Neon) |

## 3. Recent teammate changes (deployment-related)

| Commit | Change | Assessment |
|---|---|---|
| `5beb429` | Removed demo data and mock email; added Vercel and Render config | Good hardening; introduced the proxy-hostname dependency |
| `58acb13` | Allowed deploying before Gmail is set up | Good |
| `4ce4ffc` | Render free plan + Neon | Compatible with the target architecture |
| `d23060d` | API Dockerfile moved to repo root | Good: Render finds it by default |
| `3db3238` | Bootstraps admin, lead and artist accounts from env | Useful for first login. Idempotent and never overwrites. |
| `bbb7937` | Added root `vercel.json` "so routing works with Root Directory empty or set to frontend" | A workaround for the SPA 404. The live site still 404s on `/login`, so the deployed project isn't using it. |

## 4. Findings and risks

| # | Severity | Finding | Resolution |
|---|---|---|---|
| F1 | **Critical** | The frontend proxies to `studiotrack-api.onrender.com`, which has no Render service (`no-server`), so login returns 404 | New deployment: the frontend calls the API at an explicit, configurable `VITE_API_BASE_URL`. The CI smoke test verifies the bundle points at the live API. |
| F2 | **Critical** | Deep links and refreshes 404 on the deployed Vercel site | Cloudflare Pages serves `index.html` for unknown paths by default (no `404.html` in the build). The smoke test checks nested routes. |
| F3 | High | No CI. `autoDeploy: true` deploys any commit, even one with failing tests. | GitHub Actions CI. Render `autoDeployTrigger: checksPass` deploys only after CI passes. |
| F4 | High | The login per-IP limit can be bypassed: uvicorn runs with `--forwarded-allow-ips=*` and uses the **leftmost** `X-Forwarded-For` value, which the client controls | Added a per-account failed-login throttle (10 failures / 15 min), independent of IP. Verified that a spoofed `X-Forwarded-For` doesn't bypass it. |
| F5 | High | `docker compose --profile app up` (the README's local full stack) **refused to start**: compose forced `ENVIRONMENT=production` with localhost URLs | Compose now defaults to development. `APP_ENVIRONMENT=production` still opts in to production mode. Verified with an isolated compose project. |
| F6 | Medium | Missing or localhost `CORS_ORIGINS` in production would start "fine" and then fail every browser call with CORS errors | The production config guard now refuses to start without a public CORS origin (and rejects `*`) |
| F7 | Medium | Uploaded attachments live on the container disk, which Render free wipes on every deploy or restart | Documented as a known free-tier limitation. `buildFilter` stops frontend- and docs-only commits from redeploying the API. A durable fix needs object storage (e.g. Cloudflare R2), which is a code change and out of scope. |
| F8 | Medium | Serverless Postgres (Neon) suspends idle compute and drops connections | `pool_pre_ping` was already present. Added `pool_recycle=300` and `connect_timeout=15`. |
| F9 | Low | `JWT` lives in `localStorage` (XSS-readable) with no refresh token; sessions last 8 h | Kept (changing auth is out of scope). Mitigated by a strict CSP (`script-src 'self'`), server-side revocation (`token_version`) and DB role checks. Documented. |
| F10 | Low | Two `vercel.json` files and `docs/DEPLOY_STEPS.txt` describe the old platform | Kept for reference and marked superseded. Can be deleted once the old Vercel project is retired, **with your approval**. |
| F11 | Info | Free Render sleeps after ~15 min idle (first request ~30–60 s); background jobs pause while asleep | Documented. The frontend's network-error message now says the server may be waking up. |

## 5. Reuse vs replace

| Keep as is | Modify | Replace / supersede |
|---|---|---|
| All application code, models, migrations, auth, RBAC, tests | `frontend/src/lib/api.ts` (configurable API origin) | `vercel.json`, `frontend/vercel.json` → `frontend/public/_headers` + Cloudflare Pages settings |
| `Dockerfile`, `docker-entrypoint.sh`, `frontend/Dockerfile`, `nginx.conf` | `render.yaml` (CI-gated deploys, build filter, Cloudflare wording) | `docs/DEPLOY_STEPS.txt` → `PRODUCTION_DEPLOYMENT_GUIDE.md` |
| Bootstrap accounts script | `config.py` / `main.py` (CORS regex option, CORS production check), `database.py` (Neon pool settings), `rate_limit.py` + `auth_service.py` (per-account throttle) | — |
| | `docker-compose.yml` (development default) | — |

## 6. Old deployment resources (not touched)

| Resource | Status | Action |
|---|---|---|
| Vercel project serving `studiosrackai.vercel.app` | Live, broken (404s) | **Left running.** Delete or disconnect it only once you approve, after the new deployment is verified. |
| Render service `studiotrack-api` | Does not exist (`no-server`) | Nothing to clean up. The name is free to reuse. |
| Neon database (if the teammate created one) | Unknown, not visible from the repo | **Do not delete.** The new deployment uses a new Neon project. Check your Neon dashboard for an old one and decide later. |
