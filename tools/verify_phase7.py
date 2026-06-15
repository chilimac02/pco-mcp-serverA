"""End-to-end verification for Phase 7 write tools, with rollback.

This script makes REAL writes to your live PCO account. Each operation is
followed by a rollback so the account ends in the same state it started.

Tested cycles (every create has a matching delete in the same run):

  1. Blockout cycle (lowest risk — personal calendar entry):
       create_blockout(me, future date, "MCP test - DELETE ME")
         -> list_blockouts(me) confirms it appears
         -> delete_blockout(me, blockout_id)
         -> list_blockouts(me) confirms it's gone

  2. Song cycle (org-wide but easily reverted):
       create_song("ZZZ-PCO-MCP-TEST-DELETE-ME")
         -> get_song confirms
         -> update_song(title with " (updated)")
         -> get_song confirms update
         -> delete_song
         -> get_song -> 404 confirms gone

  3. Plan + plan_item cycle (full cascading rollback):
       create_plan in the FIRST service type, title "ZZZ-PCO-MCP-TEST-DELETE-ME"
         -> create_plan_item (header) inside it
         -> list_plan_items confirms the item is there
         -> update_plan_item changes its title
         -> update_plan changes the plan title
         -> delete_plan (cascades, removes the item too)
         -> get_plan -> 404 confirms gone

Skipped intentionally:
  - create_service_type / update_service_type — too sensitive for a test
  - send/accept/decline_schedule_request — would email real volunteers
  - create_team / update_team — no delete_team in our tool set, can't roll back
  - Tag assign/remove — depends on tag IDs which vary per account

If any step fails partway, the script prints the IDs it created so you can
clean them up manually in PCO.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import DB_PATH


MCP_URL = "http://127.0.0.1:8000/mcp"
PROTOCOL = "2024-11-05"
ACCEPT = "application/json, text/event-stream"
TEST_TAG = "ZZZ-PCO-MCP-TEST-DELETE-ME"


def fail(msg: str):
    print(f"FAIL: {msg}")
    sys.exit(1)


def passed(msg: str):
    print(f"[OK] {msg}")


def get_token() -> str:
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
        fail(f"SSE response had no data: line\n{resp.text}")
    fail(f"Unexpected content-type {ctype}\n{resp.text}")


def init_session(token: str) -> dict:
    r = httpx.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "verify_phase7", "version": "0.1"},
            },
        },
        headers={
            "Content-Type": "application/json",
            "Accept": ACCEPT,
            "X-Session-Token": token,
        },
        timeout=15.0,
    )
    if r.status_code not in (200, 202):
        fail(f"init: {r.status_code}\n{r.text}")
    sid = r.headers.get("mcp-session-id")
    headers = {"X-Session-Token": token, "mcp-session-id": sid}
    httpx.post(
        MCP_URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Content-Type": "application/json", "Accept": ACCEPT, **headers},
        timeout=10.0,
    )
    return headers


_req_id = [10]


def tool(name: str, args: dict | None, headers: dict, *, allow_error: bool = False) -> dict | str:
    """Call a tool. Returns parsed JSON dict on success, or the error message
    string if `allow_error=True` and the call failed."""
    _req_id[0] += 1
    rid = _req_id[0]
    r = httpx.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        },
        headers={"Content-Type": "application/json", "Accept": ACCEPT, **headers},
        timeout=30.0,
    )
    body = parse(r)
    if "error" in body:
        if allow_error:
            return body["error"].get("message", str(body["error"]))
        fail(f"{name} JSON-RPC error: {body['error']}")
    content = body.get("result", {}).get("content")
    if not content:
        if allow_error:
            # Tool may have returned isError=True with text content
            err = body.get("result", {})
            return str(err)
        fail(f"{name} returned no content")
    text = content[0]["text"]
    # FastMCP returns plain text for errors raised inside the tool
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if allow_error:
            return text
        fail(f"{name} returned non-JSON text: {text!r}")


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------

def blockout_cycle(headers: dict) -> None:
    print("\n=== Blockout cycle ===")
    me = tool("get_me", None, headers)
    person_id = me["id"]

    # Pick a date a week out so it doesn't collide with anything
    start = "2099-12-25T00:00:00Z"
    end = "2099-12-26T00:00:00Z"

    created = tool(
        "create_blockout",
        {
            "person_id": person_id,
            "reason": f"{TEST_TAG} — phase 7 verification",
            "starts_at": start,
            "ends_at": end,
        },
        headers,
    )
    bid = created.get("id")
    if not bid:
        fail(f"create_blockout returned no id: {created}")
    passed(f"create_blockout -> id={bid}, reason='{created.get('reason')}'")

    listing = tool("list_blockouts", {"person_id": person_id, "per_page": 100}, headers)
    if not any(b["id"] == bid for b in listing["blockouts"]):
        # Cleanup attempt then fail.
        tool("delete_blockout", {"person_id": person_id, "blockout_id": bid}, headers,
             allow_error=True)
        fail(f"created blockout {bid} not found in list_blockouts response")
    passed(f"list_blockouts confirms the new blockout is present")

    deleted = tool(
        "delete_blockout",
        {"person_id": person_id, "blockout_id": bid},
        headers,
    )
    if not deleted.get("deleted"):
        fail(f"delete_blockout returned unexpected: {deleted}")
    passed(f"delete_blockout({bid}) -> deleted")

    listing = tool("list_blockouts", {"person_id": person_id, "per_page": 100}, headers)
    if any(b["id"] == bid for b in listing["blockouts"]):
        fail(f"blockout {bid} still present after delete")
    passed("blockout no longer appears in list — rollback complete")


def song_cycle(headers: dict) -> None:
    print("\n=== Song cycle ===")
    created = tool(
        "create_song",
        {"title": TEST_TAG, "author": "PCO MCP Verify"},
        headers,
    )
    sid = created.get("id")
    if not sid:
        fail(f"create_song returned no id: {created}")
    passed(f"create_song -> id={sid}, title='{created.get('title')}'")

    got = tool("get_song", {"song_id": sid}, headers)
    if got.get("title") != TEST_TAG:
        tool("delete_song", {"song_id": sid}, headers, allow_error=True)
        fail(f"get_song returned wrong title: {got}")
    passed(f"get_song({sid}) confirms title")

    updated_title = f"{TEST_TAG} (updated)"
    upd = tool(
        "update_song",
        {"song_id": sid, "title": updated_title, "ccli_number": 9999999},
        headers,
    )
    if upd.get("title") != updated_title:
        tool("delete_song", {"song_id": sid}, headers, allow_error=True)
        fail(f"update_song didn't apply title change: {upd}")
    passed(f"update_song -> title='{upd.get('title')}', ccli_number={upd.get('ccli_number')}")

    deleted = tool("delete_song", {"song_id": sid}, headers)
    if not deleted.get("deleted"):
        fail(f"delete_song returned unexpected: {deleted}")
    passed(f"delete_song({sid}) -> deleted")

    # Confirm 404 via tool (it should raise PCONotFound which becomes an error)
    err = tool("get_song", {"song_id": sid}, headers, allow_error=True)
    if isinstance(err, dict) and err.get("id"):
        fail(f"get_song still found {sid} after delete: {err}")
    passed("get_song after delete -> not found (rollback complete)")


def plan_cycle(headers: dict) -> None:
    print("\n=== Plan + plan_item cycle ===")
    sts = tool("list_service_types", None, headers)["service_types"]
    if not sts:
        print("  no service types found — skipping plan cycle")
        return
    st_id = sts[0]["id"]
    st_name = sts[0].get("name")
    print(f"  using service_type id={st_id} '{st_name}'")

    # 1. create plan
    plan = tool(
        "create_plan",
        {
            "service_type_id": st_id,
            "title": TEST_TAG,
            "series_title": "Phase 7 Verify",
        },
        headers,
    )
    plan_id = plan.get("id")
    if not plan_id:
        fail(f"create_plan returned no id: {plan}")
    passed(f"create_plan -> id={plan_id}, title='{plan.get('title')}'")

    cleanup_plan_id = plan_id  # ensure we try to delete even if later steps fail

    try:
        # 2. add a header item (no song relationship needed)
        item = tool(
            "create_plan_item",
            {
                "service_type_id": st_id,
                "plan_id": plan_id,
                "item_type": "header",
                "title": f"{TEST_TAG} — header",
            },
            headers,
        )
        item_id = item.get("id")
        if not item_id:
            fail(f"create_plan_item returned no id: {item}")
        passed(f"create_plan_item -> id={item_id}, title='{item.get('title')}'")

        # 3. confirm via list_plan_items
        items = tool(
            "list_plan_items",
            {"service_type_id": st_id, "plan_id": plan_id, "per_page": 50},
            headers,
        )["items"]
        if not any(i["id"] == item_id for i in items):
            fail(f"item {item_id} not in list_plan_items")
        passed(f"list_plan_items confirms the item ({len(items)} item(s) on plan)")

        # 4. update item
        upd_item = tool(
            "update_plan_item",
            {
                "service_type_id": st_id,
                "plan_id": plan_id,
                "item_id": item_id,
                "title": f"{TEST_TAG} — UPDATED",
                "length": 90,
            },
            headers,
        )
        if "UPDATED" not in (upd_item.get("title") or ""):
            fail(f"update_plan_item didn't apply title: {upd_item}")
        passed(f"update_plan_item -> title='{upd_item.get('title')}', length={upd_item.get('length')}")

        # 5. update plan
        upd_plan = tool(
            "update_plan",
            {
                "service_type_id": st_id,
                "plan_id": plan_id,
                "title": f"{TEST_TAG} (renamed)",
            },
            headers,
        )
        if "renamed" not in (upd_plan.get("title") or ""):
            fail(f"update_plan didn't apply title: {upd_plan}")
        passed(f"update_plan -> title='{upd_plan.get('title')}'")

    finally:
        # 6. delete plan — cascade removes items too
        deleted = tool(
            "delete_plan",
            {"service_type_id": st_id, "plan_id": cleanup_plan_id},
            headers,
            allow_error=True,
        )
        if isinstance(deleted, dict) and deleted.get("deleted"):
            passed(f"delete_plan({cleanup_plan_id}) -> deleted (cascades to items)")
        else:
            print(f"WARNING: delete_plan failed; PLEASE MANUALLY DELETE plan id={cleanup_plan_id} "
                  f"in service_type {st_id}. Response: {deleted}")
            return

    # 7. confirm plan gone
    err = tool(
        "get_plan",
        {"service_type_id": st_id, "plan_id": cleanup_plan_id},
        headers,
        allow_error=True,
    )
    if isinstance(err, dict) and err.get("id"):
        fail(f"get_plan still found {cleanup_plan_id} after delete: {err}")
    passed("get_plan after delete -> not found (rollback complete)")


def main():
    token = get_token()
    print(f"Using session_token: {token}")
    headers = init_session(token)
    passed(f"handshake -> sid {headers['mcp-session-id'][:8]}...")

    # Quick tools/list sanity check — should be 69 now.
    r = httpx.post(
        MCP_URL,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers={"Content-Type": "application/json", "Accept": ACCEPT, **headers},
        timeout=15.0,
    )
    body = parse(r)
    n_tools = len(body["result"]["tools"])
    print(f"  tools registered: {n_tools}")
    if n_tools < 60:
        fail(f"Expected 60+ tools after Phase 7, got {n_tools}")

    started = time.time()
    blockout_cycle(headers)
    song_cycle(headers)
    plan_cycle(headers)
    print(f"\nAll Phase 7 cycles completed in {time.time() - started:.1f}s.")


if __name__ == "__main__":
    main()
