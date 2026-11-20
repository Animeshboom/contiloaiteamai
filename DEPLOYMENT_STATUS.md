# StudioTrack AI — Deployment Status

Last updated: 2026-11-20

## Resources

| Component | Provider | URL / identifier | Status |
|---|---|---|---|
| Source | GitHub | `srinivaspatnaik52-svg/StudioTrack-AI`, branch `deploy/cloudflare-render-neon` → `main` | Branch prepared locally, **not yet pushed** (awaiting approval) |
| CI | GitHub Actions | `ci.yml`, `dependency-audit.yml`, `smoke.yml` | Written; steps verified locally. First GitHub run pending push. |
| Database | Neon | project `studiotrack` | **Not created yet** (needs your account) |
| API | Render | `studiotrack-api`: `<API_URL>` | **Not created yet** (needs your account) |
| Frontend | Cloudflare Pages | `studiotrack-ai`: `<WEB_URL>` | **Not created yet** (needs your account) |
| Old frontend | Vercel | `studiosrackai.vercel.app` | Live but broken. **Left untouched.** |
| Old API | Render | `studiotrack-api.onrender.com` | Does not exist (`no-server`) |

## Deployment steps

| # | Step | Status |
|---|---|---|
| 1 | GitHub repo/branch verification | Done locally (clean tree, branch created). Push pending approval. |
| 2 | Neon database creation | Pending (you) |
| 3 | Database connection configuration | Pending |
| 4 | Migrations | Verified on local Postgres 16. Neon pending (runs at first Render start). |
| 5 | Backend deployment to Render | Pending (you) |
| 6 | Backend health verification | Pending |
| 7 | Authentication endpoint verification | Pending |
| 8 | Cloudflare Pages deployment | Pending (you) |
| 9 | Frontend-backend integration | Pending |
| 10 | Login testing | Pending |
| 11 | Role-based workflow testing | Pending |
| 12 | Production verification | Pending |

## Verification checklist

Legend: ✅ executed and passed · ❌ executed and failed · ⏳ not yet executed. **Nothing is marked passed unless it was actually run.**

The **Local replica** column = the exact Render Docker image, run in `ENVIRONMENT=production` on `PORT=10000` against a throwaway Postgres 16 container with dummy accounts (2026-11-20). The **Deployed** column is filled in after the real deployment.

### Build and pipeline
| Check | Local replica | Deployed |
|---|---|---|
| Backend tests, SQLite (146) | ✅ 146 passed | ⏳ (CI) |
| Backend tests, Postgres 16 (146) | ✅ 146 passed | ⏳ (CI) |
| Migrations on empty Postgres | ✅ 0001→0003 applied | ⏳ Neon |
| `alembic check` (no model/migration drift) | ✅ no drift | ⏳ (CI) |
| Frontend tests (14) | ✅ 14 passed | ⏳ (CI + Pages build) |
| Frontend lint | ✅ 0 errors (7 pre-existing warnings) | ⏳ (CI) |
| Frontend production build | ✅ with and without `VITE_API_BASE_URL` | ⏳ Pages |
| API Docker image builds | ✅ | ⏳ Render |
| Image refuses unsafe production config | ✅ (incl. missing `CORS_ORIGINS`) | — |
| Dependency audit (pip-audit, npm audit) | ✅ 0 known vulnerabilities | ⏳ (CI) |
| Local Docker full stack (compose, dev mode) | ✅ health 200; `/`, `/login`, `/admin/projects/3` → 200 via nginx | — |

### Deployment
| Check | Local replica | Deployed |
|---|---|---|
| Frontend loads | ✅ (nginx stack) | ⏳ |
| API responds (`/api/health`) | ✅ `{"status":"ok","environment":"production"}` | ⏳ |
| Database works (health runs `SELECT 1`; workflow writes and reads) | ✅ | ⏳ |
| Refresh on nested routes works | ✅ (nginx) | ⏳ (Pages SPA fallback) |
| No 404 login errors | ✅ | ⏳ |
| CORS: web origin allowed, foreign origin rejected | ✅ | ⏳ |
| No broken API URLs (bundle points at API) | ✅ build inspected | ⏳ (smoke test) |
| API docs hidden in production (`/docs` 404) | ✅ | ⏳ |

### Authentication
| Check | Local replica | Deployed |
|---|---|---|
| Login (admin, lead, artist) | ✅ | ⏳ |
| Logout (client-side: token removed from storage; no server endpoint) | ⏳ not covered by an automated test | ⏳ browser |
| Bad credentials store no token (frontend) | ✅ frontend test | ⏳ |
| Invalid credentials → 401, generic message | ✅ | ⏳ |
| Malformed login → 422 | ✅ | ⏳ |
| Token expiry → 401 | ✅ backend unit test (expired JWT) | n/a (8 h) |
| Tampered token → 401 | ✅ | ⏳ |
| Protected endpoint without token → 401 | ✅ | ⏳ |
| Deactivated user: existing token and login rejected | ✅ | ⏳ |
| Per-account brute-force throttle (spoofed `X-Forwarded-For` doesn't bypass) | ✅ 429 after 3 (test limit) | ⏳ |
| Role permissions: lead can't create employees; artist can't list users, roster or review; lead can't read email logs | ✅ | ⏳ |

### Admin / Team lead / Artist workflow (`scripts/e2e_workflow.py`)
| Check | Local replica | Deployed |
|---|---|---|
| Admin creates employees (lead, artist) | ✅ | ⏳ |
| Admin creates team, project, episode with scenes | ✅ | ⏳ |
| Artist login and check-in (double check-in → 409) | ✅ | ⏳ |
| Lead attendance overview shows the artist checked in | ✅ | ⏳ |
| Lead assigns tasks | ✅ | ⏳ |
| Artist views assignments, submits completed work | ✅ | ⏳ |
| Lead review queue, partial approve and reject with revision feedback | ✅ | ⏳ |
| Partial approval without feedback refused (422); double review refused (409) | ✅ | ⏳ |
| Artist views review feedback and notifications | ✅ | ⏳ |
| Artist resubmits; lead approves; assignment completed | ✅ | ⏳ |
| **Total** | ✅ **41/41**, run twice | ⏳ |

## Log

| Date | Event |
|---|---|
| 2026-11-20 | Audit: old API hostname has no Render service; old Vercel site 404s on `/login` (`DEPLOYMENT_AUDIT.md`) |
| 2026-11-20 | Deployment changes prepared on branch `deploy/cloudflare-render-neon`; all local verification above executed |
