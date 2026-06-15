"""FastAPI auth routes: /auth/login, /auth/start, /auth/callback, /auth/logout.

Flow:
  GET /auth/login    → simple HTML landing page with "Connect" button
  GET /auth/start    → make PKCE pair + state, set signed cookie, 302 to PCO
  GET /auth/callback → verify state, exchange code for tokens, fetch profile,
                       insert session, render confirmation page with session_token
  GET /auth/logout/{token} → delete the session row

State + PKCE verifier travel between /start and /callback in a signed,
http-only cookie (itsdangerous URLSafeTimedSerializer). The signature stops
tampering; the timeout (10 min) stops replay across long delays.
"""

from __future__ import annotations

import html
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.auth import oauth, token_store
from app.config import get_settings


logger = logging.getLogger("pco_mcp.auth.routes")

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_COOKIE_NAME = "pco_oauth_state"
OAUTH_COOKIE_MAX_AGE_SECONDS = 600  # 10 minutes — well over the OAuth round-trip
COOKIE_SALT = "pco-oauth-v1"


def _serializer() -> URLSafeTimedSerializer:
    """itsdangerous serializer keyed by SESSION_SECRET. New per-call so a
    rotated secret is picked up without restart in dev (cheap to construct)."""
    return URLSafeTimedSerializer(get_settings().session_secret, salt=COOKIE_SALT)


def _is_https_redirect() -> bool:
    """Set the cookie's Secure flag iff we're configured for HTTPS callbacks."""
    return get_settings().pco_redirect_uri.lower().startswith("https://")


