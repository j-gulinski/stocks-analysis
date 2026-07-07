"""Application settings.

Loaded once from environment variables (with `.env` as a local fallback) via
pydantic-settings — the Python equivalent of a typed IOptions<Settings> bound
to appsettings + user-secrets in ASP.NET.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://stocks:stocks@localhost:5432/stocks"

    # PortalAnaliz forum credentials (optional until forum features are used).
    pa_username: str | None = None
    pa_password: str | None = None
    pa_base_url: str = "https://portalanaliz.pl/forum/"

    # Claude API (Phase 5).
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    ai_daily_limit: int = 20

    # Static bearer token required in production (Phase 6). When unset,
    # auth middleware is disabled — local dev runs open on localhost.
    api_token: str | None = None

    # Pages fetched more recently than this are served from the DB, not re-scraped.
    scrape_cache_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so every import shares one Settings instance."""
    return Settings()
