"""Studio chat: automatic group channels, live delivery, 90-day history.

Channels (never created by hand; membership follows teams and roles):
- ``everyone``    — the whole studio. Only admins and team leads post; everyone reads.
- ``leads``       — all team leads and admins.
- ``team:<id>``   — one per team: its lead, its artists, and the admins.

Messages are plain text (links become clickable in the app). Authors can edit or delete their own message for
15 minutes; admins can delete any message. Messages older than CHAT_RETENTION_DAYS (90) are deleted daily.
Live delivery: connected browsers get new/edited/deleted messages over Server-Sent Events (see ``hub``).
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.core.timeutils import ensure_utc, utcnow
from app.models import ChatMessage, ChatRead, RoleName, Team, User
from app.services import audit, scope

log = logging.getLogger("studiotrack.chat")
EDIT_WINDOW = timedelta(minutes=15)
PAGE = 50


@dataclass
class Channel:
    key: str
    name: str
    kind: str  # everyone | leads | team
    can_post: bool


# ---------------- membership ----------------

def channels_for(db: Session, user: User) -> list[Channel]:
    is_admin, is_lead = scope.is_admin(user), scope.is_lead(user)
    out = [Channel("everyone", "Everyone", "everyone", is_admin or is_lead)]
    if is_admin or is_lead:
        out.append(Channel("leads", "Leads & Admin", "leads", True))
    if is_admin:
        teams = list(db.scalars(select(Team).where(Team.deleted_at.is_(None)).order_by(Team.name)))
    else:
        ids = scope.lead_team_ids(db, user) if is_lead else set()
        if user.team_id:
            ids = set(ids) | {user.team_id}
        teams = list(db.scalars(select(Team).where(Team.id.in_(ids or {-1}), Team.deleted_at.is_(None))
                                .order_by(Team.name)))
    out += [Channel(f"team:{t.id}", t.name, "team", True) for t in teams]
    return out


def _channel(db: Session, user: User, key: str) -> Channel:
    ch = next((c for c in channels_for(db, user) if c.key == key), None)
    if ch is None:
        raise NotFound("Chat not found")
    return ch


def channel_keys(db: Session, user: User) -> set[str]:
    return {c.key for c in channels_for(db, user)}


# ---------------- messages ----------------

def _out(m: ChatMessage, names: dict[int, str]) -> dict:
    deleted = m.deleted_at is not None
    return {"id": m.id, "channel": m.channel, "sender_id": m.sender_id, "sender": names.get(m.sender_id, "—"),
            "body": None if deleted else m.body, "created_at": m.created_at, "edited_at": m.edited_at,
            "deleted": deleted}


def _names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids or {-1}))).all())


def list_messages(db: Session, user: User, key: str, before_id: int | None = None, limit: int = PAGE) -> list[dict]:
    _channel(db, user, key)
    q = select(ChatMessage).where(ChatMessage.channel == key)
    if before_id:
        q = q.where(ChatMessage.id < before_id)
    rows = list(db.scalars(q.order_by(ChatMessage.id.desc()).limit(min(limit, 100))))[::-1]
    names = _names(db, {m.sender_id for m in rows})
    return [_out(m, names) for m in rows]


def post(db: Session, user: User, key: str, body: str) -> dict:
    ch = _channel(db, user, key)
    if not ch.can_post:
        raise Forbidden("Only team leads and admins can post here")
    body = body.strip()
    if not body:
        raise ValidationFailed("Write a message first")
    m = ChatMessage(channel=key, sender_id=user.id, body=body)
    db.add(m)
    db.flush()
    _mark_read(db, user, key, m.id)
    db.commit()
    out = _out(m, {user.id: user.full_name})
    hub.publish(key, "message", out)
    return out


def _own_editable(db: Session, user: User, message_id: int) -> ChatMessage:
    m = db.get(ChatMessage, message_id)
    if not m or m.deleted_at is not None:
        raise NotFound("Message not found")
    _channel(db, user, m.channel)
    return m


def edit(db: Session, user: User, message_id: int, body: str) -> dict:
    m = _own_editable(db, user, message_id)
    if m.sender_id != user.id:
        raise Forbidden("You can only edit your own messages")
    if utcnow() - ensure_utc(m.created_at) > EDIT_WINDOW:
        raise Forbidden("Messages can be edited for 15 minutes")
    body = body.strip()
    if not body:
        raise ValidationFailed("Write a message first")
    m.body, m.edited_at = body, utcnow()
    db.commit()
    out = _out(m, _names(db, {m.sender_id}))
    hub.publish(m.channel, "edit", out)
    return out


def remove(db: Session, user: User, message_id: int, ip: str | None) -> None:
    m = _own_editable(db, user, message_id)
    own = m.sender_id == user.id
    if own and utcnow() - ensure_utc(m.created_at) > EDIT_WINDOW and not scope.is_admin(user):
        raise Forbidden("Messages can be deleted for 15 minutes")
    if not own and not scope.is_admin(user):
        raise Forbidden("Only an administrator can delete other people's messages")
    m.deleted_at, m.deleted_by_id = utcnow(), user.id
    audit.record(db, actor_id=user.id, action="chat.delete", entity_type="chat_message", entity_id=m.id,
                 before={"channel": m.channel, "sender_id": m.sender_id, "body": m.body}, ip=ip)
    db.commit()
    hub.publish(m.channel, "delete", {"id": m.id, "channel": m.channel})


# ---------------- unread ----------------

def _mark_read(db: Session, user: User, key: str, last_id: int) -> None:
    r = db.get(ChatRead, (user.id, key))
    if r is None:
        db.add(ChatRead(user_id=user.id, channel=key, last_read_id=last_id))
    elif last_id > r.last_read_id:
        r.last_read_id = last_id


def mark_read(db: Session, user: User, key: str, last_id: int) -> None:
    _channel(db, user, key)
    _mark_read(db, user, key, last_id)
    db.commit()


def overview(db: Session, user: User) -> list[dict]:
    """Each chat with its unread count and latest message, for the chat list."""
    chans = channels_for(db, user)
    keys = [c.key for c in chans]
    reads = {r.channel: r.last_read_id for r in db.scalars(select(ChatRead).where(
        ChatRead.user_id == user.id, ChatRead.channel.in_(keys or ["-"])))}
    out = []
    for c in chans:
        unread = db.scalar(select(func.count(ChatMessage.id)).where(
            ChatMessage.channel == c.key, ChatMessage.id > reads.get(c.key, 0), ChatMessage.deleted_at.is_(None),
            ChatMessage.sender_id != user.id)) or 0
        last = db.scalar(select(ChatMessage).where(ChatMessage.channel == c.key).order_by(ChatMessage.id.desc()).limit(1))
        out.append({"key": c.key, "name": c.name, "kind": c.kind, "can_post": c.can_post, "unread": unread,
                    "last_message": _out(last, _names(db, {last.sender_id})) if last else None})
    return out


def unread_total(db: Session, user: User) -> int:
    return sum(c["unread"] for c in overview(db, user))


# ---------------- retention (background job) ----------------

def purge_old(db: Session) -> int:
    cutoff = utcnow() - timedelta(days=get_settings().chat_retention_days)
    n = db.execute(delete(ChatMessage).where(ChatMessage.created_at < cutoff)).rowcount or 0
    db.commit()
    return n


# ---------------- live delivery (Server-Sent Events) ----------------

class Hub:
    """In-process fan-out to connected browsers. Each connection has a queue and the channel keys it may see.
    Runs in a single API process (Render/Docker as configured); browsers fall back to polling if a
    connection drops."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.subscribers: dict[asyncio.Queue, set[str]] = {}

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self, keys: set[str]) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.subscribers[q] = keys
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.pop(q, None)

    def publish(self, key: str, event: str, data: dict) -> None:
        if self.loop is None:
            return
        for q, keys in list(self.subscribers.items()):
            if key in keys:
                self.loop.call_soon_threadsafe(self._offer, q, (event, data))

    @staticmethod
    def _offer(q: asyncio.Queue, item) -> None:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:  # a stuck browser; it will resync by polling
            pass


hub = Hub()
