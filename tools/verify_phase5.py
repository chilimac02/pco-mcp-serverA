"""End-to-end verification for Phase 5 — first real PCO data through MCP.

Walks through the Streamable HTTP transport with the session token loaded
from SQLite, then invokes each new tool and asserts the response shape +
includes plausible real data.

Checks:
  1. tools/list                            -> includes get_me, list_service_types, get_service_type
  2. tools/call get_me                     -> returns id=3531037, name='Justin Allison'
  3. tools/call list_service_types         -> returns >=0 service_types, paginated shape
  4. (if service types exist) get_service_type({first.id}) -> returns the same id
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import DB_PATH


MCP_URL = "http://127.0.0.1:8000/mcp"
PROTOCOL = "2024-11-05"
ACCEPT = "application/json, text/event-stream"


def fail(msg: str):
    print(f"FAIL: {msg}")
    sys.exit(1)


def passed(msg: str):
    print(f"[OK] {msg}")


def session_token() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT session_token FROM sessions LIMIT 1").fetchone()
    if not row:
        sys.exit("No session in DB — run OAuth flow first.")
    return row[0]


def parse(resp: httpx.Response) -> dict:
    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        return resp.json()
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        fail(f"No data: line in SSE response\n{resp.text}")
    fail(f"Unexpected content-type {ctype}\n{resp.text}")


def call(payload: dict, *, headers: dict, **kw) -> httpx.Response:
    h = {"Content-Type": "application/json", "Accept": ACCEPT, **headers}
    return httpx.post(MCP_URL, json=payload, headers=h, timeout=30.0, **kw)


def tool_payload(name: str, args: dict | None = None, *, req_id: int) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": args or {}},
    }


def main():
    token = session_token()
    print(f"Using session_token: {token}\n")

    # ----- initialize handshake (required) -----------------------------
    init_resp = call(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "verify_phase5", "version": "0.1"},
            },
        },
        headers={"X-Session-Token": token},
    )
    if init_resp.status_code not in (200, 202):
        fail(f"initialize failed: {init_resp.status_code}\n{init_resp.text}")
    mcp_sid = init_resp.headers.get("mcp-session-id")
    if not mcp_sid:
        fail("initialize did not return mcp-session-id header")
    base_headers = {"X-Session-Token": token, "mcp-session-id": mcp_sid}
    call({"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=base_headers)
    passed(f"initialize handshake -> mcp-session-id {mcp_sid[:8]}...")

    # ----- 1. tools/list now includes new tools ------------------------
    r = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=base_headers)
    tools = [t["name"] for t in parse(r).get("result", {}).get("tools", [])]
    expected = {"get_me", "list_service_types", "get_service_type"}
    missing = expected - set(tools)
    if missing:
        fail(f"#1 tools/list missing {missing}; got {tools}")
    passed(f"tools/list -> {sorted(tools)}")

    # ----- 2. get_me ---------------------------------------------------
    r = call(tool_payload("get_me", req_id=3), headers=base_headers)
    me = json.loads(parse(r)["result"]["content"][0]["text"])
    if me.get("id") != "3531037":
        fail(f"#2 get_me returned unexpected id: {me}")
    if not me.get("name"):
        fail(f"#2 get_me returned no name: {me}")
    passed(f"get_me -> id={me['id']}, name='{me['name']}', "
           f"first_name='{me.get('first_name')}', last_name='{me.get('last_name')}'")

    # ----- 3. list_service_types ---------------------------------------
    r = call(tool_payload("list_service_types", req_id=4), headers=base_headers)
    body = parse(r)
    if "error" in body:
        fail(f"#3 list_service_types JSON-RPC error: {body['error']}")
    result = json.loads(body["result"]["content"][0]["text"])
    for key in ("service_types", "count", "total_count", "offset", "per_page"):
        if key not in result:
            fail(f"#3 list_service_types result missing key '{key}': {result}")
    items = result["service_types"]
    print(f"     service_types returned: count={result['count']}, "
          f"total_count={result['total_count']}, next_offset={result.get('next_offset')}")
    for st in items[:5]:
        print(f"       - id={st['id']:>8}  name={st.get('name')}")
    passed("list_service_types -> properly paginated response")

    # ----- 4. get_service_type (if we got at least one) ----------------
    if items:
        target_id = items[0]["id"]
        r = call(
            tool_payload("get_service_type", {"service_type_id": target_id}, req_id=5),
            headers=base_headers,
        )
        body = parse(r)
        if "error" in body:
            fail(f"#4 get_service_type error: {body['error']}")
        st = json.loads(body["result"]["content"][0]["text"])
        if st.get("id") != target_id:
            fail(f"#4 get_service_type returned wrong id: requested {target_id}, got {st}")
        passed(f"get_service_type({target_id}) -> name='{st.get('name')}'")
    else:
        print("[SKIP] get_service_type — no service types in this PCO account")

    print("\nAll Phase 5 checks passed.")


if __name__ == "__main__":
    main()
