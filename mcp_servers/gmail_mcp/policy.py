"""Server-side authorization against the StudioTrack database (read-only queries).

These checks run inside the MCP server regardless of what the caller claims, so the
server cannot be used to email arbitrary addresses even if a client is compromised.
"""
from datetime import datetime
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from gmail_mcp import approval


class PolicyError(Exception):
    """Request is not allowed. Never retried."""


@lru_cache(maxsize=4)
def _engine(url: str) -> Engine:
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)


class Policy:
    def __init__(self, database_url: str, approval_secret: str):
        self.engine = _engine(database_url)
        self.secret = approval_secret

    def _scalar(self, sql: str, **params):
        with self.engine.connect() as c:
            return c.execute(text(sql), params).scalar()

    def require_active_artist(self, email: str) -> None:
        found = self._scalar(
            "SELECT 1 FROM users u JOIN roles r ON r.id = u.role_id "
            "WHERE lower(u.email) = :e AND u.is_active = :t AND u.deleted_at IS NULL AND r.name = 'artist'",
            e=email.strip().lower(), t=True,
        )
        if not found:
            raise PolicyError(f"Recipient is not an active artist in StudioTrack: {mask(email)}")

    def require_authorized_recipients(self, emails: list[str]) -> list[str]:
        if not emails:
            raise PolicyError("At least one recipient is required")
        with self.engine.connect() as c:
            allowed = {r[0].lower() for r in c.execute(
                text("SELECT email FROM authorized_recipients WHERE is_active = :t"), {"t": True})}
        cleaned = sorted({e.strip().lower() for e in emails})
        bad = [e for e in cleaned if e not in allowed]
        if bad:
            raise PolicyError("Not an authorized report recipient: " + ", ".join(mask(b) for b in bad))
        return cleaned

    def require_not_already_sent(self, idempotency_key: str) -> None:
        status = self._scalar("SELECT status FROM email_logs WHERE idempotency_key = :k", k=idempotency_key)
        if status in ("sent", "drafted"):
            raise PolicyError(f"Duplicate request: '{idempotency_key}' was already delivered")

    def approved_report(self, report_id: int, approval_reference: str, recipients: list[str]) -> dict:
        """Return the approved report's stored subject/body, or raise PolicyError."""
        with self.engine.connect() as c:
            row = c.execute(text(
                "SELECT id, status, subject, body, recipients, approved_by_id, approved_at "
                "FROM daily_reports WHERE id = :id"), {"id": report_id}).mappings().first()
        if not row:
            raise PolicyError(f"Report {report_id} does not exist")
        if row["status"] not in ("approved", "failed"):  # failed = approved but delivery failed; may retry
            raise PolicyError(f"Report {report_id} has not been approved for sending (status: {row['status']})")
        if not row["approved_by_id"] or not row["approved_at"]:
            raise PolicyError(f"Report {report_id} has no recorded approver")
        approved_at = row["approved_at"]
        if isinstance(approved_at, str):  # SQLite returns text
            approved_at = datetime.fromisoformat(approved_at)
        approved_recipients = _as_list(row["recipients"])
        requested = sorted({r.strip().lower() for r in recipients})
        if requested != sorted({r.lower() for r in approved_recipients}):
            raise PolicyError("Recipients differ from the list the team lead approved")
        if not approval.verify(self.secret, approval_reference, row["id"], row["approved_by_id"], approved_at, requested):
            raise PolicyError("Invalid approval reference: the report must be approved in StudioTrack by a team lead")
        return {"subject": row["subject"], "body": row["body"]}


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        import json
        value = json.loads(value)
    return list(value or [])


def mask(email: str) -> str:
    """Keep logs useful without exposing full addresses."""
    local, _, domain = email.strip().partition("@")
    return f"{local[:2]}***@{domain}" if domain else "***"
