"""SQLite CRUD for OAuth sessions — with at-rest encryption + auto-refresh.

Public surface:
  create_session(...)               – inserts a new session, returns session_token
  get_session(session_token)        – returns row with DECRYPTED tokens, or None
  get_session_with_fresh_token(...) – ensures access_token has >5min left
                                       (refreshes via PCO if not), returns the
                                       row with the fresh decrypted tokens.
                                       This is the call site MCP middleware uses.
  update_tokens(...)                – persists a refreshed token pair (encrypted)
  touch_session(session_token)      – bump last_used
  delete_session(session_token)     – remove a session
  list_sessions()                   – admin view, NEVER includes token columns
  migrate_plaintext_tokens()        – idempotent; called from init_db at startup

Encryption: every write goes through `crypto.encrypt()`; every read goes
through `crypto.decrypt()`. Plain text never touches the SQLite file.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import aiosqlite

from app.auth import crypto, oauth
from app.config import get_settings


logger = logging.getLogger("pco_mcp.auth.token_store")


# Tokens are refreshed if they expire within this many seconds. PCO access
# tokens last 7200s; 300s gives a comfortable safety margin for slow API calls.
REFRESH_THRESHOLD_SECONDS = 300


class RefreshFailed(Exception):
    """Raised when PCO refuses to mint a fresh access_token.

    Usually means the refresh token is older than 90 days, was revoked from
    the PCO side, or the OAuth app's credentials changed. The session is
    unrecoverable — the user has to re-authenticate via /auth/login.
    """


# ---------------------------------------------------------------------------
# Create / read
# ---------------------------------------------------------------------------

async def create_session(
    *,
    pco_user_id: str,
    pco_user_name: str | None,
    pco_user_email: str | None,
    access_token: str,
    refresh_token: str,
    token_expires: int,
    scopes: str,
) -> str:
    """Persist a new session (tokens encrypted) and return the session_token."""
    settings = get_settings()
    session_token = str(uuid.uuid4())
    now = int(time.time())

    enc_access = crypto.encrypt(access_token)
    enc_refresh = crypto.encrypt(refresh_token)

    async with aiosqlite.connect(settings.db_path) as conn:
        await conn.execute(
            """
            INSERT INTO sessions (
                session_token, pco_user_id, pco_user_name, pco_user_email,
                access_token, refresh_token, token_expires, scopes,
                created_at, last_used
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_token,
                pco_user_id,
                pco_user_name,
                pco_user_email,
                enc_access,
                enc_refresh,
                token_expires,
                scopes,
                now,
                now,
            ),
        )
        await conn.commit()

    logger.info(
        "Created session for PCO user %s (%s)",
        pco_user_id,
        pco_user_name or "no name",
    )
    return session_token


