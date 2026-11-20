"""End-of-day reports: generate (deterministic metrics + AI narrative) -> edit -> approve -> send.

Sending is a separate, explicit action by an authorized team lead or admin. It signs an
approval token over (report, approver, approval time, exact recipients) that the Gmail MCP
server verifies before sending the report's stored content. Nothing an AI produces can send.
"""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import approval
from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.timeutils import studio_today, utcnow
from app.models import (
    AuthorizedRecipient, DailyReport, EmailLog, EmailStatus, ReportStatus, Role, RoleName, Team, User,
)
from app.schemas.reports import ReportGenerate, ReportListItem, ReportOut, ReportUpdate
from app.services import audit, email_service, notification_service, report_ai, report_metrics, scope


# ---------------- rendering ----------------

def _fmt_date(d: str) -> str:
    return date.fromisoformat(d).strftime("%a, %d %b %Y")


def render_body(m: dict, narrative: dict, ai_status: str) -> str:
    """Plain-text email. Narrative from Claude (or template); every table is computed data."""
    t = m["totals"]
    lines = [f"{get_settings().app_name} — Daily Production Report", f"Date: {_fmt_date(m['report_date'])} ({m['as_of']})"]
    if m["scope"]["teams"]:
        lines.append("Team: " + ", ".join(m["scope"]["teams"]))
    if m["scope"]["filters"]:
        lines.append("Filters: " + ", ".join(f"{k}: {v}" for k, v in m["scope"]["filters"].items()))
    lines += ["", "SUMMARY", narrative.get("summary", "")]  # mail clients wrap plain text themselves
    for title, key in (("HIGHLIGHTS", "highlights"), ("CONCERNS", "concerns")):
        if narrative.get(key):
            lines += ["", title, *[f"  • {x}" for x in narrative[key]]]

    lines += ["", "ATTENDANCE",
              f"  Team members: {t['team_members']} · Present: {t['present']} (half day: {t['half_day']}) · "
              f"Leave: {t['on_leave']} · Absent: {t['absent']}" + (f" · Not checked in: {t['not_checked_in']}" if t["not_checked_in"] else "")]
    for status, names in m["attendance_by_status"].items():
        if names and status != "present":
            lines.append(f"  {status.replace('_', ' ').title()}: {', '.join(names)}")

    lines += ["", "PRODUCTION",
              f"  Assignments distributed: {t['assignments_distributed']} · Active: {t['assignments_active']} · "
              f"Projects worked on: {t['projects_worked_on']}",
              f"  Scenes assigned: {t['scenes_assigned']} · Submitted: {t['scenes_submitted']} · "
              f"Approved: {t['scenes_approved']} · Rejected: {t['scenes_rejected']}",
              f"  Pending reviews: {t['pending_reviews']} · Incomplete (due today): {t['incomplete_assignments']} · "
              f"Delayed: {t['delayed_assignments']}"]
    if m["projects"]:
        lines += ["", "PROJECTS"]
        for p in m["projects"]:
            lines.append(f"  {p['code']} {p['title']}: active {p['assignments_active']}, new {p['assignments_distributed']}, "
                         f"submitted {p['scenes_submitted']}, approved {p['scenes_approved']}, rejected {p['scenes_rejected']}")

    lines += ["", "ARTIST PERFORMANCE",
              f"  {'Artist':<32}{'Attend.':<16}{'Active':>7}{'Subm.':>7}{'Appr.':>7}{'Rej.':>6}{'Pend.':>7}{'Late':>6}"]
    for a in m["artists"]:
        show_time = get_settings().show_checkin_times and a.get("check_in")
        att = a["attendance"].replace("_", " ") + (f" {a['check_in']}" if show_time else "")
        lines.append(f"  {a['name'][:31]:<32}{att[:15]:<16}{a['active_assignments']:>7}{a['scenes_submitted']:>7}"
                     f"{a['scenes_approved']:>7}{a['scenes_rejected']:>6}{a['pending_reviews']:>7}{a['delayed_assignments']:>6}")

    notes = [a for a in m["artists"] if a.get("work_note")]
    if notes:
        lines += ["", "NOTES FROM THE TEAM (what I did / blockers)", *[f"  • {a['name']}: {a['work_note']}" for a in notes]]

    for title, key in (("DELAYED ASSIGNMENTS", "delayed_assignments"), ("INCOMPLETE (DUE TODAY)", "incomplete_assignments")):
        if m[key]:
            lines += ["", title]
            lines += [f"  • {r['project']} · {r['title']} — {r['artist']} (due {r['deadline']}, {r['status'].replace('_', ' ')})"
                      for r in m[key]]
    if m["remarks"]:
        lines += ["", "REMARKS", *[f"  • {r}" for r in m["remarks"]]]

    source = {"generated": f"Narrative drafted by Claude ({get_settings().anthropic_model}) from the figures above",
              }.get(ai_status, "Narrative generated from a template")
    lines += ["", "—", f"All figures are computed from {get_settings().app_name} records. {source}; reviewed and approved by the team lead before sending."]
    return "\n".join(lines)


