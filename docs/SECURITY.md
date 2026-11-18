# Security review

This review covered the full prototype (backend, Gmail MCP server, frontend and Docker deployment). Every finding was verified, either by a test or against the running Docker stack.

## Findings fixed during the review (Phase 6)

| # | Finding | Severity | Fix | Verified by |
|---|---|---|---|---|
| 1 | **Rate-limit bypass with a forged `X-Forwarded-For`.** nginx appended to the client-supplied header and uvicorn trusted the chain. 12 failed logins with forged IPs got no 429. | High | nginx now **overwrites** `X-Forwarded-For` with `$remote_addr`; uvicorn trusts forwarded headers only behind it | The same test after the fix returns `401 ×10, 429, 429` |
| 2 | **Vulnerable dependencies:** starlette (7 advisories), pyjwt (17), python-multipart (6), mcp (7), setuptools (5), react-router (open redirect, constructor injection) | High | FastAPI 0.163 with Starlette 1.10, PyJWT 2.15.1, python-multipart 0.0.34, mcp 1.30.0, setuptools 84.2 (also in the image), React Router 7.18.5 | `pip-audit` on the venv **and inside the built image**: *No known vulnerabilities*. `npm audit --omit=dev`: *0 vulnerabilities*. 139 + 12 tests and the 17-step DoD pass on the upgraded stack |
| 3 | **Production could start with placeholder secrets**, the dev database URL, or the mock email provider | High | The API refuses to start in production and lists every problem (`Settings.production_problems`) | `test_production_refuses_placeholder_secrets`, plus a manual start with the dev `.env` |
| 4 | **Demo accounts with published passwords** were seeded by default in Docker | High | `SEED_DEMO_DATA` defaults to `false`; `scripts.create_admin` creates the first real admin; the API logs a `SECURITY` warning if active demo accounts exist in production | `test_create_admin_script`, plus the warning observed in container logs |
| 5 | Report approval token re-signed at send time, so post-approval recipient tampering was accepted *(found in Phase 5)* | High | Token issued and stored at approval; the MCP server verifies it | `test_tampered_approval_is_refused_by_mcp_server` |
| 6 | MCP errors arrive wrapped by the protocol, so policy blocks were misclassified as retryable *(found in Phase 4)* | Medium | Marker parsed anywhere in the message | Protocol-level MCP tests |
| 7 | Interactive API docs exposed in production | Low | `/docs`, `/redoc` and `/openapi.json` disabled when `ENVIRONMENT=production` | `curl /api/docs` → 404 on the stack |
| 8 | Missing browser security headers | Low | nginx: strict CSP (`script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `server_tokens off` | Headers checked with `curl -I`; the full DoD runs under the CSP with no console errors |
| 9 | Container ran as root | Low | Backend image runs as uid 10001; only `/app/data` is writable | `docker compose exec api id` |

## Controls in place (by area)

**Authentication and sessions**
- bcrypt (cost 12) password hashing.
- Generic login errors, with a dummy hash check against user enumeration by timing.
- Login limited to 10 per minute per IP; password change to 5 per minute.
- JWT (HS256, algorithm pinned) carries `token_version`, which is bumped on password change, role change and deactivation, so revocation is immediate.

**Authorization**
- Roles are always read from the database; the token's role claim is ignored. A test forges an admin claim to prove it.
- Every service call is scoped: leads see their own teams, artists see their own records.
- Out-of-scope IDs return 404 rather than 403, so IDs can't be probed.
- The frontend's role checks are UX only.

**Data integrity**
- Submissions and reviews are immutable or append-only.
- Every state change writes an audit row (secrets are stripped).
- Review uses a row lock (`SELECT … FOR UPDATE`) against double review.
- Transactions commit atomically with their notifications and outbox entries.

**Uploads**
- Extension allow-list, and a size cap enforced while streaming.
- Magic-byte check; executables are rejected even when renamed.
- Random storage names outside any static path; path-traversal guard.
- Downloads are authenticated and scoped, served as `application/octet-stream` with `nosniff`.

**Email (Gmail MCP)**
- The server re-checks policy itself against the database: active artists only, and authorized report recipients only.
- Report sends need an HMAC approval token and use content loaded from the database, not from the caller.
- Idempotency keys prevent duplicates.
- Header-injection safe; addresses masked in logs; only the `gmail.compose` scope.

**AI**
- Claude receives only deterministic metrics, never free-text descriptions or comments (tested with an injected instruction).
- Structured output, plus a number guard that discards any narrative containing figures not in the records.
- The AI cannot send email: sending needs an explicit lead approval.

**Secrets**
- Environment variables only; `.env` and `secrets/` are gitignored.
- The MCP subprocess receives only the variables it needs.
- No stack traces in API responses.

## Known limitations and recommendations

| Area | Status | Recommendation |
|---|---|---|
| JWT in `localStorage` | XSS would expose the token. Mitigated by the strict CSP (no inline or third-party scripts) and React's escaping | Move to `httpOnly`, `SameSite=Strict` cookies with CSRF protection |
| Rate-limit storage | In memory, per process | Use Redis-backed `slowapi` storage when running more than one API replica |
| Account protection | IP rate limits only | Add per-account lockout or backoff, and MFA for admins and leads |
| TLS | The compose stack serves HTTP on the published port | Terminate TLS in front of nginx (load balancer, Caddy or Traefik) and add HSTS there. If that proxy is a separate hop, switch nginx to the `realip` module so it trusts only that proxy's address |
| Database credentials | One DB user for the API and the MCP server | Give the MCP server a **read-only** role (it only runs `SELECT`s); set a strong `POSTGRES_PASSWORD` |
| Uploaded files | Validated by type, size and signature, but not malware-scanned | Add AV scanning (e.g. ClamAV) or use object storage with scanning |
| Google Fonts | The CSP allows `fonts.googleapis.com` / `fonts.gstatic.com` | Self-host the two fonts to remove the third-party dependency |
| Dev tooling advisories | 13 advisories in **dev-only** packages (Vite/Vitest transitive deps such as `picomatch`, `tinypool`, typescript-eslint). None ship: the production image serves static files only. Some have no fixed release (`picomatch`: every version) | Upgrade Vite and Vitest to their next majors in a dedicated change and re-run `npm audit`. Until then, run the dev server only on localhost (the default) |
| Audit log | Append-only by convention, not tamper-evident | Ship audit rows to an external log store if needed for compliance |

## How to re-run the checks

```bash
# Python dependencies (backend venv)
pip install pip-audit && pip-audit --path backend/.venv/Lib/site-packages
# Inside the built image
docker run --rm --user root --entrypoint sh studiotrack-ai-api -c "pip install -q pip-audit && pip-audit -l"
# Frontend production dependencies
cd frontend && npm audit --omit=dev
# Rate limit cannot be bypassed with forged headers (expect 429s after 10 attempts)
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code} " -X POST localhost:8090/api/v1/auth/login \
  -H "Content-Type: application/json" -H "X-Forwarded-For: 10.0.$i.1" -d '{"email":"x@x.io","password":"x"}'; done
```
