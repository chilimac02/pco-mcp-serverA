"""FastMCP server instance + Phase-4 diagnostic tool.

Phase 4 ships ONE tool: `_diagnostic_ping`. It does no PCO work — it just
reads the per-request CurrentSession from the contextvar and returns a tiny
JSON payload. The point is to validate end-to-end that:

  * The Streamable HTTP transport is reachable at /mcp
  * The SessionMiddleware ran (or the call would have 401'd)
  * The contextvar was actually populated for the tool

Phase 5 deletes this and adds the real tools (`get_me`, `list_service_types`,
…). Leaving the diagnostic in place harmlessly through Phase 5 is fine if
we want it for ongoing health checks.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from app.config import get_settings
from app.mcp.context import get_current_session


logger = logging.getLogger("pco_mcp.mcp.server")


def _build_mcp() -> FastMCP:
    """Construct the FastMCP instance.

    `log_level` is passed explicitly because FastMCP reads env vars with the
    `FASTMCP_` prefix AND a plain `LOG_LEVEL` fallback — our .env has
    `LOG_LEVEL=info` (lowercase) which doesn't match FastMCP's required
    enum. Forcing it here neutralises the collision.

    `streamable_http_path="/"` so the FastMCP Starlette app's route lives at
    the root of its sub-app. We then mount that sub-app at /mcp in
    main.py, giving us the public endpoint at exactly /mcp (not /mcp/mcp).
    """
    settings = get_settings()
    return FastMCP(
        name="planning-center",
        instructions=(
            "Planning Center Services MCP server. Each user authenticates "
            "with their own PCO account, so tool calls are constrained by "
            "the calling user's PCO permissions."
        ),
        log_level=settings.log_level.upper(),
        streamable_http_path="/",
    )


mcp = _build_mcp()


# ---------------------------------------------------------------------------
# Diagnostic tool (Phase 4 — wiring sanity check)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="_diagnostic_ping",
    description=(
        "Connectivity check. Returns 'pong' along with the authenticated "
        "Planning Center user's name and ID. Use this to confirm your "
        "session token is wired up correctly."
    ),
)
def diagnostic_ping() -> dict:
    """Returns identity + ping, sourced from the per-request contextvar."""
    session = get_current_session()
    return {
        "pong": True,
        "pco_user_id": session.pco_user_id,
        "pco_user_name": session.pco_user_name,
        "scopes": session.scopes,
        "access_token_expires_in_seconds": max(
            0, session.token_expires - _now()
        ),
    }


def _now() -> int:
    import time
    return int(time.time())


# ---------------------------------------------------------------------------
# ASGI export — wrapped with SessionMiddleware in main.py
# ---------------------------------------------------------------------------

def get_streamable_http_app():
    """Returns the Starlette ASGI app that handles MCP Streamable HTTP.

    main.py wraps this with `SessionMiddleware` and mounts it at /mcp.
    """
    return mcp.streamable_http_app()


# ---------------------------------------------------------------------------
# Tool registration — imports below trigger @mcp.tool() decorators
# ---------------------------------------------------------------------------
#
# Each module imports `mcp` from THIS module and decorates its functions
# with @mcp.tool(). Importing the modules at the bottom (after `mcp` is
# constructed) ensures the decorators see a fully-built FastMCP instance.
#
# Adding a new tools module:
#   1. Create app/mcp/tools/<area>.py
#   2. Import the `mcp` instance from app.mcp.server
#   3. Decorate functions with @mcp.tool(name=..., description=...)
#   4. Add `from app.mcp.tools import <area> as _<area>` below
#   5. The `as _<area>` keeps linters from yelling about unused imports
#
# Order matters only if tool modules cross-import; today they don't.

from app.mcp.tools import me as _me  # noqa: E402, F401  — registers get_me
from app.mcp.tools import service_types as _service_types  # noqa: E402, F401
# Phase 6: read tools across the rest of the Services API.
from app.mcp.tools import plans as _plans  # noqa: E402, F401
from app.mcp.tools import songs as _songs  # noqa: E402, F401
from app.mcp.tools import teams as _teams  # noqa: E402, F401
from app.mcp.tools import volunteers as _volunteers  # noqa: E402, F401
from app.mcp.tools import notes as _notes  # noqa: E402, F401
from app.mcp.tools import song_tags as _song_tags  # noqa: E402, F401
