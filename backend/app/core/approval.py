"""Report-send approval tokens.

The backend issues a token only when an authorized team lead approves a report.
The token binds the report id, approver, approval time and exact recipient list, so
it cannot be reused for another report or widened to more recipients. The logic must
match mcp_servers/gmail_mcp/approval.py (a test checks both produce identical tokens).
"""
import hashlib
import hmac
from datetime import datetime, timezone


def _ts(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _message(report_id: int, approver_id: int, approved_at: datetime, recipients: list[str]) -> bytes:
    rcpts = ",".join(sorted({r.strip().lower() for r in recipients}))
    return f"daily_report|{report_id}|{approver_id}|{_ts(approved_at)}|{rcpts}".encode()


def sign(secret: str, report_id: int, approver_id: int, approved_at: datetime, recipients: list[str]) -> str:
    return hmac.new(secret.encode(), _message(report_id, approver_id, approved_at, recipients), hashlib.sha256).hexdigest()


def verify(secret: str, token: str, report_id: int, approver_id: int, approved_at: datetime, recipients: list[str]) -> bool:
    expected = sign(secret, report_id, approver_id, approved_at, recipients)
    return hmac.compare_digest(expected, token or "")
