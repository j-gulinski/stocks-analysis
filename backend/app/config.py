"""Application settings.

Loaded once from environment variables (with `.env` as a local fallback) via
pydantic-settings — the Python equivalent of a typed IOptions<Settings> bound
to appsettings + user-secrets in ASP.NET.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Anchored to an absolute path: a relative "env_file=\".env\"" resolves
    # against the PROCESS cwd, not this file's location, so it silently
    # loaded nothing whenever uvicorn was started from the repo root instead
    # of backend/ (the reported "ANTHROPIC_API_KEY missing" bug even though
    # it WAS set in backend/.env). config.py lives at backend/app/config.py,
    # so parents[1] is backend/ — same directory .env lives in.
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://stocks:stocks@localhost:5433/stocks"

    # PortalAnaliz forum credentials (optional until forum features are used).
    pa_username: str | None = None
    pa_password: str | None = None
    pa_base_url: str = "https://portalanaliz.pl/forum/"

    # BiznesRadar premium session (P1.9, optional — enhancement, not a hard
    # dependency). No creds => refresh runs fully anonymous, unchanged from
    # before this task. br_username is the account e-mail. Login recipe verified
    # live 2026-07-08 (POST /login/, 'account-settings' marker) — see
    # app/scrapers/biznesradar.py BrClient.
    br_username: str | None = None
    br_password: str | None = None

    # Claude API (Phase 5 verdict product; also the WP2b thesis refiner).
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"
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

    # When true (and a key is configured) the dossier build runs the AI
    # refiners (thesis_ai / scenarios_ai / valuation_ai / insights_ai) with the
    # real settings instead of forcing the deterministic no-key path. File
    # caches keyed on input-hash+model keep repeat GETs cheap.
    ai_refiners_enabled: bool = True

    # P5.9 forum distiller (services/forum_distiller.py): a cheap model is
    # enough for per-post classification/claim-extraction, so it defaults
    # separately from the (pricier) verdict model. Falls back to
    # `anthropic_model` if unset.
    ai_distill_model: str = "claude-haiku-4-5"

    # Static bearer token required in production (Phase 6). When unset,
    # auth middleware is disabled — local dev runs open on localhost.
    api_token: str | None = None

    # myfund.pl explicit snapshot sync. The key is generated in myfund and is
    # never persisted in the database or logs. `myfund_portfolio` is the exact
    # name of the one pinned portfolio accepted by getPortfel.php (not its id).
    myfund_api_key: str | None = None
    myfund_portfolio: str | None = None
    myfund_base_url: str = "https://myfund.pl/"

    # Pages fetched more recently than this are served from the DB, not re-scraped.
    scrape_cache_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so every import shares one Settings instance."""
    return Settings()
