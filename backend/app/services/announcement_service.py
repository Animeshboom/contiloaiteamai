"""Announcements.

- Team leads post to teams they lead (at least one).
- Admins post to everyone (no teams chosen) or to chosen teams.
- Optional ``show_until`` date; people see active ones for their team or everyone, newest first (max 10),
  and get an in-app notification.
- The author or an admin can delete one.
"""
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.core.timeutils import studio_today
from app.models import Announcement, RoleName, Team, User, announcement_teams
from app.services import audit, notification_service, scope

HOME_LIMIT = 10


def _out(a: Announcement) -> dict:
    return {"id": a.id, "title": a.title, "body": a.body, "author": a.author.full_name if a.author else None,
            "author_id": a.author_id, "applies_to_all": a.applies_to_all,
            "teams": [{"id": t.id, "name": t.name} for t in a.teams], "show_until": a.show_until,
            "created_at": a.created_at, "active": a.show_until is None or a.show_until >= studio_today()}


def _active():
    return or_(Announcement.show_until.is_(None), Announcement.show_until >= studio_today())


def create(db: Session, actor: User, title: str, body: str, team_ids: list[int], show_until: date | None,
           ip: str | None) -> dict:
    if show_until and show_until < studio_today():
        raise ValidationFailed("'Show until' cannot be in the past")
    team_ids = list(dict.fromkeys(team_ids))
    if not scope.is_admin(actor):
        if not team_ids:
            raise ValidationFailed("Choose at least one of your teams")
        if not set(team_ids) <= scope.lead_team_ids(db, actor):
            raise Forbidden("You can only post to teams you lead")
    teams = []
    for tid in team_ids:
        t = db.get(Team, tid)
        if not t or t.deleted_at is not None:
            raise ValidationFailed(f"Team {tid} not found")
        teams.append(t)
    a = Announcement(title=title.strip(), body=body.strip(), author_id=actor.id, applies_to_all=not teams,
                     show_until=show_until, teams=teams)
    db.add(a)
    db.flush()
    audit.record(db, actor_id=actor.id, action="announcement.create", entity_type="announcement", entity_id=a.id,
                 after={"title": a.title, "team_ids": team_ids, "show_until": show_until}, ip=ip)

    q = select(User).where(User.is_active.is_(True), User.deleted_at.is_(None), User.id != actor.id)
    if teams:
        q = q.where(User.team_id.in_(team_ids))
    preview = a.body if len(a.body) <= 140 else a.body[:137] + "…"
    home = {RoleName.ADMIN: "/admin", RoleName.TEAM_LEAD: "/lead"}
    for person in db.scalars(q):
        uid = person.id
        notification_service.notify(
            db, user_id=uid, event_type="announcement", title=a.title, message=preview,
            link=home.get(person.role_name, "/artist"),
            entity_type="announcement", entity_id=a.id, dedupe_key=f"announcement:{a.id}:{uid}")
    db.commit()
    db.refresh(a)
    return _out(a)


def list_for_manager(db: Session, actor: User, include_expired: bool = False) -> list[dict]:
    q = select(Announcement)
    if not scope.is_admin(actor):
        mine = select(announcement_teams.c.announcement_id).where(
            announcement_teams.c.team_id.in_(scope.lead_team_ids(db, actor) or {-1}))
        q = q.where(or_(Announcement.author_id == actor.id, Announcement.applies_to_all.is_(True),
                        Announcement.id.in_(mine)))
    if not include_expired:
        q = q.where(_active())
    return [_out(a) for a in db.scalars(q.order_by(Announcement.created_at.desc(), Announcement.id.desc()).limit(200))]


def list_for_person(db: Session, user: User) -> list[dict]:
    """What shows on someone's home: active announcements for everyone or for their team."""
    targeted = select(announcement_teams.c.announcement_id).where(
        announcement_teams.c.team_id == (user.team_id or -1))
    q = select(Announcement).where(
        or_(Announcement.applies_to_all.is_(True), Announcement.id.in_(targeted)), _active(),
    ).order_by(Announcement.created_at.desc(), Announcement.id.desc()).limit(HOME_LIMIT)
    return [_out(a) for a in db.scalars(q)]


def delete(db: Session, actor: User, announcement_id: int, ip: str | None) -> None:
    a = db.get(Announcement, announcement_id)
    if not a:
        raise NotFound("Announcement not found")
    if a.author_id != actor.id and not scope.is_admin(actor):
        raise Forbidden("Only the author or an administrator can delete this")
    audit.record(db, actor_id=actor.id, action="announcement.delete", entity_type="announcement", entity_id=a.id,
                 before={"title": a.title}, ip=ip)
    db.delete(a)
    db.commit()
