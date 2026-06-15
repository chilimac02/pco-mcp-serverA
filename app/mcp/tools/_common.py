"""Shared helpers for PCO MCP tool modules.

Every PCO Services list endpoint follows the same JSON:API shape:

    {
      "data": [ {id, type, attributes: {...}}, ... ],
      "meta": {"total_count": 123, ...},
      "links": {"self": "...", "next": "...", "prev": "..."}
    }

Single-resource endpoints return the same shape with `data` as one object
instead of a list. The helpers below normalise both forms into clean dicts
the AI can reason over without parsing JSON:API by hand.

`flatten_resource(...)` keeps the `id` and `type` discriminator alongside
all attribute fields, so any field PCO returns (now or in the future) is
visible to the AI without us hand-listing every one.
"""

from __future__ import annotations

from typing import Any


def flatten_resource(data: dict | None) -> dict:
    """Flatten a JSON:API resource object into id/type plus its attributes.

    Returns an empty dict for None or missing input — tools call this on
    `response.get("data")` which can legitimately be None when PCO returns
    an empty resource.
    """
    if not data:
        return {}
    attrs = data.get("attributes") or {}
    flat = {
        "id": str(data["id"]) if data.get("id") is not None else None,
        "type": data.get("type"),
        **attrs,
    }
    # Preserve relationship hints so tools chasing related resources have IDs.
    relationships = data.get("relationships")
    if relationships:
        rels = {}
        for rel_name, rel_body in relationships.items():
            rel_data = (rel_body or {}).get("data")
            if isinstance(rel_data, dict):
                rels[rel_name] = {"id": str(rel_data.get("id")), "type": rel_data.get("type")}
            elif isinstance(rel_data, list):
                rels[rel_name] = [
                    {"id": str(r.get("id")), "type": r.get("type")} for r in rel_data
                ]
        if rels:
            flat["_relationships"] = rels
    return flat


def paginated_response(
    *,
    response: dict,
    items_key: str,
    offset: int,
    per_page: int,
) -> dict:
    """Standard return shape for list_* tools.

    Wraps the per-tool item key (`plans`, `songs`, etc.) with consistent
    pagination metadata so the AI can request the next page without having
    to remember per-endpoint quirks.
    """
    items = [flatten_resource(d) for d in response.get("data", [])]
    meta = response.get("meta") or {}
    links = response.get("links") or {}
    total = meta.get("total_count")
    has_next = bool(links.get("next"))

    return {
        items_key: items,
        "count": len(items),
        "total_count": total,
        "offset": offset,
        "per_page": per_page,
        "next_offset": offset + per_page if has_next else None,
    }


def clamp_pagination(per_page: Any, offset: Any) -> tuple[int, int]:
    """Coerce + clamp pagination args. PCO caps per_page at 100."""
    try:
        pp = int(per_page)
    except (TypeError, ValueError):
        pp = 25
    try:
        off = int(offset)
    except (TypeError, ValueError):
        off = 0
    return max(1, min(pp, 100)), max(0, off)


# ---------------------------------------------------------------------------
# Write-side helpers
# ---------------------------------------------------------------------------

def drop_none(d: dict) -> dict:
    """Remove keys whose value is None.

    Used to build JSON:API attribute bodies — sending None for a field would
    overwrite it with null in PCO, but the calling tool typically means
    "leave it unchanged". Callers pass every possible field as a kwarg;
    we drop the unset ones here.
    """
    return {k: v for k, v in d.items() if v is not None}


def build_jsonapi_body(
    *,
    type_: str,
    attributes: dict,
    relationships: dict | None = None,
) -> dict:
    """Wrap attributes (and optional relationships) in PCO's JSON:API envelope.

    PCO POST/PATCH bodies look like:
        {"data": {"type": "Plan",
                  "attributes": {"title": "..."},
                  "relationships": {"service_type": {"data": {...}}}}}

    Attributes with value None are stripped automatically — partial updates
    work by just not passing the unchanged fields.
    """
    data: dict = {"type": type_, "attributes": drop_none(attributes)}
    if relationships:
        data["relationships"] = relationships
    return {"data": data}


def jsonapi_relationship(type_: str, resource_id: str) -> dict:
    """Build a single relationship entry: {data: {type, id}}.

    Composes into the `relationships` argument of `build_jsonapi_body`:
        relationships={
          "song": jsonapi_relationship("Song", "12345"),
          "arrangement": jsonapi_relationship("Arrangement", "67890"),
        }
    """
    return {"data": {"type": type_, "id": str(resource_id)}}
