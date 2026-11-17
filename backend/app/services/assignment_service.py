"""Task assignment.

An assignment targets one project (optionally one episode) and covers zero or more scenes.
Zero scenes = a non-scene deliverable (description required). Each artist gets an
`assignment_assignees` row so their status/progress/contribution is tracked separately.
"""
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.core.timeutils import ensure_utc, studio_day_bounds_utc, studio_eod, studio_today, utcnow
from app.models import (
    Assignment, AssignmentAssignee, AssignmentScene, AssignmentStatus, DeliverableStatus, Episode, Priority,
    ProjectStatus, RoleName, Scene, Submission, SubmissionDeliverable, User,
)
from app.schemas.assignments import AssigneeOut, AssignmentCreate, AssignmentOut, AssignmentUpdate, SceneRef
from app.services import audit, scope

DONE = {AssignmentStatus.APPROVED, AssignmentStatus.COMPLETED}


# ---------------- status ----------------

def aggregate_status(statuses: list[AssignmentStatus]) -> AssignmentStatus:
    s = set(statuses)
    if not s:
        return AssignmentStatus.ASSIGNED
    if s == {AssignmentStatus.COMPLETED}:
        return AssignmentStatus.COMPLETED
    if s <= DONE:
        return AssignmentStatus.APPROVED
    if AssignmentStatus.REVISION_REQUIRED in s:
        return AssignmentStatus.REVISION_REQUIRED
    if AssignmentStatus.SUBMITTED in s:
        return AssignmentStatus.SUBMITTED
    if s & {AssignmentStatus.IN_PROGRESS, *DONE}:
        return AssignmentStatus.IN_PROGRESS
    return AssignmentStatus.ASSIGNED


def recompute_status(a: Assignment) -> None:
    a.status = aggregate_status([x.status for x in a.assignees])


def is_overdue(a: Assignment, now: datetime | None = None) -> bool:
    return a.status not in DONE and ensure_utc(a.deadline) < (now or utcnow())


# ---------------- serialization ----------------

def _scene_counts(db: Session, assignee_ids: list[int]) -> dict[int, tuple[int, int]]:
    """assignee_id -> (distinct scenes submitted, distinct scenes approved) across all revisions."""
    if not assignee_ids:
        return {}
    base = (
        select(Submission.assignee_id, func.count(func.distinct(SubmissionDeliverable.scene_id)))
        .join(SubmissionDeliverable, SubmissionDeliverable.submission_id == Submission.id)
        .where(Submission.assignee_id.in_(assignee_ids), SubmissionDeliverable.scene_id.is_not(None))
        .group_by(Submission.assignee_id)
    )
    # A scene submitted across several revisions counts once.
    submitted = dict(db.execute(base).all())
    approved = dict(db.execute(base.where(SubmissionDeliverable.status == DeliverableStatus.APPROVED)).all())
    return {aid: (submitted.get(aid, 0), approved.get(aid, 0)) for aid in assignee_ids}


def to_out(db: Session, a: Assignment, now: datetime | None = None) -> AssignmentOut:
    counts = _scene_counts(db, [x.id for x in a.assignees])
    scenes = sorted((x.scene for x in a.scenes), key=lambda s: (s.episode.episode_number, s.scene_number))
    return AssignmentOut(
        id=a.id, title=a.title, project_id=a.project_id, project_title=a.project.title, project_code=a.project.code,
        episode_id=a.episode_id, episode_number=a.episode.episode_number if a.episode else None,
        episode_title=a.episode.title if a.episode else None, description=a.description,
        expected_deliverables=a.expected_deliverables, assignment_date=a.assignment_date,
        deadline=a.deadline, priority=a.priority, status=a.status, is_overdue=is_overdue(a, now),
        created_by_id=a.created_by_id, created_by_name=a.created_by.full_name, created_at=a.created_at,
        scenes=[SceneRef(id=s.id, scene_number=s.scene_number, label=s.label, title=s.title,
                         episode_id=s.episode_id, episode_number=s.episode.episode_number) for s in scenes],
        assignees=[
            AssigneeOut(id=x.id, user_id=x.user_id, full_name=x.user.full_name, status=x.status,
                        reported_progress_pct=x.reported_progress_pct, progress_note=x.progress_note,
                        scenes_submitted=counts.get(x.id, (0, 0))[0], scenes_approved=counts.get(x.id, (0, 0))[1])
            for x in sorted(a.assignees, key=lambda x: x.user.full_name)
        ],
    )


