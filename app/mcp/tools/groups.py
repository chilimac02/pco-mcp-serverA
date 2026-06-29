"""Planning Center Groups API tools.

Groups is PCO's small-groups product — community/discipleship/affinity
groups, group types, memberships, events, attendance.
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
# Group types
# ===========================================================================

@mcp.tool(
    name="list_group_types",
    description=(
        "List the group types (categories) defined in PCO Groups, e.g. "
        "'Life Groups', 'Bible Studies'. Groups belong to a group type."
    ),
)
async def list_group_types(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/groups/v2/group_types", params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="group_types", offset=offset, per_page=per_page
    )


# ===========================================================================
# Groups
# ===========================================================================

@mcp.tool(
    name="list_groups",
    description=(
        "List groups. Filter by group_type_id to scope to one category. "
        "Use enrollment_strategy='open'/'closed' filters as needed."
    ),
)
async def list_groups(
    group_type_id: str | None = None,
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    params: dict = {"per_page": per_page, "offset": offset}
    if group_type_id:
        # Filter via group_type relationship
        params["where[group_type_id]"] = group_type_id
    client = PCOClient(session.access_token)
    response = await client.get("/groups/v2/groups", params=params)
    return paginated_response(
        response=response, items_key="groups", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_group", description="Fetch one group by ID.")
async def get_group(group_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/groups/v2/groups/{group_id}")
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="create_group",
    description=(
        "Create a new group under a group type. Pass `group_type_id` to "
        "decide which category it lives under; `name` is required."
    ),
)
async def create_group(
    group_type_id: str,
    name: str,
    description: str | None = None,
    enrollment_strategy: str | None = None,
    location_type_preference: str | None = None,
    schedule: str | None = None,
    contact_email: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Group",
        attributes={
            "name": name,
            "description": description,
            "enrollment_strategy": enrollment_strategy,
            "location_type_preference": location_type_preference,
            "schedule": schedule,
            "contact_email": contact_email,
        },
        relationships={
            "group_type": jsonapi_relationship("GroupType", group_type_id),
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post("/groups/v2/groups", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_group",
    description=(
        "Update a group's fields. WARNING: PCO restricts which Group "
        "attributes are writable via the public API. As of late 2026, "
        "ONLY `name` reliably accepts writes; `description`, "
        "`contact_email`, `enrollment_strategy`, `location_type_preference`, "
        "and `schedule` are managed exclusively in the Church Center UI by "
        "group leaders and return 'cannot be assigned' if set via API. "
        "If you need to bulk-edit those fields, you have to do it "
        "manually in PCO Groups admin (https://groups.planningcenteronline.com)."
    ),
)
async def update_group(
    group_id: str,
    name: str | None = None,
    description: str | None = None,
    enrollment_strategy: str | None = None,
    location_type_preference: str | None = None,
    schedule: str | None = None,
    contact_email: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Group",
        attributes={
            "name": name,
            "description": description,
            "enrollment_strategy": enrollment_strategy,
            "location_type_preference": location_type_preference,
            "schedule": schedule,
            "contact_email": contact_email,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(f"/groups/v2/groups/{group_id}", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(name="delete_group", description="Delete a group. Cascades to memberships.")
async def delete_group(group_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(f"/groups/v2/groups/{group_id}")
    return {"deleted": True, "group_id": group_id}


# ===========================================================================
# Memberships
# ===========================================================================

@mcp.tool(
    name="list_group_memberships",
    description="List the members of a group (with role: 'leader' or 'member').",
)
async def list_group_memberships(
    group_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/groups/v2/groups/{group_id}/memberships",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="memberships", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="add_group_member",
    description=(
        "Add a person to a group. `role` is 'leader' or 'member' "
        "(defaults to 'member')."
    ),
)
async def add_group_member(
    group_id: str,
    person_id: str,
    role: str = "member",
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Membership",
        attributes={"role": role},
        relationships={"person": jsonapi_relationship("Person", person_id)},
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/groups/v2/groups/{group_id}/memberships", json=body
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="remove_group_member",
    description="Remove a membership from a group.",
)
async def remove_group_member(group_id: str, membership_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/groups/v2/groups/{group_id}/memberships/{membership_id}"
    )
    return {"removed": True, "membership_id": membership_id}


# ===========================================================================
# Events
# ===========================================================================

@mcp.tool(
    name="list_group_events",
    description="List the events scheduled for a group.",
)
async def list_group_events(
    group_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/groups/v2/groups/{group_id}/events",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="events", offset=offset, per_page=per_page
    )


# ===========================================================================
# Locations + tags
# ===========================================================================

@mcp.tool(name="list_group_locations", description="List Groups locations.")
async def list_group_locations(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/groups/v2/locations", params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="locations", offset=offset, per_page=per_page
    )


@mcp.tool(name="list_group_tag_groups", description="List Groups tag groups.")
async def list_group_tag_groups() -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        "/groups/v2/tag_groups", params={"per_page": 100}
    )
    return paginated_response(
        response=response, items_key="tag_groups", offset=0, per_page=100
    )


@mcp.tool(
    name="list_group_tags",
    description="List Groups tags. Optionally filter by tag_group_id.",
)
async def list_group_tags(
    tag_group_id: str | None = None,
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    path = (
        f"/groups/v2/tag_groups/{tag_group_id}/tags"
        if tag_group_id
        else "/groups/v2/tags"
    )
    response = await client.get(
        path, params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="tags", offset=offset, per_page=per_page
    )
