"""Attendance: check-in/out, rosters, history, audited corrections.

Rules:
- One attendance row per user per studio-local work date (DB unique constraint).
- Check-in is rejected if already checked in today, or if a lead marked the day as Leave/Absent.
- Check-out closes today's open record, or a night shift's open record from the previous day as long as
  it is within MAX_SHIFT_HOURS of its check-in.
- On check-out, a shift shorter than HALF_DAY_MAX_HOURS is marked Half Day automatically.
- Records left open past MAX_SHIFT_HOURS are auto-closed by a background job at that day's EOD hour
  (or at check-in time for shifts that began after EOD) and noted for the lead to review.
- Days with no record are reported as Absent (past work days, or today after STAFF_CHECKIN_CUTOFF_HOUR),
  "not_checked_in" (today before the cutoff) or "day_off" (non-working days and holidays); nothing is stored.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, ValidationFailed
from app.core.timeutils import ensure_utc, studio_eod, studio_hour, studio_today, to_studio, utcnow
from app.models import Attendance, AttendanceStatus, RoleName, Role, User
from app.schemas.attendance import (
    AttendanceCorrection, AttendanceOut, DailyCount, MonthStats, RosterRow, TodayStatus,
)
from app.services import audit, scope
from app.services.calendar import is_work_day

NOT_CHECKED_IN = "not_checked_in"
DAY_OFF = "day_off"
AUTO_CLOSED_NOTE = "Auto-closed: no check-out recorded"


def to_out(rec: Attendance) -> AttendanceOut:
    out = AttendanceOut.model_validate(rec)
    if rec.check_in_at and rec.check_out_at:
        out.worked_minutes = int((ensure_utc(rec.check_out_at) - ensure_utc(rec.check_in_at)).total_seconds() // 60)
    return out


def _get(db: Session, user_id: int, d: date) -> Attendance | None:
    return db.scalar(select(Attendance).where(Attendance.user_id == user_id, Attendance.work_date == d))


def _open_record(db: Session, user_id: int) -> Attendance | None:
    """Today's open record, else the latest one still open within MAX_SHIFT_HOURS (a night shift)."""
    rec = _get(db, user_id, studio_today())
    if rec and rec.check_in_at and rec.check_out_at is None:
        return rec
    since = utcnow() - timedelta(hours=get_settings().max_shift_hours)
    return db.scalar(
        select(Attendance)
        .where(Attendance.user_id == user_id, Attendance.check_in_at.is_not(None),
               Attendance.check_in_at >= since, Attendance.check_out_at.is_(None))
        .order_by(Attendance.check_in_at.desc()).limit(1)
    )


def today_status(db: Session, user: User) -> TodayStatus:
    d = studio_today()
    rec = _get(db, user.id, d)
    open_rec = _open_record(db, user.id)
    if open_rec is not None and open_rec is not rec:  # night shift from yesterday still open: check out first
        return TodayStatus(work_date=d, record=to_out(open_rec), can_check_in=False, can_check_out=True)
    can_in = rec is None or (rec.check_in_at is None and rec.status in (AttendanceStatus.PRESENT, AttendanceStatus.HALF_DAY))
    can_out = open_rec is not None
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


def _close(rec: Attendance, at) -> None:
    rec.check_out_at = at
    hours = (ensure_utc(at) - ensure_utc(rec.check_in_at)).total_seconds() / 3600
    if hours < get_settings().half_day_max_hours:
        rec.status = AttendanceStatus.HALF_DAY


def check_out(db: Session, user: User, ip: str | None, note: str | None = None) -> AttendanceOut:
    rec = _open_record(db, user.id)
    if rec is None:
        today = _get(db, user.id, studio_today())
        if today is not None and today.check_out_at is not None:
            raise Conflict(f"Already checked out today at {to_studio(today.check_out_at):%H:%M}")
        raise Conflict("You have not checked in today")
    now = utcnow()
    _close(rec, now)
    if note and note.strip():
        rec.work_note = note.strip()
    audit.record(db, actor_id=user.id, action="attendance.check_out", entity_type="attendance",
                 entity_id=rec.id, after={"check_out_at": now, "status": rec.status}, ip=ip)
    db.commit()
    return to_out(rec)


