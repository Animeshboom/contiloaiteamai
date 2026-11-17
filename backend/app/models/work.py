"""Assignments, assignees, attendance, submissions, deliverables, reviews."""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutils import utcnow
from app.models.base import UTCDateTime, JSONType, SoftDeleteMixin, TimestampMixin, str_enum
from app.models.enums import (
    AssignmentStatus, AttendanceStatus, DeliverableStatus, Priority, ReviewDecision, SubmissionStatus,
)
from app.models.org import User
from app.models.production import Episode, Project, Scene


class Assignment(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (Index("ix_assignments_deadline_status", "deadline", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    episode_id: Mapped[int | None] = mapped_column(ForeignKey("episodes.id"), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    expected_deliverables: Mapped[str | None] = mapped_column(Text)
    assignment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    deadline: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    priority: Mapped[Priority] = mapped_column(str_enum(Priority, "priority"), default=Priority.MEDIUM, nullable=False)
    # Aggregate status, derived from assignee statuses by the assignment service.
    status: Mapped[AssignmentStatus] = mapped_column(
        str_enum(AssignmentStatus, "assignment_status"), default=AssignmentStatus.ASSIGNED, nullable=False
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    project: Mapped[Project] = relationship()
    episode: Mapped[Episode | None] = relationship()
    created_by: Mapped[User] = relationship()
    scenes: Mapped[list["AssignmentScene"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )
    assignees: Mapped[list["AssignmentAssignee"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )


class AssignmentScene(Base):
    """Scenes covered by an assignment (one assignment -> many scenes)."""
    __tablename__ = "assignment_scenes"
    __table_args__ = (UniqueConstraint("assignment_id", "scene_id", name="uq_assignment_scene"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)

    assignment: Mapped[Assignment] = relationship(back_populates="scenes")
    scene: Mapped[Scene] = relationship()


class AssignmentAssignee(TimestampMixin, Base):
    """Per-artist slot on an assignment; each artist's contribution is tracked separately."""
    __tablename__ = "assignment_assignees"
    __table_args__ = (UniqueConstraint("assignment_id", "user_id", name="uq_assignment_assignee"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        str_enum(AssignmentStatus, "assignee_status"), default=AssignmentStatus.ASSIGNED, nullable=False, index=True
    )
    # Artist-reported progress (self-reported; never implies approval).
    reported_progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_note: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    assignment: Mapped[Assignment] = relationship(back_populates="assignees")
    user: Mapped[User] = relationship()


class Attendance(TimestampMixin, Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("user_id", "work_date", name="uq_attendance_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # studio-local date
    check_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    check_out_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[AttendanceStatus] = mapped_column(
        str_enum(AttendanceStatus, "attendance_status"), default=AttendanceStatus.PRESENT, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    corrected_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    corrected_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    user: Mapped[User] = relationship(foreign_keys=[user_id])


class Submission(TimestampMixin, Base):
    """An immutable record of one artist's submission. Revisions create new rows."""
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("assignee_id", "revision_number", name="uq_submission_assignee_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), nullable=False, index=True)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("assignment_assignees.id"), nullable=False, index=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    previous_submission_id: Mapped[int | None] = mapped_column(ForeignKey("submissions.id"))
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    submission_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # studio-local date
    scenes_completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # artist-reported
    work_description: Mapped[str] = mapped_column(Text, nullable=False)
    output_links: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    status: Mapped[SubmissionStatus] = mapped_column(
        str_enum(SubmissionStatus, "submission_status"),
        default=SubmissionStatus.PENDING_REVIEW, nullable=False, index=True,
    )

    assignment: Mapped[Assignment] = relationship()
    assignee: Mapped[AssignmentAssignee] = relationship()
    artist: Mapped[User] = relationship(foreign_keys=[artist_id])
    deliverables: Mapped[list["SubmissionDeliverable"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["SubmissionAttachment"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(back_populates="submission", order_by="Review.created_at")


class SubmissionDeliverable(TimestampMixin, Base):
    """A scene (or other deliverable) included in a submission, with its own review state."""
    __tablename__ = "submission_deliverables"
    __table_args__ = (UniqueConstraint("submission_id", "scene_id", name="uq_deliverable_submission_scene"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id"), index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[DeliverableStatus] = mapped_column(
        str_enum(DeliverableStatus, "deliverable_status"),
        default=DeliverableStatus.SUBMITTED, nullable=False, index=True,
    )
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    submission: Mapped[Submission] = relationship(back_populates="deliverables")
    scene: Mapped[Scene | None] = relationship()


class SubmissionAttachment(TimestampMixin, Base):
    __tablename__ = "submission_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    submission: Mapped[Submission] = relationship(back_populates="attachments")


class Review(Base):
    """Append-only review history."""
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    decision: Mapped[ReviewDecision] = mapped_column(str_enum(ReviewDecision, "review_decision"), nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text)
    approved_scene_ids: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)

    submission: Mapped[Submission] = relationship(back_populates="reviews")
    reviewer: Mapped[User] = relationship()
