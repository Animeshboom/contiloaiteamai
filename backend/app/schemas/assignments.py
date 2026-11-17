from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import AssignmentStatus, Priority


class AssignmentCreate(BaseModel):
    project_id: int
    episode_id: int | None = None
    scene_ids: list[int] = Field(default_factory=list, max_length=200)
    artist_ids: list[int] = Field(min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    expected_deliverables: str | None = Field(default=None, max_length=5000)
    assignment_date: date | None = None  # defaults to studio "today"
    deadline: datetime | None = None  # defaults to EOD of assignment_date
    priority: Priority = Priority.MEDIUM

    @field_validator("scene_ids", "artist_ids")
    @classmethod
    def _dedupe(cls, v: list[int]) -> list[int]:
        return list(dict.fromkeys(v))


class AssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    expected_deliverables: str | None = Field(default=None, max_length=5000)
    deadline: datetime | None = None
    priority: Priority | None = None
    add_artist_ids: list[int] = Field(default_factory=list, max_length=50)
    remove_artist_ids: list[int] = Field(default_factory=list, max_length=50)


class SceneRef(BaseModel):
    id: int
    scene_number: int
    label: str
    title: str | None
    episode_id: int
    episode_number: int


class AssigneeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    full_name: str
    status: AssignmentStatus
    reported_progress_pct: int
    progress_note: str | None
    # Filled from submission/review data in Phase 3; 0 until then.
    scenes_submitted: int = 0
    scenes_approved: int = 0


class AssignmentOut(BaseModel):
    id: int
    title: str
    project_id: int
    project_title: str
    project_code: str
    episode_id: int | None
    episode_number: int | None
    episode_title: str | None
    description: str | None
    expected_deliverables: str | None
    assignment_date: date
    deadline: datetime
    priority: Priority
    status: AssignmentStatus
    is_overdue: bool
    created_by_id: int
    created_by_name: str
    created_at: datetime
    scenes: list[SceneRef]
    assignees: list[AssigneeOut]
