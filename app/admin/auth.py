"""HTTP Basic auth dependency for the admin page.

Why Basic auth (not OAuth-style cookies):
- One credential pair, set in .env, no database changes
- Browsers handle the prompt natively
- Curl/scripts can `-u user:pass` for verification

If `ADMIN_USERNAME` or `ADMIN_PASSWORD` is unset, the dependency raises 503
to make it impossible to use /admin in a partially-configured deployment.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings


# `auto_error=False` so we can raise our own HTTPException that prompts the
# browser to show the login dialog (WWW-Authenticate header) with our realm.
_basic = HTTPBasic(auto_error=False, realm="PCO MCP Admin")


async def require_admin(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
) -> str:
    """Reject unless valid admin Basic credentials are present.

    Returns the authenticated username (for logging) on success.
    """
    settings = get_settings()

    if not settings.admin_enabled:
        # 503 makes it clearer than 401 that the FEATURE is disabled, not
        # that the caller's credentials are wrong.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Admin page is disabled. Set ADMIN_USERNAME and ADMIN_PASSWORD "
                "in the server's .env to enable."
            ),
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin login required.",
            headers={"WWW-Authenticate": 'Basic realm="PCO MCP Admin"'},
        )

    # secrets.compare_digest avoids timing attacks on byte-by-byte comparison.
    # We encode to bytes first so unicode strings of different lengths don't
    # short-circuit before the digest comparison runs.
    expected_user = (settings.admin_username or "").encode("utf-8")
    expected_pass = (settings.admin_password or "").encode("utf-8")
    given_user = credentials.username.encode("utf-8")
    given_pass = credentials.password.encode("utf-8")

    user_ok = secrets.compare_digest(given_user, expected_user)
    pass_ok = secrets.compare_digest(given_pass, expected_pass)

    if not (user_ok and pass_ok):
        # Re-prompt by sending WWW-Authenticate again; the browser will
        # discard cached creds and pop the dialog.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
            headers={"WWW-Authenticate": 'Basic realm="PCO MCP Admin"'},
        )

    return credentials.username
