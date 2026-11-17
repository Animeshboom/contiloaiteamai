"""Employees, teams and authorized recipients."""
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, require_admin, require_lead_or_admin
from app.models import RoleName, User
from app.schemas.org import (
    PasswordReset, RecipientCreate, RecipientOut, RecipientUpdate, TeamCreate, TeamOut, TeamUpdate, UserCreate,
    UserOut, UserUpdate,
)
from app.services import org_service

users = APIRouter(prefix="/users", tags=["employees"])
teams = APIRouter(prefix="/teams", tags=["teams"])
recipients = APIRouter(prefix="/recipients", tags=["authorized recipients"])


@users.get("", response_model=list[UserOut])
def list_users(
    role: RoleName | None = None,
    team_id: int | None = None,
    include_inactive: bool = False,
    search: str | None = Query(default=None, max_length=100),
    actor: User = Depends(require_lead_or_admin),
    db: Session = Depends(get_db),
):
    """Admins see everyone; team leads see members of their teams."""
    return org_service.list_users(db, actor, role=role, team_id=team_id,
                                  include_inactive=include_inactive, search=search)


@users.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, actor: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    return org_service.get_user(db, actor, user_id)


@users.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, request: Request, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    return org_service.create_user(db, actor, body, client_ip(request))


@users.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, actor: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    return org_service.update_user(db, actor, user_id, body, client_ip(request))


@users.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate(user_id: int, request: Request, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    return org_service.set_active(db, actor, user_id, False, client_ip(request))


@users.post("/{user_id}/activate", response_model=UserOut)
def activate(user_id: int, request: Request, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    return org_service.set_active(db, actor, user_id, True, client_ip(request))


@users.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(user_id: int, body: PasswordReset, request: Request, actor: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    org_service.reset_password(db, actor, user_id, body.new_password, client_ip(request))


@teams.get("", response_model=list[TeamOut])
def list_teams(actor: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    return org_service.list_teams(db, actor)


@teams.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(body: TeamCreate, request: Request, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    return org_service.create_team(db, actor, body, client_ip(request))


@teams.patch("/{team_id}", response_model=TeamOut)
def update_team(team_id: int, body: TeamUpdate, request: Request, actor: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    return org_service.update_team(db, actor, team_id, body, client_ip(request))


@teams.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: int, request: Request, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    org_service.delete_team(db, actor, team_id, client_ip(request))


@recipients.get("", response_model=list[RecipientOut])
def list_recipients(active_only: bool = False, _: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    return org_service.list_recipients(db, active_only)


@recipients.post("", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
def create_recipient(body: RecipientCreate, request: Request, actor: User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    return org_service.create_recipient(db, actor, body, client_ip(request))


@recipients.patch("/{recipient_id}", response_model=RecipientOut)
def update_recipient(recipient_id: int, body: RecipientUpdate, request: Request, actor: User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    return org_service.update_recipient(db, actor, recipient_id, body, client_ip(request))
