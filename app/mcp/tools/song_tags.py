"""Song tags — taxonomy applied to the song library.

PCO has Tag Groups (e.g., 'Themes', 'Tempo', 'Season') containing individual
Tags (e.g., 'Christmas', 'Fast', 'Easter'). A song can be tagged with any
number of tags from any group.
"""

from __future__ import annotations

from app.mcp.context import get_current_session
from app.mcp.server import mcp
from app.mcp.tools._common import (
    build_jsonapi_body,
    clamp_pagination,
    paginated_response,
)
from app.pco.client import PCOClient


@mcp.tool(
    name="list_tag_groups",
    description="List all tag groups defined on the song library.",
)
async def list_tag_groups(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/services/v2/tag_groups",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="tag_groups", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="list_tags",
    description=(
        "List tags within a tag group. Use list_tag_groups to discover "
        "tag_group_id."
    ),
)
async def list_tags(tag_group_id: str, per_page: int = 100, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/tag_groups/{tag_group_id}/tags",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="tags", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="get_song_tags",
    description="List tags applied to a specific song.",
)
async def get_song_tags(song_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/songs/{song_id}/tags",
        params={"per_page": 100},
    )
    return paginated_response(
        response=response, items_key="tags", offset=0, per_page=100
    )


# ===========================================================================
# Writes (Phase 7)
# ===========================================================================

@mcp.tool(
    name="assign_tag_to_song",
    description=(
        "Apply an existing tag to a song. Use list_tag_groups + list_tags to "
        "discover tag IDs first; this tool doesn't create tags."
    ),
)
async def assign_tag_to_song(song_id: str, tag_id: str) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(type_="Tag", attributes={"id": str(tag_id)})
    # PCO uses a slightly different shape for assignment — just send the id
    # as a relationship-style body. Some PCO versions also accept
    # /tag_assignments. Falling back to a simple POST to /tags first.
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/songs/{song_id}/assign_tags",
        json={"data": [{"type": "Tag", "id": str(tag_id)}]},
    )
    return response or {"assigned": True, "song_id": song_id, "tag_id": tag_id}


@mcp.tool(
    name="remove_tag_from_song",
    description="Remove a tag from a song. The tag itself is not deleted.",
)
async def remove_tag_from_song(song_id: str, tag_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(f"/services/v2/songs/{song_id}/tags/{tag_id}")
    return {"removed": True, "song_id": song_id, "tag_id": tag_id}
