"""Audit trail. Called inside the caller's transaction so the audit row commits atomically."""
from datetime import date, datetime
from enum import Enum

from sqlalchemy.orm import Session

from app.models import AuditLog

_SENSITIVE = {"password", "password_hash", "token", "access_token", "secret"}


def _clean(data: dict | None) -> dict | None:
    if data is None:
        return None
    out = {}
    for k, v in data.items():
        if k in _SENSITIVE:
            continue
        if isinstance(v, (datetime, date)):
            v = v.isoformat()
        elif isinstance(v, Enum):
            v = v.value
        out[k] = v
    return out


def record(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=_clean(before),
        after=_clean(after),
        ip_address=ip,
    )
    db.add(entry)
    return entry
