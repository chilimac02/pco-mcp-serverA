"""OAuth 2.0 + PKCE helpers for Planning Center.

PCO's OAuth implementation follows the standard `code` grant with PKCE
(`code_challenge_method=S256`). We're a confidential client (we have a
`client_secret`) AND we use PKCE — PCO's recommended secure setup.

This module is deliberately small and stateless. Stateful concerns (cookies,
sessions, request handling) live in `routes.py`.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import get_settings


logger = logging.getLogger("pco_mcp.auth.oauth")


@dataclass(frozen=True)
class PKCEPair:
    """A PKCE verifier and its derived challenge.

    The verifier is the secret that stays on our side until the token
    exchange; the challenge is sent up-front to PCO so they can validate
    the verifier when the user is redirected back.
    """

    verifier: str
    challenge: str


def generate_pkce() -> PKCEPair:
    """Make a fresh PKCE pair using S256.

    Verifier length is 43–128 chars per RFC 7636. We use 64 random bytes
    → ~86 base64url chars, comfortably within range.
    """
    verifier_bytes = secrets.token_bytes(64)
    verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PKCEPair(verifier=verifier, challenge=challenge)


def generate_state() -> str:
    """Anti-CSRF token. Stored in our signed cookie and echoed by PCO."""
    return secrets.token_urlsafe(32)


def build_authorize_url(*, state: str, code_challenge: str) -> str:
    """Compose the PCO authorize URL the user's browser is redirected to."""
    settings = get_settings()
    params = {
        "client_id": settings.pco_client_id,
        "redirect_uri": settings.pco_redirect_uri,
        "response_type": "code",
        "scope": settings.pco_scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{settings.pco_authorize_url}?{urlencode(params)}"


async def exchange_code_for_tokens(*, code: str, code_verifier: str) -> dict:
    """Exchange the authorization `code` for `access_token` + `refresh_token`.

    Raises httpx.HTTPStatusError if PCO rejects (bad code, wrong secret, etc.).
    Returns the parsed JSON body, which includes at minimum:
      access_token, refresh_token, token_type, expires_in, scope, created_at
    """
    settings = get_settings()
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.pco_client_id,
        "client_secret": settings.pco_client_secret,
        "redirect_uri": settings.pco_redirect_uri,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(settings.pco_token_url, data=payload)
        if resp.status_code >= 400:
            # PCO returns helpful JSON error bodies — surface them.
            logger.error(
                "Token exchange failed (status=%s): %s",
                resp.status_code,
                resp.text[:500],
            )
            resp.raise_for_status()
        return resp.json()


async def refresh_access_token(*, refresh_token: str) -> dict:
    """Use a refresh_token to mint a fresh access_token.

    Called by the background refresh logic in Phase 3 — included here so the
    OAuth surface lives in one file. Returns the same shape as
    `exchange_code_for_tokens`.
    """
    settings = get_settings()
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.pco_client_id,
        "client_secret": settings.pco_client_secret,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(settings.pco_token_url, data=payload)
        if resp.status_code >= 400:
            logger.error(
                "Token refresh failed (status=%s): %s",
                resp.status_code,
                resp.text[:500],
            )
            resp.raise_for_status()
        return resp.json()


async def fetch_user_profile(*, access_token: str) -> dict:
    """Look up the authenticated user via /services/v2/me.

    We use the Services endpoint (not /people/v2/me) because we only request
    the `services` scope by default — /people/v2/me would require the `people`
    scope. /services/v2/me returns a JSON:API Person resource with
    first_name/last_name/full_name/etc.
    """
    settings = get_settings()
    url = f"{settings.pco_api_base}/services/v2/me"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code >= 400:
            logger.error(
                "Profile fetch failed (status=%s): %s",
                resp.status_code,
                resp.text[:500],
            )
            resp.raise_for_status()
        return resp.json()
