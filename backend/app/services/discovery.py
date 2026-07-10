"""Low-request market discovery: one BR universe pull, then local triage."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentVersion, SourceDocument
from app.scrapers import biznesradar
from app.services import evidence
from app.services.refresh import _get_page

DISCOVERY_URL = f"{biznesradar.BASE_URL}/spolki-rating/akcje_gpw"
MARKET_KEY = "__GPW__"
PARSER_VERSION = "biznesradar-market-rating@1"


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[biznesradar.MarketCandidate]
    fetched_at: datetime
    source_url: str
    source_note: str


def _latest_parsed_version(db: Session) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(
            SourceDocument.company_ticker == MARKET_KEY,
            SourceDocument.source_type == "market_rating",
            DocumentVersion.parse_status == "parsed",
        )
        .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
        .limit(1)
    )


def discover_candidates(db: Session, *, force: bool = False) -> DiscoveryResult:
    """Return the cached BR universe, fetching at most one page when stale."""
    page = _get_page(db, DISCOVERY_URL, force)
    version: DocumentVersion | None = None
    if page is not None:
        recorded = evidence.record_market_document_version(
            db,
            market_key=MARKET_KEY,
            source_name="biznesradar",
            source_type="market_rating",
            scope_key="akcje_gpw",
            requested_url=page.requested_url,
            effective_url=page.effective_url,
            content=page.content,
            text=page.text,
            response_status=page.status_code,
            mime_type=page.mime_type,
            parser_version=PARSER_VERSION,
            fetched_at=page.fetched_at,
        )
        version = recorded.version
        page.fetch_log.document_version_id = version.id
        try:
            biznesradar.parse_market_rating(version.raw_content)
        except Exception as exc:
            evidence.mark_parse_result(version, success=False, error=str(exc))
            db.commit()  # preserve the failed raw response for diagnosis
            raise
        evidence.mark_parse_result(version, success=True)
        db.commit()
    else:
        version = _latest_parsed_version(db)

    if version is None:
        # A fresh fetch-log row may predate the evidence ledger.  Bypass that
        # one cache decision so the page becomes reproducible evidence.
        page = _get_page(db, DISCOVERY_URL, True)
        assert page is not None
        recorded = evidence.record_market_document_version(
            db,
            market_key=MARKET_KEY,
            source_name="biznesradar",
            source_type="market_rating",
            scope_key="akcje_gpw",
            requested_url=page.requested_url,
            effective_url=page.effective_url,
            content=page.content,
            text=page.text,
            response_status=page.status_code,
            mime_type=page.mime_type,
            parser_version=PARSER_VERSION,
            fetched_at=page.fetched_at,
        )
        version = recorded.version
        page.fetch_log.document_version_id = version.id
        try:
            biznesradar.parse_market_rating(version.raw_content)
        except Exception as exc:
            evidence.mark_parse_result(version, success=False, error=str(exc))
            db.commit()
            raise
        evidence.mark_parse_result(version, success=True)
        db.commit()

    candidates = biznesradar.parse_market_rating(version.raw_content)
    return DiscoveryResult(
        candidates=candidates,
        fetched_at=(
            version.fetched_at.replace(tzinfo=timezone.utc)
            if version.fetched_at.tzinfo is None
            else version.fetched_at
        ),
        source_url=version.effective_url,
        source_note=(
            "Rating kondycji BiznesRadar (Altman EM-Score) i Piotroski F-Score "
            "służą wyłącznie do wstępnej selekcji. Dopasowanie do strategii "
            "powstaje dopiero po zbudowaniu dossier."
        ),
    )
