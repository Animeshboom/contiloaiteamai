# StudioTrack AI — Phased Development Checklist

## Key design decisions

- **Per-artist tracking:** `assignments` holds the task. `assignment_scenes` lists the scenes it covers, and `assignment_assignees` gives each artist their own status and self-reported progress. A multi-artist assignment therefore tracks each contribution separately.
- **Three separate progress signals:**
  1. Artist-reported progress is stored in `assignment_assignees.reported_progress_pct` and `submissions.scenes_completed_count`.
  2. Submitted deliverables are `submission_deliverables` rows with `status=submitted`.
  3. Lead-approved deliverables are `submission_deliverables` rows with `status=approved`, plus `approved_by` and `approved_at`.
  Approved-scene counts come only from (3).
- **Immutable history:** a resubmission creates a new `submissions` row (`revision_number + 1`, `previous_submission_id`). `reviews` is append-only.
- **Partial submissions:** a submission names the subset of assigned scenes it delivers. Scenes it leaves out are unaffected.
- **Idempotency:** `notifications.dedupe_key` and `email_logs.idempotency_key` are unique, so a retried event or send cannot duplicate.
- **AI boundary:** EOD metrics come from deterministic SQL and are stored as a `daily_reports.metrics` snapshot. Claude writes narrative only, from that snapshot. Sending requires an explicit lead approval, and recipients are validated against `authorized_recipients`.
- **Gmail MCP:** this is a standalone Python MCP server, run inside the app's own deployment. The backend talks to it as an MCP client over stdio. A mock provider is used when there are no Google credentials.
- **Time:** all timestamps are stored in UTC. The work date and the EOD deadline are computed in `STUDIO_TIMEZONE`.

## Phase 1 — Foundation ✅
- [x] Project structure, config via env, docker-compose Postgres
- [x] SQLAlchemy models for all 19 tables (PKs, FKs, indexes, unique constraints, timestamps, soft delete)
- [x] Alembic initial migration (upgrade/downgrade round-trip verified, `alembic check` clean)
- [x] JWT auth, bcrypt, token revocation, login rate limiting, audit log
- [x] RBAC dependencies (DB-sourced roles)
- [x] Idempotent demo seed
- [x] 24 pytest tests passing on SQLite and Postgres

## Phase 2 — Core workforce management ✅
- [x] Frontend: Vite + TS + Tailwind v4 + shadcn/ui (Radix), dark charcoal/amber theme, login, role-specific layouts and navigation (only implemented pages are linked)
- [x] Employees (admin CRUD, deactivate/reactivate, role/team changes, password reset), Teams, authorized recipients
- [x] Attendance: check-in/out, duplicate/invalid prevention, auto Half Day, history, lead roster, 14-day chart, audited corrections
- [x] Projects → Episodes → Scenes CRUD (bulk scene generation, soft delete, team ownership)
- [x] Assignments: multi-scene, whole-episode, non-scene deliverables, multi-artist with per-artist tracking, EOD default deadline
- [x] Dashboards computed from DB (no hardcoded stats)
- [x] 74 backend tests (SQLite + Postgres), 9 frontend tests, scripted API walkthrough, headless-browser UI walkthrough

## Phase 3 — Artist workflow ✅
- [x] Artist progress updates (self-reported, kept separate from submitted/approved state)
- [x] Submissions: partial (any subset of open scenes), multiple non-overlapping pending, deliverable-only, links (http/https only), secure attachments (allow-list, streaming size cap, magic-byte check, random names, scoped download)
- [x] Immutable revision history: a resubmission is a new row linked to the rejected submission; append-only reviews
- [x] Review queue: approve all or selected scenes; feedback required for any rejection; double review blocked (row lock)
- [x] Derived per-scene and per-artist status; lead "Mark completed"
- [x] UI: Submit Work, My Reviews, Work History (artist); Submissions, Reviews with pending badge (lead); scene-state grid in assignment detail
- [x] 93 backend tests (SQLite + Postgres), 11 frontend tests, full browser walkthrough (submit → partial approve → revise → approve → complete)

## Phase 4 — Notifications & Gmail MCP ✅
- [x] In-app notifications for all events (unique dedupe keys); bell with unread count, Notifications page
- [x] Transactional email outbox (`email_logs`, migration 0002): idempotency keys, leased claims (no double send under concurrency), exponential backoff, max attempts, final policy blocks
- [x] Background loop: dispatcher every 30s and deadline reminders every 5 min (idempotent per deadline)
- [x] Gmail MCP server (Python MCP SDK, stdio or streamable HTTP) with the 4 tools, typed structured results, and DB-backed recipient policy
- [x] Report sends require an HMAC approval token and use DB-stored content; drafts can only go to authorized recipients
- [x] OAuth 2.0 with a single scope (`gmail.compose`), token refresh and save, classified Gmail errors, header-injection safe, masked logging
- [x] Mock delivery (.eml outbox) when Gmail isn't configured; admin email delivery log with retry
- [x] 124 backend tests (SQLite + Postgres), including protocol-level MCP tests and a real spawned-subprocess test; browser walkthrough through the real MCP path

## Phase 5 — AI reporting
- [ ] Deterministic EOD metrics service (filters: project/episode/artist)
- [ ] Claude narrative + email composition (template fallback without an API key)
- [ ] Preview/edit → approve → send; report history

## Phase 6 — Finalization
- [ ] UI polish, frontend tests, security review, Dockerfiles for api/frontend/mcp, full README + API docs