# ---------------- validation helpers ----------------

def _validate_artists(db: Session, actor: User, artist_ids: list[int]) -> list[User]:
    artists = list(db.scalars(select(User).where(User.id.in_(artist_ids))))
    if len(artists) != len(set(artist_ids)):
        raise ValidationFailed("One or more selected artists do not exist")
    for u in artists:
        if not u.is_active or u.deleted_at is not None:
            raise ValidationFailed(f"{u.full_name} is not an active employee")
        if u.role_name != RoleName.ARTIST:
            raise ValidationFailed(f"{u.full_name} is not an artist")
        scope.ensure_can_manage_artist(db, actor, u)
    return artists


def _validate_scenes(db: Session, project_id: int, episode_id: int | None, scene_ids: list[int]) -> list[Scene]:
    if not scene_ids:
        return []
    scenes = list(db.scalars(select(Scene).where(Scene.id.in_(scene_ids), Scene.deleted_at.is_(None))))
    if len(scenes) != len(scene_ids):
        raise ValidationFailed("One or more selected scenes do not exist")
    for s in scenes:
        if s.episode.project_id != project_id or s.episode.deleted_at is not None:
            raise ValidationFailed(f"Scene {s.label} does not belong to the selected project")
        if episode_id and s.episode_id != episode_id:
            raise ValidationFailed(f"Scene {s.label} does not belong to the selected episode")
    return scenes


def _auto_title(episode: Episode | None, scenes: list[Scene], description: str | None) -> str:
    if scenes:
        eps = {s.episode for s in scenes}
        nums = sorted(s.scene_number for s in scenes)
        scene_txt = f"Scene {nums[0]:02d}" if len(nums) == 1 else "Scenes " + ", ".join(f"{n:02d}" for n in nums)
        if len(scene_txt) > 80:
            scene_txt = f"{len(nums)} scenes"
        if len(eps) == 1:
            ep = next(iter(eps))
            return f"EP{ep.episode_number:02d} {ep.title} — {scene_txt}"[:200]
        return scene_txt[:200]
    if episode:
        return f"EP{episode.episode_number:02d} {episode.title} — deliverable"[:200]
    return (description or "Production deliverable").split("\n")[0][:200]


# ---------------- commands ----------------

def create(db: Session, actor: User, data: AssignmentCreate, ip: str | None) -> Assignment:
    project = scope.get_project_for_edit(db, actor, data.project_id)
    if project.status in (ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED):
        raise ValidationFailed(f"Cannot assign work on a {project.status.value} project")

    episode = None
    if data.episode_id:
        episode = db.get(Episode, data.episode_id)
        if not episode or episode.deleted_at is not None or episode.project_id != project.id:
            raise ValidationFailed("Episode does not belong to the selected project")

    scenes = _validate_scenes(db, project.id, data.episode_id, data.scene_ids)
    if not scenes and not (data.description or data.expected_deliverables):
        raise ValidationFailed("Select at least one scene, or describe the deliverable")
    if scenes and not episode and len({s.episode_id for s in scenes}) == 1:
        episode = scenes[0].episode

    artists = _validate_artists(db, actor, data.artist_ids)

    assignment_date = data.assignment_date or studio_today()
    if data.deadline:
        deadline = ensure_utc(data.deadline)
    else:
        deadline = studio_eod(assignment_date)
        if deadline <= utcnow():  # assigned after the EOD cutoff: due by end of the studio day
            deadline = studio_day_bounds_utc(assignment_date)[1].replace(microsecond=0)
    if deadline <= utcnow():
        raise ValidationFailed("Deadline must be in the future")
    if deadline < studio_day_bounds_utc(assignment_date)[0]:
        raise ValidationFailed("Deadline cannot be before the assignment date")

    a = Assignment(
        title=(data.title or "").strip() or _auto_title(episode, scenes, data.description),
        project_id=project.id, episode_id=episode.id if episode else None, description=data.description,
        expected_deliverables=data.expected_deliverables, assignment_date=assignment_date, deadline=deadline,
        priority=data.priority, status=AssignmentStatus.ASSIGNED, created_by_id=actor.id,
    )
    a.scenes = [AssignmentScene(scene_id=s.id) for s in scenes]
    a.assignees = [AssignmentAssignee(user_id=u.id) for u in artists]
    db.add(a)
    db.flush()
    audit.record(db, actor_id=actor.id, action="assignment.create", entity_type="assignment", entity_id=a.id,
                 after={"title": a.title, "project_id": project.id, "scene_ids": [s.id for s in scenes],
                        "artist_ids": [u.id for u in artists], "deadline": deadline, "priority": a.priority}, ip=ip)
    _notify_new_assignment(db, a, artists)
    db.commit()
    db.refresh(a)
    return a


