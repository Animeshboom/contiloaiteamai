# StudioTrack AI — Troubleshooting

Start with the **Production smoke test** workflow (Actions tab). Its failing step names the problem.

## Login / API

| Symptom | Cause | Fix |
|---|---|---|
| Login: "Cannot reach the StudioTrack server… may be waking up" | Render free instance is asleep (first request ~30–60 s), or the URL is wrong | Wait a minute and retry. Open `<API_URL>/api/health` directly. If that's 404 with `x-render-routing: no-server`, the URL is wrong; see next row. |
| Every API call 404s; `x-render-routing: no-server` | `VITE_API_BASE_URL` points at a Render hostname with no service (this was the original outage) | Copy the exact URL from the Render service page into Cloudflare Pages → Settings → Environment variables → `VITE_API_BASE_URL`, then **Deployments → Retry deployment**. Vite bakes it in at build time, so a rebuild is required. |
| API calls go to `<WEB_URL>/api/...` and 404/405 | `VITE_API_BASE_URL` was empty at build time | Set it for **Production and Preview** and redeploy |
| Console: `blocked by CORS policy: No 'Access-Control-Allow-Origin'` | `CORS_ORIGINS` on Render doesn't contain the exact page origin: scheme (`https`), host and port must match. Trailing slashes are stripped automatically, but `www.` vs no `www.`, `http` vs `https`, or a preview hostname all count as different origins. | Render → Environment → `CORS_ORIGINS=["https://studiotrack-ai.pages.dev"]` → Save and deploy. Preview URL? See `CORS_ORIGIN_REGEX` in `DEPLOYMENT_PLAN.md`. |
| Console: `Refused to connect … violates Content-Security-Policy connect-src` | The API isn't on `*.onrender.com` (e.g. a custom domain) | Add the API origin to `connect-src` in `frontend/public/_headers` and push |
| "Invalid email or password" for the bootstrap admin | Account created earlier with a different password (bootstrap never overwrites), or a typo | Check Render logs for `Bootstrap: … created` vs `already exists`. Reset through another admin (Employees → Reset password). |
| HTTP 429 "Too many failed sign-in attempts for this account" | 10 failed logins for that email within 15 min | Wait 15 min, or restart the Render service (the counter is in memory) |
| HTTP 429 "Too many requests" | 10 login requests/min from one IP | Wait a minute |
| Signed out unexpectedly | Token expired (8 h), password changed, role changed, or account deactivated | Sign in again (by design) |

## Render deploy

| Symptom | Fix |
|---|---|
| Logs: `Refusing to start in production:` + list | Fix each listed variable: secrets must be long and random, `DATABASE_URL` not localhost, `APP_BASE_URL` and `CORS_ORIGINS` the public Pages URL |
| Logs: `error parsing value for field "cors_origins" from source "EnvSettingsSource"` (the API exits before the "Refusing to start" check) | `CORS_ORIGINS` isn't a JSON array: brackets or double quotes are missing, e.g. `https://studiotrack-ai.pages.dev` or `['https://…']` | Use exactly `["https://studiotrack-ai.pages.dev"]`: square brackets, **double** quotes, comma-separated for more than one (`["https://a.pages.dev","https://studio.example.com"]`). No `*`. |
| Logs: `connection … failed` / `password authentication failed` | Re-copy the Neon string (role `neondb_owner`, `?sslmode=require`). A reset Neon password invalidates the old string. |
| Logs: `SSL connection is required` | Append `?sslmode=require` to `DATABASE_URL` |
| Health check failing, logs fine | `/api/health` queries the DB, so check Neon (project suspended, quota exceeded) in the Neon console |
| New commit didn't deploy | Auto-deploy waits for **CI checks to pass**: check the Actions tab. Commits touching only `frontend/`, docs or tests are skipped by the build filter (expected). |
| `ADMIN_PASSWORD must be at least 12 characters` | Use a longer password |
| Attachments disappeared | Free-plan disk is wiped on deploy or restart (known limitation) |

## Cloudflare Pages build

| Symptom | Fix |
|---|---|
| `Vite requires Node.js version 20.19+ or 22.12+` | Add `NODE_VERSION=22` env var (Production and Preview), retry |
| Build fails at `npm test` | A frontend test is failing. Run `cd frontend && npm test` locally. The previous deployment stays live. |
| `Could not read package.json` | Root directory must be `frontend` |
| Refresh on `/admin/...` gives 404 | A `404.html` was added to `frontend/public` (it disables SPA mode). Remove it. |

## CI (GitHub Actions)

| Failing step | Meaning |
|---|---|
| `Models and migrations are in sync` | You changed a model without a migration: `alembic revision --autogenerate -m "..."`, review, commit |
| `Migrations apply on an empty Postgres` | A migration is broken on Postgres. Fix before merging (Render would fail the same way). |
| `Image starts in production mode…` | The API image fails to import or start. Run `docker build .` locally. |
| Dependency audit | A dependency has a published advisory. Bump it in `requirements.txt` or `package.json`. |

## Local development

| Symptom | Fix |
|---|---|
| `docker compose --profile app up` exits with "Refusing to start in production" | You set `APP_ENVIRONMENT=production` with localhost URLs. Unset it (the default is development). |
| `EPERM` during `npm install` / `pip install` | OneDrive is syncing the folder. Pause syncing. |
| Frontend can't reach API in `npm run dev` | Start the API on :8000, or set `VITE_API_PROXY`. Leave `VITE_API_BASE_URL` **empty** locally. |

## Useful commands

```bash
curl -i <API_URL>/api/health                                         # API + DB
curl -i -X OPTIONS <API_URL>/api/v1/auth/login -H "Origin: <WEB_URL>" -H "Access-Control-Request-Method: POST"   # CORS
curl -s -o /dev/null -w "%{http_code}\n" <WEB_URL>/admin/projects     # SPA fallback (expect 200)
py -3.11 scripts/e2e_workflow.py                                      # full workflow (reads .e2e.env)
```
