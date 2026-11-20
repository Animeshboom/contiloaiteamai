"""External notification channels that run alongside in-app notifications (WhatsApp, SMS, …).

Every new in-app notification is offered to each registered channel, which decides whether to deliver it
(for example only "leave_approved", to ``user.phone``). Nothing is registered yet: WhatsApp is
planned. A channel must not send synchronously inside the request; it should queue its own outbox row
(like ``email_service.enqueue``) and let a background job deliver it.

To add one:
    class WhatsAppChannel:
        name = "whatsapp"
        def deliver(self, db, notification, user): ...queue a message for user.phone...
    CHANNELS.append(WhatsAppChannel())
"""
import logging
from typing import Protocol

from sqlalchemy.orm import Session

from app.models import Notification, User

log = logging.getLogger("studiotrack.channels")


class Channel(Protocol):
    name: str

    def deliver(self, db: Session, notification: Notification, user: User) -> None: ...


CHANNELS: list[Channel] = []


def deliver(db: Session, notification: Notification) -> None:
    if not CHANNELS:
        return
    user = db.get(User, notification.user_id)
    if user is None or not user.is_active:
        return
    for channel in CHANNELS:
        try:
            channel.deliver(db, notification, user)
        except Exception:  # a broken channel must never break the in-app notification
            log.exception("channel %s failed for notification %s", channel.name, notification.id)