def _notify_new_assignment(db: Session, a: Assignment, artists: list[User]) -> None:
    """Hook for the notification service (Phase 4)."""
    try:
        from app.services import notification_service  # noqa: PLC0415
    except ImportError:
        return
    for u in artists:
        notification_service.assignment_created(db, a, u)


def update(db: Session, actor: User, assignment_id: int, data: AssignmentUpdate, ip: str | None) -> Assignment:
    a = scope.get_assignment_for_edit(db, actor, assignment_id)
    changes = data.model_dump(exclude_unset=True, exclude={"add_artist_ids", "remove_artist_ids"})
    before = {k: getattr(a, k) for k in changes}
    if "deadline" in changes and changes["deadline"] is not None:
        changes["deadline"] = ensure_utc(changes["deadline"])
        if changes["deadline"] < studio_day_bounds_utc(a.assignment_date)[0]:
            raise ValidationFailed("Deadline cannot be before the assignment date")
    for k, v in changes.items():
        if v is not None:
            setattr(a, k, v)

    added: list[User] = []
    if data.add_artist_ids:
        existing = {x.user_id for x in a.assignees}
        added = [u for u in _validate_artists(db, actor, data.add_artist_ids) if u.id not in existing]
        for u in added:
            a.assignees.append(AssignmentAssignee(user_id=u.id))
    if data.remove_artist_ids:
        for x in list(a.assignees):
            if x.user_id in data.remove_artist_ids:
                has_work = db.scalar(select(func.count(Submission.id)).where(Submission.assignee_id == x.id))
                if has_work:
                    raise ValidationFailed(f"{x.user.full_name} has already submitted work and cannot be removed")
                a.assignees.remove(x)
        if not a.assignees:
            raise ValidationFailed("An assignment must have at least one artist")
    db.flush()
    recompute_status(a)
    audit.record(db, actor_id=actor.id, action="assignment.update", entity_type="assignment", entity_id=a.id,
                 before=before, after={**changes, "added": [u.id for u in added],
                                       "removed": data.remove_artist_ids}, ip=ip)
    if added:
        _notify_new_assignment(db, a, added)
    db.commit()
    db.refresh(a)
    return a


def delete(db: Session, actor: User, assignment_id: int, ip: str | None) -> None:
    a = scope.get_assignment_for_edit(db, actor, assignment_id)
    a.deleted_at = utcnow()
    audit.record(db, actor_id=actor.id, action="assignment.delete", entity_type="assignment", entity_id=a.id, ip=ip)
    db.commit()


def list_for(db: Session, actor: User, *, status: AssignmentStatus | None = None, project_id: int | None = None,
             artist_id: int | None = None, on_date: date | None = None, overdue: bool = False,
             priority: Priority | None = None, limit: int = 200) -> list[Assignment]:
    q = scope.assignment_query(db, actor)
    if status:
        q = q.where(Assignment.status == status)
    if project_id:
        q = q.where(Assignment.project_id == project_id)
    if priority:
        q = q.where(Assignment.priority == priority)
    if artist_id:
        q = q.where(Assignment.id.in_(select(AssignmentAssignee.assignment_id).where(AssignmentAssignee.user_id == artist_id)))
    if on_date:
        q = q.where(Assignment.assignment_date == on_date)
    if overdue:
        q = q.where(Assignment.deadline < utcnow(), Assignment.status.not_in(list(DONE)))
    return list(db.scalars(q.order_by(Assignment.deadline.asc(), Assignment.id.desc()).limit(limit)))
