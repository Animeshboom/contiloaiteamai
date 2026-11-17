"""Derives per-artist scene state and status from submission/review records.

The state of a scene for an artist is the deliverable status in the *latest*
submission that included it:  submitted (pending review) | approved | rejected.
Scenes never submitted have no state. Artist-reported progress never affects this.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssignmentAssignee, AssignmentStatus, DeliverableStatus, Submission, SubmissionDeliverable, SubmissionStatus,
)

PENDING = DeliverableStatus.SUBMITTED.value
APPROVED = DeliverableStatus.APPROVED.value
REJECTED = DeliverableStatus.REJECTED.value


def scene_states(db: Session, assignee_ids: list[int]) -> dict[int, dict[int, str]]:
    """{assignee_id: {scene_id: 'submitted'|'approved'|'rejected'}}"""
    out: dict[int, dict[int, str]] = {aid: {} for aid in assignee_ids}
    if not assignee_ids:
        return out
    rows = db.execute(
        select(Submission.assignee_id, SubmissionDeliverable.scene_id, SubmissionDeliverable.status)
        .join(SubmissionDeliverable, SubmissionDeliverable.submission_id == Submission.id)
        .where(Submission.assignee_id.in_(assignee_ids), SubmissionDeliverable.scene_id.is_not(None))
        .order_by(Submission.revision_number.asc(), Submission.id.asc())
    ).all()
    for aid, scene_id, status in rows:  # later submissions overwrite earlier ones
        out[aid][scene_id] = status.value if hasattr(status, "value") else status
    return out


def latest_submission(db: Session, assignee_id: int) -> Submission | None:
    return db.scalar(
        select(Submission).where(Submission.assignee_id == assignee_id)
        .order_by(Submission.revision_number.desc()).limit(1)
    )


def derive_assignee_status(db: Session, x: AssignmentAssignee) -> AssignmentStatus:
    if x.status == AssignmentStatus.COMPLETED:
        return x.status  # set explicitly by a lead; sticky
    scene_ids = [s.scene_id for s in x.assignment.scenes]
    if scene_ids:
        states = scene_states(db, [x.id])[x.id]
        values = [states.get(sid) for sid in scene_ids]
        if all(v == APPROVED for v in values):
            return AssignmentStatus.APPROVED
        if PENDING in values:
            return AssignmentStatus.SUBMITTED
        if REJECTED in values:
            return AssignmentStatus.REVISION_REQUIRED
        if APPROVED in values or x.reported_progress_pct > 0 or x.started_at:
            return AssignmentStatus.IN_PROGRESS
        return AssignmentStatus.ASSIGNED
    # Deliverable-only assignment: follow the most recent submission.
    last = latest_submission(db, x.id)
    if last is None:
        return AssignmentStatus.IN_PROGRESS if (x.reported_progress_pct > 0 or x.started_at) else AssignmentStatus.ASSIGNED
    return {
        SubmissionStatus.PENDING_REVIEW: AssignmentStatus.SUBMITTED,
        SubmissionStatus.APPROVED: AssignmentStatus.APPROVED,
        SubmissionStatus.REJECTED: AssignmentStatus.REVISION_REQUIRED,
    }[last.status]
