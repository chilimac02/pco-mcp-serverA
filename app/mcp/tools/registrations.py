"""Planning Center Registrations API tools.

Registrations handles signups (events, classes, camps, retreats) — taking
registrations, capturing payments, managing categories and attendees.

Read coverage is comprehensive; writes are limited to the most common
admin operation (cancelling an attendee). Payment-touching endpoints
are not exposed.
"""

from __future__ import annotations

from app.mcp.context import get_current_session
from app.mcp.server import mcp
from app.mcp.tools._common import (
    clamp_pagination,
    flatten_resource,
    paginated_response,
)
from app.pco.client import PCOClient


# ===========================================================================
# Signups
# ===========================================================================

@mcp.tool(
    name="list_signups",
    description=(
        "List Registrations signups (events / classes / camps that accept "
        "registrations)."
    ),
)
async def list_signups(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/registrations/v2/signups",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="signups", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_signup", description="Fetch one signup by ID.")
async def get_signup(signup_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/registrations/v2/signups/{signup_id}")
    return flatten_resource(response.get("data"))


# ===========================================================================
# Attendees
# ===========================================================================

@mcp.tool(
    name="list_signup_attendees",
    description="List attendees registered for a signup.",
)
async def list_signup_attendees(
    signup_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/registrations/v2/signups/{signup_id}/attendees",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="attendees", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_signup_attendee", description="Fetch one attendee by ID.")
async def get_signup_attendee(signup_id: str, attendee_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/registrations/v2/signups/{signup_id}/attendees/{attendee_id}"
    )
    return flatten_resource(response.get("data"))


# ===========================================================================
# Categories
# ===========================================================================

@mcp.tool(
    name="list_signup_categories",
    description="List the categories defined for organizing signups.",
)
async def list_signup_categories(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/registrations/v2/categories",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="categories", offset=offset, per_page=per_page
    )


# ===========================================================================
# Registrations
# ===========================================================================

@mcp.tool(
    name="list_signup_registrations",
    description=(
        "List Registration records (the payment-/transaction-level record "
        "for a signup; an attendee belongs to a registration)."
    ),
)
async def list_signup_registrations(
    signup_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/registrations/v2/signups/{signup_id}/registrations",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="registrations", offset=offset, per_page=per_page
    )


# ===========================================================================
# Selection types (the price/option choices on a signup)
# ===========================================================================

@mcp.tool(
    name="list_signup_selection_types",
    description=(
        "List the selection types on a signup — the price tiers / options "
        "an attendee can pick (e.g., 'Adult $50', 'Child $25')."
    ),
)
async def list_signup_selection_types(
    signup_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/registrations/v2/signups/{signup_id}/selection_types",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="selection_types", offset=offset, per_page=per_page
    )
