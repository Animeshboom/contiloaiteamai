from datetime import datetime

from pydantic import BaseModel, Field, field_validator

SCENE_STATUSES = ("not_started", "assigned", "in_progress", "in_review", "approved", "on_hold", "final")
OVERRIDES = ("on_hold", "final")


class NamedRef(BaseModel):
    id: int
    name: str


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RefLink(BaseModel):
    label: str = Field(default="", max_length=120)
    url: str = Field(min_length=8, max_length=1000)

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        v = v.strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("Links must start with http:// or https://")
        return v


class PromptIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    tool: str | None = Field(default=None, max_length=80)
    seed: str | None = Field(default=None, max_length=80)
    settings: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)


class PromptOut(BaseModel):
    id: int
    version: int
    prompt: str
    tool: str | None
    seed: str | None
    settings: str | None
    notes: str | None
    created_by: str | None
    created_at: datetime


class SceneEdit(BaseModel):
    """Everything a lead can change on a scene. ``status`` sets the manual override only:
    "on_hold" / "final", or null to go back to automatic."""
    scene_number: int | None = Field(default=None, ge=1, le=9999)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = None
    duration_sec: float | None = Field(default=None, ge=0, le=36000)
    frame_in: int | None = Field(default=None, ge=0)
    frame_out: int | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, gt=0, le=1000)
    location_id: int | None = None
    character_ids: list[int] | None = None
    reference_links: list[RefLink] | None = Field(default=None, max_length=30)

    @field_validator("status")
    @classmethod
    def _override(cls, v):
        if v is not None and v not in OVERRIDES:
            raise ValueError("Only on_hold or final can be set by hand (others are automatic)")
        return v


class SceneBulkEdit(BaseModel):
    scene_ids: list[int] = Field(min_length=1, max_length=500)
    status: str | None = None  # on_hold | final | "auto" (clear the override)
    add_character_ids: list[int] = []
    remove_character_ids: list[int] = []
    location_id: int | None = None
    clear_location: bool = False

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is not None and v not in (*OVERRIDES, "auto"):
            raise ValueError("Status must be on_hold, final or auto")
        return v


class SceneRow(BaseModel):
    id: int
    episode_id: int
    scene_number: int
    label: str
    title: str | None
    description: str | None
    status: str  # derived: not_started | assigned | in_progress | in_review | approved | on_hold | final
    status_override: str | None
    duration_sec: float | None
    frame_in: int | None
    frame_out: int | None
    fps: float | None
    location: NamedRef | None
    characters: list[NamedRef]
    reference_links: list[dict]
    artists: list[NamedRef]  # people currently assigned (not reassigned)
    current_prompt: PromptOut | None = None


class SceneHistoryItem(BaseModel):
    kind: str  # assignment | submission | review | prompt
    at: datetime
    title: str
    detail: str | None = None
    person: str | None = None
    links: list[str] = []
    assignment_id: int | None = None
    submission_id: int | None = None


class SceneDetail(SceneRow):
    prompts: list[PromptOut]
    history: list[SceneHistoryItem]


class Progress(BaseModel):
    total: int
    approved: int  # approved + final
    final: int
    in_review: int
    in_progress: int
    not_started: int


class ImportRowError(BaseModel):
    row: int
    message: str


class SceneImportResult(BaseModel):
    created: int
    updated: int
    errors: list[ImportRowError]
