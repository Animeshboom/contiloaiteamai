"""Gmail MCP server: protocol, policy, approval tokens, Gmail error handling, and the real stdio path."""
import asyncio
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select

from app.core import approval as backend_approval
from app.core.config import get_settings
from app.core.timeutils import studio_today, utcnow
from app.models import DailyReport, EmailLog, EmailStatus, ReportStatus, User
from gmail_mcp import approval as server_approval
from gmail_mcp import backends
from gmail_mcp.server import mcp
from tests.conftest import ADMIN, ARTIST, LEAD

SECRET = "test-approval-secret-0123456789-abcdefghij"
MGMT = ["producer@studiotrack.demo", "studio.head@studiotrack.demo"]


def call(tool: str, args: dict):
    async def run():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            return await client.call_tool(tool, args)
    return asyncio.run(run())


def ok(res) -> dict:
    assert not res.isError, res.content[0].text
    assert res.structuredContent, "tools must return structured content"
    return res.structuredContent


def err(res) -> str:
    """Error text after the protocol wrapper ("Error executing tool x: ")."""
    assert res.isError
    text = res.content[0].text
    return text[text.index(": ") + 2:] if text.startswith("Error executing tool") else text


def last_eml() -> str:
    files = sorted(Path(get_settings().mail_outbox_dir).glob("*.eml"))
    return files[-1].read_text()


def test_exposes_exactly_the_four_tools():
    async def run():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            return (await client.list_tools()).tools
    tools = {t.name: t for t in asyncio.run(run())}
    assert set(tools) == {"send_artist_notification", "create_daily_report_draft", "send_daily_report",
                          "send_task_revision_notification"}
    assert {"report_id", "authorized_recipients", "approval_reference"} <= set(tools["send_daily_report"].inputSchema["properties"])


# ---------------- artist notifications ----------------

def test_send_artist_notification_to_active_artist():
    data = ok(call("send_artist_notification", {
        "recipient_email": ARTIST.upper(), "subject": "Hello", "message_body": "New work",
        "assignment_reference": "Assignment #1", "idempotency_key": "t:1"}))
    assert data["status"] == "sent" and data["backend"] == "mock" and data["message_id"].startswith("mock-msg-")
    assert "Reference: Assignment #1" in last_eml()


@pytest.mark.parametrize("email", ["stranger@example.com", LEAD, ADMIN])
def test_artist_tools_refuse_non_artists(email):
    msg = err(call("send_artist_notification", {
        "recipient_email": email, "subject": "x", "message_body": "x", "assignment_reference": "x",
        "idempotency_key": f"t:{email}"}))
    assert msg.startswith("BLOCKED:") and "not an active artist" in msg
    assert "@" in msg and email not in msg  # address is masked in errors/logs


def test_inactive_artist_refused(db):
    u = db.scalar(select(User).where(User.email == ARTIST))
    u.is_active = False
    db.commit()
    assert err(call("send_artist_notification", {"recipient_email": ARTIST, "subject": "x", "message_body": "x",
                                                 "assignment_reference": "x", "idempotency_key": "t:2"})).startswith("BLOCKED")


def test_already_delivered_key_is_refused(db):
    db.add(EmailLog(idempotency_key="dup:1", tool_name="send_artist_notification", provider="mock",
                    recipients=[ARTIST], subject="s", status=EmailStatus.SENT, payload={}))
    db.commit()
    msg = err(call("send_artist_notification", {"recipient_email": ARTIST, "subject": "x", "message_body": "x",
                                                "assignment_reference": "x", "idempotency_key": "dup:1"}))
    assert "Duplicate" in msg