# ---------------------------------------------------------------------------
# /auth/login — human-facing landing page
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    """Plain HTML 'Connect with Planning Center' page."""
    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PCO MCP — Connect</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 520px; margin: 4rem auto; padding: 1rem; color: #222;
           line-height: 1.5; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    p { color: #444; }
    .btn { display: inline-block; padding: 0.75rem 1.5rem; background: #4a90e2;
           color: white; text-decoration: none; border-radius: 6px;
           font-weight: 600; margin-top: 0.5rem; }
    .btn:hover { background: #3a7fcf; }
    .note { color: #666; font-size: 0.9rem; margin-top: 2rem; }
  </style>
</head>
<body>
  <h1>Connect your Planning Center account</h1>
  <p>You'll be redirected to Planning Center to sign in and authorize this
     MCP server. After approval, you'll receive a session token to paste
     into your AI client (Claude Desktop, Open WebUI, ChatGPT Desktop).</p>
  <p><a class="btn" href="/auth/start">Connect with Planning Center →</a></p>
  <p class="note">Each user's actions are constrained by their own PCO
     permissions. A volunteer can read; a worship pastor can create/update.</p>
</body>
</html>"""
    )


# ---------------------------------------------------------------------------
# /auth/start — PKCE setup + redirect to PCO
# ---------------------------------------------------------------------------

@router.get("/start")
async def login_start() -> RedirectResponse:
    pkce = oauth.generate_pkce()
    state = oauth.generate_state()

    # Pack state + verifier into a signed, http-only cookie. The signature
    # prevents tampering; the timeout in the loader prevents replay.
    cookie_value = _serializer().dumps({"state": state, "verifier": pkce.verifier})

    authorize_url = oauth.build_authorize_url(
        state=state, code_challenge=pkce.challenge
    )
    response = RedirectResponse(url=authorize_url, status_code=302)
    response.set_cookie(
        OAUTH_COOKIE_NAME,
        cookie_value,
        max_age=OAUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
        secure=_is_https_redirect(),
    )
    logger.info("OAuth flow started; redirecting to PCO authorize")
    return response


# ---------------------------------------------------------------------------
# /auth/callback — code exchange + session creation
# ---------------------------------------------------------------------------

@router.get("/callback")
async def login_callback(
    response: Response,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
    pco_oauth_state: Annotated[str | None, Cookie()] = None,
) -> HTMLResponse:
    # --- Did PCO return an error? ---
    if error:
        return _error_page(
            f"Planning Center returned an error: <code>{html.escape(error)}</code> "
            f"— {html.escape(error_description or '')}"
        )

    if not code or not state:
        return _error_page("Missing <code>code</code> or <code>state</code> from PCO.")

    if not pco_oauth_state:
        return _error_page(
            "Missing OAuth cookie. Start over at "
            "<a href='/auth/login'>/auth/login</a>."
        )

    # --- Verify our signed cookie ---
    try:
        cookie_data = _serializer().loads(
            pco_oauth_state, max_age=OAUTH_COOKIE_MAX_AGE_SECONDS
        )
    except SignatureExpired:
        return _error_page("OAuth cookie expired. Try again from /auth/login.")
    except BadSignature:
        logger.warning("OAuth callback received a cookie with a bad signature.")
        return _error_page("OAuth cookie failed verification (tampered or invalid).")

    if cookie_data.get("state") != state:
        logger.warning("State mismatch on OAuth callback — possible CSRF.")
        return _error_page("OAuth state mismatch — possible CSRF; aborting.")

    code_verifier = cookie_data.get("verifier")
    if not code_verifier:
        return _error_page("OAuth cookie is missing the PKCE verifier; aborting.")

    # --- Exchange the code for tokens ---
    try:
        tokens = await oauth.exchange_code_for_tokens(
            code=code, code_verifier=code_verifier
        )
    except Exception as exc:  # noqa: BLE001 — surface PCO errors to user
        logger.exception("Token exchange failed")
        return _error_page(f"Token exchange failed: {html.escape(str(exc))}")

    try:
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        expires_in = int(tokens.get("expires_in", 7200))
        scopes = tokens.get("scope") or get_settings().pco_scopes
    except KeyError as exc:
        logger.exception("Token response missing expected key")
        return _error_page(
            f"Token response missing field: <code>{html.escape(str(exc))}</code>"
        )
    token_expires = int(time.time()) + expires_in

    # --- Fetch the PCO user profile ---
    try:
        profile = await oauth.fetch_user_profile(access_token=access_token)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Profile fetch failed")
        return _error_page(
            f"Could not fetch your Planning Center profile: {html.escape(str(exc))}"
        )

    person = profile.get("data") or {}
    pco_user_id = str(person.get("id", "unknown"))
    attrs = person.get("attributes") or {}
    pco_user_name = (
        attrs.get("full_name")
        or attrs.get("name")
        or " ".join(filter(None, [attrs.get("first_name"), attrs.get("last_name")])).strip()
        or None
    )
    # /services/v2/me doesn't always include an email — that's fine.
    pco_user_email = attrs.get("email_address") or attrs.get("email") or None

    # --- Persist the session ---
    session_token = await token_store.create_session(
        pco_user_id=pco_user_id,
        pco_user_name=pco_user_name,
        pco_user_email=pco_user_email,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires=token_expires,
        scopes=scopes,
    )

    # --- Render success page; clear the OAuth cookie ---
    success = _success_page(
        session_token=session_token,
        user_name=pco_user_name or pco_user_id,
        pco_user_id=pco_user_id,
    )
    success.delete_cookie(OAUTH_COOKIE_NAME, path="/")
    return success


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------

@router.get("/logout/{session_token}")
async def logout(session_token: str) -> HTMLResponse:
    deleted = await token_store.delete_session(session_token)
    if deleted:
        msg = (
            "Session deleted. You'll need to log in again at "
            "<a href='/auth/login'>/auth/login</a> to use this MCP server."
        )
    else:
        msg = "No matching session found (already logged out?)."
    return HTMLResponse(f"<p style='font-family:sans-serif;max-width:480px;margin:4rem auto'>{msg}</p>")


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _success_page(*, session_token: str, user_name: str, pco_user_id: str) -> HTMLResponse:
    safe_name = html.escape(user_name)
    safe_token = html.escape(session_token)
    safe_uid = html.escape(pco_user_id)
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PCO MCP — Connected</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 720px; margin: 3rem auto; padding: 1rem; color: #222;
           line-height: 1.5; }}
    h1 {{ font-size: 1.5rem; }}
    h2 {{ font-size: 1.05rem; margin-top: 2rem; color: #333; }}
    .token {{ font-family: ui-monospace, "SF Mono", Menlo, monospace;
             background: #f3f3f3; padding: 0.9rem; border-radius: 6px;
             word-break: break-all; user-select: all; font-size: 1.05rem;
             border: 1px solid #ddd; }}
    .config {{ background: #1e1e1e; color: #d4d4d4; padding: 1rem;
              border-radius: 6px; font-family: ui-monospace, monospace;
              font-size: 0.85rem; overflow-x: auto; white-space: pre; }}
    .warn {{ background: #fff8e1; border-left: 4px solid #ffc107;
            padding: 0.75rem 1rem; margin: 1rem 0; border-radius: 4px;
            font-size: 0.92rem; }}
    .ok {{ color: #2e7d32; }}
    .muted {{ color: #666; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <h1 class="ok">✓ Connected as {safe_name}</h1>
  <p class="muted">PCO user ID: <code>{safe_uid}</code></p>

  <h2>Your session token</h2>
  <p>Save this token — you'll paste it into your AI client.</p>
  <p class="token">{safe_token}</p>
  <div class="warn">
    <strong>One-time display.</strong> If you lose this token you can always
    log in again to mint a new one — your existing session keeps working.
  </div>

  <h2>Claude Desktop config</h2>
  <pre class="config">{{
  "mcpServers": {{
    "planning-center": {{
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {{
        "X-Session-Token": "{safe_token}"
      }}
    }}
  }}
}}</pre>

  <h2>Query-param variant (ChatGPT Desktop, Open WebUI)</h2>
  <pre class="config">http://localhost:8000/mcp?token={safe_token}</pre>

  <p class="muted" style="margin-top:2rem">
    Want to disconnect? Visit
    <code>/auth/logout/{safe_token}</code> — that deletes this session
    from the server (your PCO account is unaffected).
  </p>
</body>
</html>"""
    )


def _error_page(message_html: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PCO MCP — Auth Error</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 520px; margin: 4rem auto; padding: 1rem; color: #222; }}
    h1 {{ font-size: 1.4rem; color: #c62828; }}
    .err {{ background: #ffebee; border-left: 4px solid #c62828;
           padding: 0.75rem 1rem; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Authentication failed</h1>
  <div class="err">{message_html}</div>
  <p><a href="/auth/login">← Try again</a></p>
</body>
</html>""",
        status_code=400,
    )
