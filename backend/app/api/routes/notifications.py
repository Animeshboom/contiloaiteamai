from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_any_user, require_admin
from app.core.errors import Conflict, NotFound
from app.core.timeutils import utcnow
from app.models import EmailLog, EmailStatus, Notification, User
from app.services import email_service

router = APIRouter(tags=["notifications & email"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: str
    title: str
    message: str
    link: str | None
    entity_type: str | None
    entity_id: int | None
    read_at: datetime | None
    created_at: datetime


class EmailLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tool_name: str
    provider: str
    recipients: list[str]
    subject: str
    status: EmailStatus
    provider_message_id: str | None
    error: str | None
    attempts: int
    entity_type: str | None
    entity_id: int | None
    created_at: datetime
    last_attempt_at: datetime | None
    next_attempt_at: datetime | None
    sent_at: datetime | None


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(unread_only: bool = False, limit: int = Query(default=50, ge=1, le=200),
                       user: User = Depends(get_any_user), db: Session = Depends(get_db)):
    q = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    return db.scalars(q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()


@router.get("/notifications/unread-count")
def unread_count(user: User = Depends(get_any_user), db: Session = Depends(get_db)):
    n = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return {"unread": n or 0}


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, user: User = Depends(get_any_user), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:  # never reveal other users' notifications
        raise NotFound("Notification not found")
    if n.read_at is None:
        n.read_at = utcnow()
        db.commit()
    return n


@router.post("/notifications/read-all")
def mark_all_read(user: User = Depends(get_any_user), db: Session = Depends(get_db)):
    res = db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
                     .values(read_at=utcnow()))
    db.commit()
    return {"updated": res.rowcount}


@router.get("/email-logs", response_model=list[EmailLogOut])
def email_logs(status: EmailStatus | None = None, limit: int = Query(default=100, ge=1, le=500),
               _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Delivery audit trail (admin). Message bodies are not exposed here."""
    q = select(EmailLog)
    if status:
        q = q.where(EmailLog.status == status)
    return db.scalars(q.order_by(EmailLog.id.desc()).limit(limit)).all()


@router.post("/email-logs/{log_id}/retry", response_model=EmailLogOut)
async def retry_email(log_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(EmailLog, log_id)
    if not row:
        raise NotFound("Email log not found")
    try:
        email_service.retry(db, row)
    except ValueError as e:
        raise Conflict(str(e)) from e
    return await email_service.deliver_now(row.id)
