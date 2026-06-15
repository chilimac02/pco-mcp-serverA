"""`get_me` MCP tool — returns the authenticated user's PCO Services profile."""

from __future__ import annotations

from app.mcp.context import get_current_session
from app.mcp.server import mcp
from app.pco.client import PCOClient


@mcp.tool(
    name="get_me",
    description=(
        "Return the authenticated Planning Center user's profile (the "
        "person whose session token is being used). Useful for confirming "
        "who the AI assistant is acting as before making changes."
    ),
)
async def get_me() -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get("/services/v2/me")

    data = response.get("data") or {}
    attrs = data.get("attributes") or {}
    return _format_person(data["id"] if "id" in data else session.pco_user_id, attrs)


def _format_person(person_id: str, attrs: dict) -> dict:
    """Flatten a JSON:API Person resource into a plain dict for MCP output.

    Keeps the fields most useful for downstream tools/AI reasoning. Returns
    None values rather than dropping keys so the AI can see what's missing.
    """
    return {
        "id": str(person_id),
        "name": attrs.get("full_name") or attrs.get("name"),
        "first_name": attrs.get("first_name"),
        "last_name": attrs.get("last_name"),
        "given_name": attrs.get("given_name"),
        "middle_name": attrs.get("middle_name"),
        "nickname": attrs.get("nickname"),
        "anniversary": attrs.get("anniversary"),
        "birthdate": attrs.get("birthdate"),
        "site_administrator": attrs.get("site_administrator"),
        "status": attrs.get("status"),
        "created_at": attrs.get("created_at"),
        "updated_at": attrs.get("updated_at"),
    }
