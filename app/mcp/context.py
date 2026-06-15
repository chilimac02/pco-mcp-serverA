"""Per-request session context for MCP tool calls.

The ASGI middleware in `middleware.py` looks up the calling user's PCO
session (decrypted access_token + user identity) and stashes it in a
`ContextVar`. Tool functions read it via `get_current_session()`.

Why a contextvar (vs threading.local or a request-scoped FastAPI dep):
- ContextVar is asyncio-aware: each Task gets its own copy, isolated from
  concurrent requests.
- FastMCP tools are plain async functions — no DI mechanism to thread a
  Request object into them. ContextVar gives ambient access without
  changing every tool signature.
- Each HTTP request to /mcp handles a single JSON-RPC message in Streamable
  HTTP, so we don't need fancy scoping — the middleware sets it on entry
  and resets on exit.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CurrentSession:
    """Frozen view of the calling user's session for tools to read.

    Built once per request by the middleware. Includes everything a tool
    needs to act as the user (the decrypted access_token) and to identify
    them (PCO user id + name).

    Don't pass this object across requests — it's tied to one MCP call and
    its access_token may be stale outside that window.
    """

    session_token: str
    pco_user_id: str
    pco_user_name: str | None
    pco_user_email: str | None
    access_token: str
    scopes: str
    token_expires: int

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CurrentSession":
        """Build from a token_store.get_session() result dict."""
        return cls(
            session_token=row["session_token"],
            pco_user_id=row["pco_user_id"],
            pco_user_name=row.get("pco_user_name"),
            pco_user_email=row.get("pco_user_email"),
            access_token=row["access_token"],
            scopes=row.get("scopes", ""),
            token_expires=int(row["token_expires"]),
        )


# The actual ContextVar. No default → calling get() outside a request raises
# LookupError, which the helper below turns into a clearer RuntimeError.
_current_session: contextvars.ContextVar[CurrentSession] = contextvars.ContextVar(
    "pco_current_session"
)


def set_current_session(session: CurrentSession) -> contextvars.Token:
    """Used by the ASGI middleware; tools should NOT call this."""
    return _current_session.set(session)


def reset_current_session(token: contextvars.Token) -> None:
    """Pair of `set_current_session` — middleware resets in a finally block."""
    _current_session.reset(token)


def get_current_session() -> CurrentSession:
    """Read the calling user's session from inside a tool function.

    Raises RuntimeError if no session is set — almost always a sign the tool
    was invoked outside the MCP middleware (e.g., in a unit test that
    didn't seed the context).
    """
    try:
        return _current_session.get()
    except LookupError as exc:
        raise RuntimeError(
            "No PCO session in context — tool was called outside the MCP "
            "middleware, or the middleware failed to set the context."
        ) from exc
