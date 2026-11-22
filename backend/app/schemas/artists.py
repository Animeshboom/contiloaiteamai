from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.auth import UserOut

EMPLOYEE_CODE = r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$"
PHONE = r"^\+?[0-9 ()-]{6,24}$"


class ArtistCreate(BaseModel):
    """One way to sign in: a real email, or an Employee ID for people without one. Leave both empty to get
    the next automatic Employee ID (EMP001, EMP002, ...)."""
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    employee_code: str | None = Field(default=None, pattern=EMPLOYEE_CODE)
    team_id: int | None = None
    job_title: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, pattern=PHONE)
    password: str | None = Field(default=None, min_length=8, max_length=128)  # generated when empty

    @model_validator(mode="after")
    def _one_login(self):
        if self.email and self.employee_code:
            raise ValueError("Give either an email or an Employee ID, not both")
        return self


class Credentials(BaseModel):
    """Returned once, when an account is created or its password reset. Never stored in plain text."""
    user: UserOut
    login: str  # what they type to sign in: their email or Employee ID
    password: str


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportResult(BaseModel):
    created: list[Credentials]
    errors: list[ImportRowError]


# ---------------- leave ----------------

class LeaveCreate(BaseModel):
    start: date
    end: date
    reason: str = Field(min_length=3, max_length=1000)
    leave_type: str = Field(default="casual", pattern="^(casual|sick|privilege|unpaid)$")
    half_day: str | None = Field(default=None, pattern="^(first_half|second_half)$")


class LeaveDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=1000)


class LeaveOut(BaseModel):
    id: int
    user_id: int
    person: str
    team_id: int | None
    team_name: str | None
    start: date
    end: date
    days: float
    reason: str
    leave_type: str = "casual"
    half_day: str | None = None
    active_tasks_count: int = 0
    team_overlap_count: int = 0
    days_taken_year: float = 0.0
    days_taken_month: float = 0.0
    status: str  # pending | approved | rejected | cancelled
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
