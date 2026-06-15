"""End-to-end verification for Phase 6 read tools.

Smoke-tests one representative tool from each module against real PCO data,
chaining IDs from one call to the next:

    list_service_types -> pick first -> list_plans
                                       -> pick first plan -> list_plan_items
                                                          -> list_plan_team_members
                                                          -> list_plan_notes
                       -> list_teams -> pick first -> list_team_positions
                       -> list_note_categories
    list_songs -> pick first -> get_song
                              -> list_arrangements -> pick first -> list_keys
                                                                 -> list_attachments
                              -> get_song_tags
    list_tag_groups -> pick first -> list_tags

Asserts that tools/list reports all expected tools and that each call
returns the canonical paginated shape with non-error data.
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


EXPECTED_TOOLS = {
    # Phase 4-5
    "_diagnostic_ping", "get_me",
    "list_service_types", "get_service_type",
    # Phase 6 plans
    "list_plans", "get_plan", "list_plan_items", "get_plan_item", "list_plan_times",
    # Phase 6 songs
    "list_songs", "get_song", "get_song_schedules",
    "list_arrangements", "get_arrangement", "list_keys", "list_attachments",
    # Phase 6 teams
    "list_teams", "get_team", "list_team_positions",
    # Phase 6 volunteers
    "list_plan_team_members", "get_plan_team_member", "list_blockouts",
    # Phase 6 notes
    "list_plan_notes", "get_plan_note", "list_note_categories",
    # Phase 6 song tags
    "list_tag_groups", "list_tags", "get_song_tags",
}


def fail(msg: str):
    print(f"FAIL: {msg}")
    sys.exit(1)


def passed(msg: str):
    print(f"[OK] {msg}")


def get_token() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT session_token FROM sessions LIMIT 1").fetchone()
    if not row:
        sys.exit("No session in DB.")
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


def call(payload: dict, *, headers: dict) -> dict:
    h = {"Content-Type": "application/json", "Accept": ACCEPT, **headers}
    resp = httpx.post(MCP_URL, json=payload, headers=h, timeout=30.0)
    if resp.status_code not in (200, 202):
        fail(f"HTTP {resp.status_code} for {payload.get('method')}/{payload.get('params', {}).get('name')}\n{resp.text}")
    return parse(resp)


def tool(name: str, args: dict | None, req_id: int, headers: dict) -> dict:
    body = call(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        },
        headers=headers,
    )
    if "error" in body:
        fail(f"Tool {name} errored: {body['error']}")
    content = body["result"]["content"]
    if not content:
        fail(f"Tool {name} returned empty content")
    return json.loads(content[0]["text"])


def main():
    token = get_token()
    print(f"Using session_token: {token}\n")

    # ----- handshake ---------------------------------------------------
    init_resp = httpx.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "verify_phase6", "version": "0.1"},
            },
        },
        headers={
            "Content-Type": "application/json",
            "Accept": ACCEPT,
            "X-Session-Token": token,
        },
        timeout=10.0,
    )
    if init_resp.status_code not in (200, 202):
        fail(f"init: {init_resp.status_code}\n{init_resp.text}")
    sid = init_resp.headers["mcp-session-id"]
    base = {"X-Session-Token": token, "mcp-session-id": sid}
    httpx.post(
        MCP_URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Content-Type": "application/json", "Accept": ACCEPT, **base},
        timeout=10.0,
    )
    passed(f"handshake -> sid {sid[:8]}...")

    # ----- 1. tools/list completeness ----------------------------------
    body = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=base)
    actual = {t["name"] for t in body["result"]["tools"]}
    missing = EXPECTED_TOOLS - actual
    extra = actual - EXPECTED_TOOLS
    if missing:
        fail(f"tools/list missing: {sorted(missing)}")
    if extra:
        print(f"  (note: unexpected tools also present: {sorted(extra)})")
    passed(f"tools/list reports all {len(EXPECTED_TOOLS)} expected tools")

    # ----- 2. service types -> plans chain -----------------------------
    sts = tool("list_service_types", None, 3, base)["service_types"]
    if not sts:
        fail("No service types — can't continue chain")
    st_id = sts[0]["id"]
    st_name = sts[0].get("name")
    print(f"  using service_type id={st_id} name='{st_name}'")

    plans = tool("list_plans", {"service_type_id": st_id, "filter": "past",
                                 "order": "-sort_date", "per_page": 5}, 4, base)
    plan_items = plans["plans"]
    if not plan_items:
        # Try without filter
        plans = tool("list_plans", {"service_type_id": st_id, "per_page": 5}, 5, base)
        plan_items = plans["plans"]
    if not plan_items:
        print("  no plans in this service type — skipping plan chain")
        plan_id = None
    else:
        plan_id = plan_items[0]["id"]
        passed(f"list_plans -> {len(plan_items)} returned (total={plans.get('total_count')})")
        for p in plan_items[:3]:
            print(f"    - plan id={p['id']}  title='{p.get('title')}'  sort_date='{p.get('sort_date')}'")

        get_p = tool("get_plan", {"service_type_id": st_id, "plan_id": plan_id}, 6, base)
        if get_p.get("id") != plan_id:
            fail(f"get_plan returned wrong id: {get_p}")
        passed(f"get_plan({plan_id}) -> title='{get_p.get('title')}'")

        items = tool("list_plan_items", {"service_type_id": st_id, "plan_id": plan_id,
                                         "per_page": 10}, 7, base)["items"]
        passed(f"list_plan_items -> {len(items)} items")

        times = tool("list_plan_times", {"service_type_id": st_id, "plan_id": plan_id}, 8, base)["plan_times"]
        passed(f"list_plan_times -> {len(times)} times")

        members = tool("list_plan_team_members", {"service_type_id": st_id, "plan_id": plan_id,
                                                  "per_page": 10}, 9, base)["plan_team_members"]
        passed(f"list_plan_team_members -> {len(members)} members")

        notes = tool("list_plan_notes", {"service_type_id": st_id, "plan_id": plan_id}, 10, base)["notes"]
        passed(f"list_plan_notes -> {len(notes)} notes")

    # ----- 3. teams chain ----------------------------------------------
    teams = tool("list_teams", {"service_type_id": st_id, "per_page": 5}, 11, base)["teams"]
    passed(f"list_teams -> {len(teams)} teams")
    for t in teams[:3]:
        print(f"    - team id={t['id']}  name='{t.get('name')}'")
    if teams:
        team_id = teams[0]["id"]
        get_t = tool("get_team", {"service_type_id": st_id, "team_id": team_id}, 12, base)
        if get_t.get("id") != team_id:
            fail(f"get_team returned wrong id: {get_t}")
        passed(f"get_team({team_id}) -> name='{get_t.get('name')}'")

        positions = tool("list_team_positions", {"service_type_id": st_id, "team_id": team_id}, 13, base)["team_positions"]
        passed(f"list_team_positions -> {len(positions)} positions")

    note_cats = tool("list_note_categories", {"service_type_id": st_id}, 14, base)["note_categories"]
    passed(f"list_note_categories -> {len(note_cats)} categories")

    # ----- 4. songs chain ----------------------------------------------
    songs = tool("list_songs", {"per_page": 5, "order": "-updated_at"}, 15, base)["songs"]
    passed(f"list_songs -> {len(songs)} songs (total={tool('list_songs', {'per_page': 1}, 16, base).get('total_count')})")
    for s in songs[:3]:
        print(f"    - song id={s['id']}  title='{s.get('title')}'  author='{s.get('author')}'")
    if songs:
        song_id = songs[0]["id"]
        get_s = tool("get_song", {"song_id": song_id}, 17, base)
        passed(f"get_song({song_id}) -> title='{get_s.get('title')}'")

        arrs = tool("list_arrangements", {"song_id": song_id}, 18, base)["arrangements"]
        passed(f"list_arrangements -> {len(arrs)} arrangements")
        if arrs:
            arr_id = arrs[0]["id"]
            keys = tool("list_keys", {"song_id": song_id, "arrangement_id": arr_id}, 19, base)["keys"]
            atts = tool("list_attachments", {"song_id": song_id, "arrangement_id": arr_id}, 20, base)["attachments"]
            passed(f"list_keys -> {len(keys)} keys; list_attachments -> {len(atts)} attachments")

        song_tags = tool("get_song_tags", {"song_id": song_id}, 21, base)["tags"]
        passed(f"get_song_tags({song_id}) -> {len(song_tags)} tags")

    # ----- 5. tag groups -----------------------------------------------
    tgs = tool("list_tag_groups", None, 22, base)["tag_groups"]
    passed(f"list_tag_groups -> {len(tgs)} tag groups")
    if tgs:
        tg_id = tgs[0]["id"]
        tags = tool("list_tags", {"tag_group_id": tg_id}, 23, base)["tags"]
        passed(f"list_tags({tg_id}) -> {len(tags)} tags")

    # ----- 6. blockouts for current user -------------------------------
    me = tool("get_me", None, 24, base)
    bos = tool("list_blockouts", {"person_id": me["id"]}, 25, base)["blockouts"]
    passed(f"list_blockouts(me) -> {len(bos)} blockouts")

    print("\nAll Phase 6 checks passed.")


if __name__ == "__main__":
    main()
