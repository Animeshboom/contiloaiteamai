"""Artist accounts (admin) and leave requests (everyone; leads/admins decide)."""
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, get_current_user, require_admin, require_lead_or_admin
from app.core.errors import ValidationFailed
from app.models import LeaveStatus, User
from app.schemas.artists import ArtistCreate, Credentials, ImportResult, LeaveCreate, LeaveDecision, LeaveOut
from app.services import artist_service as svc

artists = APIRouter(prefix="/artists", tags=["artist accounts"])
leave = APIRouter(tags=["leave"])

MAX_CSV_BYTES = 2 * 1024 * 1024


@artists.post("", response_model=Credentials, status_code=status.HTTP_201_CREATED)
def create_artist(body: ArtistCreate, request: Request, actor: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """Email, or an Employee ID (auto-numbered EMP001… when both are left empty). The password is shown once."""
    return svc.create_artist(db, actor, body, client_ip(request))


@artists.post("/import", response_model=ImportResult)
async def import_artists(request: Request, file: UploadFile = File(...), team_id: int | None = Form(default=None),
                         actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    """CSV: name, and email or employee_id (or neither: auto ID); optional team, job_title, phone, password.
    Valid rows are created even if others fail; each new password is shown once."""
    content = await file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise ValidationFailed("The CSV file is too large (max 2 MB)")
    return svc.import_csv(db, actor, content, client_ip(request), default_team_id=team_id)


@artists.post("/{user_id}/reset-password", response_model=Credentials)
def reset_password(user_id: int, request: Request, actor: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """Generates a new password and shows it once. The person is signed out everywhere."""
    return svc.reset_password(db, actor, user_id, client_ip(request))


@leave.get("/me/leave", response_model=list[LeaveOut])
def my_leave(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.my_leave(db, user)


@leave.post("/me/leave", response_model=LeaveOut, status_code=status.HTTP_201_CREATED)
def request_leave(body: LeaveCreate, request: Request, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Any date range, past or future. Artists' requests go to their team lead; leads' requests to the admin."""
    return svc.request_leave(db, user, body, client_ip(request))


@leave.post("/me/leave/{leave_id}/cancel", response_model=LeaveOut)
def cancel_leave(leave_id: int, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return svc.cancel_leave(db, user, leave_id, client_ip(request))


@leave.get("/leave", response_model=list[LeaveOut])
def list_leave(status_: LeaveStatus | None = Query(default=None, alias="status"), team_id: int | None = None,
               actor: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """Leads: their team's artists. Admins: everyone (including leads' own requests)."""
    return svc.list_leave(db, actor, status=status_, team_id=team_id)


@leave.post("/leave/{leave_id}/decide", response_model=LeaveOut)
def decide_leave(leave_id: int, body: LeaveDecision, request: Request, actor: User = Depends(require_lead_or_admin),
                 db: Session = Depends(get_db)):
    """Approve, or reject with a note. A team lead's own leave is decided by an admin."""
    return svc.decide_leave(db, actor, leave_id, body, client_ip(request))
