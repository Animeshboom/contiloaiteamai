"""StudioTrack Gmail MCP server.

Run (stdio, spawned by the backend):   python -m gmail_mcp.server
Run (HTTP, separate container):        python -m gmail_mcp.server --http --host 0.0.0.0 --port 8765

Every tool:
  1. validates recipients against the StudioTrack database (policy.py),
  2. refuses an idempotency key that was already delivered,
  3. sends through the configured backend (Gmail API or mock),
  4. logs the attempt without message bodies and with masked addresses.

Errors are raised as ToolError with a machine-readable prefix the client uses to
decide whether to retry:  BLOCKED: (policy, never retry) | RETRYABLE: | AUTH: | FAILED:
"""
import argparse
import logging
import sys
import textwrap

from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from mcp.server.fastmcp.exceptions import ToolError

from gmail_mcp import config as config_mod
from gmail_mcp.backends import DeliveryError, build_message, make_backend
from gmail_mcp.policy import Policy, PolicyError, mask

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s gmail_mcp: %(message)s")
log = logging.getLogger("gmail_mcp")

mcp = FastMCP(
    "studiotrack-gmail",
    instructions=(
        "Controlled email tools for StudioTrack. Recipients are validated against the studio database. "
        "Daily reports can only be sent after a team lead approves them in StudioTrack."
    ),
)


class DeliveryResult(BaseModel):
    """Structured tool result (returned as MCP structuredContent)."""
    status: Literal["sent", "drafted"]
    backend: str
    message_id: str | None = None
    thread_id: str | None = None
    draft_id: str | None = None


def _ctx():
    cfg = config_mod.load()
    return cfg, Policy(cfg.database_url, cfg.approval_secret)


def _deliver(tool: str, key: str, recipients: list[str], fn):
    """Run a delivery function, translating errors to ToolError prefixes and logging the attempt."""
    who = ", ".join(mask(r) for r in recipients)
    try:
        result = fn()
    except PolicyError as e:
        log.warning("%s key=%s to=[%s] BLOCKED: %s", tool, key, who, e)
        raise ToolError(f"BLOCKED: {e}") from e
    except DeliveryError as e:
        log.error("%s key=%s to=[%s] %s: %s", tool, key, who, e.kind.upper(), e)
        raise ToolError(f"{e.kind.upper()}: {e}") from e
    log.info("%s key=%s to=[%s] OK %s", tool, key, who, {k: v for k, v in result.items() if v})
    return DeliveryResult(**result)


def _require_key(key: str) -> str:
    key = (key or "").strip()
    if not key or len(key) > 200:
        raise ToolError("BLOCKED: idempotency_key is required (1-200 chars)")
    return key


@mcp.tool()
def send_artist_notification(recipient_email: str, subject: str, message_body: str, assignment_reference: str,
                             idempotency_key: str) -> DeliveryResult:
    """Email one StudioTrack artist about their work (e.g. a new assignment or an approval).
    The recipient must be an active artist in StudioTrack."""
    key = _require_key(idempotency_key)

    def run():
        cfg, policy = _ctx()
        policy.require_active_artist(recipient_email)
        policy.require_not_already_sent(key)
        body = f"{message_body.strip()}\n\nReference: {assignment_reference}\n\n— {cfg.app_name}"
        msg = build_message(cfg.sender, [recipient_email], subject, body, cfg.app_name)
        return {"status": "sent", "backend": cfg.backend, **make_backend(cfg).send(msg)}

    return _deliver("send_artist_notification", key, [recipient_email], run)


@mcp.tool()
def send_task_revision_notification(artist_email: str, project_title: str, episode: str, scene_references: list[str],
                                    team_lead_feedback: str, idempotency_key: str, assignment_link: str = "") -> DeliveryResult:
    """Tell an artist their submission needs revision, including the team lead's feedback.
    The recipient must be an active artist in StudioTrack."""
    key = _require_key(idempotency_key)
    if not team_lead_feedback.strip():
        raise ToolError("BLOCKED: team_lead_feedback is required")

    def run():
        cfg, policy = _ctx()
        policy.require_active_artist(artist_email)
        policy.require_not_already_sent(key)
        scenes = ", ".join(scene_references) or "the submitted deliverable"
        body = textwrap.dedent(f"""\
            Your team lead has requested a revision.

            Project: {project_title}
            Episode: {episode or "—"}
            Scenes to revise: {scenes}

            Feedback:
            {team_lead_feedback.strip()}
            """)
        if assignment_link:
            body += f"\nOpen the assignment: {assignment_link}\n"
        body += f"\n— {cfg.app_name}"
        subject = f"Revision requested: {project_title}" + (f" · {episode}" if episode else "")
        msg = build_message(cfg.sender, [artist_email], subject, body, cfg.app_name)
        return {"status": "sent", "backend": cfg.backend, **make_backend(cfg).send(msg)}

    return _deliver("send_task_revision_notification", key, [artist_email], run)


@mcp.tool()
def create_daily_report_draft(report_date: str, report_content: str, authorized_recipients: list[str],
                              idempotency_key: str, subject: str = "") -> DeliveryResult:
    """Create a Gmail DRAFT of an end-of-day report addressed to authorized management recipients.
    This never sends. Recipients must be on StudioTrack's authorized recipient list."""
    key = _require_key(idempotency_key)

    def run():
        cfg, policy = _ctx()
        recipients = policy.require_authorized_recipients(authorized_recipients)
        msg = build_message(cfg.sender, recipients, subject or f"Daily production report — {report_date}",
                            report_content, cfg.app_name)
        return {"status": "drafted", "backend": cfg.backend, **make_backend(cfg).create_draft(msg)}

    return _deliver("create_daily_report_draft", key, authorized_recipients, run)


@mcp.tool()
def send_daily_report(report_id: int, authorized_recipients: list[str], approval_reference: str,
                      idempotency_key: str) -> DeliveryResult:
    """Send an end-of-day report that a team lead has APPROVED in StudioTrack.
    The report's content is loaded from StudioTrack (not taken from the caller), the recipients must
    exactly match the approved list, and approval_reference must be the token StudioTrack issued at approval."""
    key = _require_key(idempotency_key)

    def run():
        cfg, policy = _ctx()
        recipients = policy.require_authorized_recipients(authorized_recipients)
        report = policy.approved_report(report_id, approval_reference, recipients)
        policy.require_not_already_sent(key)
        msg = build_message(cfg.sender, recipients, report["subject"], report["body"], cfg.app_name)
        return {"status": "sent", "backend": cfg.backend, **make_backend(cfg).send(msg)}

    return _deliver("send_daily_report", key, authorized_recipients, run)


def main() -> None:
    parser = argparse.ArgumentParser(description="StudioTrack Gmail MCP server")
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    cfg = config_mod.load()  # fail fast on missing configuration
    log.info("starting (backend=%s, transport=%s)", cfg.backend, "http" if args.http else "stdio")
    if args.http:
        mcp.settings.host, mcp.settings.port = args.host, args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