def test_revision_notification_requires_feedback_and_blocks_header_injection():
    base = {"artist_email": ARTIST, "project_title": "Neon", "episode": "EP01", "scene_references": ["SC02"],
            "idempotency_key": "t:rev"}
    assert err(call("send_task_revision_notification", {**base, "team_lead_feedback": "  "})).startswith("BLOCKED")
    ok(call("send_task_revision_notification", {
        **base, "project_title": "Neon\r\nBcc: attacker@evil.example", "team_lead_feedback": "Fix flicker"}))
    from email import message_from_string, policy
    msg = message_from_string(last_eml(), policy=policy.default)  # unfolds RFC 5322 continuation lines
    assert msg["Bcc"] is None and msg["Cc"] is None  # no header was injected
    assert "\n" not in msg["Subject"] and "\r" not in msg["Subject"]
    assert msg["Subject"].startswith("Revision requested: Neon Bcc: attacker")  # neutralised into plain text
    assert msg["To"] == ARTIST
    body = msg.get_content()
    assert "Fix flicker" in body and "Scenes to revise: SC02" in body


# ---------------- daily reports ----------------

def test_draft_requires_authorized_recipients():
    data = ok(call("create_daily_report_draft", {"report_date": "2026-11-18", "report_content": "Body",
                                                 "authorized_recipients": MGMT, "idempotency_key": "d:1"}))
    assert data["status"] == "drafted" and data["draft_id"].startswith("mock-draft-")
    msg = err(call("create_daily_report_draft", {"report_date": "2026-11-18", "report_content": "Body",
                                                 "authorized_recipients": [*MGMT, "boss@gmail.com"],
                                                 "idempotency_key": "d:2"}))
    assert msg.startswith("BLOCKED:") and "Not an authorized report recipient" in msg


def _report(db, status=ReportStatus.APPROVED, recipients=MGMT):
    lead = db.scalar(select(User).where(User.email == LEAD))
    r = DailyReport(report_date=studio_today(), subject="EOD report", body="Stored, approved body",
                    status=status, recipients=recipients, created_by_id=lead.id, metrics={}, filters={})
    if status != ReportStatus.DRAFT:
        r.approved_by_id, r.approved_at = lead.id, utcnow().replace(microsecond=0)
    db.add(r)
    db.commit()
    token = (backend_approval.sign(SECRET, r.id, lead.id, r.approved_at, recipients) if r.approved_at else "")
    return r, token


def test_send_daily_report_with_valid_approval_uses_stored_content(db):
    r, token = _report(db)
    data = ok(call("send_daily_report", {"report_id": r.id, "authorized_recipients": list(reversed(MGMT)),
                                         "approval_reference": token, "idempotency_key": f"report:{r.id}"}))
    assert data["status"] == "sent"
    eml = last_eml()
    assert "Stored, approved body" in eml and "Subject: EOD report" in eml


def test_send_daily_report_refusals(db):
    draft, _ = _report(db, status=ReportStatus.DRAFT)
    assert "not been approved" in err(call("send_daily_report", {
        "report_id": draft.id, "authorized_recipients": MGMT, "approval_reference": "x", "idempotency_key": "r:a"}))

    r, token = _report(db)
    forged = server_approval.sign("an-attacker-guessed-secret-0123456789", r.id, r.approved_by_id, r.approved_at, MGMT)
    assert "Invalid approval reference" in err(call("send_daily_report", {
        "report_id": r.id, "authorized_recipients": MGMT, "approval_reference": forged, "idempotency_key": "r:b"}))
    assert "differ from the list" in err(call("send_daily_report", {
        "report_id": r.id, "authorized_recipients": MGMT[:1], "approval_reference": token, "idempotency_key": "r:c"}))
    assert "does not exist" in err(call("send_daily_report", {
        "report_id": 99999, "authorized_recipients": MGMT, "approval_reference": token, "idempotency_key": "r:d"}))

    r.status = ReportStatus.SENT
    db.commit()
    assert err(call("send_daily_report", {"report_id": r.id, "authorized_recipients": MGMT,
                                          "approval_reference": token, "idempotency_key": "r:e"})).startswith("BLOCKED")


