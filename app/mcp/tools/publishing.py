"""Planning Center Publishing API tools.

Publishing handles sermon series, individual episodes (sermons), and
distribution channels (podcast feeds, embed targets). Read-only here —
publishing flow has lots of side effects (media uploads, RSS regeneration)
that make blind LLM writes a bad idea.
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
# Channels
# ===========================================================================

@mcp.tool(
    name="list_publishing_channels",
    description=(
        "List Publishing channels (the destinations sermons are published to: "
        "Apple Podcasts, web, etc.)."
    ),
)
async def list_publishing_channels(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/publishing/v2/channels",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="channels", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_publishing_channel", description="Fetch one channel by ID.")
async def get_publishing_channel(channel_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/publishing/v2/channels/{channel_id}")
    return flatten_resource(response.get("data"))


# ===========================================================================
# Series
# ===========================================================================

@mcp.tool(
    name="list_publishing_series",
    description=(
        "List sermon series. Each series groups episodes around a theme."
    ),
)
async def list_publishing_series(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/publishing/v2/series",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="series", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_publishing_series", description="Fetch one series by ID.")
async def get_publishing_series(series_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/publishing/v2/series/{series_id}")
    return flatten_resource(response.get("data"))


# ===========================================================================
# Episodes
# ===========================================================================

@mcp.tool(
    name="list_publishing_episodes",
    description=(
        "List sermon episodes. Optionally filter by series_id, channel_id, "
        "or order by published_to_library_at."
    ),
)
async def list_publishing_episodes(
    series_id: str | None = None,
    channel_id: str | None = None,
    order: str = "-published_to_library_at",
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    params: dict = {"per_page": per_page, "offset": offset, "order": order}
    if series_id:
        path = f"/publishing/v2/series/{series_id}/episodes"
    elif channel_id:
        path = f"/publishing/v2/channels/{channel_id}/episodes"
    else:
        path = "/publishing/v2/episodes"
    client = PCOClient(session.access_token)
    response = await client.get(path, params=params)
    return paginated_response(
        response=response, items_key="episodes", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_publishing_episode", description="Fetch one episode by ID.")
async def get_publishing_episode(episode_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/publishing/v2/episodes/{episode_id}")
    return flatten_resource(response.get("data"))


# ===========================================================================
# Speakers
# ===========================================================================

@mcp.tool(
    name="list_publishing_speakers",
    description="List speakers (pastors / guest preachers) tagged on episodes.",
)
async def list_publishing_speakers(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/publishing/v2/speakers",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="speakers", offset=offset, per_page=per_page
    )
