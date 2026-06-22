"""Planning Center Check-Ins API tools.

Check-Ins runs the kiosks / printers / station UX for children's ministry,
youth, classes, and event attendance. Most reads here are for reporting;
the main write is `create_check_in` to programmatically check someone in.
"""

from __future__ import annotations

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


# ===========================================================================
# Events
# ===========================================================================

@mcp.tool(
    name="list_checkin_events",
    description=(
        "List Check-Ins events (the parent containers for check-in sessions, "
        "e.g. 'Sunday Morning', 'Wednesday Night')."
    ),
)
async def list_checkin_events(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/check-ins/v2/events", params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="events", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_checkin_event", description="Fetch one Check-Ins event by ID.")
async def get_checkin_event(event_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/check-ins/v2/events/{event_id}")
    return flatten_resource(response.get("data"))


# ===========================================================================
# Event times (occurrences of an event)
# ===========================================================================

@mcp.tool(
    name="list_checkin_event_times",
    description=(
        "List the time slots (specific occurrences) for a Check-Ins event."
    ),
)
async def list_checkin_event_times(
    event_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/check-ins/v2/events/{event_id}/event_times",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="event_times", offset=offset, per_page=per_page
    )


# ===========================================================================
# Locations
# ===========================================================================

@mcp.tool(
    name="list_checkin_locations",
    description="List the locations (rooms) defined in Check-Ins.",
)
async def list_checkin_locations(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/check-ins/v2/locations",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="locations", offset=offset, per_page=per_page
    )


# ===========================================================================
# Check-ins
# ===========================================================================

@mcp.tool(
    name="list_check_ins",
    description=(
        "List check-in records. Without filters returns the most recent "
        "across the org; pass event_id to scope to a specific event."
    ),
)
async def list_check_ins(
    event_id: str | None = None,
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    path = (
        f"/check-ins/v2/events/{event_id}/check_ins"
        if event_id
        else "/check-ins/v2/check_ins"
    )
    client = PCOClient(session.access_token)
    response = await client.get(
        path, params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="check_ins", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_check_in", description="Fetch one check-in record by ID.")
async def get_check_in(check_in_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/check-ins/v2/check_ins/{check_in_id}")
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="create_check_in",
    description=(
        "Programmatically check a person in to an event_time. Requires the "
        "Person ID and the EventTime ID. Optionally specify a location_id."
    ),
)
async def create_check_in(
    event_id: str,
    event_time_id: str,
    person_id: str,
    location_id: str | None = None,
    kind: str = "regular",
) -> dict:
    session = get_current_session()
    relationships = {
        "event_time": jsonapi_relationship("EventTime", event_time_id),
        "person": jsonapi_relationship("Person", person_id),
    }
    if location_id:
        relationships["location"] = jsonapi_relationship("Location", location_id)
    body = build_jsonapi_body(
        type_="CheckIn",
        attributes={"kind": kind},
        relationships=relationships,
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/check-ins/v2/events/{event_id}/check_ins", json=body
    )
    return flatten_resource(response.get("data"))


# ===========================================================================
# People + headcounts
# ===========================================================================

@mcp.tool(
    name="list_checkin_people",
    description=(
        "List Check-Ins People records (the directory view used by stations). "
        "These are linked to People records but can include guests not yet "
        "in the master directory."
    ),
)
async def list_checkin_people(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/check-ins/v2/people",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="people", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="list_checkin_stations",
    description="List the physical Check-Ins stations registered for the org.",
)
async def list_checkin_stations() -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        "/check-ins/v2/stations", params={"per_page": 100}
    )
    return paginated_response(
        response=response, items_key="stations", offset=0, per_page=100
    )


@mcp.tool(
    name="list_checkin_headcounts",
    description=(
        "List headcounts taken at check-in events — useful for service "
        "attendance reporting."
    ),
)
async def list_checkin_headcounts(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/check-ins/v2/headcounts",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="headcounts", offset=offset, per_page=per_page
    )
