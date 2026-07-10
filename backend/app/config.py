"""Application settings.

Loaded once from environment variables (with `.env` as a local fallback) via
pydantic-settings — the Python equivalent of a typed IOptions<Settings> bound
to appsettings + user-secrets in ASP.NET.
"""
from functools import lru_cache

from pydantic import Field
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

    # BiznesRadar premium session (P1.9, optional — enhancement, not a hard
    # dependency). No creds => refresh runs fully anonymous, unchanged from
    # before this task. See app/scrapers/biznesradar.py BrClient: the real
    # login markup is unverified pending a recorded login-page fixture.
    br_username: str | None = None
    br_password: str | None = None

    # Claude API (Phase 5 verdict product; also the WP2b thesis refiner).
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    ai_daily_limit: int = Field(default=20, ge=0)
    # Global provider-attempt and measured-token ceilings. Each retry consumes
    # another attempt; 0 intentionally disables model execution for the day.
    ai_daily_call_limit: int = Field(default=60, ge=0)
    ai_daily_token_limit: int = Field(default=500_000, ge=0)

    # WP2b iterative thesis refiner (services/thesis_ai.py). No key ⇒ the refiner
    # is a transparent pass-through to the deterministic read; these only bite on
    # the AI path. max_iterations is deliberately small (cost/latency guard).
    anthropic_max_iterations: int = 2
    ai_cache_enabled: bool = True

    # P5.9 forum distiller (services/forum_distiller.py): a cheap model is
    # enough for per-post classification/claim-extraction, so it defaults
    # separately from the (pricier) verdict model. Falls back to
    # `anthropic_model` if unset.
    ai_distill_model: str = "claude-haiku-4-5"

    # Static bearer token required in production (Phase 6). When unset,
    # auth middleware is disabled — local dev runs open on localhost.
    api_token: str | None = None

    # Pages fetched more recently than this are served from the DB, not re-scraped.
    scrape_cache_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so every import shares one Settings instance."""
    return Settings()
