"""Service Types tools.

A "service type" in Planning Center is a category of services (e.g.,
"Sunday Morning", "Wednesday Night", "Special Events"). Plans live underneath
a service type, so these endpoints are the entry point to most other queries.
"""

from __future__ import annotations

from app.mcp.context import get_current_session
from app.mcp.server import mcp
from app.mcp.tools._common import (
    build_jsonapi_body,
    flatten_resource,
)
from app.pco.client import PCOClient


PATH_LIST = "/services/v2/service_types"


# ---------------------------------------------------------------------------
# list_service_types
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_service_types",
    description=(
        "List all service types (categories of services like 'Sunday Morning' "
        "or 'Wednesday Night'). Use this first to find the service_type_id "
        "needed by plan / team / song-scheduling tools.\n\n"
        "Paginates with per_page (max 100) and offset. Returns a "
        "`next_offset` value if more results exist."
    ),
)
async def list_service_types(per_page: int = 25, offset: int = 0) -> dict:
    """List service types visible to the calling user."""
    session = get_current_session()
    client = PCOClient(session.access_token)

    # PCO caps per_page at 100; clamp here so we don't get a 422 from PCO.
    per_page = max(1, min(int(per_page), 100))
    offset = max(0, int(offset))

    response = await client.get(
        PATH_LIST,
        params={"per_page": per_page, "offset": offset},
    )

    items = [_format_service_type(d) for d in response.get("data", [])]
    meta = response.get("meta") or {}
    links = response.get("links") or {}

    total = meta.get("total_count")
    next_offset = offset + per_page if links.get("next") else None

    return {
        "service_types": items,
        "count": len(items),
        "total_count": total,
        "offset": offset,
        "per_page": per_page,
        "next_offset": next_offset,
    }


# ---------------------------------------------------------------------------
# get_service_type
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_service_type",
    description=(
        "Return a single service type by ID. Use list_service_types to "
        "discover IDs."
    ),
)
async def get_service_type(service_type_id: str) -> dict:
    """Fetch one service type."""
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"{PATH_LIST}/{service_type_id}")
    data = response.get("data") or {}
    return _format_service_type(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_service_type(data: dict) -> dict:
    """Flatten a JSON:API ServiceType resource into a plain dict.

    Returns None for absent attributes rather than dropping keys, so the AI
    sees the shape consistently across rows.
    """
    attrs = data.get("attributes") or {}
    return {
        "id": str(data.get("id")) if data.get("id") is not None else None,
        "name": attrs.get("name"),
        "sequence": attrs.get("sequence"),
        "frequency": attrs.get("frequency"),
        "permissions": attrs.get("permissions"),
        "attachment_types_enabled": attrs.get("attachment_types_enabled"),
        "scheduled_publish": attrs.get("scheduled_publish"),
        "created_at": attrs.get("created_at"),
        "updated_at": attrs.get("updated_at"),
        "deleted_at": attrs.get("deleted_at"),
    }


# ---------------------------------------------------------------------------
# Writes (Phase 7)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_service_type",
    description=(
        "Create a new service type. Service types are an org-level resource; "
        "this fails with 403 unless the calling user is an org administrator. "
        "Sequence controls display order; lower numbers appear first."
    ),
)
async def create_service_type(
    name: str,
    sequence: int | None = None,
    frequency: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="ServiceType",
        attributes={
            "name": name,
            "sequence": sequence,
            "frequency": frequency,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(PATH_LIST, json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_service_type",
    description=(
        "Update an existing service type. Pass only the fields you want to "
        "change; others are left as-is. Org-administrator-only."
    ),
)
async def update_service_type(
    service_type_id: str,
    name: str | None = None,
    sequence: int | None = None,
    frequency: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="ServiceType",
        attributes={
            "name": name,
            "sequence": sequence,
            "frequency": frequency,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(f"{PATH_LIST}/{service_type_id}", json=body)
    return flatten_resource(response.get("data"))
