"""Data-scoping rules shared by every service. Centralised so authorization is consistent.

- Admin: everything.
- Team lead: users in the teams they lead (plus their own team); can view all projects,
  manage projects owned by their teams (or created by them).
- Artist: only their own records, and projects they hold assignments in.
"""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.models import (
    Assignment, AssignmentAssignee, Episode, Project, RoleName, Scene, Team, User,
)

WORKERS = (RoleName.ARTIST,)  # roles that can be given assignments


def is_admin(user: User) -> bool:
    return user.role_name == RoleName.ADMIN


def is_lead(user: User) -> bool:
    return user.role_name == RoleName.TEAM_LEAD


def is_worker(user: User) -> bool:
    return user.role_name in WORKERS


def lead_team_ids(db: Session, user: User) -> set[int]:
    if not is_lead(user):
        return set()
    ids = set(db.scalars(select(Team.id).where(Team.lead_id == user.id, Team.deleted_at.is_(None))))
    if user.team_id:
        ids.add(user.team_id)
    return ids


def visible_user_ids(db: Session, user: User) -> set[int] | None:
    """None means 'all users'."""
    if is_admin(user):
        return None
    if is_lead(user):
        teams = lead_team_ids(db, user)
        ids = set(db.scalars(select(User.id).where(User.team_id.in_(teams)))) if teams else set()
        ids.add(user.id)
        return ids
    return {user.id}


def ensure_can_view_user(db: Session, actor: User, target_id: int) -> None:
    ids = visible_user_ids(db, actor)
    if ids is not None and target_id not in ids:
        raise NotFound("User not found")


def ensure_can_manage_artist(db: Session, actor: User, artist: User) -> None:
    """For assigning work / correcting attendance."""
    if is_admin(actor):
        return
    if is_lead(actor) and artist.team_id is not None and artist.team_id in lead_team_ids(db, actor):
        return
    raise Forbidden(f"{artist.full_name} is not a member of your team")


# ---------- projects ----------

def project_query(db: Session, user: User):
    q = select(Project).where(Project.deleted_at.is_(None))
    if is_worker(user):
        assigned = (
            select(Assignment.project_id)
            .join(AssignmentAssignee, AssignmentAssignee.assignment_id == Assignment.id)
            .where(AssignmentAssignee.user_id == user.id, Assignment.deleted_at.is_(None))
        )
        q = q.where(Project.id.in_(assigned))
    return q


def get_project_for_view(db: Session, user: User, project_id: int) -> Project:
    p = db.scalar(project_query(db, user).where(Project.id == project_id))
    if not p:
        raise NotFound("Project not found")
    return p


def can_manage_project(db: Session, user: User, project: Project) -> bool:
    if is_admin(user):
        return True
    if is_lead(user):
        return project.created_by_id == user.id or (
            project.team_id is not None and project.team_id in lead_team_ids(db, user)
        )
    return False


def get_project_for_edit(db: Session, user: User, project_id: int) -> Project:
    p = get_project_for_view(db, user, project_id)
    if not can_manage_project(db, user, p):
        raise Forbidden("You can only manage projects owned by your team")
    return p


def get_episode_for_edit(db: Session, user: User, episode_id: int) -> Episode:
    ep = db.get(Episode, episode_id)
    if not ep or ep.deleted_at is not None:
        raise NotFound("Episode not found")
    get_project_for_edit(db, user, ep.project_id)
    return ep


def get_scene_for_edit(db: Session, user: User, scene_id: int) -> Scene:
    sc = db.get(Scene, scene_id)
    if not sc or sc.deleted_at is not None:
        raise NotFound("Scene not found")
    get_episode_for_edit(db, user, sc.episode_id)
    return sc


# ---------- assignments ----------

def assignment_query(db: Session, user: User):
    q = select(Assignment).where(Assignment.deleted_at.is_(None))
    if is_admin(user):
        return q
    if is_lead(user):
        member_ids = visible_user_ids(db, user) or set()
        mine = select(AssignmentAssignee.assignment_id).where(AssignmentAssignee.user_id.in_(member_ids))
        return q.where(or_(Assignment.created_by_id == user.id, Assignment.id.in_(mine)))
    mine = select(AssignmentAssignee.assignment_id).where(AssignmentAssignee.user_id == user.id)
    return q.where(Assignment.id.in_(mine))


def get_assignment_for_view(db: Session, user: User, assignment_id: int) -> Assignment:
    a = db.scalar(assignment_query(db, user).where(Assignment.id == assignment_id))
    if not a:
        raise NotFound("Assignment not found")
    return a


def get_assignment_for_edit(db: Session, user: User, assignment_id: int) -> Assignment:
    a = get_assignment_for_view(db, user, assignment_id)
    if is_admin(user) or (is_lead(user) and a.created_by_id == user.id):
        return a
    if is_lead(user):
        members = visible_user_ids(db, user) or set()
        if all(x.user_id in members for x in a.assignees):
            return a
    raise Forbidden("You cannot modify this assignment")
