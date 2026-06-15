"""Song library tools.

PCO's song library is global per organisation — songs aren't scoped to a
service type. Each song has one or more arrangements (key/version), and each
arrangement has keys (transposition options) and attachments (charts, audio,
lyrics, etc.).
"""

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


# ---------------------------------------------------------------------------
# Songs
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_songs",
    description=(
        "List songs from the org's library. Supports `search` (matches title "
        "or author) and `order` (default: title; use '-updated_at' for "
        "recently-updated)."
    ),
)
async def list_songs(
    search: Annotated[str | None, "Title or author substring; PCO matches partial"] = None,
    order: str = "title",
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    params: dict = {"per_page": per_page, "offset": offset, "order": order}
    if search:
        # PCO supports `where[title]` with partial match — but the docs also
        # show `where[title_or_author]` as a friendlier filter. Stick with
        # title for the common case.
        params["where[title]"] = search

    client = PCOClient(session.access_token)
    response = await client.get("/services/v2/songs", params=params)
    return paginated_response(
        response=response, items_key="songs", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="get_song",
    description="Fetch one song by ID, including its top-level metadata.",
)
async def get_song(song_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/services/v2/songs/{song_id}")
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="get_song_schedules",
    description=(
        "List every plan a song has been scheduled in. Useful for checking "
        "how recently a song was used or finding past arrangements/keys."
    ),
)
async def get_song_schedules(song_id: str, per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/songs/{song_id}/song_schedules",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="song_schedules", offset=offset, per_page=per_page
    )


# ---------------------------------------------------------------------------
# Arrangements
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_arrangements",
    description=(
        "List arrangements for a song. Each arrangement is a distinct "
        "version (chord chart, instrumentation, etc.)."
    ),
)
async def list_arrangements(song_id: str, per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/songs/{song_id}/arrangements",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="arrangements", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="get_arrangement",
    description="Fetch one arrangement by ID for a given song.",
)
async def get_arrangement(song_id: str, arrangement_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}"
    )
    return flatten_resource(response.get("data"))


# ---------------------------------------------------------------------------
# Keys and attachments (both nested under arrangement)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_keys",
    description=(
        "List the keys available for an arrangement (e.g., the same chord "
        "chart transposed to G, A, D, etc.)."
    ),
)
async def list_keys(song_id: str, arrangement_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}/keys",
        params={"per_page": 100},
    )
    return paginated_response(
        response=response, items_key="keys", offset=0, per_page=100
    )


@mcp.tool(
    name="list_attachments",
    description=(
        "List file attachments on an arrangement — chord charts, audio "
        "files, lyric sheets. Each attachment includes a URL to download. "
        "Note: PCO scopes attachments to an arrangement, not the parent song."
    ),
)
async def list_attachments(song_id: str, arrangement_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}/attachments",
        params={"per_page": 100},
    )
    return paginated_response(
        response=response, items_key="attachments", offset=0, per_page=100
    )


# ===========================================================================
# Writes (Phase 7)
# ===========================================================================

