"""Artist submissions and lead reviews.

Submissions are immutable: a resubmission is a new row (revision_number + 1) linked to
the submission whose rejected scenes it revises. Reviews are append-only. Approval state
lives on submission_deliverables, so partial approval of a multi-scene submission is exact.
"""
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.timeutils import ensure_utc, studio_today, utcnow
from app.models import (
    Assignment, DeliverableStatus, Review, ReviewDecision, RoleName,
    Submission, SubmissionAttachment, SubmissionDeliverable, SubmissionStatus, User, WorkStatus,
)
from app.schemas.submissions import (
    AttachmentOut, DeliverableOut, ReviewCreate, ReviewOut, SubmissionCreate, SubmissionOut,
)
from app.services import assignment_service, audit, files, progress, scope

MAX_ATTACHMENTS = 10


# ---------------- serialization ----------------

def to_out(db: Session, s: Submission) -> SubmissionOut:
    a = s.assignment
    names = dict(db.execute(select(User.id, User.full_name).where(
        User.id.in_({d.approved_by_id for d in s.deliverables if d.approved_by_id} | {r.reviewer_id for r in s.reviews} or {-1})
    )).all())
    return SubmissionOut(
        id=s.id, assignment_id=a.id, assignment_title=a.title, project_id=a.project_id, project_title=a.project.title,
        project_code=a.project.code, episode_number=a.episode.episode_number if a.episode else None,
        episode_title=a.episode.title if a.episode else None, artist_id=s.artist_id, artist_name=s.artist.full_name,
        revision_number=s.revision_number, previous_submission_id=s.previous_submission_id,
        is_resubmission=s.previous_submission_id is not None, submitted_at=s.submitted_at,
        submission_date=s.submission_date, is_late=ensure_utc(s.submitted_at) > ensure_utc(a.deadline),
        deadline=a.deadline, scenes_completed_count=s.scenes_completed_count, work_description=s.work_description,
        output_links=list(s.output_links or []), comments=s.comments, status=s.status,
        deliverables=[
            DeliverableOut(id=d.id, scene_id=d.scene_id, label=d.label, status=d.status, approved_at=d.approved_at,
                           approved_by_name=names.get(d.approved_by_id))
            for d in sorted(s.deliverables, key=lambda d: d.label)
        ],
        attachments=[
            AttachmentOut(id=f.id, original_filename=f.original_filename, content_type=f.content_type,
                          size_bytes=f.size_bytes, created_at=f.created_at)
            for f in s.attachments
        ],
        reviews=[
            ReviewOut(id=r.id, reviewer_id=r.reviewer_id, reviewer_name=names.get(r.reviewer_id, "—"),
                      decision=r.decision, feedback=r.feedback, approved_scene_ids=list(r.approved_scene_ids or []),
                      created_at=r.created_at)
            for r in s.reviews
        ],
    )


# ---------------- queries ----------------

def _query(db: Session, user: User):
    q = select(Submission).join(Assignment, Assignment.id == Submission.assignment_id).where(Assignment.deleted_at.is_(None))
    if user.role_name == RoleName.ARTIST:
        return q.where(Submission.artist_id == user.id)
    ids = scope.visible_user_ids(db, user)
    if ids is not None:
        q = q.where(Submission.artist_id.in_(ids))
    return q


def get_for_view(db: Session, user: User, submission_id: int) -> Submission:
    s = db.scalar(_query(db, user).where(Submission.id == submission_id))
    if not s:
        raise NotFound("Submission not found")
    return s


def list_for(db: Session, user: User, *, status: SubmissionStatus | None = None, assignment_id: int | None = None,
             artist_id: int | None = None, project_id: int | None = None, limit: int = 200) -> list[Submission]:
    q = _query(db, user)
    if status:
        q = q.where(Submission.status == status)
    if assignment_id:
        q = q.where(Submission.assignment_id == assignment_id)
    if artist_id:
        q = q.where(Submission.artist_id == artist_id)
    if project_id:
        q = q.where(Assignment.project_id == project_id)
    order = (Submission.submitted_at.asc() if status == SubmissionStatus.PENDING_REVIEW
             else Submission.submitted_at.desc())  # review queue: oldest first
    return list(db.scalars(q.order_by(order).limit(limit)))


