"""
ASGI entrypoint for Vercel Python runtime.
Exposes FastMCP Starlette streamable HTTP app.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gmail_mcp.server import mcp  # noqa: E402

app = mcp.streamable_http_app()

