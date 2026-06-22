"""Planning Center Calendar API tools.

Calendar manages events, room/resource booking, and approvals across the
org. The two big nouns are Events (the booking-level entity) and
Resources (rooms, equipment, vehicles)."""

from __future__ import annotations

from typing import Annotated

from app.mcp.context import get_current_session
from app.mcp.server import mcp
from app.mcp.tools._common import (
    build_jsonapi_body,
    clamp_pagination,
    flatten_resource,
    paginated_response,
)
from app.pco.client import PCOClient


# ===========================================================================
# Events
# ===========================================================================

@mcp.tool(
    name="list_calendar_events",
    description=(
        "List Calendar events, ordered by starts_at by default. Pass "
        "`filter='future'` or 'past' to scope, or use where_starts_at "
        "for explicit date filters."
    ),
)
async def list_calendar_events(
    filter: Annotated[str | None, "'future', 'past', or None for all"] = None,
    order: str = "starts_at",
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    params: dict = {"per_page": per_page, "offset": offset, "order": order}
    if filter:
        params["filter"] = filter
    client = PCOClient(session.access_token)
    response = await client.get("/calendar/v2/events", params=params)
    return paginated_response(
        response=response, items_key="events", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_calendar_event", description="Fetch one Calendar event by ID.")
async def get_calendar_event(event_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/calendar/v2/events/{event_id}")
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="create_calendar_event",
    description=(
        "Create a Calendar event. `name` is required; `starts_at` and "
        "`ends_at` are ISO timestamps. Room/resource bookings are added "
        "via create_event_resource_request after the event exists."
    ),
)
async def create_calendar_event(
    name: str,
    starts_at: str,
    ends_at: str,
    description: str | None = None,
    summary: str | None = None,
    all_day_event: bool = False,
    visible_in_church_center: bool = False,
    image_url: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Event",
        attributes={
            "name": name,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "description": description,
            "summary": summary,
            "all_day_event": all_day_event,
            "visible_in_church_center": visible_in_church_center,
            "image_url": image_url,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post("/calendar/v2/events", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(name="update_calendar_event", description="Update a Calendar event's fields.")
async def update_calendar_event(
    event_id: str,
    name: str | None = None,
    starts_at: str | None = None,
    ends_at: str | None = None,
    description: str | None = None,
    summary: str | None = None,
    all_day_event: bool | None = None,
    visible_in_church_center: bool | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Event",
        attributes={
            "name": name,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "description": description,
            "summary": summary,
            "all_day_event": all_day_event,
            "visible_in_church_center": visible_in_church_center,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(f"/calendar/v2/events/{event_id}", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_calendar_event",
    description="Delete a Calendar event. Cascades to its instances and resource requests.",
)
async def delete_calendar_event(event_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(f"/calendar/v2/events/{event_id}")
    return {"deleted": True, "event_id": event_id}


# ---------------------------------------------------------------------------
# Event instances (recurring events expand into multiple instances)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_event_instances",
    description=(
        "List the recurring instances of a Calendar event. Single-occurrence "
        "events have exactly one instance."
    ),
)
async def list_event_instances(
    event_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/calendar/v2/events/{event_id}/event_instances",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="event_instances", offset=offset, per_page=per_page
    )


# ===========================================================================
# Resources (rooms / equipment)
# ===========================================================================

@mcp.tool(
    name="list_calendar_resources",
    description=(
        "List bookable resources (rooms, equipment, vehicles) in Calendar."
    ),
)
async def list_calendar_resources(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/calendar/v2/resources",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="resources", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_calendar_resource", description="Fetch one resource by ID.")
async def get_calendar_resource(resource_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/calendar/v2/resources/{resource_id}")
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="list_resource_bookings",
    description="List current bookings against a resource.",
)
async def list_resource_bookings(
    resource_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/calendar/v2/resources/{resource_id}/resource_bookings",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="resource_bookings", offset=offset, per_page=per_page
    )


# ===========================================================================
# Conflicts
# ===========================================================================

@mcp.tool(
    name="list_calendar_conflicts",
    description=(
        "List current scheduling conflicts (events that overlap on a "
        "resource without proper approval)."
    ),
)
async def list_calendar_conflicts(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/calendar/v2/conflicts",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="conflicts", offset=offset, per_page=per_page
    )
