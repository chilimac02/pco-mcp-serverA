"""Volunteer scheduling — who's on which team for which plan.

A "plan team member" is a single assignment: a Person assigned to a Team
position on a specific Plan, with a status (confirmed / declined / unconfirmed).
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


# ---------------------------------------------------------------------------
# Plan team members
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_plan_team_members",
    description=(
        "List people assigned to teams for a plan. Each row includes the "
        "person, team, position, and status (confirmed/declined/etc.)."
    ),
)
async def list_plan_team_members(
    service_type_id: str,
    plan_id: str,
    per_page: int = 100,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/team_members",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response,
        items_key="plan_team_members",
        offset=offset,
        per_page=per_page,
    )


@mcp.tool(
    name="get_plan_team_member",
    description="Fetch one team-member assignment by ID.",
)
async def get_plan_team_member(
    service_type_id: str, plan_id: str, plan_team_member_id: str
) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
        f"/team_members/{plan_team_member_id}"
    )
    return flatten_resource(response.get("data"))


# ---------------------------------------------------------------------------
# Blockouts (unavailability)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_blockouts",
    description=(
        "List a person's blockout dates — periods they've marked themselves "
        "unavailable for scheduling. Use get_me to find the calling user's "
        "person ID."
    ),
)
async def list_blockouts(person_id: str, per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/people/{person_id}/blockouts",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="blockouts", offset=offset, per_page=per_page
    )


# ===========================================================================
# Writes (Phase 7)
# ===========================================================================

# ---------------------------------------------------------------------------
# Plan team member assignments
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_plan_team_member",
    description=(
        "Schedule a person onto a plan in a specific team + position. "
        "Status starts as 'U' (unconfirmed) by default; the volunteer "
        "confirms or declines via PCO's normal scheduling flow."
    ),
)
async def create_plan_team_member(
    service_type_id: str,
    plan_id: str,
    person_id: str,
    team_id: str,
    team_position_name: str | None = None,
    status: str = "U",
    notes: str | None = None,
) -> dict:
    session = get_current_session()
    relationships = {
        "person": jsonapi_relationship("Person", person_id),
        "team": jsonapi_relationship("Team", team_id),
    }
    body = build_jsonapi_body(
        type_="PlanPerson",
        attributes={
            "team_position_name": team_position_name,
            "status": status,
            "notes": notes,
        },
        relationships=relationships,
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/team_members",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_plan_team_member",
    description=(
        "Update a team-member assignment — typically to change status "
        "('C'=confirmed, 'D'=declined, 'U'=unconfirmed) or position."
    ),
)
async def update_plan_team_member(
    service_type_id: str,
    plan_id: str,
    plan_team_member_id: str,
    status: str | None = None,
    team_position_name: str | None = None,
    notes: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="PlanPerson",
        attributes={
            "status": status,
            "team_position_name": team_position_name,
            "notes": notes,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
        f"/team_members/{plan_team_member_id}",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_plan_team_member",
    description="Remove a team-member assignment from a plan.",
)
async def delete_plan_team_member(
    service_type_id: str, plan_id: str, plan_team_member_id: str
) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
        f"/team_members/{plan_team_member_id}"
    )
    return {"deleted": True, "plan_team_member_id": plan_team_member_id}


# ---------------------------------------------------------------------------
# Schedule requests (the email-to-volunteer flow)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="send_schedule_request",
    description=(
        "Trigger PCO to send the schedule request email to a team member. "
        "Side effect: an email is sent to the volunteer. Only use this "
        "when explicitly asked — otherwise PCO sends these automatically on "
        "the schedule's normal cadence."
    ),
)
async def send_schedule_request(
    service_type_id: str, plan_id: str, plan_team_member_id: str
) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
        f"/team_members/{plan_team_member_id}/send_reminder",
        json={},
    )
    return response or {"sent": True, "plan_team_member_id": plan_team_member_id}


@mcp.tool(
    name="accept_schedule_request",
    description=(
        "Mark a schedule request as accepted on behalf of the assigned "
        "person. Only an org administrator can do this for someone else; "
        "regular users can only accept their own."
    ),
)
async def accept_schedule_request(
    service_type_id: str, plan_id: str, plan_team_member_id: str
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="PlanPerson",
        attributes={"status": "C"},  # Confirmed
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
        f"/team_members/{plan_team_member_id}",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="decline_schedule_request",
    description=(
        "Mark a schedule request as declined on behalf of the assigned "
        "person. Same permission constraints as accept_schedule_request."
    ),
)
async def decline_schedule_request(
    service_type_id: str,
    plan_id: str,
    plan_team_member_id: str,
    decline_reason: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="PlanPerson",
        attributes={"status": "D", "decline_reason": decline_reason},
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
        f"/team_members/{plan_team_member_id}",
        json=body,
    )
    return flatten_resource(response.get("data"))


# ---------------------------------------------------------------------------
# Blockouts
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_blockout",
    description=(
        "Mark a person as unavailable for a date range. `reason` is free "
        "text; `starts_at` and `ends_at` are ISO-8601 timestamps. Users can "
        "create blockouts for themselves; admins can create them for others."
    ),
)
async def create_blockout(
    person_id: str,
    reason: str,
    starts_at: str,
    ends_at: str,
    repeat_frequency: str | None = None,
    repeat_interval: str | None = None,
    repeat_until: str | None = None,
    organization_name: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Blockout",
        attributes={
            "reason": reason,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "repeat_frequency": repeat_frequency,
            "repeat_interval": repeat_interval,
            "repeat_until": repeat_until,
            "organization_name": organization_name,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/people/{person_id}/blockouts", json=body
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_blockout",
    description="Remove a blockout for a person.",
)
async def delete_blockout(person_id: str, blockout_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/people/{person_id}/blockouts/{blockout_id}"
    )
    return {"deleted": True, "blockout_id": blockout_id}