def _subject(m: dict) -> str:
    scope_label = ", ".join(m["scope"]["teams"]) or "Studio"
    return f"Daily production report — {_fmt_date(m['report_date'])} · {scope_label}"


# ---------------- access ----------------

def _query(db: Session, user: User):
    q = select(DailyReport)
    if scope.is_admin(user):
        return q
    if scope.is_lead(user):
        teams = scope.lead_team_ids(db, user)
        return q.where((DailyReport.created_by_id == user.id) | DailyReport.team_id.in_(teams or {-1}))
    return q.where(DailyReport.id == -1)


def get(db: Session, user: User, report_id: int) -> DailyReport:
    r = db.scalar(_query(db, user).where(DailyReport.id == report_id))
    if not r:
        raise NotFound("Report not found")
    return r


def list_for(db: Session, user: User, status: ReportStatus | None = None, limit: int = 100) -> list[DailyReport]:
    q = _query(db, user)
    if status:
        q = q.where(DailyReport.status == status)
    return list(db.scalars(q.order_by(DailyReport.report_date.desc(), DailyReport.id.desc()).limit(limit)))


def _names(db: Session, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids or {-1}))).all())


def to_list_item(db: Session, r: DailyReport) -> ReportListItem:
    n = _names(db, {r.created_by_id, r.sent_by_id, r.submitted_by_id, r.admin_commented_by_id})
    return ReportListItem(id=r.id, report_date=r.report_date, status=r.status, subject=r.subject, recipients=r.recipients,
                          ai_status=r.ai_status, created_by_name=n.get(r.created_by_id, "—"), created_at=r.created_at,
                          approved_at=r.approved_at, sent_at=r.sent_at, sent_by_name=n.get(r.sent_by_id),
                          delivery_status=r.delivery_status, filters=r.filters, auto_generated=r.auto_generated,
                          issues=r.issues, submitted_at=r.submitted_at, submitted_by_name=n.get(r.submitted_by_id),
                          admin_comment=r.admin_comment, admin_commented_at=r.admin_commented_at,
                          admin_commented_by_name=n.get(r.admin_commented_by_id))


def to_out(db: Session, r: DailyReport) -> ReportOut:
    n = _names(db, {r.created_by_id, r.sent_by_id, r.approved_by_id})
    err = db.scalar(select(EmailLog.error).where(EmailLog.entity_type == "daily_report", EmailLog.entity_id == r.id)
                    .order_by(EmailLog.id.desc()).limit(1)) if r.status == ReportStatus.FAILED else None
    base = to_list_item(db, r).model_dump()
    return ReportOut(**base, metrics=r.metrics, narrative=r.narrative, ai_note=r.ai_note, body=r.body,
                     approved_by_name=n.get(r.approved_by_id), gmail_message_id=r.gmail_message_id,
                     gmail_draft_id=r.gmail_draft_id, email_error=err)


