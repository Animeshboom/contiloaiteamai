"""Configuration from environment variables only. No secrets in code."""
import os
from dataclasses import dataclass
from pathlib import Path

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]  # drafts + send; nothing else


@dataclass(frozen=True)
class Config:
    database_url: str
    backend: str  # "gmail" (real delivery) | "mock" (test suite only)
    credentials_file: str | None
    token_file: str | None
    sender: str | None
    approval_secret: str
    outbox_dir: Path
    app_name: str


def load() -> Config:
    secret = os.environ.get("EMAIL_APPROVAL_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("EMAIL_APPROVAL_SECRET must be set (>= 32 chars) for the Gmail MCP server")
    db = os.environ.get("DATABASE_URL")
    if not db:
        raise RuntimeError("DATABASE_URL must be set for the Gmail MCP server (read-only access is sufficient)")
    return Config(
        database_url=db,
        backend=os.environ.get("GMAIL_BACKEND", "gmail").lower(),
        credentials_file=os.environ.get("GMAIL_CREDENTIALS_FILE") or None,
        token_file=os.environ.get("GMAIL_TOKEN_FILE") or None,
        sender=os.environ.get("EMAIL_SENDER") or None,
        approval_secret=secret,
        outbox_dir=Path(os.environ.get("MAIL_OUTBOX_DIR", "mail_outbox")),
        app_name=os.environ.get("APP_NAME", "StudioTrack AI"),
    )
