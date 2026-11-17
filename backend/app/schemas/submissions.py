from datetime import date, datetime

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from app.models import DeliverableStatus, ReviewDecision, SubmissionStatus


class ProgressUpdate(BaseModel):
    """Artist self-reported progress. Never implies approval."""
    reported_progress_pct: int = Field(ge=0, le=100)
    progress_note: str | None = Field(default=None, max_length=2000)


class SubmissionCreate(BaseModel):
    assignment_id: int
    scene_ids: list[int] = Field(default_factory=list, max_length=200)
    work_description: str = Field(min_length=3, max_length=5000)
    output_links: list[AnyHttpUrl] = Field(default_factory=list, max_length=20)
    comments: str | None = Field(default=None, max_length=5000)
    # Artist-reported; defaults to the number of scenes submitted.
    scenes_completed_count: int | None = Field(default=None, ge=0, le=200)

    @field_validator("scene_ids")
    @classmethod
    def _dedupe(cls, v: list[int]) -> list[int]:
        return list(dict.fromkeys(v))

    @field_validator("output_links")
    @classmethod
    def _http_only(cls, v: list[AnyHttpUrl]) -> list[AnyHttpUrl]:
        for url in v:
            if url.scheme not in ("http", "https"):
                raise ValueError("Links must start with http:// or https://")
            if len(str(url)) > 2000:
                raise ValueError("Link is too long")
        return v


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    feedback: str | None = Field(default=None, max_length=5000)
    # For approvals: which scenes to approve (default all). Any others are rejected and need feedback.
    approved_scene_ids: list[int] | None = Field(default=None, max_length=200)


class DeliverableOut(BaseModel):
    id: int
    scene_id: int | None
    label: str
    status: DeliverableStatus
    approved_at: datetime | None
    approved_by_name: str | None


class AttachmentOut(BaseModel):
    id: int
    original_filename: str
    content_type: str | None
    size_bytes: int
    created_at: datetime


class ReviewOut(BaseModel):
    id: int
    reviewer_id: int
    reviewer_name: str
    decision: ReviewDecision
    feedback: str | None
    approved_scene_ids: list[int]
    created_at: datetime


class SubmissionOut(BaseModel):
    id: int
    assignment_id: int
    assignment_title: str
    project_id: int
    project_title: str
    project_code: str
    episode_number: int | None
    episode_title: str | None
    artist_id: int
    artist_name: str
    revision_number: int
    previous_submission_id: int | None
    is_resubmission: bool
    submitted_at: datetime
    submission_date: date
    is_late: bool
    deadline: datetime
    scenes_completed_count: int
    work_description: str
    output_links: list[str]
    comments: str | None
    status: SubmissionStatus
    deliverables: list[DeliverableOut]
    attachments: list[AttachmentOut]
    reviews: list[ReviewOut]
