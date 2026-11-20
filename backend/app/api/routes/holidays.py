"""Holidays: days off for everyone, or for chosen teams only."""
from datetime import date

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, require_admin, require_lead_or_admin
from app.models import User
from app.services import calendar

router = APIRouter(prefix="/holidays", tags=["holidays"])


class HolidayCreate(BaseModel):
    date: date
    name: str = Field(min_length=2, max_length=120)
    team_ids: list[int] = []  # empty = everyone


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class HolidayOut(BaseModel):
    id: int
    date: date
    name: str
    applies_to_all: bool
    teams: list[TeamRef]


def _out(h) -> HolidayOut:
    return HolidayOut(id=h.id, date=h.day, name=h.name, applies_to_all=h.applies_to_all,
                      teams=[TeamRef.model_validate(t) for t in h.teams])


@router.get("", response_model=list[HolidayOut])
def list_holidays(year: int | None = None, _: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    return [_out(h) for h in calendar.list_holidays(db, year)]


@router.post("", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def create_holiday(body: HolidayCreate, request: Request, actor: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    return _out(calendar.create_holiday(db, actor, body.date, body.name, body.team_ids, client_ip(request)))


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(holiday_id: int, request: Request, actor: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    calendar.delete_holiday(db, actor, holiday_id, client_ip(request))
