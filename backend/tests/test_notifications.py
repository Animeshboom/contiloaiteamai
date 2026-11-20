import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.models import Assignment, AssignmentAssignee, EmailLog, EmailStatus, Episode, Notification, Project, Scene, User
from app.services import email_service, jobs, notification_service
from app.services.email_gateway import GatewayError
from tests.conftest import ARTIST, LEAD, LEAD_OTHER, login, uid


def outbox() -> list[Path]:
    d = Path(get_settings().mail_outbox_dir)
    return sorted(d.glob("*.eml")) if d.exists() else []


def _assign(client, lead, db, n=2, **kw):
    p = db.scalar(select(Project).where(Project.code == "NEON-01"))
    ep = db.scalar(select(Episode).where(Episode.project_id == p.id, Episode.episode_number == 1))
    scenes = list(db.scalars(select(Scene).where(Scene.episode_id == ep.id).order_by(Scene.scene_number)))[:n]
    r = client.post("/api/v1/assignments", headers=lead, json={
        "project_id": p.id, "episode_id": ep.id, "scene_ids": [s.id for s in scenes],
        "artist_ids": [uid(db, ARTIST)], "description": "Animate the rain", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _notes(db, email):
    return db.scalars(select(Notification).where(Notification.user_id == uid(db, email)).order_by(Notification.id)).all()


def _emails(db):
    db.expire_all()
    return db.scalars(select(EmailLog).order_by(EmailLog.id)).all()


@pytest.fixture(autouse=True)
def _clean_outbox():
    for f in outbox():
        f.unlink()
    yield


# ---------------- events ----------------

def test_new_assignment_notifies_artist_in_app_and_by_email(client, as_lead, db):
    a = _assign(client, as_lead, db)
    notes = _notes(db, ARTIST)
    assert len(notes) == 1 and notes[0].event_type == "assignment_created"
    assert notes[0].link == f"/artist/assignments?open={a['id']}" and notes[0].read_at is None

    [log] = _emails(db)
    assert log.tool_name == "send_artist_notification" and log.recipients == [ARTIST]
    assert log.status == EmailStatus.SENT, log.error  # dispatched by the background task
    assert log.provider == "mock:mock" and log.provider_message_id.startswith("mock-msg-")
    [eml] = outbox()
    text = eml.read_text()
    assert f"To: {ARTIST}" in text and "New assignment" in text and "SC01, SC02" in text


def test_submission_review_cycle_notifications(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db)
    s1, s2 = [s["id"] for s in a["scenes"]]
    sub = client.post("/api/v1/submissions", headers=as_artist, json={
        "assignment_id": a["id"], "scene_ids": [s1, s2], "work_description": "done"}).json()

    lead_notes = _notes(db, LEAD)
    assert [n.event_type for n in lead_notes] == ["submission_received"]
    assert lead_notes[0].link == f"/lead/reviews?open={sub['id']}"
    assert len(_emails(db)) == 1  # leads get in-app only for submissions

    client.post(f"/api/v1/submissions/{sub['id']}/review", headers=as_lead,
                json={"decision": "approved", "approved_scene_ids": [s1], "feedback": "SC02: fix the flicker at 00:04"})
    artist_notes = _notes(db, ARTIST)
    assert artist_notes[-1].event_type == "revision_requested"
    assert "SC02" in artist_notes[-1].message and "flicker" in artist_notes[-1].message
    revision = _emails(db)[-1]
    assert revision.tool_name == "send_task_revision_notification" and revision.status == EmailStatus.SENT
    body = outbox()[-1].read_text()
    assert "Revision requested" in body and "fix the flicker" in body and "EP01 SC02" in body
    assert "Approved in this submission: EP01 SC01" in body

    resub = client.post("/api/v1/submissions", headers=as_artist, json={
        "assignment_id": a["id"], "scene_ids": [s2], "work_description": "fixed"}).json()
    assert "Revised submission" in _notes(db, LEAD)[-1].title
    client.post(f"/api/v1/submissions/{resub['id']}/review", headers=as_lead, json={"decision": "approved"})
    assert _notes(db, ARTIST)[-1].event_type == "submission_approved"
    assert _emails(db)[-1].subject.startswith("Approved:")


def test_replayed_events_do_not_duplicate(client, as_lead, db):
    a = _assign(client, as_lead, db)
    row = db.get(Assignment, a["id"])
    artist = db.get(User, uid(db, ARTIST))
    for _ in range(3):  # e.g. a retried job or request
        notification_service.assignment_created(db, row, artist)
        db.commit()
    assert db.scalar(select(func.count(Notification.id))) == 1
    assert db.scalar(select(func.count(EmailLog.id))) == 1
    asyncio.run(email_service.dispatch_pending())
    assert len(outbox()) == 1



def test_emails_wait_while_gmail_is_not_configured(client, as_lead, db, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "email_provider", "mcp")
    monkeypatch.setattr(s, "gmail_backend", "gmail")
    monkeypatch.setattr(s, "gmail_mcp_url", None)
    monkeypatch.setattr(s, "gmail_token_file", None)
    assert not s.email_configured
    _assign(client, as_lead, db)  # also triggers a background dispatch, which must hold the email
    assert asyncio.run(email_service.dispatch_pending()) == {"sent": 0, "failed": 0, "blocked": 0}
    row = db.scalar(select(EmailLog))
    db.refresh(row)
    assert row.status == EmailStatus.PENDING and row.attempts == 0  # untouched: no retries burned
    monkeypatch.setattr(s, "gmail_backend", "mock")  # Gmail added later -> queued email goes out
    assert asyncio.run(email_service.dispatch_pending())["sent"] == 1

# ---------------- notification API ----------------

def test_notification_api_is_per_user(client, as_lead, as_artist, db):
    _assign(client, as_lead, db)
    _assign(client, as_lead, db, n=1)
    assert client.get("/api/v1/notifications/unread-count", headers=as_artist).json() == {"unread": 2}
    items = client.get("/api/v1/notifications", headers=as_artist).json()
    assert len(items) == 2 and items[0]["created_at"] >= items[1]["created_at"]

    other = login(client, LEAD_OTHER)
    assert client.get("/api/v1/notifications", headers=other).json() == []
    assert client.post(f"/api/v1/notifications/{items[0]['id']}/read", headers=other).status_code == 404

    r = client.post(f"/api/v1/notifications/{items[0]['id']}/read", headers=as_artist)
    assert r.status_code == 200 and r.json()["read_at"]
    assert client.get("/api/v1/notifications/unread-count", headers=as_artist).json() == {"unread": 1}
    assert len(client.get("/api/v1/notifications?unread_only=true", headers=as_artist).json()) == 1
    assert client.post("/api/v1/notifications/read-all", headers=as_artist).json() == {"updated": 1}
    assert client.get("/api/v1/notifications/unread-count", headers=as_artist).json() == {"unread": 0}


# ---------------- outbox / dispatcher ----------------

def _queue_one(client, as_lead, db, monkeypatch):
    """Create an assignment without letting the background task deliver its email."""
    async def _noop(*a, **k):
        return {}
    monkeypatch.setattr(email_service, "dispatch_pending", _noop)
    _assign(client, as_lead, db)
    monkeypatch.undo()
    [row] = _emails(db)
    assert row.status == EmailStatus.PENDING
    return row


def test_dispatch_is_idempotent_and_concurrency_safe(client, as_lead, db, monkeypatch):
    _queue_one(client, as_lead, db, monkeypatch)

    async def both():
        return await asyncio.gather(email_service.dispatch_pending(), email_service.dispatch_pending())
    results = asyncio.run(both())
    assert sum(r["sent"] for r in results) == 1
    asyncio.run(email_service.dispatch_pending())  # nothing left to do
    assert len(outbox()) == 1 and _emails(db)[0].attempts == 1


def _failing_gateway(kind):
    class _Caller:
        async def call(self, tool, args):
            raise GatewayError(kind, "simulated")

    @asynccontextmanager
    async def _open():
        yield _Caller()
    return _open


def test_transient_failure_backs_off_then_succeeds(client, as_lead, db, monkeypatch):
    row = _queue_one(client, as_lead, db, monkeypatch)
    monkeypatch.setattr(email_service, "open_gateway", _failing_gateway("retryable"))
    assert asyncio.run(email_service.dispatch_pending())["failed"] == 1
    row = _emails(db)[0]
    assert row.status == EmailStatus.FAILED and row.attempts == 1 and "simulated" in row.error
    assert row.next_attempt_at > utcnow()  # backoff
    assert asyncio.run(email_service.dispatch_pending()) == {"sent": 0, "failed": 0, "blocked": 0}

    monkeypatch.undo()
    row.next_attempt_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert asyncio.run(email_service.dispatch_pending())["sent"] == 1
    row = _emails(db)[0]
    assert row.status == EmailStatus.SENT and row.attempts == 2 and row.error is None


def test_gives_up_after_max_attempts(client, as_lead, db, monkeypatch):
    _queue_one(client, as_lead, db, monkeypatch)
    monkeypatch.setattr(email_service, "open_gateway", _failing_gateway("retryable"))
    for _ in range(get_settings().email_max_attempts + 2):
        r = _emails(db)[0]
        if r.next_attempt_at is not None:  # fast-forward the backoff
            r.next_attempt_at = utcnow() - timedelta(seconds=1)
            db.commit()
        asyncio.run(email_service.dispatch_pending())
    row = _emails(db)[0]
    assert row.attempts == get_settings().email_max_attempts and row.next_attempt_at is None


def test_policy_block_is_final(client, as_lead, as_admin, db, monkeypatch):
    """The MCP server refuses to email someone who is no longer an active artist."""
    _queue_one(client, as_lead, db, monkeypatch)
    client.post(f"/api/v1/users/{uid(db, ARTIST)}/deactivate", headers=as_admin)
    assert asyncio.run(email_service.dispatch_pending())["blocked"] == 1
    row = _emails(db)[0]
    assert row.status == EmailStatus.BLOCKED and "not an active artist" in row.error
    assert len(outbox()) == 0
    r = client.post(f"/api/v1/email-logs/{row.id}/retry", headers=as_admin)
    assert r.status_code == 409  # blocked stays blocked


def test_admin_email_log_and_retry(client, as_lead, as_admin, db, monkeypatch):
    _queue_one(client, as_lead, db, monkeypatch)
    monkeypatch.setattr(email_service, "open_gateway", _failing_gateway("auth"))
    asyncio.run(email_service.dispatch_pending())
    monkeypatch.undo()
    assert client.get("/api/v1/email-logs", headers=as_lead).status_code == 403
    logs = client.get("/api/v1/email-logs", headers=as_admin).json()
    assert logs[0]["status"] == "failed" and logs[0]["error"].startswith("auth:")
    assert "payload" not in logs[0] and "body_preview" not in logs[0]
    r = client.post(f"/api/v1/email-logs/{logs[0]['id']}/retry", headers=as_admin)
    assert r.status_code == 200 and r.json()["status"] == "sent"


# ---------------- deadline reminders ----------------

def test_deadline_reminders_once_per_deadline(client, as_lead, as_artist, db, monkeypatch):
    a = _assign(client, as_lead, db, deadline=(utcnow() + timedelta(hours=1)).isoformat())
    far = _assign(client, as_lead, db, n=1, deadline=(utcnow() + timedelta(days=2)).isoformat())
    assert jobs.send_deadline_reminders() == 1
    assert jobs.send_deadline_reminders() == 0  # idempotent
    reminder = _notes(db, ARTIST)[-1]
    assert reminder.event_type == "deadline_approaching" and reminder.entity_id == a["id"]

    # Moving the deadline earns a fresh reminder
    client.patch(f"/api/v1/assignments/{a['id']}", headers=as_lead,
                 json={"deadline": (utcnow() + timedelta(minutes=90)).isoformat()})
    assert jobs.send_deadline_reminders() == 1

    # Work already submitted for review isn't nagged
    row = db.get(Assignment, far["id"])
    row.deadline = utcnow() + timedelta(minutes=30)
    db.commit()
    client.post("/api/v1/submissions", headers=as_artist, json={
        "assignment_id": far["id"], "scene_ids": [far["scenes"][0]["id"]], "work_description": "done"})
    assert jobs.send_deadline_reminders() == 0
    statuses = {x.status.value for x in db.scalars(select(AssignmentAssignee))}
    assert "submitted" in statuses


def test_unexpected_error_does_not_strand_the_batch(client, as_lead, db, monkeypatch):
    """A timeout or malformed reply (not a GatewayError) used to abort the batch and leave rows stuck."""
    _queue_one(client, as_lead, db, monkeypatch)

    async def _noop(*a, **k):
        return {}
    monkeypatch.setattr(email_service, "dispatch_pending", _noop)
    _assign(client, as_lead, db, n=1)  # a second queued email in the same batch
    monkeypatch.undo()
    calls = []

    class _Caller:
        async def call(self, tool, args):
            calls.append(tool)
            if len(calls) == 1:
                raise TimeoutError("read timed out")
            return email_service.DeliveryResult(status="sent", backend="mock", message_id="m1")

    @asynccontextmanager
    async def _open():
        yield _Caller()
    monkeypatch.setattr(email_service, "open_gateway", _open)

    assert asyncio.run(email_service.dispatch_pending()) == {"sent": 1, "failed": 1, "blocked": 0}
    first, second = _emails(db)
    assert first.status == EmailStatus.FAILED and "TimeoutError" in first.error and first.next_attempt_at
    assert second.status == EmailStatus.SENT


def test_interrupted_last_attempt_becomes_failed_and_retryable(client, as_lead, db, monkeypatch):
    row = _queue_one(client, as_lead, db, monkeypatch)
    row.attempts = get_settings().email_max_attempts  # dispatcher died during the final attempt
    row.next_attempt_at = utcnow() - timedelta(seconds=1)  # lease expired
    db.commit()
    monkeypatch.setattr(email_service, "open_gateway", _failing_gateway("retryable"))
    asyncio.run(email_service.dispatch_pending())
    row = _emails(db)[0]
    assert row.status == EmailStatus.FAILED and row.next_attempt_at is None
    email_service.retry(db, row)  # an admin can now re-queue it
    assert row.attempts == 0
