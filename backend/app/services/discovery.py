"""Low-request market discovery: one stored BiznesRadar universe snapshot."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import DocumentVersion, FetchLog, SourceDocument
from app.scrapers import biznesradar
from app.services import evidence
from app.services.refresh import _get_page

DISCOVERY_URL = f"{biznesradar.BASE_URL}/spolki-rating/akcje_gpw"
MARKET_KEY = "__GPW__"
PARSER_VERSION = "biznesradar-market-rating@3"
_CONTINUITY_MIN_UNIVERSE = 100
_MAX_UNIVERSE_DROP_RATIO = 0.30
_MIN_INITIAL_UNIVERSE = 5
_MIN_TICKER_OVERLAP_RATIO = 0.70


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[biznesradar.MarketCandidate]
    fetched_at: datetime
    source_url: str
    source_note: str
    source_version_id: int
    source_version_created: bool
    parser_version: str
    content_version_at: datetime
    last_successful_source_check_at: datetime
    last_failed_refresh_at: datetime | None
    last_failed_refresh_reason: str | None


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


def _latest_version(db: Session) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(
            SourceDocument.company_ticker == MARKET_KEY,
            SourceDocument.source_type == "market_rating",
        )
        .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
        .limit(1)
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _last_successful_source_check(db: Session, version: DocumentVersion) -> datetime:
    """Latest 200 check whose stored document is still a parsed snapshot."""
    checked_at = db.scalar(
        select(FetchLog.fetched_at)
        .join(DocumentVersion, FetchLog.document_version_id == DocumentVersion.id)
        .where(
            FetchLog.url == DISCOVERY_URL,
            FetchLog.status == 200,
            DocumentVersion.parse_status == "parsed",
        )
        .order_by(FetchLog.fetched_at.desc(), FetchLog.id.desc())
        .limit(1)
    )
    return _as_utc(checked_at) if checked_at is not None else _as_utc(version.fetched_at)


def _last_failed_refresh(db: Session) -> tuple[datetime | None, str | None]:
    failed_fetch = db.execute(
        select(FetchLog.fetched_at, FetchLog.status)
        .where(
            FetchLog.url == DISCOVERY_URL,
            or_(FetchLog.status.is_(None), FetchLog.status != 200),
        )
        .order_by(FetchLog.fetched_at.desc(), FetchLog.id.desc())
        .limit(1)
    ).first()
    failed_parse = db.execute(
        select(DocumentVersion.fetched_at, DocumentVersion.parse_error)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(
            SourceDocument.company_ticker == MARKET_KEY,
            SourceDocument.source_type == "market_rating",
            DocumentVersion.parse_status == "failed",
        )
        .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
        .limit(1)
    ).first()
    options: list[tuple[datetime, str]] = []
    if failed_fetch is not None:
        at, status = failed_fetch
        options.append((_as_utc(at), "Błąd sieci" if status is None else f"HTTP {status}"))
    if failed_parse is not None:
        at, error = failed_parse
        options.append((_as_utc(at), f"Nie rozpoznano źródła: {error or 'błąd parsera'}"))
    return max(options, default=(None, None), key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc))


def _validate_universe_continuity(
    db: Session,
    version: DocumentVersion,
    candidates: list[biznesradar.MarketCandidate],
    *,
    enforce_initial_minimum: bool = False,
) -> None:
    """Reject a drastic drop from the last known-good market-wide universe."""
    previous_versions = db.scalars(
        select(DocumentVersion)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(
            SourceDocument.company_ticker == MARKET_KEY,
            SourceDocument.source_type == "market_rating",
            DocumentVersion.parse_status == "parsed",
            DocumentVersion.id != version.id,
        )
        .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
    )
    previous = next(iter(previous_versions), None)
    if previous is None:
        if enforce_initial_minimum and len(candidates) < _MIN_INITIAL_UNIVERSE:
            raise biznesradar.ParseError(
                "Market-rating universe has only "
                f"{len(candidates)} rows (minimum {_MIN_INITIAL_UNIVERSE})."
            )
        return
    previous_candidates = biznesradar.parse_market_rating(previous.raw_content)
    previous_count = len(previous_candidates)
    if previous_count < _CONTINUITY_MIN_UNIVERSE:
        return
    minimum_count = int(previous_count * (1 - _MAX_UNIVERSE_DROP_RATIO))
    if len(candidates) < minimum_count:
        raise biznesradar.ParseError(
            "Market-rating universe dropped from "
            f"{previous_count} to {len(candidates)} rows (minimum {minimum_count})."
        )
    previous_tickers = {candidate.ticker for candidate in previous_candidates}
    overlap = len(previous_tickers.intersection(candidate.ticker for candidate in candidates))
    minimum_overlap = int(previous_count * _MIN_TICKER_OVERLAP_RATIO)
    if overlap < minimum_overlap:
        raise biznesradar.ParseError(
            "Market-rating universe retains only "
            f"{overlap}/{previous_count} prior tickers (minimum {minimum_overlap})."
        )


def _result_from_version(
    db: Session, version: DocumentVersion, *, source_version_created: bool
) -> DiscoveryResult:
    failed_at, failed_reason = _last_failed_refresh(db)
    return DiscoveryResult(
        candidates=biznesradar.parse_market_rating(version.raw_content),
        fetched_at=_as_utc(version.fetched_at),
        source_url=version.effective_url,
        source_version_id=version.id,
        source_version_created=source_version_created,
        parser_version=version.parser_version,
        content_version_at=_as_utc(version.fetched_at),
        last_successful_source_check_at=_last_successful_source_check(db, version),
        last_failed_refresh_at=failed_at,
        last_failed_refresh_reason=failed_reason,
        source_note=(
            "Rating kondycji BiznesRadar (Altman EM-Score) i Piotroski F-Score "
            "służą wyłącznie do wstępnej selekcji. Dopasowanie do strategii "
            "powstaje dopiero po zbudowaniu dossier."
        ),
    )


def stored_discovery_candidates(db: Session) -> DiscoveryResult | None:
    """Read the latest successful snapshot without fetching or mutating state."""
    version = _latest_parsed_version(db)
    return (
        _result_from_version(db, version, source_version_created=False)
        if version is not None
        else None
    )


def discover_candidates(db: Session, *, force: bool = False) -> DiscoveryResult:
    """Return the cached BR universe, fetching at most one page when stale."""
    page = _get_page(db, DISCOVERY_URL, force)
    version: DocumentVersion | None = None
    version_created = False
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
        version_created = recorded.version_created
        page.fetch_log.document_version_id = version.id
        try:
            parsed = biznesradar.parse_market_rating(version.raw_content)
            _validate_universe_continuity(
                db, version, parsed, enforce_initial_minimum=True
            )
        except Exception as exc:
            evidence.mark_parse_result(version, success=False, error=str(exc))
            db.commit()  # preserve the failed raw response for diagnosis
            raise
        evidence.mark_parse_result(version, success=True)
        db.commit()
    else:
        # A parser upgrade can make the newest cached immutable page usable
        # without another source request. Re-parse it before falling back to
        # the older successful snapshot or forcing a fetch.
        version = _latest_version(db)
        if version is not None:
            try:
                parsed = biznesradar.parse_market_rating(version.raw_content)
                _validate_universe_continuity(db, version, parsed)
            except Exception:
                version = _latest_parsed_version(db)
            else:
                evidence.mark_parse_result(version, success=True)
                db.commit()

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
        version_created = recorded.version_created
        page.fetch_log.document_version_id = version.id
        try:
            parsed = biznesradar.parse_market_rating(version.raw_content)
            _validate_universe_continuity(
                db, version, parsed, enforce_initial_minimum=True
            )
        except Exception as exc:
            evidence.mark_parse_result(version, success=False, error=str(exc))
            db.commit()
            raise
        evidence.mark_parse_result(version, success=True)
        db.commit()

    return _result_from_version(db, version, source_version_created=version_created)
