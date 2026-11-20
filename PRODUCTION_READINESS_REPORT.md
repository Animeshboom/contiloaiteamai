# StudioTrack AI — Production Readiness Report

Date: 2026-11-20 · Scope: functional prototype on free tiers (Cloudflare Pages + Render + Neon)

## Verdict

**Ready to deploy as a prototype.** The code, configuration and pipeline were verified against a local replica of production (the same Docker image, production mode, Postgres 16). The live deployment hasn't been created yet, so this verdict becomes final once the "Deployed" column in `DEPLOYMENT_STATUS.md` is green.

Not ready for real studio production use on free tiers, because **uploaded attachments don't persist on Render free** and the API sleeps when idle (see "Limitations").

## Changes made for the deployment (minimal, application behaviour preserved)

| File | Change | Why |
|---|---|---|
| `frontend/src/lib/api.ts`, `vite-env.d.ts` | Optional `VITE_API_BASE_URL` prefix; clearer waking-up message | The frontend can call a separately hosted API. Empty = same-origin, so dev and Docker are unchanged. |
| `frontend/public/_headers` | Security headers + CSP for Cloudflare Pages (`connect-src` adds `*.onrender.com`) | Carries over the hardening from `vercel.json` and `nginx.conf` |
| `frontend/.node-version`, `frontend/.env.example` | Node 22 pin; documented public build variable | Reproducible builds; no secrets in `VITE_*` |
| `backend/app/core/rate_limit.py`, `services/auth_service.py` | Per-account failed-login throttle (10 / 15 min) | The per-IP limit can be bypassed with a forged `X-Forwarded-For` behind Render's proxy |
| `backend/app/core/config.py`, `main.py` | `CORS_ORIGIN_REGEX` (opt-in); production refuses missing, localhost or `*` CORS origins | Preview support; fail fast instead of silent CORS breakage |
| `backend/app/core/database.py` | `pool_recycle=300`, `connect_timeout=15` | Neon scales to zero and drops idle connections |
| `docker-compose.yml` | Defaults to development | The local full stack previously refused to start |
| `render.yaml` | CI-gated deploys, build filter, branch pin, Cloudflare wording | No broken deploys; fewer upload-wiping redeploys |
| `.github/workflows/*` | CI, dependency audit, production smoke test | Automated pipeline |
| `scripts/e2e_workflow.py` | Role-workflow test with dummy data | Repeatable verification of the deployed app |
| Tests | +3 backend (throttle ×2, CORS regex), 1 updated (CORS production check), +2 frontend (API base URL); vitest `testTimeout` 5 s → 20 s | Cover the changes. Two existing UI tests take ~4 s and timed out under CPU load; the Pages build runs the tests, so a flake would block deploys. |

No models, migrations, endpoints, business logic or UI were changed.

## Security review

| Control | Status |
|---|---|
| Secret management | Secrets only in the Render dashboard (`sync: false` or generated). `.env`, `.e2e.env`, `secrets/` git-ignored. Templates hold placeholders only. The frontend bundle contains only the public API URL. |
| Password hashing | bcrypt, 12 rounds; dummy-hash timing equalisation for unknown emails |
| JWT | HS256, 8 h expiry, required `sub`/`exp`, `token_version` revocation on password or role change and deactivation; role always re-read from DB |
| RBAC | Server-side on every endpoint (`require_roles` + scope service); the UI guard is UX only. Verified by the e2e script (6 negative checks). |
| CORS | Exact origin allow-list; methods and headers restricted; production refuses `*` or localhost |
| Input validation | Pydantic schemas with length and pattern limits; uniform 422 without internals; uploads: allow-list, magic bytes, size cap, path-traversal guard |
| Rate limiting | Login 10/min/IP + 10 failures / 15 min per account; change-password 5/min; report generate and send 10/min |
| Debug | `debug=False`; OpenAPI and `/docs` disabled in production; unhandled errors return a generic 500 (stack trace only in server logs) |
| Logs | No passwords or tokens logged; integrity errors log only the exception class; the entrypoint unsets Gmail JSON env vars after writing them to files with mode 600 |
| Transport | HTTPS everywhere (Pages, Render); Neon `sslmode=require`; HSTS header |
| Container | Non-root user (uid 10001); only `/app/data` writable |
| Supply chain | `pip-audit` and `npm audit`: 0 known vulnerabilities (2026-11-20); weekly re-audit workflow |

### Residual risks (accepted for a prototype)
1. **JWT in `localStorage`.** Readable by an XSS. Mitigated by a strict CSP (`script-src 'self'`) and React's escaping. A full fix (httpOnly cookie + CSRF) changes the auth design and was out of scope.
2. **In-memory rate limits** reset on restart (and on every free-tier sleep). That's acceptable for a single instance.
3. **Bootstrap passwords in Render env** until removed. The guide's step 6d says to delete them after first sign-in.
4. **Preview deployments** can reach production data only if `CORS_ORIGIN_REGEX` is set. It's off by default.

## Limitations of the free tiers

| Area | Limitation | Workaround / upgrade |
|---|---|---|
| Uploads | Render free disk is ephemeral, so attachments are lost on deploy or restart | Render Starter + disk at `/app/data`, or object storage (code change) |
| Availability | API sleeps after ~15 min, with ~30–60 s cold start | Paid instance; an uptime pinger would also keep it awake but uses the 750 h/month quota |
| Background jobs | Deadline reminders and email dispatch pause while asleep, and resume on wake | Paid instance |
| Database | Neon free: 0.5 GB, limited compute hours, ~5-min scale-to-zero | Neon Launch plan |
| Email | Needs Gmail OAuth (`docs/GMAIL_SETUP.md`); until then emails queue | Configure `GMAIL_*_JSON` |
| AI reports | Template narrative without `ANTHROPIC_API_KEY` | Add the key (paid API usage) |

## Go-live checklist
- [ ] CI green on GitHub for the merged commit
- [ ] Render Auto-Deploy = "After CI checks pass"
- [ ] `/api/health` OK on Neon
- [ ] Smoke-test workflow green
- [ ] `scripts/e2e_workflow.py` 41/41 against production
- [ ] Browser login for each role; nested-route refresh; no console errors
- [ ] Admin password changed; `*_PASSWORD` variables removed from Render
- [ ] `DEPLOYMENT_STATUS.md` "Deployed" column filled in
- [ ] Decision on the old Vercel project (retire only with owner approval)
