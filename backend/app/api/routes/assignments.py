from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, get_current_user, require_lead_or_admin
from app.core.timeutils import utcnow
from app.models import AssignmentStatus, Priority, User
from app.schemas.assignments import AssignmentCreate, AssignmentOut, AssignmentUpdate
from app.services import assignment_service as svc
from app.services import scope

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.get("", response_model=list[AssignmentOut])
def list_assignments(
    status_: AssignmentStatus | None = Query(default=None, alias="status"),
    project_id: int | None = None,
    artist_id: int | None = None,
    on_date: date | None = None,
    overdue: bool = False,
    priority: Priority | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Scoped to the caller: artists get their own, leads get their team's, admins get all."""
    now = utcnow()
    rows = svc.list_for(db, user, status=status_, project_id=project_id, artist_id=artist_id, on_date=on_date,
                        overdue=overdue, priority=priority)
    return [svc.to_out(db, a, now) for a in rows]


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(body: AssignmentCreate, request: Request, user: User = Depends(require_lead_or_admin),
                      db: Session = Depends(get_db)):
    return svc.to_out(db, svc.create(db, user, body, client_ip(request)))


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.to_out(db, scope.get_assignment_for_view(db, user, assignment_id))


@router.patch("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(assignment_id: int, body: AssignmentUpdate, request: Request,
                      user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    return svc.to_out(db, svc.update(db, user, assignment_id, body, client_ip(request)))


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(assignment_id: int, request: Request, user: User = Depends(require_lead_or_admin),
                      db: Session = Depends(get_db)):
    svc.delete(db, user, assignment_id, client_ip(request))