# ---------------- generate ----------------

def default_recipients(db: Session) -> list[str]:
    return list(db.scalars(select(AuthorizedRecipient.email).where(AuthorizedRecipient.is_active.is_(True))
                           .order_by(AuthorizedRecipient.email)))


def generate(db: Session, actor: User, data: ReportGenerate, ip: str | None, *, auto: bool = False) -> DailyReport:
    d = data.report_date or studio_today()
    if d > studio_today():
        raise ValidationFailed("Reports cannot be generated for future dates")
    team_id = data.team_id if scope.is_admin(actor) else None
    metrics = report_metrics.compute(db, actor, d, project_id=data.project_id, episode_id=data.episode_id,
                                     artist_id=data.artist_id, team_id=team_id)
    result = report_ai.generate(metrics, use_ai=data.use_ai)
    narrative = result.narrative.model_dump()
    lead_teams = scope.lead_team_ids(db, actor)
    r = DailyReport(
        report_date=d, team_id=team_id or (actor.team_id if actor.team_id in lead_teams else None),
        filters={k: v for k, v in data.model_dump(exclude={"use_ai", "report_date"}).items() if v},
        metrics=metrics, narrative=narrative, ai_summary=narrative["summary"],
        ai_generated=result.status == "generated", ai_status=result.status, ai_note=result.note,
        subject=_subject(metrics), body=render_body(metrics, narrative, result.status),
        status=ReportStatus.DRAFT, recipients=default_recipients(db), created_by_id=actor.id, auto_generated=auto,
    )
    db.add(r)
    db.flush()
    audit.record(db, actor_id=actor.id, action="report.generate", entity_type="daily_report", entity_id=r.id,
                 after={"report_date": d, "filters": r.filters, "ai_status": result.status}, ip=ip)
    if not auto:  # the 7 PM job sends its own "ready to send" notification
        notification_service.daily_report_generated(db, r.id, actor.id, d.isoformat())
    db.commit()
    db.refresh(r)
    return r


# ---------------- in-app: lead -> admin ----------------

def submit_to_admin(db: Session, actor: User, report_id: int, issues: str | None, ip: str | None) -> DailyReport:
    """The lead adds issues/remarks and sends the report to the admins (in the app; no email needed)."""
    r = get(db, actor, report_id)
    if r.submitted_at is not None:
        raise Conflict("This report was already sent to the admin")
    r.issues = (issues or "").strip() or None
    r.submitted_at, r.submitted_by_id = utcnow(), actor.id
    audit.record(db, actor_id=actor.id, action="report.submit", entity_type="daily_report", entity_id=r.id,
                 after={"issues": r.issues}, ip=ip)
    admins = db.scalars(select(User.id).join(Role).where(
        Role.name == RoleName.ADMIN, User.is_active.is_(True), User.deleted_at.is_(None), User.id != actor.id))
    for admin_id in admins:
        notification_service.notify(
            db, user_id=admin_id, event_type="report_submitted",
            title=f"Day report from {actor.full_name}: {r.report_date:%d %b}",
            message=(r.issues[:200] if r.issues else "No issues reported."), link=f"/admin/reports/{r.id}",
            entity_type="daily_report", entity_id=r.id, dedupe_key=f"report:{r.id}:submitted:{admin_id}")
    db.commit()
    db.refresh(r)
    return r