# ---------------- submit ----------------

def create(db: Session, artist: User, data: SubmissionCreate, ip: str | None) -> Submission:
    x = assignment_service.my_slot(db, artist, data.assignment_id)
    a = x.assignment
    if x.status in assignment_service.DONE:
        raise Conflict("This assignment is already approved")

    assigned = {s.scene_id: s.scene for s in a.scenes}
    states = progress.scene_states(db, [x.id])[x.id]

    if assigned:
        if not data.scene_ids:
            raise ValidationFailed("Select at least one completed scene to submit")
        unknown = [sid for sid in data.scene_ids if sid not in assigned]
        if unknown:
            raise ValidationFailed("You can only submit scenes that are part of this assignment")
        for sid in data.scene_ids:
            st = states.get(sid)
            if st == progress.PENDING:
                raise Conflict(f"{assigned[sid].label} is already awaiting review")
            if st == progress.APPROVED:
                raise Conflict(f"{assigned[sid].label} is already approved")
    else:
        if data.scene_ids:
            raise ValidationFailed("This assignment has no scenes; describe the deliverable instead")
        last = progress.latest_submission(db, x.id)
        if last and last.status == SubmissionStatus.PENDING_REVIEW:
            raise Conflict("Your previous submission is still awaiting review")

    # Link to the most recent submission that rejected any of these scenes (revision history).
    prev_id = None
    rejected_now = [sid for sid in data.scene_ids if states.get(sid) == progress.REJECTED]
    if rejected_now or (not assigned and progress.latest_submission(db, x.id)):
        q = (select(Submission.id).where(Submission.assignee_id == x.id, Submission.status == SubmissionStatus.REJECTED)
             .order_by(Submission.revision_number.desc()))
        if rejected_now:
            q = q.join(SubmissionDeliverable).where(SubmissionDeliverable.scene_id.in_(rejected_now))
        prev_id = db.scalar(q.limit(1))

    revision = (db.scalar(select(func.max(Submission.revision_number)).where(Submission.assignee_id == x.id)) or 0) + 1
    now = utcnow()
    sub = Submission(
        assignment_id=a.id, assignee_id=x.id, artist_id=artist.id, revision_number=revision,
        previous_submission_id=prev_id, submitted_at=now, submission_date=studio_today(),
        scenes_completed_count=data.scenes_completed_count if data.scenes_completed_count is not None else len(data.scene_ids),
        work_description=data.work_description.strip(), output_links=[str(u) for u in data.output_links],
        comments=(data.comments or "").strip() or None, status=SubmissionStatus.PENDING_REVIEW,
    )
    if assigned:
        sub.deliverables = [
            SubmissionDeliverable(scene_id=sid, label=f"EP{assigned[sid].episode.episode_number:02d} {assigned[sid].label}")
            for sid in data.scene_ids
        ]
        for sid in data.scene_ids:
            if assigned[sid].status in (WorkStatus.NOT_STARTED, WorkStatus.IN_PROGRESS):
                assigned[sid].status = WorkStatus.IN_REVIEW
    else:
        sub.deliverables = [SubmissionDeliverable(scene_id=None, label=(a.expected_deliverables or a.title)[:200])]
    db.add(sub)
    if x.started_at is None:
        x.started_at = now
    assignment_service.sync_status(db, x)
    audit.record(db, actor_id=artist.id, action="submission.create", entity_type="submission", entity_id=sub.id,
                 after={"assignment_id": a.id, "scene_ids": data.scene_ids, "revision": revision,
                        "previous_submission_id": prev_id}, ip=ip)
    _notify("submission_received", db, sub)
    db.commit()
    db.refresh(sub)
    return sub


