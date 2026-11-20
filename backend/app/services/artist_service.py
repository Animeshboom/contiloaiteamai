"""Artist accounts (single + CSV import, passwords shown once) and leave requests.

Everyone who does the work is an artist; trainees are artists too. People without an email get an
Employee ID (e.g. EMP001) to sign in with.
- Admins create, import and reset artist accounts.
- Artists request leave (any range, past or future); their team lead or an admin approves or rejects.
  Approved days show as "leave" in attendance unless the artist checked in anyway.
"""
import csv
import io
import re
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.timeutils import utcnow
from app.models import LeaveRequest, LeaveStatus, Role, RoleName, Team, User
from app.schemas.artists import (
    EMPLOYEE_CODE, ArtistCreate, Credentials, ImportResult, ImportRowError, LeaveCreate, LeaveDecision, LeaveOut,
)
from app.schemas.auth import UserOut
from app.services import audit, identity, notification_service, org_service, scope, security_service

EMPLOYEE_CODE_RE = re.compile(EMPLOYEE_CODE)
MAX_IMPORT_ROWS = 1000
MAX_LEAVE_DAYS = 366


# ---------------- accounts ----------------

def _login_of(u: User) -> str:
    return u.employee_code or u.email


def next_employee_code(db: Session) -> str:
    """EMP001, EMP002, ... after the highest existing EMPnnn."""
    numbers = [int(c[3:]) for c in db.scalars(select(User.employee_code).where(User.employee_code.is_not(None)))
               if c and c.upper().startswith("EMP") and c[3:].isdigit()]
    return f"EMP{(max(numbers, default=0) + 1):03d}"


def create_artist(db: Session, actor: User, data: ArtistCreate, ip: str | None) -> Credentials:
    if not data.email and not data.employee_code:
        data = data.model_copy(update={"employee_code": next_employee_code(db)})
    if data.employee_code:
        code = data.employee_code.strip().upper()
        if db.scalar(select(User.id).where(func.upper(User.employee_code) == code)):
            raise Conflict(f"Employee ID {code} is already taken")
        email = identity.id_email(code)
    else:
        code, email = None, str(data.email).lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise Conflict("An account with this email already exists")
    if data.team_id:
        org_service._team(db, data.team_id)
    password = data.password or identity.generate_password()
    password_hash, auth_user_id = identity.create_login(email, password)
    u = User(email=email, full_name=data.full_name.strip(), role_id=org_service._role(db, RoleName.ARTIST).id,
             team_id=data.team_id, job_title=(data.job_title or "").strip() or "Artist", employee_code=code,
             phone=(data.phone or "").strip() or None, password_hash=password_hash, auth_user_id=auth_user_id)
    db.add(u)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflict("That email or Employee ID is already taken")
    audit.record(db, actor_id=actor.id, action="user.create", entity_type="user", entity_id=u.id,
                 after={"full_name": u.full_name, "login": _login_of(u), "team_id": u.team_id}, ip=ip)
    db.commit()
    db.refresh(u)
    return Credentials(user=UserOut.model_validate(u), login=_login_of(u), password=password)


