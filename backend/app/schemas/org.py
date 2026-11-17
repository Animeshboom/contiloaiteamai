from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import RoleName
from app.schemas.auth import TeamRef, UserOut  # noqa: F401  (re-exported)


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role: RoleName
    team_id: int | None = None
    job_title: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=8, max_length=128)

    _s = field_validator("full_name", "job_title", mode="before")(_strip)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    role: RoleName | None = None
    team_id: int | None = None
    job_title: str | None = Field(default=None, max_length=120)
    clear_team: bool = False  # explicit flag, since team_id=None is ambiguous in a PATCH

    _s = field_validator("full_name", "job_title", mode="before")(_strip)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: EmailStr
    job_title: str | None = None


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    lead_id: int | None = None

    _s = field_validator("name", "department", mode="before")(_strip)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    lead_id: int | None = None
    clear_lead: bool = False


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    department: str | None
    description: str | None
    lead: UserBrief | None
    member_count: int = 0
    created_at: datetime


class RecipientCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=160)


class RecipientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    is_active: bool | None = None


class RecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    name: str
    purpose: str
    is_active: bool
