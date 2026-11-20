"""Studio chat: channels, messages, unread counts and a live stream (Server-Sent Events)."""
import asyncio
import json
from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.deps import client_ip, get_current_user
from app.core.errors import Unauthorized
from app.core.rate_limit import limiter
from app.core.timeutils import utcnow
from app.models import User
from app.services import chat_service as svc

router = APIRouter(prefix="/chat", tags=["chat"])


class MessageBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ReadBody(BaseModel):
    last_id: int


@router.get("/channels")
def channels(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The person's chats (Everyone, Leads & Admin, their team groups) with unread counts and the last message."""
    return svc.overview(db, user)


@router.get("/unread")
def unread(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"unread": svc.unread_total(db, user)}


@router.get("/channels/{key}/messages")
def messages(key: str, before_id: int | None = None, limit: int = Query(default=50, ge=1, le=100),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Oldest first within the page; pass before_id to load older messages."""
    return svc.list_messages(db, user, key, before_id, limit)


@router.post("/channels/{key}/messages", status_code=201)
@limiter.limit("30/minute")
def post_message(request: Request, key: str, body: MessageBody, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return svc.post(db, user, key, body.body)


@router.post("/channels/{key}/read", status_code=204)
def mark_read(key: str, body: ReadBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.mark_read(db, user, key, body.last_id)


@router.patch("/messages/{message_id}")
def edit_message(message_id: int, body: MessageBody, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Own messages, within 15 minutes."""
    return svc.edit(db, user, message_id, body.body)


@router.delete("/messages/{message_id}", status_code=204)
def delete_message(message_id: int, request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Own messages within 15 minutes; admins: any message."""
    svc.remove(db, user, message_id, client_ip(request))


# ---------------- live stream ----------------

@router.post("/stream-ticket")
def stream_ticket(user: User = Depends(get_current_user)):
    """A 60-second ticket for opening the live stream (browsers can't send headers with EventSource, and
    putting the real sign-in token in a URL would leak it into logs)."""
    s = get_settings()
    now = utcnow()
    ticket = jwt.encode({"sub": str(user.id), "tv": user.token_version, "type": "chat_stream", "iat": now,
                         "exp": now + timedelta(seconds=60)}, s.jwt_secret_key, algorithm=s.jwt_algorithm)
    return {"ticket": ticket}


@router.get("/stream")
async def stream(ticket: str, request: Request):
    s = get_settings()
    try:
        claims = jwt.decode(ticket, s.jwt_secret_key, algorithms=[s.jwt_algorithm], options={"require": ["sub", "exp"]})
        if claims.get("type") != "chat_stream":
            raise jwt.InvalidTokenError("wrong ticket")
    except jwt.PyJWTError:
        raise Unauthorized("Invalid or expired chat ticket")
    with SessionLocal() as db:
        user = db.get(User, int(claims["sub"]))
        if not user or not user.is_active or user.token_version != claims.get("tv"):
            raise Unauthorized("Sign in again")
        keys = svc.channel_keys(db, user)

    q = svc.hub.subscribe(keys)

    async def events():
        try:
            yield "retry: 5000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            svc.hub.unsubscribe(q)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
