"""Announcements (team leads: their teams; admins: everyone or chosen teams)."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, get_current_user, require_lead_or_admin
from app.models import User
from app.services import announcement_service as svc

router = APIRouter(prefix="/announcements", tags=["announcements"])
me = APIRouter(tags=["announcements"])


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    team_ids: list[int] = []  # empty = everyone (admins only)
    show_until: date | None = None


class TeamRef(BaseModel):
    id: int
    name: str


class AnnouncementOut(BaseModel):
    id: int
    title: str
    body: str
    author: str | None
    author_id: int | None
    applies_to_all: bool
    teams: list[TeamRef]
    show_until: date | None
    created_at: datetime
    active: bool


@router.get("", response_model=list[AnnouncementOut])
def list_announcements(include_expired: bool = False, actor: User = Depends(require_lead_or_admin),
                       db: Session = Depends(get_db)):
    return svc.list_for_manager(db, actor, include_expired)


@router.post("", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
def create_announcement(body: AnnouncementCreate, request: Request, actor: User = Depends(require_lead_or_admin),
                        db: Session = Depends(get_db)):
    return svc.create(db, actor, body.title, body.body, body.team_ids, body.show_until, client_ip(request))


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement(announcement_id: int, request: Request, actor: User = Depends(require_lead_or_admin),
                        db: Session = Depends(get_db)):
    svc.delete(db, actor, announcement_id, client_ip(request))


@me.get("/me/announcements", response_model=list[AnnouncementOut])
def my_announcements(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Active announcements for the person's team or everyone, newest first (max 10)."""
    return svc.list_for_person(db, user)
