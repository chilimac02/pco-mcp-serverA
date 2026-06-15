"""Plan notes — free-form annotations attached to a plan, grouped by category."""

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
# Plan notes
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_plan_notes",
    description=(
        "List notes attached to a plan. Notes have a category (e.g., 'Sound', "
        "'Pastor', 'Worship') and free-form content."
    ),
)
async def list_plan_notes(
    service_type_id: str,
    plan_id: str,
    per_page: int = 100,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/notes",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="notes", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="get_plan_note",
    description="Fetch one note from a plan by ID.",
)
async def get_plan_note(service_type_id: str, plan_id: str, note_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/notes/{note_id}"
    )
    return flatten_resource(response.get("data"))


# ---------------------------------------------------------------------------
# Note categories (per-service-type bucketing of notes)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_note_categories",
    description=(
        "List the note categories defined for a service type — these are the "
        "buckets that plan notes get filed under."
    ),
)
async def list_note_categories(service_type_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/service_types/{service_type_id}/plan_note_categories",
        params={"per_page": 100},
    )
    return paginated_response(
        response=response, items_key="note_categories", offset=0, per_page=100
    )


# ===========================================================================
# Writes (Phase 7)
# ===========================================================================

@mcp.tool(
    name="create_plan_note",
    description=(
        "Add a note to a plan. `plan_note_category_id` is required — use "
        "list_note_categories to discover valid IDs for the service type."
    ),
)
async def create_plan_note(
    service_type_id: str,
    plan_id: str,
    plan_note_category_id: str,
    content: str,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="PlanNote",
        attributes={"content": content},
        relationships={
            "plan_note_category": jsonapi_relationship(
                "PlanNoteCategory", plan_note_category_id
            ),
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/notes",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_plan_note",
    description="Edit a plan note's content or change its category.",
)
async def update_plan_note(
    service_type_id: str,
    plan_id: str,
    note_id: str,
    content: str | None = None,
    plan_note_category_id: str | None = None,
) -> dict:
    session = get_current_session()
    relationships = None
    if plan_note_category_id:
        relationships = {
            "plan_note_category": jsonapi_relationship(
                "PlanNoteCategory", plan_note_category_id
            ),
        }
    body = build_jsonapi_body(
        type_="PlanNote",
        attributes={"content": content},
        relationships=relationships,
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/notes/{note_id}",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_plan_note",
    description="Delete a plan note.",
)
async def delete_plan_note(
    service_type_id: str, plan_id: str, note_id: str
) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/notes/{note_id}"
    )
    return {"deleted": True, "note_id": note_id}