# ---------------------------------------------------------------------------
# Songs
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_song",
    description=(
        "Add a new song to the library. `title` is required by PCO; other "
        "fields populate metadata for chord charts and reporting."
    ),
)
async def create_song(
    title: str,
    author: str | None = None,
    copyright: str | None = None,
    ccli_number: int | None = None,
    hidden: bool | None = None,
    themes: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Song",
        attributes={
            "title": title,
            "author": author,
            "copyright": copyright,
            "ccli_number": ccli_number,
            "hidden": hidden,
            "themes": themes,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post("/services/v2/songs", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_song",
    description="Update song metadata. Pass only the fields you want to change.",
)
async def update_song(
    song_id: str,
    title: str | None = None,
    author: str | None = None,
    copyright: str | None = None,
    ccli_number: int | None = None,
    hidden: bool | None = None,
    themes: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Song",
        attributes={
            "title": title,
            "author": author,
            "copyright": copyright,
            "ccli_number": ccli_number,
            "hidden": hidden,
            "themes": themes,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(f"/services/v2/songs/{song_id}", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_song",
    description=(
        "Delete a song from the library. This also removes its arrangements, "
        "keys, and attachments. Past plans that referenced the song keep the "
        "title as a historical record but lose the link. Irreversible."
    ),
)
async def delete_song(song_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(f"/services/v2/songs/{song_id}")
    return {"deleted": True, "song_id": song_id}


# ---------------------------------------------------------------------------
# Arrangements
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_arrangement",
    description=(
        "Create a new arrangement (chart version) for a song. `name` "
        "distinguishes it (e.g., 'Acoustic', 'Full Band'); `chord_chart` "
        "accepts ChordPro-style markup."
    ),
)
async def create_arrangement(
    song_id: str,
    name: str,
    bpm: int | None = None,
    length: int | None = None,
    meter: str | None = None,
    chord_chart: str | None = None,
    chord_chart_key: str | None = None,
    rehearsal_mix_id: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Arrangement",
        attributes={
            "name": name,
            "bpm": bpm,
            "length": length,
            "meter": meter,
            "chord_chart": chord_chart,
            "chord_chart_key": chord_chart_key,
            "rehearsal_mix_id": rehearsal_mix_id,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/songs/{song_id}/arrangements", json=body
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_arrangement",
    description="Update arrangement fields. Pass only what you want to change.",
)
async def update_arrangement(
    song_id: str,
    arrangement_id: str,
    name: str | None = None,
    bpm: int | None = None,
    length: int | None = None,
    meter: str | None = None,
    chord_chart: str | None = None,
    chord_chart_key: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Arrangement",
        attributes={
            "name": name,
            "bpm": bpm,
            "length": length,
            "meter": meter,
            "chord_chart": chord_chart,
            "chord_chart_key": chord_chart_key,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}", json=body
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_arrangement",
    description="Delete an arrangement (and its keys + attachments).",
)
async def delete_arrangement(song_id: str, arrangement_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}")
    return {"deleted": True, "arrangement_id": arrangement_id}


# ---------------------------------------------------------------------------
# Keys (transposition options on an arrangement)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_key",
    description=(
        "Add a key to an arrangement. `starting_key` is the chord chart key "
        "(e.g., 'G'); `name` labels this transposition (e.g., 'Female Lead')."
    ),
)
async def create_key(
    song_id: str,
    arrangement_id: str,
    name: str,
    starting_key: str | None = None,
    ending_key: str | None = None,
    starting_minor: bool | None = None,
    ending_minor: bool | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Key",
        attributes={
            "name": name,
            "starting_key": starting_key,
            "ending_key": ending_key,
            "starting_minor": starting_minor,
            "ending_minor": ending_minor,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}/keys",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_key",
    description="Update a key on an arrangement.",
)
async def update_key(
    song_id: str,
    arrangement_id: str,
    key_id: str,
    name: str | None = None,
    starting_key: str | None = None,
    ending_key: str | None = None,
    starting_minor: bool | None = None,
    ending_minor: bool | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Key",
        attributes={
            "name": name,
            "starting_key": starting_key,
            "ending_key": ending_key,
            "starting_minor": starting_minor,
            "ending_minor": ending_minor,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}/keys/{key_id}",
        json=body,
    )
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_key",
    description="Delete a key from an arrangement.",
)
async def delete_key(song_id: str, arrangement_id: str, key_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}/keys/{key_id}"
    )
    return {"deleted": True, "key_id": key_id}


# ---------------------------------------------------------------------------
# Attachments (delete only — uploading binary needs multipart, not in scope)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="delete_attachment",
    description=(
        "Delete a file attachment from an arrangement. (Uploading new "
        "attachments requires a multipart binary flow not exposed here.)"
    ),
)
async def delete_attachment(
    song_id: str, arrangement_id: str, attachment_id: str
) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(
        f"/services/v2/songs/{song_id}/arrangements/{arrangement_id}"
        f"/attachments/{attachment_id}"
    )
    return {"deleted": True, "attachment_id": attachment_id}
