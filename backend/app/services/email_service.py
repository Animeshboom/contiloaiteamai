"""Email outbox + dispatcher.

``enqueue`` writes an EmailLog row (status=pending) inside the caller's transaction, keyed by a
unique idempotency key — a retried event can never queue a second email. ``dispatch_pending``
claims due rows with a short lease (so concurrent dispatchers never double-send), calls the
Gmail MCP tool, and records the outcome. Failures back off exponentially; policy blocks are final.
"""
import logging
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.timeutils import utcnow
from app.models import EmailLog, EmailStatus
from app.services.email_gateway import DeliveryResult, GatewayError, open_gateway

log = logging.getLogger("studiotrack.email")

LEASE = timedelta(minutes=5)


def enqueue(db: Session, *, tool: str, args: dict, idempotency_key: str, recipients: list[str], subject: str,
            preview: str, entity_type: str | None = None, entity_id: int | None = None,
            triggered_by_id: int | None = None) -> EmailLog | None:
    """Queue an email. Returns None if this exact email was already queued (idempotent), or if email is
    turned off (EMAIL_ENABLED=false): notifications are then in-app only and nothing is queued."""
    if not get_settings().email_enabled:
        return None
    existing = db.scalar(select(EmailLog).where(EmailLog.idempotency_key == idempotency_key))
    if existing:
        return None
    row = EmailLog(
        idempotency_key=idempotency_key, tool_name=tool, provider=get_settings().email_provider,
        recipients=recipients, subject=subject[:300], body_preview=preview[:500], status=EmailStatus.PENDING,
        payload=args, entity_type=entity_type, entity_id=entity_id, triggered_by_id=triggered_by_id,
        attempts=0, next_attempt_at=utcnow(),
    )
    db.add(row)
    return row


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(60, 2 ** attempts))  # 2, 4, 8, 16, 32, 60 min


def _claim(db: Session, limit: int, only_id: int | None) -> list[EmailLog]:
    now = utcnow()
    q = select(EmailLog).where(
        EmailLog.status.in_([EmailStatus.PENDING, EmailStatus.FAILED]),
        EmailLog.attempts < get_settings().email_max_attempts,
        or_(EmailLog.next_attempt_at.is_(None), EmailLog.next_attempt_at <= now),
    ).order_by(EmailLog.id).limit(limit)
    if only_id is not None:
        q = q.where(EmailLog.id == only_id)
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    rows = list(db.scalars(q))
    for r in rows:  # lease: other dispatchers skip these until the lease expires
        r.attempts += 1
        r.last_attempt_at = now
        r.next_attempt_at = now + LEASE
        r.provider = get_settings().email_provider
    db.commit()
    return rows


def _record_success(row: EmailLog, res: DeliveryResult) -> None:
    row.status = EmailStatus.DRAFTED if res.status == "drafted" else EmailStatus.SENT
    row.provider_message_id = res.message_id or res.draft_id
    row.provider = f"{get_settings().email_provider}:{res.backend}"
    row.sent_at = utcnow()
    row.next_attempt_at = None
    row.error = None


def _give_up_abandoned(db: Session) -> None:
    """Rows claimed for their last attempt whose dispatcher died mid-batch stay PENDING with no attempts
    left, so nothing would ever pick them up again. Mark them FAILED so an admin can see and retry them."""
    abandoned = db.scalars(select(EmailLog).where(
        EmailLog.status == EmailStatus.PENDING,
        EmailLog.attempts >= get_settings().email_max_attempts,
        EmailLog.next_attempt_at <= utcnow(),
    )).all()
    for row in abandoned:
        row.status = EmailStatus.FAILED
        row.next_attempt_at = None
        row.error = row.error or "failed: delivery was interrupted on every attempt"
    if abandoned:
        db.commit()
        log.error("gave up on %d interrupted email(s)", len(abandoned))


def _as_gateway_error(e: Exception) -> GatewayError:
    return e if isinstance(e, GatewayError) else GatewayError("retryable", f"{type(e).__name__}: {e}")


def _record_failure(row: EmailLog, err: GatewayError) -> None:
    row.error = f"{err.kind}: {err}"[:2000]
    if err.kind == "blocked":
        row.status = EmailStatus.BLOCKED
        row.next_attempt_at = None
    else:
        row.status = EmailStatus.FAILED
        final = row.attempts >= get_settings().email_max_attempts
        row.next_attempt_at = None if final else utcnow() + _backoff(row.attempts)


async def dispatch_pending(limit: int = 25, only_id: int | None = None) -> dict[str, int]:
    """Deliver due emails. Safe to call concurrently and repeatedly."""
    stats = {"sent": 0, "failed": 0, "blocked": 0}
    if not get_settings().email_enabled or not get_settings().email_configured:
        return stats  # Gmail not set up yet: leave emails pending (not failed) until it is
    with SessionLocal() as db:
        _give_up_abandoned(db)
        rows = _claim(db, limit, only_id)
        if not rows:
            return stats
        done: set[int] = set()
        try:
            async with open_gateway() as gw:
                for row in rows:
                    try:
                        res = await gw.call(row.tool_name, {**row.payload, "idempotency_key": row.idempotency_key})
                        _record_success(row, res)
                        stats["sent"] += 1
                    except Exception as e:  # never let one email strand the rest of the batch
                        err = _as_gateway_error(e)
                        _record_failure(row, err)
                        stats["blocked" if err.kind == "blocked" else "failed"] += 1
                        log.warning("email %s (%s) %s", row.id, row.tool_name, row.error)
                    done.add(row.id)
                    db.commit()
        except Exception as e:  # could not open (or cleanly close) the gateway
            err = _as_gateway_error(e)
            for row in rows:
                if row.id not in done:
                    _record_failure(row, err)
                    stats["failed"] += 1
            db.commit()
            log.error("email gateway unavailable: %s", err)
    return stats


async def deliver_now(row_id: int) -> EmailLog:
    """Synchronous-path delivery for one row (e.g. a lead clicking 'Send report')."""
    await dispatch_pending(limit=1, only_id=row_id)
    with SessionLocal() as db:
        return db.get(EmailLog, row_id)


def retry(db: Session, row: EmailLog) -> None:
    """Admin re-queues a failed email (blocked emails stay blocked: the policy said no)."""
    if row.status != EmailStatus.FAILED:
        raise ValueError("Only failed emails can be retried")
    row.attempts = 0
    row.next_attempt_at = utcnow()
    db.commit()
