# StudioTrack AI — API Reference

Base path: `/api/v1`. All endpoints except login require `Authorization: Bearer <token>`.
Interactive OpenAPI docs: http://localhost:8000/docs

**Errors** are always `{"error": "<code>", "detail": "<message>"}` (422 also includes `errors: [{field, message}]`).
`401` = not signed in / revoked · `403` = role not allowed · `404` = not found *or outside your scope* · `409` = conflict (duplicate, invalid state).

**Scope:** admins see everything; team leads see members of teams they lead; artists see only their own records. Roles are always read from the database.

## Auth
| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/auth/login` | public | Rate-limited 10/min/IP |
| GET | `/auth/me` | any | |
| POST | `/auth/change-password` | any | Returns a fresh token; revokes others |

## Employees, teams, recipients
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/users?role=&team_id=&include_inactive=&search=` | admin, lead | Leads: own team only |
| GET | `/users/{id}` | admin, lead | |
| POST | `/users` | admin | `{email, full_name, role, team_id?, job_title?, password}` |
| PATCH | `/users/{id}` | admin | Role change revokes the user's sessions; `clear_team: true` removes team |
| POST | `/users/{id}/deactivate` · `/activate` | admin | Cannot deactivate yourself |
| POST | `/users/{id}/reset-password` | admin | |
| GET | `/teams` | admin, lead | Leads: teams they lead |
| POST · PATCH · DELETE | `/teams[/{id}]` | admin | Lead must have Team Lead role; delete requires no active members |
| GET | `/recipients?active_only=` | admin, lead | Authorized EOD report recipients |
| POST · PATCH | `/recipients[/{id}]` | admin | |

## Projects, episodes, scenes
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/projects?status=` | any | Artists: only projects they're assigned to |
| POST | `/projects` | admin, lead | Lead projects default to the lead's team |
| GET | `/projects/{id}` | any (scoped) | Includes episodes and scenes; `can_manage` flag |
| PATCH · DELETE | `/projects/{id}` | admin, owning lead | Soft delete |
| POST | `/projects/{id}/episodes` | admin, owning lead | `scene_count` auto-creates SC01..SCnn |
| PATCH · DELETE | `/episodes/{id}` | admin, owning lead | |
| POST | `/episodes/{id}/scenes` | admin, owning lead | |
| POST | `/episodes/{id}/scenes/bulk` | admin, owning lead | `{count}` appends after the highest number |
| PATCH · DELETE | `/scenes/{id}` | admin, owning lead | |

## Attendance
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/attendance/today` | any | `{record, can_check_in, can_check_out}` |
| POST | `/attendance/check-in` | any | 409 if already checked in or day marked Leave/Absent |
| POST | `/attendance/check-out` | any | 409 without check-in or if already out; < 4.5h ⇒ Half Day |
| GET | `/attendance/me?start=&end=` | any | Default last 30 days |
| GET | `/attendance/users/{id}?start=&end=` | admin, lead | |
| GET | `/attendance/roster?on=&team_id=` | admin, lead | Derived `not_checked_in` (today) / `absent` (past) |
| GET | `/attendance/summary?start=&end=` | admin, lead | Daily counts per status |
| PUT | `/attendance/correct` | admin, lead | `{user_id, work_date, status, check_in_at?, check_out_at?, reason}`; audited |