def comment(db: Session, actor: User, report_id: int, text: str, ip: str | None) -> DailyReport:
    """An admin replies on a lead's report; the lead is notified."""
    r = get(db, actor, report_id)
    r.admin_comment = text.strip()
    r.admin_commented_at, r.admin_commented_by_id = utcnow(), actor.id
    audit.record(db, actor_id=actor.id, action="report.comment", entity_type="daily_report", entity_id=r.id,
                 after={"comment": r.admin_comment}, ip=ip)
    notification_service.notify(
        db, user_id=r.created_by_id, event_type="report_comment", title=f"Admin replied on {r.report_date:%d %b}",
        message=r.admin_comment[:200], link=f"/lead/reports/{r.id}", entity_type="daily_report", entity_id=r.id,
        dedupe_key=f"report:{r.id}:comment:{int(r.admin_commented_at.timestamp())}")
    db.commit()
    db.refresh(r)
    return r


def team_status(db: Session, report_date: date) -> list[dict]:
    """Admin view: for each active team lead, today's report and whether it was sent."""
    leads = db.scalars(select(User).join(Role).where(
        Role.name == RoleName.TEAM_LEAD, User.is_active.is_(True), User.deleted_at.is_(None)).order_by(User.full_name))
    out = []
    for lead in leads:
        teams = sorted(t.name for t in db.scalars(select(Team).where(Team.lead_id == lead.id, Team.deleted_at.is_(None))))
        r = db.scalar(select(DailyReport).where(DailyReport.report_date == report_date,
                                                DailyReport.created_by_id == lead.id)
                      .order_by(DailyReport.submitted_at.is_(None), DailyReport.id.desc()).limit(1))
        out.append({"lead_id": lead.id, "lead": lead.full_name, "teams": teams,
                    "report_id": r.id if r else None, "submitted_at": r.submitted_at if r else None,
                    "issues": r.issues if r else None})
    return out


# ---------------- edit / approve / revoke ----------------

def _authorized(db: Session, emails: list[str]) -> list[str]:
    cleaned = sorted({e.strip().lower() for e in emails})
    allowed = set(default_recipients(db))
    bad = [e for e in cleaned if e not in allowed]
    if bad:
        raise ValidationFailed("Not an authorized report recipient: " + ", ".join(bad))
    if not cleaned:
        raise ValidationFailed("Select at least one recipient")
    return cleaned


def update(db: Session, actor: User, report_id: int, data: ReportUpdate, ip: str | None) -> DailyReport:
    r = get(db, actor, report_id)
    if r.status != ReportStatus.DRAFT:
        raise Conflict("Only draft reports can be edited. Revoke the approval first.")
    before = {"subject": r.subject, "body_len": len(r.body), "recipients": r.recipients}
    if data.subject is not None:
        r.subject = data.subject.strip()
    if data.body is not None:
        r.body = data.body
    if data.recipients is not None:
        r.recipients = _authorized(db, [str(e) for e in data.recipients])
    audit.record(db, actor_id=actor.id, action="report.edit", entity_type="daily_report", entity_id=r.id,
                 before=before, after={"subject": r.subject, "body_len": len(r.body), "recipients": r.recipients}, ip=ip)
    db.commit()
    return r


def approve(db: Session, actor: User, report_id: int, recipients: list[str], ip: str | None) -> DailyReport:
    r = get(db, actor, report_id)
    if r.status != ReportStatus.DRAFT:
        raise Conflict(f"Report is already {r.status.value}")
    r.recipients = _authorized(db, recipients)
    r.status = ReportStatus.APPROVED
    r.approved_by_id = actor.id
    r.approved_at = utcnow().replace(microsecond=0)
    # Bind the approval to exactly these recipients now; any later change invalidates it at the MCP server.
    r.approval_token = approval.sign(get_settings().email_approval_secret, r.id, actor.id, r.approved_at, r.recipients)
    audit.record(db, actor_id=actor.id, action="report.approve", entity_type="daily_report", entity_id=r.id,
                 after={"recipients": r.recipients, "subject": r.subject}, ip=ip)
    db.commit()
    return r


