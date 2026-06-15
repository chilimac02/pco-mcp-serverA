"""SQLite bootstrap.

Uses aiosqlite so the server stays fully async. The single `sessions` table
stores one row per connected PCO user; the PCO access/refresh tokens are
stored encrypted (Phase 3 wires up the Fernet calls — Phase 1 just sets up
the schema).
"""

from __future__ import annotations

import aiosqlite

from app.config import DB_DIR, get_settings


# Schema for the sessions table — keep in sync with the project plan §7.
# We use IF NOT EXISTS so init_db() is idempotent across restarts.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_token   TEXT PRIMARY KEY,
    pco_user_id     TEXT NOT NULL,
    pco_user_name   TEXT,
    pco_user_email  TEXT,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    token_expires   INTEGER NOT NULL,
    scopes          TEXT,
    created_at      INTEGER NOT NULL,
    last_used       INTEGER
);

CREATE INDEX IF NOT EXISTS idx_sessions_pco_user_id ON sessions(pco_user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_used ON sessions(last_used);
"""


async def init_db() -> None:
    """Create the SQLite file (if missing), ensure the schema exists, and
    migrate any plaintext token rows to Fernet-encrypted form.

    Called from FastAPI's lifespan on startup. Safe to call repeatedly —
    schema creation uses IF NOT EXISTS and the migration is idempotent.
    """
    settings = get_settings()
    DB_DIR.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(settings.db_path) as conn:
        await conn.executescript(SCHEMA_SQL)
        await conn.commit()

    # Imported here to avoid a circular dependency between db.py and the auth
    # package (auth imports config; db is config-adjacent).
    from app.auth.token_store import migrate_plaintext_tokens

    await migrate_plaintext_tokens()


def get_db_path() -> str:
    """String form of the db path, for places that want a connection string."""
    return str(get_settings().db_path)
