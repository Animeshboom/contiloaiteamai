"""Email delivery backends: real Gmail API, or a mock that writes .eml files."""
import base64
import logging
import re
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from gmail_mcp.config import GMAIL_SCOPES, Config

log = logging.getLogger("gmail_mcp")


class DeliveryError(Exception):
    """kind: 'retryable' (try later), 'auth' (operator must re-authorize), 'failed' (permanent)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _clean_header(value: str) -> str:
    # Prevent header injection: no CR/LF in header values.
    return re.sub(r"[\r\n]+", " ", value).strip()[:300]


def build_message(sender: str | None, to: list[str], subject: str, body: str, app_name: str) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = ", ".join(_clean_header(t) for t in to)
    if sender:
        msg["From"] = _clean_header(f"{app_name} <{sender}>")
    msg["Subject"] = _clean_header(subject)
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="studiotrack.local")
    msg.set_content(body)
    return msg


class MockBackend:
    """Writes messages to MAIL_OUTBOX_DIR as .eml files. Used when Gmail isn't configured."""
    name = "mock"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        cfg.outbox_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, prefix: str, msg: EmailMessage) -> str:
        ident = f"{prefix}-{uuid.uuid4().hex[:16]}"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")  # sortable, sub-second
        (self.cfg.outbox_dir / f"{stamp}_{ident}.eml").write_bytes(bytes(msg))
        return ident

    def send(self, msg: EmailMessage) -> dict:
        return {"message_id": self._write("mock-msg", msg), "thread_id": None}

    def create_draft(self, msg: EmailMessage) -> dict:
        return {"draft_id": self._write("mock-draft", msg), "message_id": None}


class GmailBackend:
    """Gmail API with OAuth 2.0 user credentials (scope: gmail.compose only)."""
    name = "gmail"

    def __init__(self, cfg: Config):
        if not cfg.token_file or not Path(cfg.token_file).is_file():
            raise DeliveryError("auth", "Gmail is not authorized. Run: python -m gmail_mcp.authorize")
        self.cfg = cfg
        self._service = None

    def _creds(self):
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(self.cfg.token_file, GMAIL_SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as e:
                    raise DeliveryError("auth", "Gmail token expired or was revoked. Re-run: python -m gmail_mcp.authorize") from e
                Path(self.cfg.token_file).write_text(creds.to_json(), encoding="utf-8")
                log.info("Gmail access token refreshed")
            else:
                raise DeliveryError("auth", "Gmail credentials are invalid. Re-run: python -m gmail_mcp.authorize")
        return creds

    def _svc(self):
        from googleapiclient.discovery import build
        # Rebuild on each call so refreshed credentials are always used.
        return build("gmail", "v1", credentials=self._creds(), cache_discovery=False)

    @staticmethod
    def _raw(msg: EmailMessage) -> str:
        return base64.urlsafe_b64encode(bytes(msg)).decode()

    def _execute(self, request):
        from googleapiclient.errors import HttpError
        try:
            return request.execute(num_retries=2)
        except HttpError as e:
            status = getattr(e.resp, "status", 0)
            if status in (429, 500, 502, 503, 504):
                raise DeliveryError("retryable", f"Gmail API temporarily unavailable (HTTP {status})") from e
            if status in (401, 403):
                raise DeliveryError("auth", f"Gmail API refused the request (HTTP {status}); check OAuth consent and scopes") from e
            raise DeliveryError("failed", f"Gmail API error (HTTP {status})") from e
        except OSError as e:
            raise DeliveryError("retryable", f"Network error talking to Gmail: {type(e).__name__}") from e

    def send(self, msg: EmailMessage) -> dict:
        res = self._execute(self._svc().users().messages().send(userId="me", body={"raw": self._raw(msg)}))
        return {"message_id": res.get("id"), "thread_id": res.get("threadId")}

    def create_draft(self, msg: EmailMessage) -> dict:
        res = self._execute(self._svc().users().drafts().create(userId="me", body={"message": {"raw": self._raw(msg)}}))
        return {"draft_id": res.get("id"), "message_id": (res.get("message") or {}).get("id")}


def make_backend(cfg: Config):
    if cfg.backend == "gmail":
        return GmailBackend(cfg)
    if cfg.backend == "mock":
        return MockBackend(cfg)
    raise RuntimeError(f"Unknown GMAIL_BACKEND '{cfg.backend}' (use 'gmail' or 'mock')")