def revoke(db: Session, actor: User, report_id: int, ip: str | None) -> DailyReport:
    r = get(db, actor, report_id)
    if r.status not in (ReportStatus.APPROVED, ReportStatus.FAILED):
        raise Conflict("Only approved (unsent) reports can be returned to draft")
    r.status = ReportStatus.DRAFT
    r.approved_by_id = r.approved_at = r.approval_token = None
    audit.record(db, actor_id=actor.id, action="report.revoke", entity_type="daily_report", entity_id=r.id, ip=ip)
    db.commit()
    return r


# ---------------- send ----------------

def _require_email() -> None:
    if not get_settings().email_enabled:
        raise Conflict("Email is turned off (EMAIL_ENABLED=false). The report is saved and can be copied.")


async def send(db: Session, actor: User, report_id: int, ip: str | None) -> DailyReport:
    """Explicit, authorized send of an approved report through the Gmail MCP server."""
    _require_email()
    r = get(db, actor, report_id)
    if r.status == ReportStatus.SENT:
        raise Conflict("This report has already been sent")
    if r.status not in (ReportStatus.APPROVED, ReportStatus.FAILED) or not r.approved_at or not r.approval_token:
        raise Conflict("Approve the report before sending it")
    token = r.approval_token  # issued at approval time — never re-signed at send time
    key = f"report:{r.id}:send:{token[:24]}"  # exactly one delivery per distinct approval
    log = db.scalar(select(EmailLog).where(EmailLog.idempotency_key == key))
    if log is None:
        log = email_service.enqueue(
            db, tool="send_daily_report", idempotency_key=key,
            args={"report_id": r.id, "authorized_recipients": r.recipients, "approval_reference": token},
            recipients=r.recipients, subject=r.subject, preview=r.body, entity_type="daily_report", entity_id=r.id,
            triggered_by_id=actor.id,
        )
    elif log.status == EmailStatus.FAILED:
        log.attempts, log.next_attempt_at = 0, utcnow()
    audit.record(db, actor_id=actor.id, action="report.send", entity_type="daily_report", entity_id=r.id,
                 after={"recipients": r.recipients}, ip=ip)
    db.commit()

    delivered = await email_service.deliver_now(log.id)
    db.refresh(r)
    r.sent_by_id = actor.id
    r.delivery_status = delivered.status.value
    if delivered.status == EmailStatus.SENT:
        r.status = ReportStatus.SENT
        r.sent_at = delivered.sent_at
        r.gmail_message_id = delivered.provider_message_id
    elif delivered.status in (EmailStatus.FAILED, EmailStatus.BLOCKED):
        r.status = ReportStatus.FAILED
    db.commit()
    db.refresh(r)
    return r


async def create_gmail_draft(db: Session, actor: User, report_id: int, ip: str | None) -> DailyReport:
    """Optional: put the current text in the sender's Gmail drafts for a final look. Never sends."""
    _require_email()
    r = get(db, actor, report_id)
    if r.status == ReportStatus.SENT:
        raise Conflict("This report has already been sent")
    n = db.scalar(select(func.count(EmailLog.id)).where(EmailLog.entity_type == "daily_report_draft",
                                                        EmailLog.entity_id == r.id)) or 0
    log = email_service.enqueue(
        db, tool="create_daily_report_draft", idempotency_key=f"report:{r.id}:draft:{n + 1}",
        args={"report_date": r.report_date.isoformat(), "report_content": r.body, "subject": r.subject,
              "authorized_recipients": r.recipients},
        recipients=r.recipients, subject=r.subject, preview=r.body, entity_type="daily_report_draft", entity_id=r.id,
        triggered_by_id=actor.id,
    )
    db.commit()
    res = await email_service.deliver_now(log.id)
    if res.status != EmailStatus.DRAFTED:
        raise Conflict(f"Could not create the Gmail draft: {res.error or res.status.value}")
    r.gmail_draft_id = res.provider_message_id
    audit.record(db, actor_id=actor.id, action="report.gmail_draft", entity_type="daily_report", entity_id=r.id, ip=ip)
    db.commit()
    return r

