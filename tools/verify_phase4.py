"""End-to-end verification for Phase 4 MCP middleware + transport.

Tests, in order:
  1. POST /mcp with no token        -> 401, error="missing_session_token"
  2. POST /mcp with bogus token     -> 401, error="invalid_session_token"
  3. POST /mcp initialize via header (valid token)   -> 200 + session-id header
  4. POST /mcp tools/list via header                 -> includes _diagnostic_ping
  5. POST /mcp tools/call _diagnostic_ping via hdr   -> returns user's PCO name
  6. Same flow but with ?token= query param          -> same success

Reads the session token from SQLite so we don't need to hardcode it.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import DB_PATH


MCP_URL = "http://127.0.0.1:8000/mcp"
PROTOCOL_VERSION = "2024-11-05"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def passed(msg: str) -> None:
    print(f"[OK] {msg}")


def get_session_token() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT session_token FROM sessions LIMIT 1").fetchone()
    if not row:
        sys.exit("No session in DB — run OAuth flow first.")
    return row[0]


# Streamable HTTP transport requires *both* JSON and SSE acceptance for
# responses (server picks one). Easiest to send both on every request.
ACCEPT = "application/json, text/event-stream"


def parse_response(resp: httpx.Response) -> dict:
    """Return the JSON-RPC payload regardless of whether the server replied
    with application/json or text/event-stream."""
    ctype = resp.headers.get("content-type", "")
    body = resp.text
    if "application/json" in ctype:
        return resp.json()
    if "text/event-stream" in ctype:
        # Find the first `data: {...}` line and parse it.
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        fail(f"SSE response had no data: line\n{body}")
    fail(f"Unexpected content-type {ctype!r}; body:\n{body}")


def mcp_post(payload: dict, *, headers: dict | None = None, url: str = MCP_URL) -> httpx.Response:
    hdrs = {"Content-Type": "application/json", "Accept": ACCEPT}
    if headers:
        hdrs.update(headers)
    return httpx.post(url, json=payload, headers=hdrs, timeout=10.0)


def main() -> None:
    token = get_session_token()
    print(f"Using session_token: {token}\n")

    # ----- 1. Missing token --------------------------------------------
    r = mcp_post({"jsonrpc": "2.0", "method": "ping", "id": 1})
    if r.status_code != 401:
        fail(f"#1 expected 401 with no token; got {r.status_code}\n{r.text}")
    body = r.json()
    if body.get("error") != "missing_session_token":
        fail(f"#1 expected error code missing_session_token; got {body}")
    passed("no token -> 401 missing_session_token")

    # ----- 2. Bogus token ----------------------------------------------
    bogus = str(uuid.uuid4())
    r = mcp_post({"jsonrpc": "2.0", "method": "ping", "id": 2},
                 headers={"X-Session-Token": bogus})
    if r.status_code != 401:
        fail(f"#2 expected 401 with bogus token; got {r.status_code}\n{r.text}")
    body = r.json()
    if body.get("error") != "invalid_session_token":
        fail(f"#2 expected error code invalid_session_token; got {body}")
    passed("bogus token -> 401 invalid_session_token")

    # ----- 3. initialize via header ------------------------------------
    initialize_payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "verify_phase4", "version": "0.1"},
        },
    }
    r = mcp_post(initialize_payload, headers={"X-Session-Token": token})
    if r.status_code not in (200, 202):
        fail(f"#3 initialize: {r.status_code}\n{r.text}")
    init_body = parse_response(r)
    server_name = init_body.get("result", {}).get("serverInfo", {}).get("name")
    if server_name != "planning-center":
        fail(f"#3 unexpected serverInfo: {init_body}")
    mcp_session_id = r.headers.get("mcp-session-id")
    if not mcp_session_id:
        fail("#3 server did not return mcp-session-id header on initialize")
    passed(f"initialize via header -> serverInfo.name={server_name}, "
           f"mcp-session-id={mcp_session_id[:8]}...")

    # Streamable HTTP requires a follow-up `notifications/initialized` after
    # the initialize handshake before tools/* requests are accepted.
    auth_session_headers = {
        "X-Session-Token": token,
        "mcp-session-id": mcp_session_id,
    }
    r = mcp_post(
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=auth_session_headers,
    )
    if r.status_code not in (200, 202, 204):
        fail(f"#3b notifications/initialized: {r.status_code}\n{r.text}")

    # ----- 4. tools/list -----------------------------------------------
    r = mcp_post(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        headers=auth_session_headers,
    )
    tools_body = parse_response(r)
    tool_names = [t["name"] for t in tools_body.get("result", {}).get("tools", [])]
    if "_diagnostic_ping" not in tool_names:
        fail(f"#4 _diagnostic_ping missing from tools/list: {tool_names}")
    passed(f"tools/list -> {tool_names}")

    # ----- 5. tools/call _diagnostic_ping ------------------------------
    r = mcp_post(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "_diagnostic_ping", "arguments": {}},
        },
        headers=auth_session_headers,
    )
    call_body = parse_response(r)
    content = call_body.get("result", {}).get("content", [])
    if not content:
        fail(f"#5 empty content from _diagnostic_ping: {call_body}")
    # FastMCP serialises dict returns as JSON inside a text content item.
    payload_text = content[0].get("text", "")
    payload = json.loads(payload_text)
    if payload.get("pong") is not True:
        fail(f"#5 ping payload missing pong=True: {payload}")
    if not payload.get("pco_user_name"):
        fail(f"#5 ping payload missing pco_user_name: {payload}")
    passed(f"tools/call _diagnostic_ping -> {payload}")

    header_user_name = payload["pco_user_name"]

    # ----- 6. Same flow via ?token= query param ------------------------
    # Repeat initialize + initialized + tools/call with the token in the URL
    # rather than a header. Anything else (mcp-session-id) still comes via
    # headers since that's how the MCP transport works.
    url_with_token = f"{MCP_URL}?token={token}"

    r = mcp_post(initialize_payload, url=url_with_token)
    if r.status_code not in (200, 202):
        fail(f"#6 init via ?token: {r.status_code}\n{r.text}")
    qs_session_id = r.headers.get("mcp-session-id")
    if not qs_session_id:
        fail("#6 init via ?token: missing mcp-session-id")
    qs_session_headers = {"mcp-session-id": qs_session_id}

    mcp_post(
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=qs_session_headers,
        url=url_with_token,
    )

    r = mcp_post(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "_diagnostic_ping", "arguments": {}},
        },
        headers=qs_session_headers,
        url=url_with_token,
    )
    body = parse_response(r)
    content = body.get("result", {}).get("content", [])
    payload2 = json.loads(content[0]["text"]) if content else {}
    if payload2.get("pco_user_name") != header_user_name:
        fail(f"#6 query-param flow returned different user: {payload2}")
    passed(f"?token= query param flow -> same user ({header_user_name})")

    print("\nAll Phase 4 checks passed.")


if __name__ == "__main__":
    main()
