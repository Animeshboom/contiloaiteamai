"""Overview metrics — every number comes from a database query, scoped to the viewer."""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutils import ensure_utc, studio_day_bounds_utc, studio_today, utcnow
from app.models import (
    Assignment, AssignmentAssignee, AssignmentStatus, Project, ProjectStatus, Submission,
    SubmissionStatus, User,
)
from app.services import assignment_service, attendance_service, scope


def staff_overview(db: Session, actor: User, team_id: int | None = None) -> dict:
    today = studio_today()
    roster = attendance_service.roster(db, actor, today, team_id)
    att = {"present": 0, "half_day": 0, "leave": 0, "absent": 0, "not_checked_in": 0, "day_off": 0}
    for r in roster:
        att[r.status] = att.get(r.status, 0) + 1

    visible = assignment_service.list_for(db, actor, limit=5000)
    member_ids = {r.user_id for r in roster}
    by_status = {s.value: 0 for s in AssignmentStatus}
    workload: dict[int, dict] = {}
    now = utcnow()
    start, end = studio_day_bounds_utc(today)
    due_today = overdue = 0
    for a in visible:
        by_status[a.status.value] += 1
        active = a.status not in assignment_service.DONE
        if active and start <= ensure_utc(a.deadline) <= end:
            due_today += 1
        if assignment_service.is_overdue(a, now):
            overdue += 1
        for x in a.assignees:
            if x.user_id not in member_ids or x.status == AssignmentStatus.REASSIGNED:
                continue
            w = workload.setdefault(x.user_id, {"user_id": x.user_id, "full_name": x.user.full_name,
                                                "active": 0, "submitted": 0, "approved": 0})
            if x.status in (AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS, AssignmentStatus.REVISION_REQUIRED):
                w["active"] += 1
            elif x.status == AssignmentStatus.SUBMITTED:
                w["submitted"] += 1
            else:
                w["approved"] += 1

    pending_q = select(func.count(Submission.id)).where(Submission.status == SubmissionStatus.PENDING_REVIEW)
    ids = scope.visible_user_ids(db, actor)
    if ids is not None:
        pending_q = pending_q.where(Submission.artist_id.in_(ids))

    return {
        "date": today,
        "headcount": len(roster),
        "attendance_today": att,
        "attendance_trend": [c.model_dump() for c in attendance_service.daily_counts(
            db, actor, today - timedelta(days=6), today, team_id)],
        "assignments_by_status": by_status,
        "active_assignments": sum(1 for a in visible if a.status not in assignment_service.DONE),
        "due_today": due_today,
        "overdue": overdue,
        "pending_reviews": db.scalar(pending_q) or 0,
        "active_projects": db.scalar(select(func.count(Project.id)).where(
            Project.deleted_at.is_(None), Project.status == ProjectStatus.ACTIVE)) or 0,
        "workload": _with_targets(db, sorted(workload.values(), key=lambda w: w["full_name"])),
    }


def _with_targets(db: Session, rows: list[dict]) -> list[dict]:
    """Add this week's approved scenes, the weekly target and the private average rating to each person."""
    from app.services import lead_service  # noqa: PLC0415 (lead_service imports this module's peers)
    ids = [r["user_id"] for r in rows]
    approved = lead_service.approved_this_week(db, ids)
    targets = lead_service.targets_for(db, ids)
    ratings = lead_service.average_ratings(db, ids)
    for r in rows:
        r["approved_this_week"] = approved.get(r["user_id"], 0)
        r["weekly_target"] = targets.get(r["user_id"])
        r["avg_rating"] = ratings.get(r["user_id"])
    return rows


def artist_overview(db: Session, artist: User) -> dict:
    mine = db.scalars(
        select(AssignmentAssignee).join(Assignment)
        .where(AssignmentAssignee.user_id == artist.id, Assignment.deleted_at.is_(None))
    ).all()
    by_status = {s.value: 0 for s in AssignmentStatus}
    now = utcnow()
    overdue = 0
    for x in mine:
        by_status[x.status.value] += 1
        open_ = (AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS, AssignmentStatus.REVISION_REQUIRED)
        if x.status in open_ and assignment_service.is_overdue(x.assignment, now):
            overdue += 1
    return {
        "date": studio_today(),
        "attendance": attendance_service.today_status(db, artist).model_dump(),
        "assignments_by_status": by_status,
        "open_assignments": sum(by_status[s.value] for s in
                                (AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS, AssignmentStatus.REVISION_REQUIRED)),
        "awaiting_review": by_status[AssignmentStatus.SUBMITTED.value],
        "overdue": overdue,
    }
