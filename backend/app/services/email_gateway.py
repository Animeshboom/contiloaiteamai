"""Gateway from the backend to the Gmail MCP tools.

Two providers, same tools and same server-side policy:

* ``mcp``  — real MCP protocol. The backend spawns ``python -m gmail_mcp.server`` over stdio
             (or connects to GMAIL_MCP_URL over streamable HTTP) and calls its tools.
* ``mock`` — calls the very same tool functions in-process (no subprocess), with the server's
             mock delivery backend. Used for tests and quick local runs.

The application never talks to Gmail directly; Claude Code's own MCP connections are not used.
"""
import json
import os
import re
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

TOOLS = {"send_artist_notification", "send_task_revision_notification", "create_daily_report_draft", "send_daily_report"}


class GatewayError(Exception):
    """kind: blocked (policy; never retry) | retryable | auth | failed"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class DeliveryResult:
    status: str  # sent | drafted
    backend: str
    message_id: str | None = None
    draft_id: str | None = None
    thread_id: str | None = None


_MARKER = re.compile(r"(?<![A-Za-z])(BLOCKED|RETRYABLE|AUTH|FAILED):\s*(.*)", re.S)


def _parse_error(text: str) -> GatewayError:
    """Tool errors carry a kind marker; over MCP they arrive wrapped ("Error executing tool x: BLOCKED: ...")."""
    m = _MARKER.search(text)
    if m:
        return GatewayError(m.group(1).lower(), m.group(2).strip())
    return GatewayError("failed", text.strip())


def _result(data: dict) -> DeliveryResult:
    if "result" in data and isinstance(data["result"], dict):  # FastMCP may wrap structured output
        data = data["result"]
    return DeliveryResult(status=data.get("status", "sent"), backend=data.get("backend", "?"),
                          message_id=data.get("message_id"), draft_id=data.get("draft_id"),
                          thread_id=data.get("thread_id"))


class ToolCaller(Protocol):
    async def call(self, tool: str, args: dict) -> DeliveryResult: ...


def mcp_dir() -> Path:
    configured = Path(get_settings().gmail_mcp_dir)
    if not configured.is_absolute():
        configured = (Path(__file__).resolve().parents[2] / configured).resolve()
    return configured


def server_env() -> dict[str, str]:
    """Only the variables the MCP server needs — never the whole backend environment."""
    s = get_settings()
    env = {
        "DATABASE_URL": s.database_url,
        "EMAIL_APPROVAL_SECRET": s.email_approval_secret,
        "GMAIL_BACKEND": s.gmail_backend,
        "MAIL_OUTBOX_DIR": str(Path(s.mail_outbox_dir).resolve()),
        "APP_NAME": s.app_name,
    }
    for key, val in (("GMAIL_CREDENTIALS_FILE", s.gmail_credentials_file), ("GMAIL_TOKEN_FILE", s.gmail_token_file),
                     ("EMAIL_SENDER", s.email_sender)):
        if val:
            env[key] = str(Path(val).resolve()) if key.endswith("_FILE") else val
    return env


# ---------------- in-process ("mock") ----------------

class _InProcessCaller:
    def __init__(self):
        path = str(mcp_dir())
        if path not in sys.path:
            sys.path.insert(0, path)
        os.environ.update(server_env())  # gmail_mcp reads its configuration from the environment
        from gmail_mcp import server  # noqa: PLC0415

        self.server = server

    async def call(self, tool: str, args: dict) -> DeliveryResult:
        from mcp.server.fastmcp.exceptions import ToolError  # noqa: PLC0415

        if tool not in TOOLS:
            raise GatewayError("blocked", f"Unknown tool {tool}")
        try:
            out = getattr(self.server, tool)(**args)
            return _result(out.model_dump() if hasattr(out, "model_dump") else out)
        except ToolError as e:
            raise _parse_error(str(e)) from e
        except TypeError as e:  # bad arguments
            raise GatewayError("failed", f"Invalid arguments for {tool}: {e}") from e


# ---------------- MCP protocol ("mcp") ----------------

class _McpCaller:
    def __init__(self, session):
        self.session = session

    async def call(self, tool: str, args: dict) -> DeliveryResult:
        if tool not in TOOLS:
            raise GatewayError("blocked", f"Unknown tool {tool}")
        try:
            res = await self.session.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=60))
            text = "\n".join(getattr(c, "text", "") for c in res.content)
            if res.isError:
                raise _parse_error(text)
            if res.structuredContent:
                return _result(res.structuredContent)
            return _result(json.loads(text or "{}"))
        except GatewayError:
            raise
        except Exception as e:  # timeouts (McpError), malformed replies, dropped connections: try again later
            raise GatewayError("retryable", f"{type(e).__name__}: {e}") from e


@asynccontextmanager
async def open_gateway() -> AsyncIterator[ToolCaller]:
    """One session per batch of deliveries."""
    s = get_settings()
    if s.email_provider == "mock":
        yield _InProcessCaller()
        return
    if s.email_provider != "mcp":
        raise GatewayError("failed", f"Unknown EMAIL_PROVIDER '{s.email_provider}'")

    from mcp import ClientSession  # noqa: PLC0415

    try:
        if s.gmail_mcp_url:
            from mcp.client.streamable_http import streamablehttp_client  # noqa: PLC0415

            async with streamablehttp_client(s.gmail_mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield _McpCaller(session)
        else:
            from mcp import StdioServerParameters  # noqa: PLC0415
            from mcp.client.stdio import get_default_environment, stdio_client  # noqa: PLC0415

            env = {**get_default_environment(), **server_env(), "PYTHONPATH": str(mcp_dir())}
            params = StdioServerParameters(command=sys.executable, args=["-m", "gmail_mcp.server"],
                                           cwd=str(mcp_dir()), env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield _McpCaller(session)
    except GatewayError:
        raise
    except OSError as e:
        raise GatewayError("retryable", f"Could not reach the Gmail MCP server: {e}") from e