async def get_session(session_token: str) -> dict[str, Any] | None:
    """Return the session row with DECRYPTED tokens, or None if not found.

    Raises crypto.DecryptionError if the row exists but its ciphertext can't
    be decrypted (ENCRYPTION_KEY mismatch).
    """
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM sessions WHERE session_token = ?",
            (session_token,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        data = dict(row)
        data["access_token"] = crypto.decrypt(data["access_token"])
        data["refresh_token"] = crypto.decrypt(data["refresh_token"])
        return data


async def touch_session(session_token: str) -> None:
    """Bump `last_used` to now. Called by the MCP middleware on every call."""
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as conn:
        await conn.execute(
            "UPDATE sessions SET last_used = ? WHERE session_token = ?",
            (int(time.time()), session_token),
        )
        await conn.commit()


async def update_tokens(
    *,
    session_token: str,
    access_token: str,
    refresh_token: str,
    token_expires: int,
) -> None:
    """Persist freshly-refreshed tokens (encrypted)."""
    settings = get_settings()
    enc_access = crypto.encrypt(access_token)
    enc_refresh = crypto.encrypt(refresh_token)

    async with aiosqlite.connect(settings.db_path) as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET access_token = ?, refresh_token = ?, token_expires = ?,
                last_used = ?
            WHERE session_token = ?
            """,
            (enc_access, enc_refresh, token_expires, int(time.time()), session_token),
        )
        await conn.commit()


async def delete_session(session_token: str) -> int:
    """Remove a session. Returns the number of rows deleted (0 or 1)."""
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as conn:
        cursor = await conn.execute(
            "DELETE FROM sessions WHERE session_token = ?", (session_token,)
        )
        await conn.commit()
        return cursor.rowcount or 0


async def list_sessions() -> list[dict[str, Any]]:
    """Admin view — returns sessions WITHOUT token columns.

    Used by the admin page in Phase 10. Excluding token columns from this
    helper means casual logging or templating can't accidentally leak them.
    """
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT session_token, pco_user_id, pco_user_name, pco_user_email,
                   token_expires, scopes, created_at, last_used
            FROM sessions
            ORDER BY last_used DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------

async def get_session_with_fresh_token(session_token: str) -> dict[str, Any] | None:
    """Return the session with a guaranteed-fresh access_token.

    If the stored access_token expires within REFRESH_THRESHOLD_SECONDS, this
    calls PCO's refresh endpoint to mint a new token pair, encrypts and
    saves them, then returns the row with the new decrypted access_token.

    Returns None if no session matches the given token.
    Raises `RefreshFailed` if PCO rejects the refresh attempt.
    """
    session = await get_session(session_token)
    if session is None:
        return None

    now = int(time.time())
    remaining = int(session["token_expires"]) - now

    if remaining > REFRESH_THRESHOLD_SECONDS:
        # Plenty of headroom — just bump last_used and return as-is.
        await touch_session(session_token)
        return session

    logger.info(
        "Refreshing PCO token for session %s (expires in %ds, threshold %ds)",
        session_token[:8] + "…",
        remaining,
        REFRESH_THRESHOLD_SECONDS,
    )

    try:
        fresh = await oauth.refresh_access_token(refresh_token=session["refresh_token"])
    except Exception as exc:  # noqa: BLE001 — convert to typed error
        raise RefreshFailed(
            f"PCO refused the refresh for session {session_token[:8]}…: {exc}"
        ) from exc

    new_access = fresh["access_token"]
    # PCO rotates refresh tokens too — always save the new one, never reuse old.
    new_refresh = fresh.get("refresh_token", session["refresh_token"])
    expires_in = int(fresh.get("expires_in", 7200))
    new_expires = int(time.time()) + expires_in

    await update_tokens(
        session_token=session_token,
        access_token=new_access,
        refresh_token=new_refresh,
        token_expires=new_expires,
    )

    # Return the in-memory copy (saves a redundant round-trip to SQLite).
    session["access_token"] = new_access
    session["refresh_token"] = new_refresh
    session["token_expires"] = new_expires
    session["last_used"] = int(time.time())
    return session


# ---------------------------------------------------------------------------
# Migration: plaintext rows → encrypted (one-time, idempotent)
# ---------------------------------------------------------------------------

async def migrate_plaintext_tokens() -> int:
    """Detect rows with plaintext tokens and encrypt them in place.

    Called from `init_db()` at startup so any rows left over from Phase 2
    get upgraded silently. Idempotent — encrypted rows are skipped via the
    `crypto.looks_encrypted()` prefix check.

    Returns the number of rows that were migrated.
    """
    settings = get_settings()
    migrated = 0

    async with aiosqlite.connect(settings.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT session_token, access_token, refresh_token FROM sessions"
        )
        rows = await cursor.fetchall()

        for row in rows:
            access = row["access_token"]
            refresh = row["refresh_token"]
            needs_access = not crypto.looks_encrypted(access)
            needs_refresh = not crypto.looks_encrypted(refresh)
            if not (needs_access or needs_refresh):
                continue

            new_access = crypto.encrypt(access) if needs_access else access
            new_refresh = crypto.encrypt(refresh) if needs_refresh else refresh
            await conn.execute(
                "UPDATE sessions SET access_token = ?, refresh_token = ? "
                "WHERE session_token = ?",
                (new_access, new_refresh, row["session_token"]),
            )
            migrated += 1

        if migrated:
            await conn.commit()
            logger.warning(
                "Migrated %d session row(s) from plaintext to Fernet-encrypted tokens.",
                migrated,
            )
        else:
            logger.debug("No plaintext sessions to migrate.")

    return migrated
