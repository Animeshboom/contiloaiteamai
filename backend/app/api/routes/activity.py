"""Activity log (admin): who changed what, read-only, from the audit trail every service already writes."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.timeutils import studio_day_bounds_utc
from app.models import AuditLog, User

router = APIRouter(prefix="/activity", tags=["activity log"])

# Plain-English labels for the actions people care about; anything else falls back to the raw action.
LABELS = {
    "attendance.correct": "corrected staff attendance",
    "attendance.auto_close": "auto-closed a forgotten check-out",
    "user.create": "added a person",
    "user.update": "edited an employee",
    "user.activate": "reactivated an account",
    "user.deactivate": "deactivated an account",
    "user.password_reset": "reset a password",
    "user.unlock": "unlocked an account",
    "chat.delete": "deleted a chat message",
    "backup.download": "downloaded a backup",
    "user.mfa_reset": "reset two-step login",
    "auth.mfa_enabled": "turned on two-step login",
    "auth.mfa_failed": "entered a wrong two-step code",
    "report.submit": "sent a day report to the admin",
    "report.comment": "replied on a day report",
    "target.set": "set a weekly target",
    "assignment.reassign": "reassigned a task",
    "auth.password_changed": "changed their password",
    "auth.login": "signed in",
    "auth.login_failed": "failed to sign in",
    "holiday.create": "added a holiday",
    "holiday.delete": "removed a holiday",
    "leave.request": "requested leave",
    "leave.approved": "approved leave",
    "leave.rejected": "rejected leave",
    "leave.cancel": "cancelled a leave request",
    "announcement.create": "posted an announcement",
    "announcement.delete": "deleted an announcement",
    "assignment.create": "created an assignment",
    "assignment.update": "edited an assignment",
    "assignment.delete": "deleted an assignment",
    "assignment.progress": "updated progress",
    "assignment.complete": "completed an assignment",
    "submission.create": "submitted work",
    "submission.attach": "attached a file",
    "submission.approved": "approved a submission",
    "submission.rejected": "requested a revision",
    "attendance.check_in": "checked in",
    "attendance.check_out": "checked out",
    "report.generate": "generated an EOD report",
    "report.approve": "approved an EOD report",
    "report.send": "sent an EOD report",
    "project.create": "created a project",
    "team.create": "created a team",
    "team.update": "edited a team",
}
# Routine events, hidden unless asked for.
NOISY = ("auth.login", "attendance.check_in", "attendance.check_out",
         "assignment.progress")


class ActivityOut(BaseModel):
    id: int
    at: datetime
    actor_id: int | None
    actor: str | None
    action: str
    summary: str
    subject: str | None  # the person the change was about, when there is one
    details: dict | None
    ip: str | None


def _subject_id(log: AuditLog) -> int | None:
    after = log.after or {}
    for key in ("user_id",):
        if isinstance(after.get(key), int):
            return after[key]
    return log.entity_id if log.entity_type == "user" else None


@router.get("", response_model=list[ActivityOut])
def list_activity(
    actor_id: int | None = None,
    subject_id: int | None = Query(default=None, description="Changes about this person"),
    action: str | None = Query(default=None, max_length=80, description="Action or prefix, e.g. 'attendance'"),
    start: date | None = None,
    end: date | None = None,
    include_noisy: bool = False,
    before_id: int | None = Query(default=None, description="Paging: return entries older than this id"),
    limit: int = Query(default=100, ge=1, le=200),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Newest first. Routine events (sign-ins, check-ins, progress) are hidden unless include_noisy=true."""
    q = select(AuditLog)
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)
    if action:
        q = q.where(AuditLog.action.startswith(action))
    elif not include_noisy:
        q = q.where(AuditLog.action.not_in(NOISY))
    if start:
        q = q.where(AuditLog.created_at >= studio_day_bounds_utc(start)[0])
    if end:
        q = q.where(AuditLog.created_at <= studio_day_bounds_utc(end)[1])
    if before_id:
        q = q.where(AuditLog.id < before_id)
    # subject filter is applied in Python (the id lives in JSON or entity_id), so over-fetch a little
    rows = list(db.scalars(q.order_by(AuditLog.id.desc()).limit(limit * (5 if subject_id else 1))))
    if subject_id:
        rows = [r for r in rows if _subject_id(r) == subject_id][:limit]
    names = {u.id: u.full_name for u in db.scalars(select(User).where(
        User.id.in_({r.actor_id for r in rows} | {_subject_id(r) for r in rows} - {None} or {-1})))}
    out = []
    for r in rows:
        sid = _subject_id(r)
        subject = names.get(sid) if sid and sid != r.actor_id else None
        summary = LABELS.get(r.action, r.action.replace("_", " ").replace(".", ": "))
        if subject:
            summary += f" — {subject}"
        reason = (r.after or {}).get("reason")
        if reason:
            summary += f" (“{reason}”)"
        out.append(ActivityOut(id=r.id, at=r.created_at, actor_id=r.actor_id,
                               actor=names.get(r.actor_id) if r.actor_id else "System", action=r.action,
                               summary=summary, subject=subject, details=r.after, ip=r.ip_address))
    return out
