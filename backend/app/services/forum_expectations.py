"""Investment-expectations refresh (PLAN §8 forum distillation, P5.9b).

Thin glue between already-synced `ForumPost.content_text` rows and the
per-post distiller (`services/forum_distiller.py`): loads a company's posts,
runs `distill_company_posts`, and upserts the merged claim list onto
`ForumIntelligence.expectations`. Separate module (rather than adding this to
`forum_distiller.py`) so that module can stay PyPI-free at import time
(`test_forum_distiller.py::test_module_imports_without_pypi`) — this one
needs SQLAlchemy, so it may as well own the DB read/write plumbing too.

Same degrade-first contract as every other AI-adjacent service in this app
(`thesis_ai`, `scenarios_ai`, `forum_distiller`): a bad run must never fail
the caller (`services/refresh.py`). Unlike those, though, "no API key" here
does not fall through to an empty result — an empty distillation would
silently OVERWRITE a previous good run's claims (e.g. a key that was
temporarily unset), so no-key is a distinct short-circuit that touches
nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, ForumIntelligence, ForumPost, ForumTopic, utcnow
from app.services import forum_distiller


@dataclass
class ExpectationsRefreshResult:
    """Outcome of one `refresh_expectations` call — `services/refresh.py`
    turns this into the Polish summary line, same split as every other
    refresh sub-step (ok / skipped / error)."""

    status: str  # "ok" | "skipped" | "error"
    claim_count: int = 0
    detail: str | None = None


def _resolve_settings(settings):
    """Same lazy-load pattern as `forum_distiller._resolve_settings` —
    duplicated (not imported) so this module's dependency on that one stays
    limited to the public `distill_company_posts`/`DistilledClaim` API."""
    if settings is not None:
        return settings
    from app.config import get_settings  # lazy: pydantic only needed in prod

    return get_settings()


def refresh_expectations(
    db: Session,
    company: Company,
    *,
    settings=None,
    transport=None,
) -> ExpectationsRefreshResult:
    """Distil this company's synced forum posts into investment-expectation
    claims and upsert them onto `ForumIntelligence.expectations`.

    No `anthropic_api_key` configured -> skip WITHOUT touching any existing
    `expectations` row (see module docstring) — status="skipped".

    Any other failure (DB error, unexpected exception) is caught and reported
    as status="error" rather than raised: forum expectations having a bad day
    must never fail `refresh_company` (mirrors `_discover_forum_topics` /
    `forum_distiller._distill_post`'s degrade-to-empty discipline).
    `distill_company_posts` itself already degrades per-post transport/parse
    failures internally, so a normal "ok" run with zero claims (nothing
    fact-bearing found) is a legitimate result, not an error.
    """
    resolved_settings = _resolve_settings(settings)
    api_key = getattr(resolved_settings, "anthropic_api_key", None)
    if not api_key:
        return ExpectationsRefreshResult(status="skipped", detail="brak klucza API")

    try:
        posts = db.scalars(
            select(ForumPost)
            .join(ForumTopic, ForumPost.topic_id == ForumTopic.id)
            .where(
                ForumTopic.company_id == company.id,
                ForumPost.content_text.is_not(None),
            )
        ).all()

        claims = forum_distiller.distill_company_posts(
            posts, settings=resolved_settings, transport=transport
        )

        model = (
            getattr(resolved_settings, "ai_distill_model", None)
            or getattr(resolved_settings, "anthropic_model", None)
            or forum_distiller._FALLBACK_MODEL
        )
        payload = {
            "claims": [claim.to_dict() for claim in claims],
            "model": model,
            "updated_at": utcnow().isoformat(),
            "source_post_count": len(posts),
        }

        record = db.scalar(
            select(ForumIntelligence).where(
                ForumIntelligence.company_id == company.id,
                ForumIntelligence.source == "portal_analiz",
            )
        )
        if record is None:
            record = ForumIntelligence(
                company_id=company.id, source="portal_analiz", expectations=payload
            )
            db.add(record)
        else:
            record.expectations = payload
        db.commit()
        return ExpectationsRefreshResult(status="ok", claim_count=len(claims))
    except Exception as exc:  # noqa: BLE001 — degrade contract, see docstring
        db.rollback()
        return ExpectationsRefreshResult(status="error", detail=str(exc))
