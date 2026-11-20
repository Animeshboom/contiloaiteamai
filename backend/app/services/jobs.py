"""Periodic jobs: deadline reminders, closing forgotten check-outs, and the email outbox dispatcher.

Both are idempotent (dedupe/idempotency keys), so running them more than once — or on
several app instances — never duplicates notifications or emails.
"""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.timeutils import utcnow
from app.models import Assignment, AssignmentAssignee, AssignmentStatus
from app.services import attendance_service, chat_service, email_service, lead_service, notification_service

log = logging.getLogger("studiotrack.jobs")

OPEN = [AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS, AssignmentStatus.REVISION_REQUIRED]


def send_deadline_reminders() -> int:
    """Remind artists whose open work is due within DEADLINE_REMINDER_HOURS."""
    now = utcnow()
    horizon = now + timedelta(hours=get_settings().deadline_reminder_hours)
    created = 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(AssignmentAssignee).join(Assignment)
            .where(Assignment.deleted_at.is_(None), Assignment.deadline > now, Assignment.deadline <= horizon,
                   AssignmentAssignee.status.in_(OPEN))
        ).all()
        for x in rows:
            if notification_service.deadline_approaching(db, x):
                created += 1
        db.commit()
    return created


def close_stale_attendance() -> int:
    with SessionLocal() as db:
        closed = attendance_service.auto_close_stale(db)
        chat_service.purge_old(db)  # chat history is kept CHAT_RETENTION_DAYS
        return closed


def send_teacher_summaries() -> int:
    with SessionLocal() as db:
        return (lead_service.send_noon_summaries(db) + lead_service.send_evening_summaries(db)
                + lead_service.send_report_reminders(db))


async def run_forever(stop: asyncio.Event, dispatch_every: float = 30, reminders_every: float = 300) -> None:
    last_reminders = 0.0
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        try:
            if loop.time() - last_reminders >= reminders_every:
                n = await asyncio.to_thread(send_deadline_reminders)
                last_reminders = loop.time()
                if n:
                    log.info("queued %d deadline reminder(s)", n)
                closed = await asyncio.to_thread(close_stale_attendance)
                if closed:
                    log.info("auto-closed %d attendance record(s) with no check-out", closed)
                summaries = await asyncio.to_thread(send_teacher_summaries)
                if summaries:
                    log.info("sent %d batch attendance summar(ies)", summaries)
            stats = await email_service.dispatch_pending()
            if any(stats.values()):
                log.info("email dispatch: %s", stats)
        except Exception:  # never let the loop die
            log.exception("background job failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=dispatch_every)
        except asyncio.TimeoutError:
            pass
