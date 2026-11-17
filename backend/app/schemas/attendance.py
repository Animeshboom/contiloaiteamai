from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import AttendanceStatus


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    work_date: date
    check_in_at: datetime | None
    check_out_at: datetime | None
    status: AttendanceStatus
    notes: str | None
    corrected_by_id: int | None
    corrected_at: datetime | None
    worked_minutes: int | None = None


class TodayStatus(BaseModel):
    work_date: date
    record: AttendanceOut | None
    can_check_in: bool
    can_check_out: bool


class RosterRow(BaseModel):
    user_id: int
    full_name: str
    job_title: str | None
    team_name: str | None
    # "not_checked_in" is a derived display state for today, never stored.
    status: str
    record: AttendanceOut | None


class AttendanceCorrection(BaseModel):
    user_id: int
    work_date: date
    status: AttendanceStatus
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def _times(self):
        if self.check_out_at and not self.check_in_at:
            raise ValueError("A check-out time requires a check-in time")
        if self.check_in_at and self.check_out_at and self.check_out_at <= self.check_in_at:
            raise ValueError("Check-out must be after check-in")
        return self


class DailyCount(BaseModel):
    date: date
    present: int
    half_day: int
    leave: int
    absent: int
