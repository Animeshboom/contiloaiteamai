from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import ReportStatus


class ReportGenerate(BaseModel):
    report_date: date | None = None  # default: studio today
    project_id: int | None = None
    episode_id: int | None = None
    artist_id: int | None = None
    team_id: int | None = None  # admin only
    use_ai: bool = True


class ReportUpdate(BaseModel):
    """Team lead edits the email before approving."""
    subject: str | None = Field(default=None, min_length=3, max_length=300)
    body: str | None = Field(default=None, min_length=10, max_length=100_000)
    recipients: list[EmailStr] | None = Field(default=None, max_length=50)


class ReportApprove(BaseModel):
    recipients: list[EmailStr] = Field(min_length=1, max_length=50)


class ReportListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    report_date: date
    status: ReportStatus
    subject: str
    recipients: list[str]
    ai_status: str | None
    created_by_name: str
    created_at: datetime
    approved_at: datetime | None
    sent_at: datetime | None
    sent_by_name: str | None
    delivery_status: str | None
    filters: dict


class ReportOut(ReportListItem):
    metrics: dict
    narrative: dict
    ai_note: str | None
    body: str
    approved_by_name: str | None
    gmail_message_id: str | None
    gmail_draft_id: str | None
    email_error: str | None = None
