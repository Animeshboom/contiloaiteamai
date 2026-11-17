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

## Dashboard & meta
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/dashboard/overview?team_id=` | admin, lead | All numbers computed from DB |
| GET | `/dashboard/me` | artist | |
| GET | `/meta/config` | any | Studio timezone, EOD hour, today, provider flags |
| GET | `/api/health` | public | (outside `/api/v1`) |
