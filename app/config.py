"""Application configuration loaded from environment / .env.

Uses pydantic-settings so values are validated at startup. If a required
secret is missing the app refuses to start rather than failing later in a
confusing place (e.g., mid-OAuth flow).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root = the directory that contains this file's parent (the `app/` dir).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "db"
DB_PATH = DB_DIR / "pco_sessions.db"


class Settings(BaseSettings):
    """Server settings. Read from environment variables and/or a .env file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- PCO OAuth app credentials ---
    pco_client_id: str = Field(..., description="OAuth client_id from PCO developer portal")
    pco_client_secret: str = Field(..., description="OAuth client_secret from PCO developer portal")
    pco_redirect_uri: str = Field(
        ...,
        description="Must EXACTLY match a redirect URI registered on the PCO OAuth app.",
    )
    pco_scopes: str = Field(
        "services",
        description="Space-separated OAuth scopes requested from PCO.",
    )

    # --- Server secrets ---
    encryption_key: str = Field(
        ...,
        description="Fernet key for encrypting stored PCO tokens at rest. NEVER change after first run.",
    )
    session_secret: str = Field(
        ...,
        description="Random secret for signing OAuth state cookies.",
    )

    # --- Runtime ---
    port: int = 8000
    log_level: str = "info"
    session_expiry_days: int = Field(
        0,
        description="0 = no inactivity expiry. >0 = delete sessions whose last_used is older than this many days.",
    )

    # --- Admin page (Phase 10) ---
    # Optional. If either is unset/blank, /admin returns 503 'admin disabled'.
    admin_username: str | None = Field(
        None,
        description="HTTP Basic auth username for /admin. Leave unset to disable the admin UI.",
    )
    admin_password: str | None = Field(
        None,
        description="HTTP Basic auth password for /admin.",
    )

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_username) and bool(self.admin_password)

    # --- Convenience ---
    @property
    def db_path(self) -> Path:
        return DB_PATH

    @property
    def pco_authorize_url(self) -> str:
        return "https://api.planningcenteronline.com/oauth/authorize"

    @property
    def pco_token_url(self) -> str:
        return "https://api.planningcenteronline.com/oauth/token"

    @property
    def pco_api_base(self) -> str:
        return "https://api.planningcenteronline.com"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor so we parse env exactly once."""
    return Settings()  # type: ignore[call-arg]  # values come from env/.env
