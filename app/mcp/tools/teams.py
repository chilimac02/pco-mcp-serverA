"""Teams + team positions.

A Team in PCO Services is a group of people (e.g., "Worship Team", "Tech",
"Ushers") that can be scheduled into plans. Each team has positions
(e.g., "Drums", "Vocals", "Sound Engineer") that volunteers fill.
"""

from __future__ import annotations

from app.mcp.context import get_current_session
from app.mcp.server import mcp
from app.mcp.tools._common import (
    build_jsonapi_body,
    clamp_pagination,
    flatten_resource,
    paginated_response,
)
from app.pco.client import PCOClient


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_teams",
    description="List teams for a service type (the groups that can be scheduled).",
)
async def list_teams(service_type_id: str, per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/teams",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="teams", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="get_team",
    description="Fetch one team by ID for a given service type.",
)
async def get_team(service_type_id: str, team_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/teams/{team_id}"
    )
    return flatten_resource(response.get("data"))


# ---------------------------------------------------------------------------
# Team positions
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_team_positions",
    description=(
        "List positions within a team (e.g., 'Drums', 'Vocals'). Positions "
        "are what volunteers get scheduled into."
    ),
)
async def list_team_positions(
    service_type_id: str,
    team_id: str,
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/teams/{team_id}/team_positions",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response,
        items_key="team_positions",
        offset=offset,
        per_page=per_page,
    )


# ===========================================================================
# Writes (Phase 7)
# ===========================================================================

@mcp.tool(
    name="create_team",
    description=(
        "Create a new team within a service type. `name` is required; "
        "scheduling-related fields are optional."
    ),
)
async def create_team(
    service_type_id: str,
    name: str,
    sequence: int | None = None,
    schedule_to: str | None = None,
    default_status: str | None = None,
    default_prepare_notifications: bool | None = None,
    rehearsal_team: bool | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Team",
        attributes={
            "name": name,
            "sequence": sequence,
            "schedule_to": schedule_to,
            "default_status": default_status,
            "default_prepare_notifications": default_prepare_notifications,
            "rehearsal_team": rehearsal_team,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/teams", json=body
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_team",
    description="Update a team's fields.",
)
async def update_team(
    service_type_id: str,
    team_id: str,
    name: str | None = None,
    sequence: int | None = None,
    schedule_to: str | None = None,
    default_status: str | None = None,
    default_prepare_notifications: bool | None = None,
    rehearsal_team: bool | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Team",
        attributes={
            "name": name,
            "sequence": sequence,
            "schedule_to": schedule_to,
            "default_status": default_status,
            "default_prepare_notifications": default_prepare_notifications,
            "rehearsal_team": rehearsal_team,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/teams/{team_id}", json=body
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="create_team_position",
    description=(
        "Add a position (e.g., 'Drums', 'Vocals') to a team. Positions are "
        "the slots that get assigned to volunteers on each plan."
    ),
)
async def create_team_position(
    service_type_id: str,
    team_id: str,
    name: str,
    sequence: int | None = None,
    negative_tag_groups: list[str] | None = None,
    tag_groups: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="TeamPosition",
        attributes={
            "name": name,
            "sequence": sequence,
            "negative_tag_groups": negative_tag_groups,
            "tag_groups": tag_groups,
            "tags": tags,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/teams/{team_id}/team_positions",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_team_position",
    description="Update a team position's fields.",
)
async def update_team_position(
    service_type_id: str,
    team_id: str,
    team_position_id: str,
    name: str | None = None,
    sequence: int | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="TeamPosition",
        attributes={"name": name, "sequence": sequence},
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/teams/{team_id}"
        f"/team_positions/{team_position_id}",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_team_position",
    description="Delete a position from a team.",
)
async def delete_team_position(
    service_type_id: str, team_id: str, team_position_id: str
) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/service_types/{service_type_id}/teams/{team_id}"
        f"/team_positions/{team_position_id}"
    )
    return {"deleted": True, "team_position_id": team_position_id}