def auto_close_stale(db: Session) -> int:
    """Close records left open longer than MAX_SHIFT_HOURS (forgotten check-outs).

    The check-out is set to that work day's EOD hour; a shift that began after EOD is closed at its
    check-in time (no hours credited). Either way the record is noted so the lead can correct it.
    """
    cutoff = utcnow() - timedelta(hours=get_settings().max_shift_hours)
    stale = db.scalars(select(Attendance).where(
        Attendance.check_in_at.is_not(None), Attendance.check_out_at.is_(None), Attendance.check_in_at < cutoff)).all()
    for rec in stale:
        check_in = ensure_utc(rec.check_in_at)
        eod = studio_eod(rec.work_date)
        _close(rec, eod if check_in < eod else check_in)
        rec.notes = f"{rec.notes} · {AUTO_CLOSED_NOTE}" if rec.notes else AUTO_CLOSED_NOTE
        audit.record(db, actor_id=None, action="attendance.auto_close", entity_type="attendance", entity_id=rec.id,
                     after={"check_out_at": rec.check_out_at, "status": rec.status}, ip=None)
    db.commit()
    return len(stale)


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
    """Artists and leads whose attendance this actor oversees (admins excluded)."""
    q = select(User).join(Role).where(
        User.is_active.is_(True), User.deleted_at.is_(None), Role.name.in_([RoleName.TEAM_LEAD, RoleName.ARTIST])
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


def derived_status(rec: Attendance | None, d: date, team_id: int | None = None, on_leave: bool = False) -> str:
    """A record (check-in or correction) wins; then a day off (weekday rule / holiday for everyone or the
    team); then approved leave; otherwise Absent once missed, else not checked in yet."""
    if rec:
        return rec.status.value
    if not is_work_day(d, team_id):
        return DAY_OFF
    if on_leave:
        return AttendanceStatus.LEAVE.value
    return AttendanceStatus.ABSENT.value if _missed(d) else NOT_CHECKED_IN


def _leave_days(db: Session, user_ids: list[int], start: date, end: date) -> dict[int, set[date]]:
    from app.services.artist_service import leave_days  # noqa: PLC0415 (avoid an import cycle)
    found = leave_days(db, user_ids, start, end)
    return {i: found.get(i, set()) for i in user_ids}


def month_stats(db: Session, users: list[User], today: date | None = None) -> dict[int, MonthStats]:
    """This month so far per person: attended (half days count 0.5) / work days decided."""
    today = today or studio_today()
    first = today.replace(day=1)
    ids = [u.id for u in users]
    recs = {(r.user_id, r.work_date): r for r in db.scalars(select(Attendance).where(
        Attendance.user_id.in_(ids or [-1]), Attendance.work_date >= first, Attendance.work_date <= today))}
    leave = _leave_days(db, ids, first, today)
    low_pct = get_settings().low_attendance_pct
    out = {}
    for u in users:
        attended, counted = 0.0, 0
        d = max(first, to_studio(u.created_at).date())
        while d <= today:
            status = derived_status(recs.get((u.id, d)), d, u.team_id, d in leave[u.id])
            if status in ("present", "half_day", "absent", "leave"):
                counted += 1
                attended += {"present": 1.0, "half_day": 0.5}.get(status, 0.0)
            d += timedelta(days=1)
        pct = round(100 * attended / counted) if counted else None
        out[u.id] = MonthStats(month=today.strftime("%Y-%m"), present=attended, counted_days=counted, pct=pct,
                               low=pct is not None and pct < low_pct)
    return out


def _missed(d: date) -> bool:
    """A work day with no check-in counts as Absent once it is past, or today after the staff cutoff
    (STAFF_CHECKIN_CUTOFF_HOUR). A late check-in still works and replaces it."""
    today = studio_today()
    return d < today or (d == today and utcnow() >= studio_hour(d, get_settings().staff_checkin_cutoff_hour))


def roster(db: Session, actor: User, d: date, team_id: int | None = None) -> list[RosterRow]:
    users = [u for u in _roster_users(db, actor, team_id) if _existed_on(u, d)]
    recs = {
        r.user_id: r
        for r in db.scalars(select(Attendance).where(
            Attendance.work_date == d, Attendance.user_id.in_([u.id for u in users] or [-1])))
    }
    leave = _leave_days(db, [u.id for u in users], d, d)
    months = month_stats(db, users)
    return [
        RosterRow(
            user_id=u.id, full_name=u.full_name, job_title=u.job_title,
            team_name=u.team.name if u.team else None,
            status=derived_status(recs.get(u.id), d, u.team_id, d in leave[u.id]),
            record=to_out(recs[u.id]) if u.id in recs else None,
            month=months.get(u.id),
        )
        for u in users
    ]


def daily_counts(db: Session, actor: User, start: date, end: date, team_id: int | None = None) -> list[DailyCount]:
    users = _roster_users(db, actor, team_id)
    ids = [u.id for u in users]
    recs = {(r.user_id, r.work_date): r for r in db.scalars(select(Attendance).where(
        Attendance.user_id.in_(ids or [-1]), Attendance.work_date >= start, Attendance.work_date <= end))}
    leave = _leave_days(db, ids, start, end)
    out = []
    d = start
    while d <= end:
        c = {"present": 0, "half_day": 0, "leave": 0, "absent": 0}
        for u in users:
            if _existed_on(u, d):
                status = derived_status(recs.get((u.id, d)), d, u.team_id, d in leave[u.id])
                if status in c:
                    c[status] += 1
        out.append(DailyCount(date=d, **c))
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


def export_month_csv(db: Session, actor: User, month: str, team_id: int | None = None) -> tuple[str, str]:
    """Staff monthly sheet: one row per person (leads + artists the actor oversees), one column per day
    (P present, H half day, L leave, A absent, - not checked in yet, off), then totals and hours worked."""
    import csv
    import io
    import re
    from datetime import datetime

    try:
        first = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise ValidationFailed("Month must look like 2026-11")
    today = studio_today()
    if first > today:
        raise ValidationFailed("That month has not started yet")
    last = min((first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), today)
    users = _roster_users(db, actor, team_id)
    recs = {(r.user_id, r.work_date): r for r in db.scalars(select(Attendance).where(
        Attendance.user_id.in_([u.id for u in users] or [-1]),
        Attendance.work_date >= first, Attendance.work_date <= last))}
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    leave = _leave_days(db, [u.id for u in users], first, last)
    code = {"present": "P", "half_day": "H", "leave": "L", "absent": "A", NOT_CHECKED_IN: "-", DAY_OFF: "off"}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Email", "Role", "Team"] + [f"{d:%d}" for d in days]
               + ["Present", "Half days", "Leave", "Absent", "Hours worked", "Attendance %"])
    for u in users:
        cells, counts, minutes = [], {"present": 0, "half_day": 0, "leave": 0, "absent": 0}, 0
        for d in days:
            if not _existed_on(u, d):
                cells.append("")
                continue
            rec = recs.get((u.id, d))
            status = derived_status(rec, d, u.team_id, d in leave[u.id])
            cells.append(code.get(status, status))
            if status in counts:
                counts[status] += 1
            if rec:
                minutes += to_out(rec).worked_minutes or 0
        expected = counts["present"] + counts["half_day"] + counts["absent"] + counts["leave"]
        attended = counts["present"] + 0.5 * counts["half_day"]
        pct = round(100 * attended / expected) if expected else ""
        w.writerow([u.full_name, u.email, u.role_name.value.replace("_", " "), u.team.name if u.team else ""]
                   + cells + [counts["present"], counts["half_day"], counts["leave"], counts["absent"],
                              f"{minutes // 60}:{minutes % 60:02d}", pct])
    label = "all-staff"
    if team_id:
        team = next((u.team for u in users if u.team_id == team_id and u.team), None)
        label = re.sub(r"[^A-Za-z0-9_-]+", "-", team.name) if team else f"team-{team_id}"
    return f"staff-attendance-{label}-{month}.csv", buf.getvalue()
