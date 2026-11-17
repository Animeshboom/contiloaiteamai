"""Attendance: check-in/out, rosters, history, audited corrections.

Rules:
- One attendance row per user per studio-local work date (DB unique constraint).
- Check-in is rejected if already checked in today, or if a lead marked the day as Leave/Absent.
- Check-out requires a check-in today and no prior check-out.
- On check-out, a shift shorter than HALF_DAY_MAX_HOURS is marked Half Day automatically.
- Days with no record are reported as Absent (past dates) or "not_checked_in" (today); nothing is stored.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, ValidationFailed
from app.core.timeutils import ensure_utc, studio_today, to_studio, utcnow
from app.models import Attendance, AttendanceStatus, RoleName, Role, User
from app.schemas.attendance import AttendanceCorrection, AttendanceOut, DailyCount, RosterRow, TodayStatus
from app.services import audit, scope

NOT_CHECKED_IN = "not_checked_in"


def to_out(rec: Attendance) -> AttendanceOut:
    out = AttendanceOut.model_validate(rec)
    if rec.check_in_at and rec.check_out_at:
        out.worked_minutes = int((ensure_utc(rec.check_out_at) - ensure_utc(rec.check_in_at)).total_seconds() // 60)
    return out


def _get(db: Session, user_id: int, d: date) -> Attendance | None:
    return db.scalar(select(Attendance).where(Attendance.user_id == user_id, Attendance.work_date == d))


def today_status(db: Session, user: User) -> TodayStatus:
    d = studio_today()
    rec = _get(db, user.id, d)
    can_in = rec is None or (rec.check_in_at is None and rec.status in (AttendanceStatus.PRESENT, AttendanceStatus.HALF_DAY))
    can_out = rec is not None and rec.check_in_at is not None and rec.check_out_at is None
    return TodayStatus(work_date=d, record=to_out(rec) if rec else None, can_check_in=can_in, can_check_out=can_out)


def check_in(db: Session, user: User, ip: str | None) -> AttendanceOut:
    d = studio_today()
    rec = _get(db, user.id, d)
    if rec and rec.check_in_at:
        raise Conflict(f"Already checked in today at {to_studio(rec.check_in_at):%H:%M}")
    if rec and rec.status in (AttendanceStatus.LEAVE, AttendanceStatus.ABSENT):
        raise Conflict(f"Today is recorded as {rec.status.value.replace('_', ' ')}. Ask your team lead to update it.")
    now = utcnow()
    if rec is None:
        rec = Attendance(user_id=user.id, work_date=d, check_in_at=now, status=AttendanceStatus.PRESENT)
        db.add(rec)
    else:
        rec.check_in_at = now
    try:
        db.flush()
    except IntegrityError:  # concurrent double-click: the unique constraint wins
        db.rollback()
        raise Conflict("Already checked in today")
    audit.record(db, actor_id=user.id, action="attendance.check_in", entity_type="attendance",
                 entity_id=rec.id, after={"work_date": d, "check_in_at": now}, ip=ip)
    db.commit()
    return to_out(rec)


def check_out(db: Session, user: User, ip: str | None) -> AttendanceOut:
    d = studio_today()
    rec = _get(db, user.id, d)
    if rec is None or rec.check_in_at is None:
        raise Conflict("You have not checked in today")
    if rec.check_out_at is not None:
        raise Conflict(f"Already checked out today at {to_studio(rec.check_out_at):%H:%M}")
    now = utcnow()
    rec.check_out_at = now
    hours = (now - ensure_utc(rec.check_in_at)).total_seconds() / 3600
    if hours < get_settings().half_day_max_hours:
        rec.status = AttendanceStatus.HALF_DAY
    audit.record(db, actor_id=user.id, action="attendance.check_out", entity_type="attendance",
                 entity_id=rec.id, after={"check_out_at": now, "status": rec.status}, ip=ip)
    db.commit()
    return to_out(rec)


def history(db: Session, actor: User, user_id: int, start: date, end: date) -> list[AttendanceOut]:
    scope.ensure_can_view_user(db, actor, user_id)
    if end < start:
        raise ValidationFailed("End date must be on or after start date")
    if (end - start).days > 366:
        raise ValidationFailed("Date range cannot exceed one year")
    rows = db.scalars(
        select(Attendance)
        .where(Attendance.user_id == user_id, Attendance.work_date >= start, Attendance.work_date <= end)
        .order_by(Attendance.work_date.desc())
    )
    return [to_out(r) for r in rows]


def _roster_users(db: Session, actor: User, team_id: int | None) -> list[User]:
    """Artists and leads whose attendance this actor oversees (admins excluded from rosters)."""
    q = select(User).join(Role).where(
        User.is_active.is_(True), User.deleted_at.is_(None), Role.name != RoleName.ADMIN
    )
    ids = scope.visible_user_ids(db, actor)
    if ids is not None:
        q = q.where(User.id.in_(ids))
    if team_id:
        q = q.where(User.team_id == team_id)
    return list(db.scalars(q.order_by(User.full_name)))


def _existed_on(u: User, d: date) -> bool:
    """People are only expected at work from the day their account was created."""
    return to_studio(u.created_at).date() <= d


def derived_status(rec: Attendance | None, d: date) -> str:
    if rec:
        return rec.status.value
    return NOT_CHECKED_IN if d >= studio_today() else AttendanceStatus.ABSENT.value


def roster(db: Session, actor: User, d: date, team_id: int | None = None) -> list[RosterRow]:
    users = [u for u in _roster_users(db, actor, team_id) if _existed_on(u, d)]
    recs = {
        r.user_id: r
        for r in db.scalars(select(Attendance).where(
            Attendance.work_date == d, Attendance.user_id.in_([u.id for u in users] or [-1])))
    }
    return [
        RosterRow(
            user_id=u.id, full_name=u.full_name, job_title=u.job_title,
            team_name=u.team.name if u.team else None,
            status=derived_status(recs.get(u.id), d),
            record=to_out(recs[u.id]) if u.id in recs else None,
        )
        for u in users
    ]


def daily_counts(db: Session, actor: User, start: date, end: date, team_id: int | None = None) -> list[DailyCount]:
    users = _roster_users(db, actor, team_id)
    ids = [u.id for u in users] or [-1]
    recs = db.scalars(select(Attendance).where(
        Attendance.user_id.in_(ids), Attendance.work_date >= start, Attendance.work_date <= end))
    by_day: dict[date, dict[str, int]] = {}
    for r in recs:
        by_day.setdefault(r.work_date, {}).setdefault(r.status.value, 0)
        by_day[r.work_date][r.status.value] += 1
    out = []
    d = start
    today = studio_today()
    while d <= end:
        c = by_day.get(d, {})
        recorded = sum(c.values())
        expected = sum(1 for u in users if _existed_on(u, d))
        absent = c.get("absent", 0) + (max(expected - recorded, 0) if d < today else 0)
        out.append(DailyCount(date=d, present=c.get("present", 0), half_day=c.get("half_day", 0),
                              leave=c.get("leave", 0), absent=absent))
        d += timedelta(days=1)
    return out


def correct(db: Session, actor: User, data: AttendanceCorrection, ip: str | None) -> AttendanceOut:
    target = db.get(User, data.user_id)
    if not target or target.deleted_at is not None:
        raise ValidationFailed("User not found")
    scope.ensure_can_manage_artist(db, actor, target)
    if target.id == actor.id and not scope.is_admin(actor):
        raise ValidationFailed("You cannot correct your own attendance")
    if data.work_date > studio_today():
        if data.status != AttendanceStatus.LEAVE:
            raise ValidationFailed("Only Leave can be recorded for future dates")
        if data.check_in_at or data.check_out_at:
            raise ValidationFailed("Future leave cannot have check-in/out times")
    for ts in (data.check_in_at, data.check_out_at):
        if ts is not None and to_studio(ts).date() != data.work_date:
            raise ValidationFailed("Check-in/out times must fall on the selected work date (studio time)")

    rec = _get(db, target.id, data.work_date)
    before = None
    if rec is None:
        rec = Attendance(user_id=target.id, work_date=data.work_date)
        db.add(rec)
    else:
        before = {"status": rec.status, "check_in_at": rec.check_in_at, "check_out_at": rec.check_out_at,
                  "notes": rec.notes}
    rec.status = data.status
    if data.status in (AttendanceStatus.LEAVE, AttendanceStatus.ABSENT):
        rec.check_in_at = rec.check_out_at = None
    else:
        rec.check_in_at = data.check_in_at
        rec.check_out_at = data.check_out_at
    rec.notes = data.reason
    rec.corrected_by_id = actor.id
    rec.corrected_at = utcnow()
    db.flush()
    audit.record(db, actor_id=actor.id, action="attendance.correct", entity_type="attendance", entity_id=rec.id,
                 before=before,
                 after={"user_id": target.id, "work_date": data.work_date, "status": rec.status,
                        "check_in_at": rec.check_in_at, "check_out_at": rec.check_out_at, "reason": data.reason},
                 ip=ip)
    db.commit()
    return to_out(rec)
