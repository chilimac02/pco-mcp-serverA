"""Thin async httpx wrapper around the Planning Center JSON:API.

Why we wrote this instead of using pypco:
  - pypco's coverage of write endpoints (POST/PATCH/DELETE) is patchy and
    lags behind the API. We need ALL CRUD on ~60 endpoints.
  - We want full control over per-call Authorization headers (bearer token
    rotates per user) without instantiating a heavyweight client per call.
  - We want explicit, typed error surfaces (401/403/404/429/5xx → distinct
    exception subclasses) so MCP tools can convert them to clean messages.

Usage from a tool:
    session = get_current_session()
    client = PCOClient(session.access_token)
    data = await client.get("/services/v2/service_types", params={"per_page": 25})

The class is cheap to construct (no httpx.Client until a request is made;
we use a one-shot AsyncClient inside `request()`). For higher throughput we
could pool clients later — Phase 5 doesn't need that.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import get_settings


logger = logging.getLogger("pco_mcp.pco.client")


# How long to wait if PCO returns 429 with no Retry-After header.
DEFAULT_429_BACKOFF_SECONDS = 20

# Max single-request timeout. PCO occasionally takes a few seconds for big
# list endpoints; 30s is generous without letting requests stack up forever.
REQUEST_TIMEOUT_SECONDS = 30.0


# ---------------------------------------------------------------------------
# Exceptions — typed by status code so tools can choose how to surface them.
# ---------------------------------------------------------------------------

class PCOAPIError(Exception):
    """Base class for any non-2xx response from PCO."""

    def __init__(self, *, status_code: int, path: str, body: Any) -> None:
        self.status_code = status_code
        self.path = path
        self.body = body
        # Extract the human-friendly error message if PCO returned JSON:API errors.
        message = self._extract_message(body) or f"HTTP {status_code} on {path}"
        super().__init__(message)

    @staticmethod
    def _extract_message(body: Any) -> str | None:
        if isinstance(body, dict):
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    return first.get("detail") or first.get("title")
        return None


class PCOUnauthorized(PCOAPIError):
    """401 from PCO — access token rejected (probably expired mid-call)."""


class PCOForbidden(PCOAPIError):
    """403 from PCO — user lacks permission for this action.

    This is the expected outcome when, e.g., a volunteer tries to create a
    plan. The MCP tool should surface this verbatim so the AI client can
    relay the permission gap to the user.
    """


class PCONotFound(PCOAPIError):
    """404 from PCO — the resource doesn't exist or isn't visible to this user."""


class PCORateLimited(PCOAPIError):
    """429 from PCO — Retry-After exhausted. Raised after the single retry."""


class PCOServerError(PCOAPIError):
    """5xx from PCO — transient infra issue on their side."""


def _classify(status_code: int) -> type[PCOAPIError]:
    if status_code == 401:
        return PCOUnauthorized
    if status_code == 403:
        return PCOForbidden
    if status_code == 404:
        return PCONotFound
    if status_code == 429:
        return PCORateLimited
    if 500 <= status_code < 600:
        return PCOServerError
    return PCOAPIError


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class PCOClient:
    """Per-call PCO API client. One instance per MCP tool invocation."""

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token
        self.base_url = get_settings().pco_api_base

    # ---- public helpers ----------------------------------------------

    async def get(self, path: str, *, params: dict | None = None) -> dict:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, *, json: dict) -> dict:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, *, json: dict) -> dict:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str) -> dict:
        return await self.request("DELETE", path)

    # ---- core request loop -------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        """Execute a single request with one 429-aware retry.

        Returns the parsed JSON body (or {} for 204 No Content). Raises a
        `PCOAPIError` subclass on any 4xx/5xx; the message is the PCO error
        `detail` when available, so it's safe to log/show.
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            for attempt in (1, 2):
                resp = await client.request(
                    method, url, params=params, json=json, headers=headers
                )

                # Happy paths first.
                if 200 <= resp.status_code < 300:
                    return _safe_json(resp)

                # Retry once on 429, honoring Retry-After if PCO sent it.
                if resp.status_code == 429 and attempt == 1:
                    wait = _retry_after_seconds(resp) or DEFAULT_429_BACKOFF_SECONDS
                    logger.warning(
                        "PCO rate-limited %s %s — sleeping %ss before retry",
                        method, path, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                # Any other error — classify and raise.
                body = _safe_json(resp)
                cls = _classify(resp.status_code)
                logger.warning(
                    "PCO %s %s -> %s: %s",
                    method, path, resp.status_code, body,
                )
                raise cls(status_code=resp.status_code, path=path, body=body)

        # Loop fell through (shouldn't happen — both attempts must return or raise).
        raise PCOAPIError(status_code=0, path=path, body="unreachable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(resp: httpx.Response) -> dict:
    """Return resp.json() or {} if the body is empty / not JSON.

    PCO returns empty bodies on 204 (DELETE) and sometimes 200 — both should
    be treated as success without forcing the caller to handle JSON errors.
    """
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        # Non-JSON body on an error response — wrap as a string for the caller.
        return {"raw_body": resp.text[:1000]}


def _retry_after_seconds(resp: httpx.Response) -> int | None:
    """Parse Retry-After (PCO sends an integer number of seconds)."""
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        # Cap at 60s — we don't want to block a single MCP call for minutes.
        return min(int(raw), 60)
    except (TypeError, ValueError):
        return None
