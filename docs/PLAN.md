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

## Phase 3 — Artist workflow
- [ ] Artist dashboard, progress updates
- [ ] Submissions (partial, links, validated file uploads), revision history
- [ ] Review dashboard: approve (per scene) / reject with required feedback; resubmission cycle

## Phase 4 — Notifications & Gmail MCP
- [ ] In-app notifications (deduplicated), deadline-approaching job
- [ ] Notification service → email provider interface (mock + Gmail MCP)
- [ ] Gmail MCP server: 4 tools, OAuth 2.0, minimal scopes (`gmail.send`, `gmail.compose`), recipient allow-list, logging

## Phase 5 — AI reporting
- [ ] Deterministic EOD metrics service (filters: project/episode/artist)
- [ ] Claude narrative + email composition (template fallback without an API key)
- [ ] Preview/edit → approve → send; report history

## Phase 6 — Finalization
- [ ] UI polish, frontend tests, security review, Dockerfiles for api/frontend/mcp, full README + API docs