def import_csv(db: Session, actor: User, content: bytes, ip: str | None,
               default_team_id: int | None = None) -> ImportResult:
    """CSV columns: name; optional email OR employee_id (neither = automatic EMPnnn), team (by name),
    job_title, phone, password."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationFailed("The file must be UTF-8 CSV")
    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip().lower().replace(" ", "_"): h for h in (reader.fieldnames or [])}
    pick = lambda *names: next((headers[n] for n in names if n in headers), None)  # noqa: E731
    cols = {
        "name": pick("name", "full_name"),
        "email": pick("email", "e-mail", "mail"),
        "code": pick("employee_id", "employee_code", "id", "login_id", "code"),
        "team": pick("team", "team_name"),
        "title": pick("job_title", "title", "role"),
        "phone": pick("phone", "mobile", "phone_number"),
        "password": pick("password"),
    }
    if not cols["name"]:
        raise ValidationFailed("The CSV needs a header row with at least a 'name' column")
    rows = list(reader)
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValidationFailed(f"At most {MAX_IMPORT_ROWS} people per file")
    if default_team_id is not None:
        org_service._team(db, default_team_id)

    teams = {t.name.lower(): t.id for t in db.scalars(select(Team).where(Team.deleted_at.is_(None)))}
    get = lambda row, key: (row.get(cols[key]) or "").strip() if cols[key] else ""  # noqa: E731
    created, errors, seen = [], [], set()
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name, email, code = get(row, "name"), get(row, "email").lower(), get(row, "code").upper()
        if not (name or email or code):
            continue  # blank line
        try:
            if len(name) < 2:
                raise ValidationFailed("Name is missing")
            if code and not EMPLOYEE_CODE_RE.match(code):
                raise ValidationFailed(f"'{code}' is not a valid Employee ID (letters, digits, - or _)")
            if email and code:
                raise ValidationFailed("Give either an email or an Employee ID, not both")
            key = email or code  # empty: an automatic Employee ID is assigned
            if key and key in seen:
                raise ValidationFailed(f"{key} appears twice in the file")
            team_name = get(row, "team")
            team_id = default_team_id
            if team_name:
                team_id = teams.get(team_name.lower())
                if team_id is None:
                    raise ValidationFailed(f"Team '{team_name}' does not exist")
            if key:
                seen.add(key)
            created.append(create_artist(db, actor, ArtistCreate(
                full_name=name, email=email or None, employee_code=code or None, team_id=team_id,
                job_title=get(row, "title") or None, phone=get(row, "phone") or None,
                password=get(row, "password") or None), ip))
        except (ValidationFailed, Conflict, NotFound) as e:
            db.rollback()
            errors.append(ImportRowError(row=i, message=e.message))
        except ValueError as e:  # pydantic validation of one row (bad email, phone, short password)
            db.rollback()
            msg = e.errors()[0]["msg"] if hasattr(e, "errors") else str(e)
            errors.append(ImportRowError(row=i, message=msg.replace("Value error, ", "")))
    if created:
        security_service.check_bulk(db, actor, "user.create", count=len(created))
        db.commit()
    return ImportResult(created=created, errors=errors)


def reset_password(db: Session, actor: User, user_id: int, ip: str | None) -> Credentials:
    u = org_service.get_user(db, actor, user_id)
    password = identity.generate_password()
    identity.set_password(u, password)
    u.token_version += 1
    u.active_session_id = None
    security_service.unlock(u)
    audit.record(db, actor_id=actor.id, action="user.password_reset", entity_type="user", entity_id=u.id, ip=ip)
    security_service.check_bulk(db, actor, "user.password_reset")
    db.commit()
    return Credentials(user=UserOut.model_validate(u), login=_login_of(u), password=password)


# ---------------- leave requests ----------------

def _span(start: date, end: date) -> str:
    return f"{start:%d %b}" if start == end else f"{start:%d %b} – {end:%d %b}"


def _leave_out(lr: LeaveRequest) -> LeaveOut:
    u = lr.user
    return LeaveOut(id=lr.id, user_id=u.id, person=u.full_name, team_id=u.team_id,
                    team_name=u.team.name if u.team else None, start=lr.start_day, end=lr.end_day,
                    days=(lr.end_day - lr.start_day).days + 1, reason=lr.reason, status=lr.status.value,
                    decided_by=lr.decided_by.full_name if lr.decided_by else None, decided_at=lr.decided_at,
                    decision_note=lr.decision_note, created_at=lr.created_at)


def leave_days(db: Session, user_ids: list[int], start: date, end: date) -> dict[int, set[date]]:
    """Approved leave per person between start and end (inclusive)."""
    out: dict[int, set[date]] = {i: set() for i in user_ids}
    for lr in db.scalars(select(LeaveRequest).where(
            LeaveRequest.user_id.in_(user_ids or [-1]), LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_day <= end, LeaveRequest.end_day >= start)):
        d = max(lr.start_day, start)
        while d <= min(lr.end_day, end):
            out.setdefault(lr.user_id, set()).add(d)
            d += timedelta(days=1)
    return out


def request_leave(db: Session, user: User, data: LeaveCreate, ip: str | None) -> LeaveOut:
    if data.end < data.start:
        raise ValidationFailed("The end date must be on or after the start date")
    if (data.end - data.start).days + 1 > MAX_LEAVE_DAYS:
        raise ValidationFailed("A leave request can cover at most one year")
    if db.scalar(select(LeaveRequest.id).where(
            LeaveRequest.user_id == user.id, LeaveRequest.status.in_([LeaveStatus.PENDING, LeaveStatus.APPROVED]),
            LeaveRequest.start_day <= data.end, LeaveRequest.end_day >= data.start)):
        raise Conflict("You already have a leave request covering some of these days")
    lr = LeaveRequest(user_id=user.id, start_day=data.start, end_day=data.end, reason=data.reason.strip())
    db.add(lr)
    db.flush()
    audit.record(db, actor_id=user.id, action="leave.request", entity_type="leave_request", entity_id=lr.id,
                 after={"start": data.start, "end": data.end}, ip=ip)
    # Artists' requests go to their team lead; a lead's own request (or a team without a lead) to the admins.
    lead = user.team.lead if user.team else None
    if user.role_name == RoleName.ARTIST and lead and lead.is_active and lead.id != user.id:
        approvers, link = [lead.id], "/lead/leave"
    else:
        approvers = list(db.scalars(select(User.id).join(Role).where(
            Role.name == RoleName.ADMIN, User.is_active.is_(True), User.deleted_at.is_(None))))
        link = "/admin/leave"
    for approver in approvers:
        notification_service.notify(
            db, user_id=approver, event_type="leave_requested", title=f"Leave request from {user.full_name}",
            message=f"{_span(data.start, data.end)}: {lr.reason}", link=link,
            entity_type="leave_request", entity_id=lr.id, dedupe_key=f"leave:{lr.id}:requested:{approver}")
    db.commit()
    db.refresh(lr)
    return _leave_out(lr)


def my_leave(db: Session, user: User) -> list[LeaveOut]:
    return [_leave_out(lr) for lr in db.scalars(select(LeaveRequest).where(LeaveRequest.user_id == user.id)
                                                 .order_by(LeaveRequest.start_day.desc(), LeaveRequest.id.desc()))]


def cancel_leave(db: Session, user: User, leave_id: int, ip: str | None) -> LeaveOut:
    lr = db.get(LeaveRequest, leave_id)
    if not lr or lr.user_id != user.id:
        raise NotFound("Leave request not found")
    if lr.status != LeaveStatus.PENDING:
        raise Conflict("Only a pending request can be cancelled")
    lr.status = LeaveStatus.CANCELLED
    audit.record(db, actor_id=user.id, action="leave.cancel", entity_type="leave_request", entity_id=lr.id, ip=ip)
    db.commit()
    return _leave_out(lr)


def list_leave(db: Session, actor: User, *, status: LeaveStatus | None = None,
               team_id: int | None = None) -> list[LeaveOut]:
    q = select(LeaveRequest).join(User, User.id == LeaveRequest.user_id).where(User.deleted_at.is_(None))
    ids = scope.visible_user_ids(db, actor)
    if ids is not None:
        q = q.where(LeaveRequest.user_id.in_(ids - {actor.id} or {-1}))
    if team_id:
        q = q.where(User.team_id == team_id)
    if status:
        q = q.where(LeaveRequest.status == status)
    q = q.order_by(LeaveRequest.created_at.asc() if status == LeaveStatus.PENDING else LeaveRequest.start_day.desc())
    return [_leave_out(lr) for lr in db.scalars(q.limit(500))]


def decide_leave(db: Session, actor: User, leave_id: int, data: LeaveDecision, ip: str | None) -> LeaveOut:
    lr = db.scalar(select(LeaveRequest).where(LeaveRequest.id == leave_id).with_for_update())
    if not lr:
        raise NotFound("Leave request not found")
    if lr.user_id == actor.id:
        raise Forbidden("You cannot decide your own leave request")
    if lr.user.role_name != RoleName.ARTIST and not scope.is_admin(actor):
        raise Forbidden("A team lead's leave is decided by an administrator")
    scope.ensure_can_manage_artist(db, actor, lr.user)
    if lr.status != LeaveStatus.PENDING:
        raise Conflict(f"This request is already {lr.status.value}")
    if data.decision == "rejected" and not (data.note or "").strip():
        raise ValidationFailed("Say why the request is rejected")
    lr.status = LeaveStatus(data.decision)
    lr.decided_by_id, lr.decided_at = actor.id, utcnow()
    lr.decision_note = (data.note or "").strip() or None
    audit.record(db, actor_id=actor.id, action=f"leave.{data.decision}", entity_type="leave_request",
                 entity_id=lr.id, after={"user_id": lr.user_id, "note": lr.decision_note}, ip=ip)
    notification_service.notify(
        db, user_id=lr.user_id, event_type=f"leave_{data.decision}",
        title=f"Leave {data.decision}: {_span(lr.start_day, lr.end_day)}",
        message=lr.decision_note or f"By {actor.full_name}",
        link="/lead/attendance" if lr.user.role_name == RoleName.TEAM_LEAD else "/artist/attendance",
        entity_type="leave_request", entity_id=lr.id, dedupe_key=f"leave:{lr.id}:{data.decision}")
    db.commit()
    db.refresh(lr)
    return _leave_out(lr)
