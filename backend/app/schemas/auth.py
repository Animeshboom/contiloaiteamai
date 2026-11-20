from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import RoleName


class LoginRequest(BaseModel):
    email: str = Field(min_length=2, max_length=255)  # an email, or an Employee ID such as EMP001
    password: str = Field(min_length=1, max_length=200)


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: RoleName = Field(validation_alias="role_name")
    job_title: str | None
    team: TeamRef | None
    employee_code: str | None = None
    phone: str | None = None
    is_active: bool
    mfa_enabled: bool = Field(default=False, validation_alias="totp_enabled")
    locked_until: datetime | None = None
    last_login_at: datetime | None
    created_at: datetime


class MfaLogin(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=8)


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TokenResponse(BaseModel):
    access_token: str | None  # None after a password change with Supabase Auth, or while mfa_required
    mfa_required: bool = False  # admin with two-step login: send the code to /auth/login/mfa with mfa_token
    mfa_token: str | None = None
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
