"""Plan tools — the heart of the Services API.

A Plan is a single service occurrence (e.g., "Sunday Morning, May 31 9:00am").
Plans live under a service type and contain ordered items (songs, headers,
media), team assignments, scheduled times, and notes.
"""

from __future__ import annotations

from typing import Annotated

from app.mcp.context import get_current_session
from app.mcp.server import mcp
from app.mcp.tools._common import (
    build_jsonapi_body,
    clamp_pagination,
    flatten_resource,
    jsonapi_relationship,
    paginated_response,
)
from app.pco.client import PCOClient


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_plans",
    description=(
        "List plans within a service type, ordered by sort_date by default. "
        "Use the `filter` parameter to restrict to 'future' or 'past' plans. "
        "Each plan includes title, dates, and basic metadata; use get_plan "
        "for full detail."
    ),
)
async def list_plans(
    service_type_id: Annotated[str, "Service type ID — use list_service_types to discover"],
    filter: Annotated[str | None, "Optional: 'future', 'past', 'no_dates', or 'planning_center_published'"] = None,
    order: Annotated[str, "Sort field; prefix with '-' to reverse (e.g., '-sort_date')"] = "sort_date",
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    params: dict = {"per_page": per_page, "offset": offset, "order": order}
    if filter:
        params["filter"] = filter

    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans",
        params=params,
    )
    return paginated_response(
        response=response, items_key="plans", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="get_plan",
    description="Fetch one plan by ID (within a service type).",
)
async def get_plan(service_type_id: str, plan_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
    )
    return flatten_resource(response.get("data"))


# ---------------------------------------------------------------------------
# Plan items (the songs/headers/media in the running order)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_plan_items",
    description=(
        "List items in a plan in order — songs, headers, and media that make "
        "up the running order. Items include the linked song id, key, length, "
        "and description."
    ),
)
async def list_plan_items(
    service_type_id: str,
    plan_id: str,
    per_page: int = 100,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="items", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="get_plan_item",
    description="Fetch one item from a plan.",
)
async def get_plan_item(service_type_id: str, plan_id: str, item_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items/{item_id}"
    )
    return flatten_resource(response.get("data"))


# ---------------------------------------------------------------------------
# Plan times (the scheduled service occurrences for this plan)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_plan_times",
    description=(
        "List the scheduled service times for a plan (e.g., 9am and 11am "
        "services on the same Sunday share a plan but have multiple times)."
    ),
)
async def list_plan_times(service_type_id: str, plan_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/plan_times",
        params={"per_page": 100},
    )
    return paginated_response(
        response=response, items_key="plan_times", offset=0, per_page=100
    )


# ===========================================================================
# Writes (Phase 7)
# ===========================================================================
# Permission notes: PCO enforces team-level + plan-level permissions on
# every write. A user with edit access to a service type can typically
# create/update/delete plans within it; everyone else gets 403.

# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_plan",
    description=(
        "Create a new plan inside a service type. `dates` is a free-form "
        "human-readable string ('Sunday May 31') stored as-is; `sort_date` "
        "is the ISO-8601 timestamp used for ordering."
    ),
)
async def create_plan(
    service_type_id: str,
    title: str | None = None,
    series_title: str | None = None,
    dates: str | None = None,
    sort_date: str | None = None,
    public: bool | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Plan",
        attributes={
            "title": title,
            "series_title": series_title,
            "dates": dates,
            "sort_date": sort_date,
            "public": public,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/plans", json=body
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_plan",
    description="Update plan fields. Pass only what you want to change.",
)
async def update_plan(
    service_type_id: str,
    plan_id: str,
    title: str | None = None,
    series_title: str | None = None,
    dates: str | None = None,
    sort_date: str | None = None,
    public: bool | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Plan",
        attributes={
            "title": title,
            "series_title": series_title,
            "dates": dates,
            "sort_date": sort_date,
            "public": public,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}", json=body
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_plan",
    description=(
        "Delete a plan. PCO cascades — items, times, notes, and team-member "
        "assignments on the plan are deleted with it. Irreversible."
    ),
)
async def delete_plan(service_type_id: str, plan_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
    )
    return {"deleted": True, "plan_id": plan_id}


@mcp.tool(
    name="copy_plan",
    description=(
        "Copy an existing plan into the same (or a different) service type. "
        "Choose what to carry over via copy_items / copy_people / copy_notes "
        "/ copy_team. The new plan is returned."
    ),
)
async def copy_plan(
    service_type_id: str,
    plan_id: str,
    plan_title: str | None = None,
    copy_items: bool = True,
    copy_people: bool = False,
    copy_notes: bool = False,
    copy_team: bool = False,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="PlanCopy",
        attributes={
            "plan_title": plan_title,
            "copy_items": copy_items,
            "copy_people": copy_people,
            "copy_notes": copy_notes,
            "copy_team": copy_team,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/copy",
        json=body,
    )
    return flatten_resource(response.get("data"))


# ---------------------------------------------------------------------------
# Plan items
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_plan_item",
    description=(
        "Add an item to a plan's running order. item_type is one of "
        "'song', 'header', 'media', or 'item'. For songs, pass song_id "
        "(and optionally arrangement_id + key_id). For headers and freeform "
        "items, just set title and item_type."
    ),
)
async def create_plan_item(
    service_type_id: str,
    plan_id: str,
    item_type: str = "item",
    title: str | None = None,
    length: int | None = None,
    description: str | None = None,
    song_id: str | None = None,
    arrangement_id: str | None = None,
    key_id: str | None = None,
) -> dict:
    session = get_current_session()
    relationships: dict = {}
    if song_id:
        relationships["song"] = jsonapi_relationship("Song", song_id)
    if arrangement_id:
        relationships["arrangement"] = jsonapi_relationship("Arrangement", arrangement_id)
    if key_id:
        relationships["key"] = jsonapi_relationship("Key", key_id)

    body = build_jsonapi_body(
        type_="Item",
        attributes={
            "item_type": item_type,
            "title": title,
            "length": length,
            "description": description,
        },
        relationships=relationships or None,
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_plan_item",
    description="Update an item's title / length / description / etc.",
)
async def update_plan_item(
    service_type_id: str,
    plan_id: str,
    item_id: str,
    title: str | None = None,
    length: int | None = None,
    description: str | None = None,
    item_type: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Item",
        attributes={
            "title": title,
            "length": length,
            "description": description,
            "item_type": item_type,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items/{item_id}",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_plan_item",
    description="Remove an item from a plan's running order. Irreversible.",
)
async def delete_plan_item(service_type_id: str, plan_id: str, item_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items/{item_id}"
    )
    return {"deleted": True, "item_id": item_id}


@mcp.tool(
    name="reorder_plan_items",
    description=(
        "Reorder a plan's items. Provide `item_ids` as the new top-to-bottom "
        "order — every item currently in the plan must be present in the list."
    ),
)
async def reorder_plan_items(
    service_type_id: str,
    plan_id: str,
    item_ids: list[str],
) -> dict:
    session = get_current_session()
    # PCO's reorder endpoint takes a special PlanItemReorder envelope.
    body = build_jsonapi_body(
        type_="PlanItemReorder",
        attributes={"sequence": [str(i) for i in item_ids]},
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items/reorder",
        json=body,
    )
    # Reorder returns a thin acknowledgement; surface raw response.
    return response or {"reordered": True, "plan_id": plan_id, "count": len(item_ids)}


# ---------------------------------------------------------------------------
# Plan times
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_plan_time",
    description=(
        "Add a scheduled service time to a plan. `starts_at` and `ends_at` "
        "are ISO-8601 timestamps. time_type is one of 'rehearsal', "
        "'service', or 'other'."
    ),
)
async def create_plan_time(
    service_type_id: str,
    plan_id: str,
    starts_at: str,
    ends_at: str | None = None,
    name: str | None = None,
    time_type: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="PlanTime",
        attributes={
            "starts_at": starts_at,
            "ends_at": ends_at,
            "name": name,
            "time_type": time_type,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/plan_times",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_plan_time",
    description="Update one of a plan's scheduled times.",
)
async def update_plan_time(
    service_type_id: str,
    plan_id: str,
    plan_time_id: str,
    starts_at: str | None = None,
    ends_at: str | None = None,
    name: str | None = None,
    time_type: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="PlanTime",
        attributes={
            "starts_at": starts_at,
            "ends_at": ends_at,
            "name": name,
            "time_type": time_type,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
        f"/plan_times/{plan_time_id}",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_plan_time",
    description="Remove a scheduled time from a plan.",
)
async def delete_plan_time(
    service_type_id: str, plan_id: str, plan_time_id: str
) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
        f"/plan_times/{plan_time_id}"
    )
    return {"deleted": True, "plan_time_id": plan_time_id}