async def add_attachment(db: Session, artist: User, submission_id: int, upload: UploadFile, ip: str | None) -> Submission:
    sub = get_for_view(db, artist, submission_id)
    if sub.artist_id != artist.id:
        raise NotFound("Submission not found")
    if sub.status != SubmissionStatus.PENDING_REVIEW or sub.reviews:
        raise Conflict("Files can only be attached before the submission is reviewed")
    if len(sub.attachments) >= MAX_ATTACHMENTS:
        raise ValidationFailed(f"A submission can have at most {MAX_ATTACHMENTS} attachments")
    meta = await files.store_upload(upload, f"submissions/{sub.id}")
    att = SubmissionAttachment(submission_id=sub.id, **meta)
    db.add(att)
    db.flush()
    audit.record(db, actor_id=artist.id, action="submission.attach", entity_type="submission", entity_id=sub.id,
                 after={"file": meta["original_filename"], "size": meta["size_bytes"], "sha256": meta["sha256"]}, ip=ip)
    db.commit()
    db.refresh(sub)
    return sub


def get_attachment(db: Session, user: User, submission_id: int, attachment_id: int) -> SubmissionAttachment:
    sub = get_for_view(db, user, submission_id)
    att = next((f for f in sub.attachments if f.id == attachment_id), None)
    if not att:
        raise NotFound("Attachment not found")
    return att


# ---------------- review ----------------

def review(db: Session, reviewer: User, submission_id: int, data: ReviewCreate, ip: str | None) -> Submission:
    sub = db.scalar(_query(db, reviewer).where(Submission.id == submission_id).with_for_update(of=Submission))
    if not sub:
        raise NotFound("Submission not found")
    scope.ensure_can_manage_artist(db, reviewer, sub.artist)
    if sub.artist_id == reviewer.id:
        raise ValidationFailed("You cannot review your own submission")
    if sub.status != SubmissionStatus.PENDING_REVIEW:
        raise Conflict("This submission has already been reviewed")

    feedback = (data.feedback or "").strip() or None
    scene_deliverables = {d.scene_id: d for d in sub.deliverables if d.scene_id is not None}

    if data.decision == ReviewDecision.APPROVED:
        if data.approved_scene_ids is None:
            approve_ids = set(scene_deliverables)
        else:
            approve_ids = set(data.approved_scene_ids)
            if not approve_ids:
                raise ValidationFailed("Select at least one scene to approve, or reject the submission")
            if not approve_ids <= set(scene_deliverables):
                raise ValidationFailed("Approved scenes must be part of this submission")
        partial = bool(set(scene_deliverables) - approve_ids)
        if partial and (not feedback or len(feedback) < 3):
            raise ValidationFailed("Explain what needs revision for the scenes you are not approving")
    else:
        if not feedback or len(feedback) < 3:
            raise ValidationFailed("Rejection feedback is required so the artist knows what to revise")
        approve_ids = set()

    now = utcnow()
    for d in sub.deliverables:
        ok = (d.scene_id in approve_ids) if d.scene_id is not None else data.decision == ReviewDecision.APPROVED
        d.status = DeliverableStatus.APPROVED if ok else DeliverableStatus.REJECTED
        if ok:
            d.approved_by_id, d.approved_at = reviewer.id, now
        if d.scene is not None:
            d.scene.status = WorkStatus.APPROVED if ok else WorkStatus.IN_PROGRESS

    all_ok = all(d.status == DeliverableStatus.APPROVED for d in sub.deliverables)
    sub.status = SubmissionStatus.APPROVED if all_ok else SubmissionStatus.REJECTED
    decision = ReviewDecision.APPROVED if all_ok else ReviewDecision.REJECTED
    db.add(Review(submission_id=sub.id, reviewer_id=reviewer.id, decision=decision, feedback=feedback,
                  approved_scene_ids=sorted(approve_ids), created_at=now))
    assignment_service.sync_status(db, sub.assignee)
    audit.record(db, actor_id=reviewer.id, action=f"submission.{decision.value}", entity_type="submission",
                 entity_id=sub.id, after={"approved_scene_ids": sorted(approve_ids), "feedback": feedback}, ip=ip)
    db.flush()
    _notify("submission_approved" if all_ok else "submission_rejected", db, sub)
    db.commit()
    db.refresh(sub)
    return sub


def _notify(event: str, db: Session, sub: Submission) -> None:
    """Hook for the notification service (Phase 4)."""
    try:
        from app.services import notification_service  # noqa: PLC0415
    except ImportError:
        return
    getattr(notification_service, event)(db, sub)

