"""Pure-ASGI middleware that authenticates MCP requests.

Why pure ASGI (not Starlette's BaseHTTPMiddleware):
- The MCP Streamable HTTP transport streams responses (SSE-style). BaseHTTPMiddleware
  buffers the response, which would break streaming. ASGI middleware is invisible
  to streaming.
- We only need to peek at the request (headers + query string); we don't need
  to read the body. ASGI lets us short-circuit on auth failure without ever
  touching `receive`.

Auth flow per request:
  1. Pull session_token from `X-Session-Token` header OR `?token=` query param
  2. Look up the session via token_store.get_session_with_fresh_token()
     (refreshes the PCO access_token automatically if close to expiry)
  3. Stash the resulting CurrentSession in a ContextVar
  4. Call the wrapped FastMCP app
  5. Reset the ContextVar in a `finally` so it can't leak across requests
"""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable
from urllib.parse import parse_qs

from app.auth import token_store
from app.auth.crypto import DecryptionError
from app.mcp.context import (
    CurrentSession,
    reset_current_session,
    set_current_session,
)


logger = logging.getLogger("pco_mcp.mcp.middleware")


# ASGI types — keep loose to avoid pulling in starlette types here.
Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


SESSION_HEADER_NAME = b"x-session-token"   # ASGI gives header names lowercased
SESSION_QUERY_NAME = "token"


class SessionMiddleware:
    """ASGI middleware that gates all MCP traffic on a valid session token."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Pass non-HTTP scopes through (e.g., lifespan, websocket).
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        token = _extract_session_token(scope)
        if not token:
            await _send_error(
                send,
                status=401,
                code="missing_session_token",
                message=(
                    "Provide a session token via the X-Session-Token header "
                    "or ?token= query parameter. Visit /auth/login to get one."
                ),
            )
            return

        # Look up the session and ensure the PCO access_token is fresh.
        try:
            session_row = await token_store.get_session_with_fresh_token(token)
        except token_store.RefreshFailed as exc:
            logger.warning("Refresh failed for session %s…: %s", token[:8], exc)
            await _send_error(
                send,
                status=401,
                code="session_refresh_failed",
                message=(
                    "Your Planning Center session can no longer be refreshed "
                    "(token may be older than 90 days or revoked). Please "
                    "re-authenticate at /auth/login."
                ),
            )
            return
        except DecryptionError:
            # ENCRYPTION_KEY changed since the row was written — unrecoverable.
            logger.error("Could not decrypt session %s… — ENCRYPTION_KEY mismatch?", token[:8])
            await _send_error(
                send,
                status=500,
                code="encryption_key_mismatch",
                message=(
                    "Server cannot decrypt the stored token. Contact the "
                    "administrator — this usually means ENCRYPTION_KEY has "
                    "been changed since this session was created."
                ),
            )
            return

        if session_row is None:
            await _send_error(
                send,
                status=401,
                code="invalid_session_token",
                message=(
                    "Unknown session token. Visit /auth/login to get a valid one."
                ),
            )
            return

        # Stash a frozen view for tools to read.
        current = CurrentSession.from_row(session_row)
        ctx_token = set_current_session(current)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_session(ctx_token)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_session_token(scope: Scope) -> str | None:
    """Pull the session token from header (preferred) or query param."""
    # ASGI headers come as a list of (name_bytes, value_bytes) — case is
    # lowercased per spec, but we still call .lower() for safety.
    for name, value in scope.get("headers", []):
        if name.lower() == SESSION_HEADER_NAME:
            decoded = value.decode("latin-1").strip()
            if decoded:
                return decoded

    qs = scope.get("query_string", b"")
    if qs:
        params = parse_qs(qs.decode("latin-1"))
        values = params.get(SESSION_QUERY_NAME)
        if values:
            token = values[0].strip()
            if token:
                return token

    return None


async def _send_error(
    send: Send, *, status: int, code: str, message: str
) -> None:
    """Emit a small JSON error response and end the ASGI cycle.

    MCP clients typically surface HTTP-level errors directly; we include a
    helpful JSON body so anyone debugging with curl can see what's wrong.
    """
    body = json.dumps({"error": code, "message": message}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})