## Assignments
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/assignments?status=&project_id=&artist_id=&on_date=&overdue=&priority=` | any (scoped) | |
| POST | `/assignments` | admin, lead | `{project_id, episode_id?, scene_ids[], artist_ids[], description?, expected_deliverables?, deadline?, priority}`; deadline defaults to studio EOD |
| GET | `/assignments/{id}` | any (scoped) | Per-artist status, reported %, scenes submitted/approved |
| PATCH | `/assignments/{id}` | admin, lead | Deadline, priority, text, `add_artist_ids`, `remove_artist_ids` |
| DELETE | `/assignments/{id}` | admin, lead | Soft delete |

## Progress, submissions & reviews
| Method | Path | Roles | Notes |
|---|---|---|---|
| PUT | `/assignments/{id}/progress` | artist (assignee) | `{reported_progress_pct 0-100, progress_note?}`. Self-reported only; never marks work complete |
| POST | `/assignments/{id}/complete` | admin, lead | Only when every artist's work is approved (409 otherwise) |
| GET | `/submissions?status=&assignment_id=&artist_id=&project_id=` | any (scoped) | Pending queue (`status=pending_review`) is oldest-first |
| POST | `/submissions` | artist | `{assignment_id, scene_ids[], work_description, output_links[], comments?, scenes_completed_count?}`. Any subset of open scenes (partial). 409 if a scene is already pending or approved |
| GET | `/submissions/{id}` | any (scoped) | Deliverables with per-scene state, attachments, full review history, `previous_submission_id` |
| POST | `/submissions/{id}/attachments` | artist (owner) | multipart `file`. Extension allow-list, size cap, content signature check. Only before review; max 10 |
| GET | `/submissions/{id}/attachments/{att_id}` | any (scoped) | Download (`application/octet-stream`, `nosniff`) |
| POST | `/submissions/{id}/review` | admin, lead (artist's team) | `{decision: approved\|rejected, feedback?, approved_scene_ids?}`. Rejecting, or approving only some scenes, requires feedback. 409 if already reviewed |

**Derived state.** Each scene's state for an artist comes from the latest submission that included it: `submitted` (pending), `approved` or `rejected`. Assignee status is derived from these states. *Approved* means every assigned scene is approved. Artist-reported progress never affects it.

## Notifications & email
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/notifications?unread_only=&limit=` | any | The caller's own notifications, newest first |
| GET | `/notifications/unread-count` | any | `{unread}` |
| POST | `/notifications/{id}/read` | any (own only) | 404 for other users' notifications |
| POST | `/notifications/read-all` | any | `{updated}` |
| GET | `/email-logs?status=` | admin | Delivery attempts via the Gmail MCP integration (no message bodies) |
| POST | `/email-logs/{id}/retry` | admin | Re-queues a **failed** email and delivers it now. Blocked emails stay blocked |

Events that notify: a new assignment (artist; in-app and email), a submission received (team leads; in-app), an approval (artist; in-app and email), a revision request (artist; in-app and email with feedback), and a deadline within `DEADLINE_REMINDER_HOURS` (artist; in-app and email). Every event has a unique dedupe or idempotency key, so retried requests or jobs never duplicate. See [GMAIL_SETUP.md](GMAIL_SETUP.md).

## End-of-day reports
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/reports/metrics?report_date=&project_id=&episode_id=&artist_id=&team_id=` | admin, lead | Live deterministic metrics (nothing saved, no AI) |
| POST | `/reports` | admin, lead (10/min) | `{report_date?, project_id?, episode_id?, artist_id?, team_id? (admin), use_ai}`. Snapshots metrics and drafts the narrative. Returns a **draft** |
| GET | `/reports` · `/reports/{id}` | admin, lead (own team) | History, and full report with metrics snapshot, narrative and body |
| PATCH | `/reports/{id}` | admin, lead | Edit subject, body or recipients. **Draft only** |
| POST | `/reports/{id}/approve` | admin, lead | `{recipients}` must be active authorized recipients. Issues an HMAC approval token over (report, approver, time, exact recipients) |
| POST | `/reports/{id}/revoke` | admin, lead | Approved or failed → draft (invalidates the token) |
| POST | `/reports/{id}/send` | admin, lead (10/min) | Sends an **approved** report via MCP `send_daily_report`. One delivery per approval; 409 if already sent |
| POST | `/reports/{id}/gmail-draft` | admin, lead | Optional: puts the current text in Gmail drafts via `create_daily_report_draft`. Never sends |

**AI boundary.** Every figure comes from `report_metrics.compute` (SQL plus arithmetic) and is stored on the report as `metrics`. Claude (`claude-opus-5-5`, structured output, server-side refusal fallback enabled) receives only that snapshot and returns `{summary, highlights, concerns}`. A number guard discards any narrative containing a figure or time that isn't in the snapshot. Without an API key, or on errors or refusals, a deterministic template is used, and `ai_status`/`ai_note` record which.

## Dashboard & meta
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/dashboard/overview?team_id=` | admin, lead | All numbers computed from DB |
| GET | `/dashboard/me` | artist | |
| GET | `/meta/config` | any | Studio timezone, EOD hour, today, provider flags |
| GET | `/api/health` | public | (outside `/api/v1`) |
