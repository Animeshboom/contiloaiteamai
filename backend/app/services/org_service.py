"""Employees, teams and authorized report recipients."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import hash_password
from app.core.timeutils import utcnow
from app.models import AuthorizedRecipient, Role, RoleName, Team, User
from app.schemas.org import (
    RecipientCreate, RecipientUpdate, TeamCreate, TeamOut, TeamUpdate, UserBrief, UserCreate, UserUpdate,
)
from app.services import audit, scope


def _user_snapshot(u: User) -> dict:
    return {"email": u.email, "full_name": u.full_name, "role": u.role_name.value, "team_id": u.team_id,
            "job_title": u.job_title, "is_active": u.is_active}


def _role(db: Session, name: RoleName) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if not role:
        raise ValidationFailed(f"Role {name.value} is not configured")
    return role


def _team(db: Session, team_id: int) -> Team:
    t = db.get(Team, team_id)
    if not t or t.deleted_at is not None:
        raise ValidationFailed("Team not found")
    return t


# ---------------- users ----------------

def list_users(db: Session, actor: User, *, role: RoleName | None = None, team_id: int | None = None,
               include_inactive: bool = False, search: str | None = None) -> list[User]:
    q = select(User).where(User.deleted_at.is_(None))
    ids = scope.visible_user_ids(db, actor)
    if ids is not None:
        q = q.where(User.id.in_(ids))
    if role:
        q = q.join(Role).where(Role.name == role)
    if team_id:
        q = q.where(User.team_id == team_id)
    if not include_inactive:
        q = q.where(User.is_active.is_(True))
    if search:
        like = f"%{search.lower()}%"
        q = q.where(func.lower(User.full_name).like(like) | func.lower(User.email).like(like))
    return list(db.scalars(q.order_by(User.full_name)))


def get_user(db: Session, actor: User, user_id: int) -> User:
    scope.ensure_can_view_user(db, actor, user_id)
    u = db.get(User, user_id)
    if not u or u.deleted_at is not None:
        raise NotFound("User not found")
    return u


def create_user(db: Session, actor: User, data: UserCreate, ip: str | None) -> User:
    email = data.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise Conflict("An account with this email already exists")
    if data.team_id:
        _team(db, data.team_id)
    u = User(
        email=email, full_name=data.full_name, role_id=_role(db, data.role).id, team_id=data.team_id,
        job_title=data.job_title, password_hash=hash_password(data.password),
    )
    db.add(u)
    db.flush()
    audit.record(db, actor_id=actor.id, action="user.create", entity_type="user", entity_id=u.id,
                 after=_user_snapshot(u), ip=ip)
    db.commit()
    db.refresh(u)
    return u


def update_user(db: Session, actor: User, user_id: int, data: UserUpdate, ip: str | None) -> User:
    u = get_user(db, actor, user_id)
    before = _user_snapshot(u)
    if data.full_name is not None:
        u.full_name = data.full_name
    if data.job_title is not None:
        u.job_title = data.job_title or None
    if data.clear_team:
        u.team_id = None
    elif data.team_id is not None:
        u.team_id = _team(db, data.team_id).id
    if data.role is not None and data.role != u.role_name:
        if u.id == actor.id:
            raise ValidationFailed("You cannot change your own role")
        if u.role_name == RoleName.TEAM_LEAD:
            # Demoting a lead: unlink them from teams they led.
            for t in db.scalars(select(Team).where(Team.lead_id == u.id)):
                t.lead_id = None
        u.role_id = _role(db, data.role).id
        u.token_version += 1  # force re-login with new permissions
    db.flush()
    db.refresh(u)
    audit.record(db, actor_id=actor.id, action="user.update", entity_type="user", entity_id=u.id,
                 before=before, after=_user_snapshot(u), ip=ip)
    db.commit()
    return u


def set_active(db: Session, actor: User, user_id: int, active: bool, ip: str | None) -> User:
    u = get_user(db, actor, user_id)
    if u.id == actor.id and not active:
        raise ValidationFailed("You cannot deactivate your own account")
    if u.is_active == active:
        return u
    u.is_active = active
    u.token_version += 1
    if not active:
        for t in db.scalars(select(Team).where(Team.lead_id == u.id)):
            t.lead_id = None
    audit.record(db, actor_id=actor.id, action="user.activate" if active else "user.deactivate",
                 entity_type="user", entity_id=u.id, ip=ip)
    db.commit()
    return u


def reset_password(db: Session, actor: User, user_id: int, new_password: str, ip: str | None) -> None:
    u = get_user(db, actor, user_id)
    u.password_hash = hash_password(new_password)
    u.token_version += 1
    audit.record(db, actor_id=actor.id, action="user.password_reset", entity_type="user", entity_id=u.id, ip=ip)
    db.commit()


# ---------------- teams ----------------

def _team_out(db: Session, t: Team) -> TeamOut:
    count = db.scalar(select(func.count(User.id)).where(
        User.team_id == t.id, User.is_active.is_(True), User.deleted_at.is_(None)))
    return TeamOut(id=t.id, name=t.name, department=t.department, description=t.description,
                   lead=UserBrief.model_validate(t.lead) if t.lead else None,
                   member_count=count or 0, created_at=t.created_at)


def list_teams(db: Session, actor: User) -> list[TeamOut]:
    q = select(Team).where(Team.deleted_at.is_(None)).order_by(Team.name)
    if not scope.is_admin(actor):
        q = q.where(Team.id.in_(scope.lead_team_ids(db, actor) or {-1}))
    return [_team_out(db, t) for t in db.scalars(q)]


def _set_lead(db: Session, team: Team, lead_id: int) -> None:
    lead = db.get(User, lead_id)
    if not lead or not lead.is_active or lead.role_name != RoleName.TEAM_LEAD:
        raise ValidationFailed("Team lead must be an active user with the Team Lead role")
    team.lead_id = lead.id
    lead.team_id = team.id


def create_team(db: Session, actor: User, data: TeamCreate, ip: str | None) -> TeamOut:
    if db.scalar(select(Team.id).where(func.lower(Team.name) == data.name.lower(), Team.deleted_at.is_(None))):
        raise Conflict("A team with this name already exists")
    t = Team(name=data.name, department=data.department, description=data.description)
    db.add(t)
    db.flush()
    if data.lead_id:
        _set_lead(db, t, data.lead_id)
    audit.record(db, actor_id=actor.id, action="team.create", entity_type="team", entity_id=t.id,
                 after={"name": t.name, "lead_id": t.lead_id}, ip=ip)
    db.commit()
    db.refresh(t)
    return _team_out(db, t)


def update_team(db: Session, actor: User, team_id: int, data: TeamUpdate, ip: str | None) -> TeamOut:
    t = db.get(Team, team_id)
    if not t or t.deleted_at is not None:
        raise NotFound("Team not found")
    before = {"name": t.name, "department": t.department, "lead_id": t.lead_id}
    for field in ("name", "department", "description"):
        val = getattr(data, field)
        if val is not None:
            setattr(t, field, val)
    if data.clear_lead:
        t.lead_id = None
    elif data.lead_id is not None:
        _set_lead(db, t, data.lead_id)
    audit.record(db, actor_id=actor.id, action="team.update", entity_type="team", entity_id=t.id, before=before,
                 after={"name": t.name, "department": t.department, "lead_id": t.lead_id}, ip=ip)
    db.commit()
    db.refresh(t)
    return _team_out(db, t)


def delete_team(db: Session, actor: User, team_id: int, ip: str | None) -> None:
    t = db.get(Team, team_id)
    if not t or t.deleted_at is not None:
        raise NotFound("Team not found")
    active_members = db.scalar(select(func.count(User.id)).where(User.team_id == t.id, User.is_active.is_(True)))
    if active_members:
        raise Conflict("Move or deactivate this team's members before deleting it")
    t.deleted_at = utcnow()
    t.lead_id = None
    audit.record(db, actor_id=actor.id, action="team.delete", entity_type="team", entity_id=t.id, ip=ip)
    db.commit()


# ---------------- authorized recipients ----------------

def list_recipients(db: Session, active_only: bool = False) -> list[AuthorizedRecipient]:
    q = select(AuthorizedRecipient).order_by(AuthorizedRecipient.name)
    if active_only:
        q = q.where(AuthorizedRecipient.is_active.is_(True))
    return list(db.scalars(q))


def create_recipient(db: Session, actor: User, data: RecipientCreate, ip: str | None) -> AuthorizedRecipient:
    email = data.email.lower()
    if db.scalar(select(AuthorizedRecipient.id).where(func.lower(AuthorizedRecipient.email) == email)):
        raise Conflict("This recipient is already configured")
    r = AuthorizedRecipient(email=email, name=data.name)
    db.add(r)
    db.flush()
    audit.record(db, actor_id=actor.id, action="recipient.create", entity_type="authorized_recipient",
                 entity_id=r.id, after={"email": email, "name": data.name}, ip=ip)
    db.commit()
    return r


def update_recipient(db: Session, actor: User, rid: int, data: RecipientUpdate, ip: str | None) -> AuthorizedRecipient:
    r = db.get(AuthorizedRecipient, rid)
    if not r:
        raise NotFound("Recipient not found")
    before = {"name": r.name, "is_active": r.is_active}
    if data.name is not None:
        r.name = data.name
    if data.is_active is not None:
        r.is_active = data.is_active
    audit.record(db, actor_id=actor.id, action="recipient.update", entity_type="authorized_recipient",
                 entity_id=r.id, before=before, after={"name": r.name, "is_active": r.is_active}, ip=ip)
    db.commit()
    return r
