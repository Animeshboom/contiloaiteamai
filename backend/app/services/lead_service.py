"""Team-lead tools: the "Today" action list, reassigning work, weekly scene targets, feedback phrases,
private review ratings, and the evening summary.

Scope is always the lead's own people (the artists in the teams they lead);
admins see everyone.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.timeutils import ensure_utc, studio_day_bounds_utc, studio_eod, studio_today, to_studio, utcnow
from app.models import (
    Assignment, AssignmentAssignee, AssignmentStatus, DeliverableStatus, FeedbackPhrase, LeaveStatus, Review,
    RoleName, Submission, SubmissionDeliverable, SubmissionStatus, User, WeeklyTarget,
)
from app.services import (
    artist_service, assignment_service, attendance_service, audit, notification_service, scope,
)
from app.services.calendar import is_work_day

OPEN = (AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS, AssignmentStatus.REVISION_REQUIRED,
        AssignmentStatus.SUBMITTED)
DEFAULT_PHRASES = ["Fix lighting", "Check continuity", "Match the reference", "Clean up edges",
                   "Timing feels off", "Great work"]


def _people_ids(db: Session, actor: User) -> set[int] | None:
    """None = everyone (admin)."""
    ids = scope.visible_user_ids(db, actor)
    if ids is not None:
        ids = ids - {actor.id}
    return ids


def _ensure_manages(db: Session, actor: User, person: User) -> None:
    if not scope.is_worker(person):
        raise ValidationFailed("Targets and tasks are for artists")
    scope.ensure_can_manage_artist(db, actor, person)


# ---------------- reassign ----------------

def reassign(db: Session, actor: User, assignment_id: int, from_user_id: int, to_user_id: int,
             note: str | None, ip: str | None) -> Assignment:
    """Move one person's unfinished work to someone else. The old person comes off the task; if they
    already submitted something, their slot is kept as history with status "reassigned"."""
    a = scope.get_assignment_for_edit(db, actor, assignment_id)
    old = next((x for x in a.assignees if x.user_id == from_user_id), None)
    if old is None or old.status == AssignmentStatus.REASSIGNED:
        raise NotFound("That person is not on this task")
    if old.status in assignment_service.DONE:
        raise Conflict("Their part is already approved; nothing to reassign")
    if from_user_id == to_user_id:
        raise ValidationFailed("Choose a different person")
    [new_person] = assignment_service._validate_artists(db, actor, [to_user_id])
    existing = next((x for x in a.assignees if x.user_id == to_user_id), None)
    if existing and existing.status != AssignmentStatus.REASSIGNED:
        raise Conflict(f"{new_person.full_name} is already on this task")

    has_work = db.scalar(select(func.count(Submission.id)).where(Submission.assignee_id == old.id))
    if has_work:
        old.status = AssignmentStatus.REASSIGNED
        old.completed_at = utcnow()  # no longer counts as active or late work
    else:
        a.assignees.remove(old)
    if existing:  # they had it before and it was moved away from them: give it back
        existing.status, existing.completed_at = AssignmentStatus.ASSIGNED, None
    else:
        a.assignees.append(AssignmentAssignee(user_id=new_person.id))
    db.flush()
    assignment_service.recompute_status(a)
    audit.record(db, actor_id=actor.id, action="assignment.reassign", entity_type="assignment", entity_id=a.id,
                 after={"from_user_id": from_user_id, "to_user_id": to_user_id, "note": note}, ip=ip)
    notification_service.assignment_created(db, a, new_person)
    old_user = db.get(User, from_user_id)
    notification_service.notify(
        db, user_id=from_user_id, event_type="assignment_reassigned", title=f"Task moved: {a.title}",
        message=f"{actor.full_name} gave this task to {new_person.full_name}." + (f" {note}" if note else ""),
        link=None, entity_type="assignment", entity_id=a.id,
        dedupe_key=f"assignment:{a.id}:reassigned:{from_user_id}:{to_user_id}:{int(utcnow().timestamp())}")
    db.commit()
    db.refresh(a)
    return a


# ---------------- feedback phrases (studio list, admin-managed) ----------------

def ensure_default_phrases(db: Session) -> None:
    if db.scalar(select(func.count(FeedbackPhrase.id))) == 0:
        for i, text in enumerate(DEFAULT_PHRASES):
            db.add(FeedbackPhrase(text=text, position=i))
        db.flush()


def list_phrases(db: Session) -> list[FeedbackPhrase]:
    return list(db.scalars(select(FeedbackPhrase).order_by(FeedbackPhrase.position, FeedbackPhrase.id)))


def add_phrase(db: Session, actor: User, text: str, ip: str | None) -> FeedbackPhrase:
    text = text.strip()
    if db.scalar(select(FeedbackPhrase.id).where(func.lower(FeedbackPhrase.text) == text.lower())):
        raise Conflict("That phrase already exists")
    pos = (db.scalar(select(func.max(FeedbackPhrase.position))) or 0) + 1
    p = FeedbackPhrase(text=text, position=pos)
    db.add(p)
    db.flush()
    audit.record(db, actor_id=actor.id, action="feedback_phrase.create", entity_type="feedback_phrase",
                 entity_id=p.id, after={"text": text}, ip=ip)
    db.commit()
    return p


def delete_phrase(db: Session, actor: User, phrase_id: int, ip: str | None) -> None:
    p = db.get(FeedbackPhrase, phrase_id)
    if not p:
        raise NotFound("Phrase not found")
    audit.record(db, actor_id=actor.id, action="feedback_phrase.delete", entity_type="feedback_phrase",
                 entity_id=p.id, before={"text": p.text}, ip=ip)
    db.delete(p)
    db.commit()


# ---------------- weekly targets ----------------

def week_bounds(d: date | None = None) -> tuple[date, date]:
    """Monday..Sunday of the studio week containing ``d``."""
    d = d or studio_today()
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def approved_this_week(db: Session, user_ids: list[int], d: date | None = None) -> dict[int, int]:
    start, end = week_bounds(d)
    lo, hi = studio_day_bounds_utc(start)[0], studio_day_bounds_utc(end)[1]
    rows = db.execute(
        select(Submission.artist_id, func.count(SubmissionDeliverable.id))
        .join(Submission, SubmissionDeliverable.submission_id == Submission.id)
        .where(Submission.artist_id.in_(user_ids or [-1]), SubmissionDeliverable.scene_id.is_not(None),
               SubmissionDeliverable.status == DeliverableStatus.APPROVED,
               SubmissionDeliverable.approved_at >= lo, SubmissionDeliverable.approved_at <= hi)
        .group_by(Submission.artist_id))
    out = {i: 0 for i in user_ids}
    out.update({uid: n for uid, n in rows})
    return out


def targets_for(db: Session, user_ids: list[int]) -> dict[int, int]:
    return {t.user_id: t.scenes_per_week for t in db.scalars(
        select(WeeklyTarget).where(WeeklyTarget.user_id.in_(user_ids or [-1])))}


def set_target(db: Session, actor: User, user_id: int, scenes_per_week: int | None, ip: str | None) -> dict:
    person = db.get(User, user_id)
    if not person or person.deleted_at is not None:
        raise NotFound("Person not found")
    _ensure_manages(db, actor, person)
    t = db.get(WeeklyTarget, user_id)
    if scenes_per_week is None:
        if t:
            db.delete(t)
    elif t:
        t.scenes_per_week, t.set_by_id = scenes_per_week, actor.id
    else:
        db.add(WeeklyTarget(user_id=user_id, scenes_per_week=scenes_per_week, set_by_id=actor.id))
    audit.record(db, actor_id=actor.id, action="target.set", entity_type="user", entity_id=user_id,
                 after={"user_id": user_id, "scenes_per_week": scenes_per_week}, ip=ip)
    db.commit()
    return my_target(db, person)


def my_target(db: Session, person: User) -> dict:
    start, end = week_bounds()
    return {"week_start": start, "week_end": end, "target": targets_for(db, [person.id]).get(person.id),
            "approved": approved_this_week(db, [person.id])[person.id]}


def average_ratings(db: Session, user_ids: list[int]) -> dict[int, float]:
    rows = db.execute(
        select(Submission.artist_id, func.avg(Review.rating))
        .join(Review, Review.submission_id == Submission.id)
        .where(Submission.artist_id.in_(user_ids or [-1]), Review.rating.is_not(None))
        .group_by(Submission.artist_id))
    return {uid: round(float(avg), 1) for uid, avg in rows if avg is not None}


# ---------------- the lead's "Today" list ----------------

def _open_slots(db: Session, actor: User):
    q = (select(Assignment, AssignmentAssignee).join(AssignmentAssignee, AssignmentAssignee.assignment_id == Assignment.id)
         .where(Assignment.deleted_at.is_(None), AssignmentAssignee.status.in_(OPEN)))
    ids = _people_ids(db, actor)
    if ids is not None:
        q = q.where(AssignmentAssignee.user_id.in_(ids or {-1}))
    return db.execute(q.order_by(Assignment.deadline)).all()


def today(db: Session, actor: User) -> dict:
    d = studio_today()
    now = utcnow()
    start, end = studio_day_bounds_utc(d)
    ids = _people_ids(db, actor)

    pending = select(Submission).where(Submission.status == SubmissionStatus.PENDING_REVIEW)
    if ids is not None:
        pending = pending.where(Submission.artist_id.in_(ids or {-1}))
    pending_rows = list(db.scalars(pending.order_by(Submission.submitted_at).limit(50)))
    reviews = [{"submission_id": s.id, "person": s.artist.full_name, "assignment": s.assignment.title,
                "submitted_at": s.submitted_at, "late": ensure_utc(s.submitted_at) > ensure_utc(s.assignment.deadline)}
               for s in pending_rows]

    leave = [x.model_dump() for x in artist_service.list_leave(db, actor, status=LeaveStatus.PENDING)][:50]

    overdue, due_today = [], []
    for a, x in _open_slots(db, actor):
        item = {"assignment_id": a.id, "title": a.title, "person": x.user.full_name, "person_id": x.user_id,
                "deadline": a.deadline, "status": x.status.value}
        if ensure_utc(a.deadline) < now and x.status != AssignmentStatus.SUBMITTED:
            overdue.append(item)
        elif start <= ensure_utc(a.deadline) <= end:
            due_today.append(item)

    absent = [{"person_id": r.user_id, "person": r.full_name, "status": r.status}
              for r in attendance_service.roster(db, actor, d) if r.status in ("absent", "not_checked_in")]
    return {"date": d, "is_work_day": is_work_day(d), "reviews": reviews, "leave_requests": leave,
            "overdue": overdue[:50], "due_today": due_today[:50], "absent": absent,
            "counts": {"reviews": len(pending_rows), "leave_requests": len(leave), "overdue": len(overdue),
                       "due_today": len(due_today), "absent": len(absent)}}


# ---------------- 12:00 attendance summaries (background job) ----------------

def _attendance_line(rows) -> str:
    present = sum(r.status in ("present", "half_day") for r in rows)
    absent = [r.full_name for r in rows if r.status == "absent"]
    leave = sum(r.status == "leave" for r in rows)
    line = f"{present} present, {len(absent)} absent" + (f", {leave} on leave" if leave else "")
    if absent:
        line += ": " + ", ".join(absent[:10]) + (f" and {len(absent) - 10} more" if len(absent) > 10 else "")
    return line


def send_noon_summaries(db: Session) -> int:
    """After the check-in cutoff on a work day: each team lead gets their team's present/absent list, and
    each admin gets the studio-wide numbers per team. Once per day each."""
    from app.core.timeutils import studio_hour  # noqa: PLC0415
    d = studio_today()
    if not is_work_day(d) or utcnow() < studio_hour(d, get_settings().staff_checkin_cutoff_hour):
        return 0
    sent = 0
    users = db.scalars(select(User).where(User.is_active.is_(True), User.deleted_at.is_(None))).all()
    for u in users:
        if u.role_name == RoleName.TEAM_LEAD:
            rows = [r for r in attendance_service.roster(db, u, d) if r.user_id != u.id]
            if not rows:
                continue
            title, msg, link = f"Attendance {d:%d %b}", _attendance_line(rows), "/lead/attendance"
        elif u.role_name == RoleName.ADMIN:
            rows = attendance_service.roster(db, u, d)
            if not rows:
                continue
            by_team: dict[str, list] = {}
            for r in rows:
                by_team.setdefault(r.team_name or "No team", []).append(r)
            present = sum(r.status in ("present", "half_day") for r in rows)
            absent = sum(r.status == "absent" for r in rows)
            leave = sum(r.status == "leave" for r in rows)
            msg = f"Studio: {present} present, {absent} absent, {leave} on leave. " + " · ".join(
                f"{team}: {sum(r.status in ('present', 'half_day') for r in rs)}/{len(rs)}"
                for team, rs in sorted(by_team.items()))
            title, link = f"Studio attendance {d:%d %b}", "/admin"
        else:
            continue
        if notification_service.notify(db, user_id=u.id, event_type="noon_attendance_summary", title=title,
                                       message=msg, link=link, entity_type="user", entity_id=u.id,
                                       dedupe_key=f"user:{u.id}:noon:{d.isoformat()}"):
            sent += 1
    db.commit()
    return sent


# ---------------- evening summary (background job) ----------------

def send_evening_summaries(db: Session) -> int:
    """At the 6:40 PM EOD review window (20 mins before the 7:00 PM EOD deadline on work days),
    each active team lead gets one in-app summary of their people's day to review, check Drive deliverables,
    and prepare their report for the admin."""
    d = studio_today()
    if not is_work_day(d) or utcnow() < studio_eod(d) - timedelta(minutes=20):
        return 0
    sent = 0
    leads = db.scalars(select(User).join(User.role).where(
        User.is_active.is_(True), User.deleted_at.is_(None))).all()
    for lead in [u for u in leads if u.role_name == RoleName.TEAM_LEAD]:
        ids = _people_ids(db, lead)
        if not ids:
            continue
        start, end = studio_day_bounds_utc(d)
        submitted = db.scalar(select(func.count(Submission.id)).where(
            Submission.artist_id.in_(ids), Submission.submitted_at >= start, Submission.submitted_at <= end)) or 0
        approved = db.scalar(select(func.count(SubmissionDeliverable.id)).join(Submission).where(
            Submission.artist_id.in_(ids), SubmissionDeliverable.status == DeliverableStatus.APPROVED,
            SubmissionDeliverable.scene_id.is_not(None),
            SubmissionDeliverable.approved_at >= start, SubmissionDeliverable.approved_at <= end)) or 0
        t = today(db, lead)
        late = sorted({o["person"] for o in t["overdue"]})
        msg = (f"6:40 PM EOD Review Window: {submitted} submission(s) today, {approved} scene(s) approved, "
               f"{t['counts']['reviews']} waiting for review, {t['counts']['overdue']} overdue")
        if late:
            msg += ": " + ", ".join(late[:8]) + (f" and {len(late) - 8} more" if len(late) > 8 else "")
        report_id = _ensure_draft(db, lead, d)
        if notification_service.notify(
                db, user_id=lead.id, event_type="evening_summary",
                title=f"EOD Review Open (6:40 PM) — {d:%d %b}",
                message=msg + ". Check Drive playblasts, write remarks, and submit to Admin by 7:00 PM.",
                link=f"/lead/reports/{report_id}" if report_id else "/lead/reports",
                entity_type="daily_report" if report_id else "user", entity_id=report_id or lead.id,
                dedupe_key=f"lead:{lead.id}:evening:{d.isoformat()}"):
            sent += 1
    db.commit()
    return sent


def _ensure_draft(db: Session, lead: User, d: date) -> int | None:
    """Today's automatic draft for this lead (created once)."""
    from app.models import DailyReport  # noqa: PLC0415
    from app.schemas.reports import ReportGenerate  # noqa: PLC0415
    from app.services import report_service  # noqa: PLC0415 (report_service imports notification code)
    existing = db.scalar(select(DailyReport.id).where(DailyReport.report_date == d,
                                                      DailyReport.created_by_id == lead.id,
                                                      DailyReport.auto_generated.is_(True)))
    if existing:
        return existing
    try:
        r = report_service.generate(db, lead, ReportGenerate(report_date=d, use_ai=bool(get_settings().anthropic_api_key)),
                                    ip=None, auto=True)
        return r.id
    except Exception:  # a report problem must not stop everyone else's summary
        db.rollback()
        return None


