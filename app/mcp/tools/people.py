"""Planning Center People API tools.

The People product is PCO's identity / directory layer. Every Person in
Services, Groups, Calendar, etc. is fundamentally a People record. So
queries that need to act on humans (search by email, update contact info,
add to workflows) live here.

Coverage:
  - People: search/get/create/update/delete + emails / addresses / phones
  - Households
  - Lists + list results
  - Workflows + workflow cards
  - Notes + note categories
  - Field definitions + field data (custom fields)
  - Forms + form submissions
"""

from __future__ import annotations

from typing import Annotated

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
# People
# ===========================================================================

@mcp.tool(
    name="search_people",
    description=(
        "Search the People directory. Pass `query` for fuzzy name/email "
        "match, or any of the where_* filters for exact matches. Returns "
        "paginated People records with id + attributes."
    ),
)
async def search_people(
    query: Annotated[str | None, "Free-text fuzzy search across name and email"] = None,
    where_email: Annotated[str | None, "Exact email match"] = None,
    where_first_name: str | None = None,
    where_last_name: str | None = None,
    per_page: int = 25,
    offset: int = 0,
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    params: dict = {"per_page": per_page, "offset": offset}
    if query:
        params["where[search_name_or_email]"] = query
    if where_email:
        params["where[email]"] = where_email
    if where_first_name:
        params["where[first_name]"] = where_first_name
    if where_last_name:
        params["where[last_name]"] = where_last_name

    client = PCOClient(session.access_token)
    response = await client.get("/people/v2/people", params=params)
    return paginated_response(
        response=response, items_key="people", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="get_person",
    description="Fetch one Person by ID, including their core attributes.",
)
async def get_person(person_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/people/v2/people/{person_id}")
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="create_person",
    description=(
        "Add a new Person to PCO People. `first_name` and `last_name` are "
        "the only effectively required fields; other contact details can "
        "be added afterward via update_person / add_email / add_phone."
    ),
)
async def create_person(
    first_name: str,
    last_name: str,
    nickname: str | None = None,
    middle_name: str | None = None,
    gender: Annotated[str | None, "'Male', 'Female', or 'Other'"] = None,
    birthdate: Annotated[str | None, "ISO date YYYY-MM-DD"] = None,
    anniversary: str | None = None,
    membership: str | None = None,
    status: Annotated[str | None, "'active' or 'inactive'"] = None,
    school_grade: str | None = None,
    medical_notes: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Person",
        attributes={
            "first_name": first_name,
            "last_name": last_name,
            "nickname": nickname,
            "middle_name": middle_name,
            "gender": gender,
            "birthdate": birthdate,
            "anniversary": anniversary,
            "membership": membership,
            "status": status,
            "school_grade": school_grade,
            "medical_notes": medical_notes,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post("/people/v2/people", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="update_person",
    description="Update a Person's core attributes. Pass only what changes.",
)
async def update_person(
    person_id: str,
    first_name: str | None = None,
    last_name: str | None = None,
    nickname: str | None = None,
    middle_name: str | None = None,
    gender: str | None = None,
    birthdate: str | None = None,
    anniversary: str | None = None,
    membership: str | None = None,
    status: str | None = None,
    school_grade: str | None = None,
    medical_notes: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Person",
        attributes={
            "first_name": first_name,
            "last_name": last_name,
            "nickname": nickname,
            "middle_name": middle_name,
            "gender": gender,
            "birthdate": birthdate,
            "anniversary": anniversary,
            "membership": membership,
            "status": status,
            "school_grade": school_grade,
            "medical_notes": medical_notes,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.patch(f"/people/v2/people/{person_id}", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="delete_person",
    description=(
        "Delete a Person from PCO. Cascades to all related child records. "
        "Permanent — usually you want to set `status='inactive'` via "
        "update_person instead."
    ),
)
async def delete_person(person_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    await client.delete(f"/people/v2/people/{person_id}")
    return {"deleted": True, "person_id": person_id}


# ---------------------------------------------------------------------------
# Contact details (emails / addresses / phone numbers)
# ---------------------------------------------------------------------------

@mcp.tool(name="list_person_emails", description="List a person's email addresses.")
async def list_person_emails(person_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/people/{person_id}/emails", params={"per_page": 100}
    )
    return paginated_response(response=response, items_key="emails", offset=0, per_page=100)


@mcp.tool(
    name="add_person_email",
    description="Attach a new email address to a Person.",
)
async def add_person_email(
    person_id: str,
    address: str,
    location: Annotated[str, "'Home', 'Work', 'Mobile', or 'Other'"] = "Home",
    primary: bool = False,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Email",
        attributes={"address": address, "location": location, "primary": primary},
    )
    client = PCOClient(session.access_token)
    response = await client.post(f"/people/v2/people/{person_id}/emails", json=body)
    return flatten_resource(response.get("data"))


@mcp.tool(name="list_person_addresses", description="List a person's postal addresses.")
async def list_person_addresses(person_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/people/{person_id}/addresses", params={"per_page": 100}
    )
    return paginated_response(response=response, items_key="addresses", offset=0, per_page=100)


@mcp.tool(name="list_person_phone_numbers", description="List a person's phone numbers.")
async def list_person_phone_numbers(person_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/people/{person_id}/phone_numbers", params={"per_page": 100}
    )
    return paginated_response(
        response=response, items_key="phone_numbers", offset=0, per_page=100
    )


@mcp.tool(
    name="add_person_phone_number",
    description="Attach a new phone number to a Person.",
)
async def add_person_phone_number(
    person_id: str,
    number: str,
    location: Annotated[str, "'Home', 'Work', 'Mobile', 'Fax', or 'Other'"] = "Mobile",
    primary: bool = False,
    carrier: str | None = None,
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="PhoneNumber",
        attributes={
            "number": number,
            "location": location,
            "primary": primary,
            "carrier": carrier,
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/people/v2/people/{person_id}/phone_numbers", json=body
    )
    return flatten_resource(response.get("data"))


# ===========================================================================
# Households
# ===========================================================================

@mcp.tool(
    name="list_households",
    description="List households (family units) in PCO People.",
)
async def list_households(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/people/v2/households", params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="households", offset=offset, per_page=per_page
    )


@mcp.tool(name="get_household", description="Fetch one household by ID.")
async def get_household(household_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(f"/people/v2/households/{household_id}")
    return flatten_resource(response.get("data"))


@mcp.tool(
    name="list_household_members",
    description="List the people in a household.",
)
async def list_household_members(household_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/households/{household_id}/people", params={"per_page": 100}
    )
    return paginated_response(response=response, items_key="people", offset=0, per_page=100)


# ===========================================================================
# Lists
# ===========================================================================

@mcp.tool(
    name="list_people_lists",
    description=(
        "List the saved People lists (smart lists / filters defined in the "
        "PCO People UI)."
    ),
)
async def list_people_lists(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/people/v2/lists", params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="lists", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="list_people_in_list",
    description="Get the people currently matching a saved People list.",
)
async def list_people_in_list(
    list_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/lists/{list_id}/people",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="people", offset=offset, per_page=per_page
    )


# ===========================================================================
# Workflows
# ===========================================================================

@mcp.tool(
    name="list_workflows",
    description=(
        "List the workflows defined in PCO People (e.g., 'New Visitor "
        "Follow-up', 'Membership Class'). Workflows have cards that move "
        "through steps."
    ),
)
async def list_workflows(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/people/v2/workflows", params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="workflows", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="list_workflow_cards",
    description=(
        "List the cards currently inside a workflow — each card represents a "
        "person moving through the workflow's steps."
    ),
)
async def list_workflow_cards(
    workflow_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/workflows/{workflow_id}/cards",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="workflow_cards", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="add_person_to_workflow",
    description=(
        "Create a workflow card for a Person, putting them at the start of "
        "the workflow."
    ),
)
async def add_person_to_workflow(workflow_id: str, person_id: str) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="WorkflowCard",
        attributes={},
        relationships={"person": jsonapi_relationship("Person", person_id)},
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/people/v2/workflows/{workflow_id}/cards", json=body
    )
    return flatten_resource(response.get("data"))


# ===========================================================================
# Notes
# ===========================================================================

@mcp.tool(
    name="list_people_note_categories",
    description="List the note categories defined for PCO People.",
)
async def list_people_note_categories() -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        "/people/v2/note_categories", params={"per_page": 100}
    )
    return paginated_response(
        response=response, items_key="note_categories", offset=0, per_page=100
    )


@mcp.tool(
    name="list_person_notes",
    description="List notes attached to a specific Person.",
)
async def list_person_notes(person_id: str, per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/people/{person_id}/notes",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="notes", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="create_person_note",
    description=(
        "Add a note to a Person. `note_category_id` is required — use "
        "list_people_note_categories to discover valid IDs."
    ),
)
async def create_person_note(
    person_id: str, note_category_id: str, note: str
) -> dict:
    session = get_current_session()
    body = build_jsonapi_body(
        type_="Note",
        attributes={"note": note},
        relationships={
            "note_category": jsonapi_relationship("NoteCategory", note_category_id),
            "person": jsonapi_relationship("Person", person_id),
        },
    )
    client = PCOClient(session.access_token)
    response = await client.post(
        f"/people/v2/people/{person_id}/notes", json=body
    )
    return flatten_resource(response.get("data"))


# ===========================================================================
# Custom fields
# ===========================================================================

@mcp.tool(
    name="list_field_definitions",
    description=(
        "List custom field definitions in PCO People (the per-org custom "
        "data fields you can attach to a Person)."
    ),
)
async def list_field_definitions() -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        "/people/v2/field_definitions", params={"per_page": 100}
    )
    return paginated_response(
        response=response, items_key="field_definitions", offset=0, per_page=100
    )


@mcp.tool(
    name="list_person_field_data",
    description="List custom-field values stored for a specific Person.",
)
async def list_person_field_data(person_id: str) -> dict:
    session = get_current_session()
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/people/{person_id}/field_data", params={"per_page": 100}
    )
    return paginated_response(
        response=response, items_key="field_data", offset=0, per_page=100
    )


# ===========================================================================
# Forms
# ===========================================================================

@mcp.tool(name="list_people_forms", description="List PCO People forms.")
async def list_people_forms(per_page: int = 25, offset: int = 0) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        "/people/v2/forms", params={"per_page": per_page, "offset": offset}
    )
    return paginated_response(
        response=response, items_key="forms", offset=offset, per_page=per_page
    )


@mcp.tool(
    name="list_form_submissions",
    description="List submissions to a People form.",
)
async def list_form_submissions(
    form_id: str, per_page: int = 25, offset: int = 0
) -> dict:
    session = get_current_session()
    per_page, offset = clamp_pagination(per_page, offset)
    client = PCOClient(session.access_token)
    response = await client.get(
        f"/people/v2/forms/{form_id}/form_submissions",
        params={"per_page": per_page, "offset": offset},
    )
    return paginated_response(
        response=response, items_key="form_submissions", offset=offset, per_page=per_page
    )