def test_approval_token_identical_in_backend_and_server():
    at = utcnow()
    assert backend_approval.sign(SECRET, 5, 2, at, ["B@x.io", "a@x.io"]) == server_approval.sign(SECRET, 5, 2, at, ["a@x.io", "b@x.io"])
    assert not server_approval.verify(SECRET, backend_approval.sign(SECRET, 5, 2, at, ["a@x.io"]), 6, 2, at, ["a@x.io"])


# ---------------- Gmail API error handling ----------------

def _gmail(tmp_path):
    cfg = SimpleNamespace(token_file=str(tmp_path / "token.json"))
    (tmp_path / "token.json").write_text("{}")
    g = backends.GmailBackend.__new__(backends.GmailBackend)
    g.cfg = cfg
    return g


@pytest.mark.parametrize("status,kind", [(429, "retryable"), (503, "retryable"), (403, "auth"), (401, "auth"), (400, "failed")])
def test_gmail_http_errors_are_classified(tmp_path, status, kind):
    from googleapiclient.errors import HttpError

    class Req:
        def execute(self, num_retries=0):
            raise HttpError(SimpleNamespace(status=status, reason="x"), b"{}")
    with pytest.raises(backends.DeliveryError) as e:
        _gmail(tmp_path)._execute(Req())
    assert e.value.kind == kind


def test_gmail_expired_token_is_refreshed_and_saved(tmp_path, monkeypatch):
    import google.oauth2.credentials as gcreds

    class FakeCreds:
        valid, expired, refresh_token = False, True, "r"
        def refresh(self, _req):
            self.valid = True
        def to_json(self):
            return json.dumps({"refreshed": True})
    monkeypatch.setattr(gcreds.Credentials, "from_authorized_user_file", staticmethod(lambda *a, **k: FakeCreds()))
    g = _gmail(tmp_path)
    g._creds()
    assert json.loads(Path(g.cfg.token_file).read_text()) == {"refreshed": True}


def test_gmail_revoked_token_reports_auth_error(tmp_path, monkeypatch):
    import google.oauth2.credentials as gcreds
    from google.auth.exceptions import RefreshError

    class FakeCreds:
        valid, expired, refresh_token = False, True, "r"
        def refresh(self, _req):
            raise RefreshError("invalid_grant")
    monkeypatch.setattr(gcreds.Credentials, "from_authorized_user_file", staticmethod(lambda *a, **k: FakeCreds()))
    with pytest.raises(backends.DeliveryError) as e:
        _gmail(tmp_path)._creds()
    assert e.value.kind == "auth" and "authorize" in str(e.value)


def test_gmail_backend_without_token_is_auth_error(tmp_path):
    cfg = SimpleNamespace(token_file=str(tmp_path / "missing.json"))
    with pytest.raises(backends.DeliveryError) as e:
        backends.GmailBackend(cfg)
    assert e.value.kind == "auth"


# ---------------- real MCP over stdio (subprocess) ----------------

def test_backend_delivers_through_spawned_mcp_server(client, as_lead, db, monkeypatch):
    """EMAIL_PROVIDER=mcp: the backend spawns the MCP server and calls its tool over stdio."""
    from app.services import email_service
    from tests.test_notifications import _assign

    async def _noop(*a, **k):
        return {}
    monkeypatch.setattr(email_service, "dispatch_pending", _noop)
    _assign(client, as_lead, db)
    monkeypatch.undo()
    monkeypatch.setattr(get_settings(), "email_provider", "mcp")

    stats = asyncio.run(email_service.dispatch_pending())
    db.expire_all()
    row = db.scalars(select(EmailLog)).one()
    assert stats["sent"] == 1, row.error
    assert row.status == EmailStatus.SENT and row.provider == "mcp:mock"
    assert row.provider_message_id.startswith("mock-msg-")
    _ = timedelta  # keep import used
