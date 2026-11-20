"""Team-lead tools: Today list, reassigning, weekly targets, feedback phrases."""
from datetime import date

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, require_admin, require_artist, require_lead_or_admin
from app.models import User
from app.schemas.assignments import AssignmentOut
from app.services import assignment_service, lead_service

router = APIRouter(tags=["team lead"])


class ReassignBody(BaseModel):
    from_user_id: int
    to_user_id: int
    note: str | None = Field(default=None, max_length=500)


class TargetBody(BaseModel):
    scenes_per_week: int | None = Field(default=None, ge=1, le=200)  # null removes the target


class TargetOut(BaseModel):
    week_start: date
    week_end: date
    target: int | None
    approved: int


class PhraseBody(BaseModel):
    text: str = Field(min_length=2, max_length=200)


class PhraseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str


@router.get("/lead/today")
def lead_today(actor: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """Things that need the lead now: reviews waiting, leave requests, overdue / due today, absent people."""
    return lead_service.today(db, actor)


@router.post("/assignments/{assignment_id}/reassign", response_model=AssignmentOut)
def reassign(assignment_id: int, body: ReassignBody, request: Request, actor: User = Depends(require_lead_or_admin),
             db: Session = Depends(get_db)):
    """Move one person's unfinished part to someone else; earlier submissions stay in history."""
    a = lead_service.reassign(db, actor, assignment_id, body.from_user_id, body.to_user_id, body.note,
                              client_ip(request))
    return assignment_service.to_out(db, a)


@router.put("/targets/{user_id}", response_model=TargetOut)
def set_target(user_id: int, body: TargetBody, request: Request, actor: User = Depends(require_lead_or_admin),
               db: Session = Depends(get_db)):
    """Approved scenes per week expected from one of the lead's people (null clears it)."""
    return lead_service.set_target(db, actor, user_id, body.scenes_per_week, client_ip(request))


@router.get("/me/target", response_model=TargetOut)
def my_target(user: User = Depends(require_artist), db: Session = Depends(get_db)):
    """This week's target and approved scenes so far (Mon–Sun, studio time)."""
    return lead_service.my_target(db, user)


@router.get("/feedback-phrases", response_model=list[PhraseOut])
def list_phrases(_: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    return lead_service.list_phrases(db)


@router.post("/feedback-phrases", response_model=PhraseOut, status_code=status.HTTP_201_CREATED)
def add_phrase(body: PhraseBody, request: Request, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    return lead_service.add_phrase(db, actor, body.text, client_ip(request))


@router.delete("/feedback-phrases/{phrase_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_phrase(phrase_id: int, request: Request, actor: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    lead_service.delete_phrase(db, actor, phrase_id, client_ip(request))