def send_report_reminders(db: Session) -> int:
    """At 7:00 PM EOD deadline on work days: leads who haven't sent today's report to the admin
    trigger the 7:00 PM safety net auto-dispatch so production metrics & Drive links reach Admin immediately."""
    from app.models import DailyReport  # noqa: PLC0415
    from app.services import report_service  # noqa: PLC0415
    d = studio_today()
    if not is_work_day(d) or utcnow() < studio_eod(d):
        return 0
    sent = 0
    for lead in db.scalars(select(User).where(User.is_active.is_(True), User.deleted_at.is_(None))).all():
        if lead.role_name != RoleName.TEAM_LEAD or not _people_ids(db, lead):
            continue
        reports = db.scalars(select(DailyReport).where(DailyReport.report_date == d,
                                                       DailyReport.created_by_id == lead.id)).all()
        if any(r.submitted_at for r in reports):
            continue
        draft = next((r for r in reports if r.auto_generated), None)
        if not draft and reports:
            draft = reports[0]
        if not draft:
            draft_id = _ensure_draft(db, lead, d)
            if draft_id:
                draft = db.get(DailyReport, draft_id)
        if draft and draft.submitted_at is None:
            note = "[Auto-dispatched at 7:00 PM EOD safety net]"
            if draft.issues:
                note = f"{draft.issues}\n{note}"
            try:
                report_service.submit_to_admin(db, lead, draft.id, issues=note, ip=None)
                notification_service.notify(
                    db, user_id=lead.id, event_type="report_reminder",
                    title="Reminder: Report dispatched to Admin (7:00 PM safety net)",
                    message="Your team's EOD report was automatically dispatched to the admin.",
                    link=f"/lead/reports/{draft.id}", entity_type="daily_report", entity_id=draft.id,
                    dedupe_key=f"lead:{lead.id}:auto_dispatch:{d.isoformat()}")
                sent += 1
            except Exception:
                db.rollback()
    db.commit()
    return sent
