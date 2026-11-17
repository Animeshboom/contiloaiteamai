from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ProjectStatus, ProjectType, WorkStatus


class ProjectCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    project_type: ProjectType
    status: ProjectStatus = ProjectStatus.PLANNING
    start_date: date | None = None
    expected_completion_date: date | None = None
    team_id: int | None = None

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.expected_completion_date and self.expected_completion_date < self.start_date:
            raise ValueError("Expected completion date cannot be before the start date")
        return self


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    project_type: ProjectType | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    expected_completion_date: date | None = None
    team_id: int | None = None


class SceneCreate(BaseModel):
    scene_number: int = Field(ge=1, le=9999)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class SceneBulkCreate(BaseModel):
    """Create scenes N..M in one go (e.g. a new episode with 12 scenes)."""
    count: int = Field(ge=1, le=200)


class SceneUpdate(BaseModel):
    scene_number: int | None = Field(default=None, ge=1, le=9999)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: WorkStatus | None = None


class SceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    episode_id: int
    scene_number: int
    label: str
    title: str | None
    description: str | None
    status: WorkStatus


class EpisodeCreate(BaseModel):
    episode_number: int = Field(ge=1, le=9999)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    scene_count: int = Field(default=0, ge=0, le=200)


class EpisodeUpdate(BaseModel):
    episode_number: int | None = Field(default=None, ge=1, le=9999)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: WorkStatus | None = None


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    episode_number: int
    title: str
    description: str | None
    status: WorkStatus
    scenes: list[SceneOut] = []


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    title: str
    description: str | None
    project_type: ProjectType
    status: ProjectStatus
    start_date: date | None
    expected_completion_date: date | None
    team_id: int | None
    team_name: str | None = None
    created_at: datetime
    episode_count: int = 0
    scene_count: int = 0
    can_manage: bool = False


class ProjectDetail(ProjectOut):
    episodes: list[EpisodeOut] = []
