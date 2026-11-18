"""Deterministic end-of-day metrics.

Every number in a daily report comes from here — plain database queries and arithmetic.
The AI never computes or invents figures; it only narrates this snapshot.

Definitions (studio-local day D, cutoff = min(now, end of D)):
  scenes_assigned      scene slots (scene × artist) in assignments dated D
  scenes_submitted     scene deliverables in submissions dated D
  scenes_approved      scene deliverables whose approval timestamp falls on D
  scenes_rejected      scene deliverables sent back by reviews made on D
  pending_reviews      submissions made by the cutoff with no review by the cutoff
  incomplete           artist slots due on D and not approved by the cutoff
  delayed              artist slots past deadline at the cutoff and not approved by then
"""
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutils import ensure_utc, studio_day_bounds_utc, studio_today, to_studio, utcnow
from app.models import (
    Assignment, AssignmentAssignee, Attendance, DeliverableStatus, Episode, Project, Review, Submission,
    SubmissionDeliverable, Team, User,
)
from app.services import assignment_service, attendance_service, scope


def _hhmm(dt: datetime | None) -> str | None:
    return to_studio(dt).strftime("%H:%M") if dt else None


def _pct(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def compute(db: Session, actor: User, report_date: date, *, project_id: int | None = None,
            episode_id: int | None = None, artist_id: int | None = None, team_id: int | None = None) -> dict:
    start, end = studio_day_bounds_utc(report_date)
    now = utcnow()
    cutoff = min(now, end)
    is_today = report_date == studio_today()

    # ---------- people in scope ----------
    members = [u for u in attendance_service._roster_users(db, actor, team_id)
               if attendance_service._existed_on(u, report_date)]
    if artist_id:
        scope.ensure_can_view_user(db, actor, artist_id)
        members = [u for u in members if u.id == artist_id]
    member_ids = {u.id for u in members}

    att = {r.user_id: r for r in db.scalars(select(Attendance).where(
        Attendance.work_date == report_date, Attendance.user_id.in_(member_ids or {-1})))}
    att_counts = {"present": 0, "half_day": 0, "leave": 0, "absent": 0, "not_checked_in": 0}
    for u in members:
        att_counts[attendance_service.derived_status(att.get(u.id), report_date)] += 1

    # ---------- assignment slots in scope ----------
    q = scope.assignment_query(db, actor)
    if project_id:
        q = q.where(Assignment.project_id == project_id)
    if episode_id:
        q = q.where(Assignment.episode_id == episode_id)
    assignments = [a for a in db.scalars(q) if a.assignment_date <= report_date]
    slots: list[tuple[Assignment, AssignmentAssignee]] = [
        (a, x) for a in assignments for x in a.assignees if x.user_id in member_ids
    ]
    slot_ids = {x.id for _, x in slots}
    assignment_ids = {a.id for a, _ in slots}

    def done_by_cutoff(x: AssignmentAssignee) -> bool:
        return x.completed_at is not None and ensure_utc(x.completed_at) <= cutoff

    distributed = {a.id for a, _ in slots if a.assignment_date == report_date}
    scenes_assigned = sum(len(a.scenes) for a, _ in slots if a.assignment_date == report_date)
    active = [(a, x) for a, x in slots if not done_by_cutoff(x)]
    due_today = [(a, x) for a, x in slots if start <= ensure_utc(a.deadline) <= end]
    incomplete = [(a, x) for a, x in due_today if not done_by_cutoff(x)]
    delayed = [(a, x) for a, x in slots if ensure_utc(a.deadline) < cutoff and not done_by_cutoff(x)]

    # ---------- submissions & reviews ----------
    subs_today = list(db.scalars(select(Submission).where(
        Submission.submission_date == report_date, Submission.assignee_id.in_(slot_ids or {-1}))))
    scene_dels_today = [d for s in subs_today for d in s.deliverables if d.scene_id is not None]

    approved_dels = list(db.scalars(
        select(SubmissionDeliverable).join(Submission)
        .where(Submission.assignee_id.in_(slot_ids or {-1}), SubmissionDeliverable.scene_id.is_not(None),
               SubmissionDeliverable.status == DeliverableStatus.APPROVED,
               SubmissionDeliverable.approved_at >= start, SubmissionDeliverable.approved_at <= end)))
    reviews_today = list(db.scalars(select(Review).join(Submission).where(
        Submission.assignee_id.in_(slot_ids or {-1}), Review.created_at >= start, Review.created_at <= end)))
    rejected_dels = [d for r in reviews_today for d in r.submission.deliverables
                     if d.scene_id is not None and d.scene_id not in set(r.approved_scene_ids or [])]

    pending = [s for s in db.scalars(select(Submission).where(
        Submission.assignee_id.in_(slot_ids or {-1}), Submission.submitted_at <= cutoff))
        if not any(ensure_utc(r.created_at) <= cutoff for r in s.reviews)]

    # ---------- per artist ----------
    per: dict[int, dict] = {}
    for u in members:
        rec = att.get(u.id)
        per[u.id] = {
            "name": u.full_name, "job_title": u.job_title,
            "attendance": attendance_service.derived_status(rec, report_date),
            "check_in": _hhmm(rec.check_in_at) if rec else None,
            "check_out": _hhmm(rec.check_out_at) if rec else None,
            "worked_minutes": attendance_service.to_out(rec).worked_minutes if rec else None,
            "active_assignments": 0, "scenes_assigned_today": 0, "scenes_submitted": 0, "scenes_approved": 0,
            "scenes_rejected": 0, "pending_reviews": 0, "delayed_assignments": 0, "late_submissions": 0,
            "reported_progress_pct": None,
        }
    progress: dict[int, list[int]] = defaultdict(list)
    for a, x in active:
        per[x.user_id]["active_assignments"] += 1
        progress[x.user_id].append(x.reported_progress_pct)
    for a, x in slots:
        if a.assignment_date == report_date:
            per[x.user_id]["scenes_assigned_today"] += len(a.scenes)
    for a, x in delayed:
        per[x.user_id]["delayed_assignments"] += 1
    for s in subs_today:
        per[s.artist_id]["scenes_submitted"] += sum(1 for d in s.deliverables if d.scene_id is not None)
        if ensure_utc(s.submitted_at) > ensure_utc(s.assignment.deadline):
            per[s.artist_id]["late_submissions"] += 1
    for d in approved_dels:
        per[d.submission.artist_id]["scenes_approved"] += 1
    for d in rejected_dels:
        per[d.submission.artist_id]["scenes_rejected"] += 1
    for s in pending:
        per[s.artist_id]["pending_reviews"] += 1
    for uid, vals in progress.items():
        per[uid]["reported_progress_pct"] = round(sum(vals) / len(vals)) if vals else None

    # ---------- projects ----------
    proj: dict[int, dict] = {}

    def p_row(a: Assignment) -> dict:
        return proj.setdefault(a.project_id, {
            "code": a.project.code, "title": a.project.title, "assignments_active": 0,
            "assignments_distributed": 0, "scenes_submitted": 0, "scenes_approved": 0, "scenes_rejected": 0,
        })
    for a, x in active:
        p_row(a)["assignments_active"] += 1
    for aid in distributed:
        a = next(a for a, _ in slots if a.id == aid)
        p_row(a)["assignments_distributed"] += 1
    for d in scene_dels_today:
        p_row(d.submission.assignment)["scenes_submitted"] += 1
    for d in approved_dels:
        p_row(d.submission.assignment)["scenes_approved"] += 1
    for d in rejected_dels:
        p_row(d.submission.assignment)["scenes_rejected"] += 1

    def slot_row(a: Assignment, x: AssignmentAssignee) -> dict:
        return {"assignment_id": a.id, "title": a.title, "project": a.project.code, "artist": x.user.full_name,
                "deadline": to_studio(a.deadline).strftime("%Y-%m-%d %H:%M"), "status": x.status.value,
                "reported_progress_pct": x.reported_progress_pct}

    reviewed_scenes = len(approved_dels) + len(rejected_dels)
    totals = {
        "team_members": len(members),
        "present": att_counts["present"] + att_counts["half_day"],
        "half_day": att_counts["half_day"], "on_leave": att_counts["leave"], "absent": att_counts["absent"],
        "not_checked_in": att_counts["not_checked_in"],
        "attendance_rate_pct": _pct(att_counts["present"] + att_counts["half_day"], len(members)),
        "projects_worked_on": len(proj),
        "assignments_distributed": len(distributed), "assignments_active": len({a.id for a, _ in active}),
        "scenes_assigned": scenes_assigned, "scenes_submitted": len(scene_dels_today),
        "deliverables_submitted": sum(len(s.deliverables) for s in subs_today),
        "submissions": len(subs_today), "scenes_approved": len(approved_dels), "scenes_rejected": len(rejected_dels),
        "approval_rate_pct": _pct(len(approved_dels), reviewed_scenes),
        "pending_reviews": len(pending), "incomplete_assignments": len(incomplete),
        "delayed_assignments": len(delayed),
        "late_submissions": sum(r["late_submissions"] for r in per.values()),
    }

    remarks = _remarks(totals, per, delayed, slot_row)

    labels = {}
    if project_id:
        p = db.get(Project, project_id)
        labels["project"] = f"{p.code} — {p.title}" if p else str(project_id)
    if episode_id:
        e = db.get(Episode, episode_id)
        labels["episode"] = f"EP{e.episode_number:02d} {e.title}" if e else str(episode_id)
    if artist_id:
        labels["artist"] = per[artist_id]["name"] if artist_id in per else str(artist_id)
    if team_id:
        labels["team"] = db.scalar(select(Team.name).where(Team.id == team_id))
    team_names = sorted({u.team.name for u in members if u.team})

    return {
        "report_date": report_date.isoformat(),
        "generated_at": now.isoformat(timespec="seconds"),
        "as_of": "end of day" if not is_today else f"{_hhmm(now)} (day in progress)",
        "scope": {"teams": team_names, "filters": labels},
        "totals": totals,
        "attendance_by_status": {k: sorted(per[u.id]["name"] for u in members if per[u.id]["attendance"] == k)
                                 for k in ("present", "half_day", "leave", "absent", "not_checked_in")},
        "projects": sorted(proj.values(), key=lambda p: p["code"]),
        "artists": sorted(per.values(), key=lambda r: r["name"]),
        "incomplete_assignments": [slot_row(a, x) for a, x in incomplete],
        "delayed_assignments": [slot_row(a, x) for a, x in delayed],
        "remarks": remarks,
    }


def _remarks(t: dict, per: dict, delayed, slot_row) -> list[str]:
    out = []
    if t["pending_reviews"]:
        out.append(f"{t['pending_reviews']} submission(s) awaiting review.")
    for a, x in delayed:
        r = slot_row(a, x)
        out.append(f"{r['artist']}: \"{r['title']}\" is past its deadline ({r['deadline']}).")
    for r in per.values():
        if r["attendance"] in ("absent", "leave") and r["active_assignments"]:
            out.append(f"{r['name']} is {r['attendance']} with {r['active_assignments']} open assignment(s).")
    if t["late_submissions"]:
        out.append(f"{t['late_submissions']} submission(s) arrived after their deadline.")
    if t["scenes_rejected"]:
        out.append(f"{t['scenes_rejected']} scene(s) were sent back for revision.")
    return out
