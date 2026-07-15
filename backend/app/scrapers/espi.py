"""GPW ESPI/EBI report ingestion for canonical Research cases.

Fetch GPW list pages politely, ingest Research-company reports idempotently,
and advance the durable completeness watermark only after a complete page walk.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable
from unicodedata import normalize as unicode_normalize
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    DocumentVersion,
    Event,
    EventReport,
    ListPollState,
    ResearchCase,
    utcnow,
)
from app.scrapers import http
from app.services.evidence import mark_parse_result, record_document_version

GPW_BASE_URL = "https://www.gpw.pl/"
GPW_REPORTS_URL = urljoin(GPW_BASE_URL, "espi-ebi-reports")
WARSAW_TZ = ZoneInfo("Europe/Warsaw")
SOURCE_KEY = "gpw-espi-ebi"
GPW_REPORTS_LIMIT = 15
GPW_REPORTS_HARD_PAGE_CAP = 5

LEGAL_SUFFIX_WORDS = {
    "sa",
    "s",
    "a",
    "spolka",
    "akcyjna",
    "plc",
    "nv",
    "n",
    "v",
    "se",
}


@dataclass(frozen=True)
class GpwReportSummary:
    report_id: str
    source: str
    report_type: str
    report_no: str
    published_at: datetime
    issuer_name: str
    isin: str | None
    title: str
    detail_url: str

    @property
    def external_id(self) -> str:
        return f"gpw:{self.report_id}"


@dataclass(frozen=True)
class GpwReportDetail:
    raw_text: str
    parsed: dict


@dataclass(frozen=True)
class GpwReportListPage:
    reports: list[GpwReportSummary]
    next_offset: int | None
    next_limit: int | None


class GpwReportParseError(ValueError):
    """GPW HTML shape is not the list/detail contract this scraper ingests."""


def gpw_report_list_params(*, offset: int, limit: int) -> list[tuple[str, str]]:
    """Observed GPW ESPI/EBI list request: GET query with repeated filters."""
    return [
        ("action", "GPWEspiReportUnion"),
        ("start", "ajaxSearch"),
        ("page", "espi-ebi-reports"),
        ("format", "html"),
        ("lang", "EN"),
        ("offset", str(offset)),
        ("limit", str(limit)),
        ("categoryRaports[]", "EBI"),
        ("categoryRaports[]", "ESPI"),
        ("typeRaports[]", "RB"),
        ("typeRaports[]", "P"),
        ("typeRaports[]", "Q"),
        ("typeRaports[]", "O"),
        ("typeRaports[]", "R"),
    ]


def fetch_report_list_page(
    *, offset: int = 0, limit: int = GPW_REPORTS_LIMIT
) -> GpwReportListPage:
    response = http.fetch(
        GPW_REPORTS_URL,
        params=gpw_report_list_params(offset=offset, limit=limit),
    )
    response.raise_for_status()
    return parse_report_list_page(response.text, request_offset=offset, request_limit=limit)


def fetch_report_detail(url: str) -> GpwReportDetail:
    response = http.fetch(url)
    response.raise_for_status()
    return parse_report_detail(response.text)


def parse_report_list(html: str) -> list[GpwReportSummary]:
    return parse_report_list_page(html).reports


def parse_report_list_page(
    html: str,
    *,
    request_offset: int = 0,
    request_limit: int = GPW_REPORTS_LIMIT,
) -> GpwReportListPage:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("ul#search-result")
    if container is None:
        raise GpwReportParseError("missing GPW search-result container")

    reports: list[GpwReportSummary] = []
    for index, item in enumerate(container.select(":scope > li"), start=1):
        date_el = item.select_one("span.date")
        issuer_link = item.select_one("strong.name a[href]")
        title_el = item.find("p")
        if date_el is None or issuer_link is None or title_el is None:
            raise GpwReportParseError(f"malformed GPW report row {index}")

        date_parts = [part.strip() for part in date_el.get_text(" ", strip=True).split("|")]
        if len(date_parts) != 4 or not all(date_parts):
            raise GpwReportParseError(f"malformed GPW row metadata {index}")
        try:
            published_at = datetime.strptime(date_parts[0], "%d-%m-%Y %H:%M:%S").replace(
                tzinfo=WARSAW_TZ
            )
        except ValueError as exc:
            raise GpwReportParseError(f"invalid GPW report date in row {index}") from exc
        source = date_parts[2].lower()
        if source not in {"espi", "ebi"}:
            raise GpwReportParseError(f"invalid GPW report source in row {index}")
        href = issuer_link.get("href") or ""
        report_id = _query_value(href, "geru_id")
        if not report_id or not report_id.isdigit():
            raise GpwReportParseError(f"invalid GPW report id in row {index}")
        issuer_name, isin = _parse_issuer(issuer_link.get_text(" ", strip=True))
        title = title_el.get_text(" ", strip=True)
        if not issuer_name or not title:
            raise GpwReportParseError(f"empty GPW issuer/title in row {index}")
        reports.append(
            GpwReportSummary(
                report_id=report_id,
                source=source,
                report_type=date_parts[1],
                report_no=date_parts[3],
                published_at=published_at,
                issuer_name=issuer_name,
                isin=isin,
                title=title,
                detail_url=urljoin(GPW_BASE_URL, href),
            )
        )
    if not reports:
        raise GpwReportParseError("empty GPW report list")
    next_offset, next_limit = _parse_next_page(
        soup,
        request_offset=request_offset,
        request_limit=request_limit,
    )
    return GpwReportListPage(
        reports=reports,
        next_offset=next_offset,
        next_limit=next_limit,
    )


def parse_report_detail(html: str) -> GpwReportDetail:
    soup = BeautifulSoup(html, "html.parser")
    report_data = soup.select_one(".report-data")
    if report_data is None:
        raise GpwReportParseError("missing GPW report-data container")
    raw_text = _clean_text(report_data.get_text("\n", strip=True))
    if not raw_text:
        raise GpwReportParseError("empty GPW report detail")
    body = _report_body_text(raw_text)
    if not body or _looks_like_detail_placeholder(body):
        raise GpwReportParseError("empty GPW report content")
    parsed = {
        "company": _label_value_any(raw_text, ["Firma", "Company"]),
        "date": _label_value_any(raw_text, ["Data", "Date"]),
        "subject": _find_after(raw_text, ["Temat", "Subject"]),
        "legal_basis": _find_after(raw_text, ["Podstawa prawna", "Legal basis"]),
    }
    if not parsed["company"] or not parsed["date"] or not parsed["subject"]:
        raise GpwReportParseError("missing GPW report detail metadata")
    return GpwReportDetail(raw_text=raw_text, parsed={k: v for k, v in parsed.items() if v})


def poll_research_reports(
    db: Session,
    *,
    ticker: str | None = None,
    fetch_details: bool = True,
) -> dict:
    global_poll = ticker is None
    metadata_only = not fetch_details
    companies = _researched_companies(db, ticker=ticker)
    if ticker is not None and not companies:
        return _poll_result(
            matched_count=0,
            new_count=0,
            rows=[],
            pages_fetched=0,
            previous_watermark=None,
            next_watermark=None,
            boundary_reached=False,
            cap_reached=False,
            complete=False,
            ok=False,
            metadata_only=metadata_only,
            incomplete_reason="unknown_ticker",
        )
    if global_poll and not companies:
        return _poll_result(
            matched_count=0,
            new_count=0,
            rows=[],
            pages_fetched=0,
            previous_watermark=None,
            next_watermark=None,
            boundary_reached=False,
            cap_reached=False,
            complete=False,
            ok=False,
            metadata_only=metadata_only,
            incomplete_reason="empty_research",
        )

    poll_started_at = utcnow()
    state = None
    previous_watermark = None
    scan_started_at = None
    scan_target_at = None
    offset = 0
    limit = GPW_REPORTS_LIMIT
    if global_poll and not metadata_only:
        state = _poll_state(db, create=True)
        previous_watermark = _aware_utc(state.last_polled_at)
        if _scan_in_progress(state):
            scan_started_at = _aware_utc(state.scan_started_at) or poll_started_at
            scan_target_at = _aware_utc(state.scan_target_at)
            offset = state.scan_next_offset if state.scan_next_offset is not None else 0
            limit = state.scan_next_limit or GPW_REPORTS_LIMIT
        else:
            scan_started_at = poll_started_at
            scan_target_at = previous_watermark or _bootstrap_research_watermark(
                db,
                fallback=poll_started_at,
            )
            state.scan_started_at = scan_started_at
            state.scan_target_at = scan_target_at
            state.scan_next_offset = 0
            state.scan_next_limit = GPW_REPORTS_LIMIT

    rows = []
    new_count = 0
    matched_count = 0
    pages_fetched = 0
    boundary_reached = False
    cap_reached = False
    seen_report_keys: set[tuple[str, str]] = set()
    last_seen_published_at: datetime | None = None

    while True:
        current_offset = offset
        current_limit = limit
        try:
            page = fetch_report_list_page(offset=current_offset, limit=current_limit)
            last_seen_published_at = _validate_report_page(
                page,
                request_offset=current_offset,
                request_limit=current_limit,
                previous_published_at=last_seen_published_at,
            )
        except Exception as exc:  # noqa: BLE001 - surface scraper failures as metadata.
            db.commit()
            return _poll_result(
                matched_count=matched_count,
                new_count=new_count,
                rows=rows,
                pages_fetched=pages_fetched,
                previous_watermark=previous_watermark,
                next_watermark=previous_watermark,
                boundary_reached=boundary_reached,
                cap_reached=cap_reached,
                complete=False,
                ok=False,
                metadata_only=metadata_only,
                incomplete_reason=f"list_page_error: {exc}",
                scan_started_at=scan_started_at,
                scan_target_at=scan_target_at,
                continuation_offset=offset,
                continuation_limit=limit,
            )

        pages_fetched += 1
        page_reached_boundary = scan_target_at is not None and any(
            _aware_utc(summary.published_at) <= scan_target_at
            for summary in page.reports
        )
        if page_reached_boundary:
            boundary_reached = True

        for summary in page.reports:
            if (
                global_poll
                and scan_started_at is not None
                and _aware_utc(summary.published_at) > scan_started_at
            ):
                # GPW is append-only by publish time: rows newer than this scan's
                # stable start belong to the next scan, while offset overlap makes
                # older rows idempotently drainable even if fresh rows appear in front.
                continue
            report_key = (summary.source, summary.external_id)
            if report_key in seen_report_keys:
                continue
            seen_report_keys.add(report_key)

            company = _matching_company(summary.issuer_name, companies)
            if company is None:
                continue
            matched_count += 1

            existing = db.scalar(
                select(EventReport).where(
                    EventReport.source == summary.source,
                    EventReport.external_id == summary.external_id,
                )
            )
            detail = None
            needs_detail = (
                existing is None or not (existing.raw_text or "").strip()
            )
            if needs_detail and not fetch_details:
                pass
            elif needs_detail:
                try:
                    detail = fetch_report_detail(summary.detail_url)
                except Exception as exc:  # noqa: BLE001
                    db.commit()
                    return _poll_result(
                        matched_count=matched_count,
                        new_count=new_count,
                        rows=rows,
                        pages_fetched=pages_fetched,
                        previous_watermark=previous_watermark,
                        next_watermark=previous_watermark,
                        boundary_reached=boundary_reached,
                        cap_reached=cap_reached,
                        complete=False,
                        ok=False,
                        metadata_only=metadata_only,
                        incomplete_reason=f"detail_error: {exc}",
                        scan_started_at=scan_started_at,
                        scan_target_at=scan_target_at,
                        continuation_offset=offset,
                        continuation_limit=limit,
                    )

            report, created = _upsert_event_report(db, company, summary, detail)
            if created:
                new_count += 1
            rows.append(
                {
                    "ticker": company.ticker,
                    "event_report_id": report.id,
                    "source": report.source,
                    "external_id": report.external_id,
                    "title": report.title,
                    "status": "new" if created else "updated",
                }
            )

        archive_end_reached = page.next_offset is None
        if boundary_reached or archive_end_reached:
            if metadata_only:
                db.commit()
                return _poll_result(
                    matched_count=matched_count,
                    new_count=new_count,
                    rows=rows,
                    pages_fetched=pages_fetched,
                    previous_watermark=previous_watermark,
                    next_watermark=previous_watermark,
                    boundary_reached=boundary_reached,
                    archive_end_reached=archive_end_reached,
                    cap_reached=False,
                    complete=False,
                    ok=False,
                    metadata_only=True,
                    incomplete_reason="details_skipped_metadata_only",
                    scan_started_at=scan_started_at,
                    scan_target_at=scan_target_at,
                    continuation_offset=None,
                    continuation_limit=None,
                )
            if global_poll and state is not None:
                _complete_global_scan(state, scan_started_at or poll_started_at)
            next_watermark = (
                state.last_polled_at if global_poll and state is not None else None
            )
            db.commit()
            return _poll_result(
                matched_count=matched_count,
                new_count=new_count,
                rows=rows,
                pages_fetched=pages_fetched,
                previous_watermark=previous_watermark,
                next_watermark=next_watermark,
                boundary_reached=boundary_reached,
                archive_end_reached=archive_end_reached,
                cap_reached=False,
                complete=True,
                ok=True,
                metadata_only=metadata_only,
                incomplete_reason=None,
                scan_started_at=scan_started_at,
                scan_target_at=scan_target_at,
                continuation_offset=None,
                continuation_limit=None,
            )

        if global_poll and state is not None and not metadata_only:
            state.scan_started_at = scan_started_at
            state.scan_target_at = scan_target_at
            state.scan_next_offset = page.next_offset
            state.scan_next_limit = page.next_limit or current_limit

        if pages_fetched >= GPW_REPORTS_HARD_PAGE_CAP:
            cap_reached = True
            db.commit()
            return _poll_result(
                matched_count=matched_count,
                new_count=new_count,
                rows=rows,
                pages_fetched=pages_fetched,
                previous_watermark=previous_watermark,
                next_watermark=previous_watermark,
                boundary_reached=False,
                cap_reached=True,
                complete=False,
                ok=False,
                metadata_only=metadata_only,
                incomplete_reason="hard_page_cap_reached_before_watermark",
                scan_started_at=scan_started_at,
                scan_target_at=scan_target_at,
                continuation_offset=page.next_offset,
                continuation_limit=page.next_limit or current_limit,
            )

        db.commit()
        offset = page.next_offset
        limit = page.next_limit or current_limit


def _poll_result(
    *,
    matched_count: int,
    new_count: int,
    rows: list[dict],
    pages_fetched: int,
    previous_watermark: datetime | None,
    next_watermark: datetime | None,
    boundary_reached: bool,
    cap_reached: bool,
    complete: bool,
    ok: bool,
    metadata_only: bool,
    incomplete_reason: str | None,
    archive_end_reached: bool = False,
    scan_started_at: datetime | None = None,
    scan_target_at: datetime | None = None,
    continuation_offset: int | None = None,
    continuation_limit: int | None = None,
) -> dict:
    source_status = "ok" if complete and ok else "incomplete"
    retry_later = bool(
        incomplete_reason
        and (
            "HTTP 5" in incomplete_reason
            or "Giving up on" in incomplete_reason
            or "network error" in incomplete_reason
        )
    )
    if retry_later:
        source_status = "temporarily_unavailable"
    return {
        "ok": ok,
        "capability_id": "espi-source-ingestion-v1",
        "source": SOURCE_KEY,
        "capability": "live-ingestion",
        "matched": matched_count,
        "new": new_count,
        "reports": rows,
        "pages_fetched": pages_fetched,
        "previous_watermark": _iso_or_none(previous_watermark),
        "next_watermark": _iso_or_none(next_watermark),
        "boundary_reached": boundary_reached,
        "archive_end_reached": archive_end_reached,
        "cap_reached": cap_reached,
        "complete": complete,
        "metadata_only": metadata_only,
        "incomplete_reason": incomplete_reason,
        "source_status": source_status,
        "retry_later": retry_later,
        "scan_started_at": _iso_or_none(scan_started_at),
        "scan_target_at": _iso_or_none(scan_target_at),
        "continuation_offset": continuation_offset,
        "continuation_limit": continuation_limit,
    }


def _poll_state(db: Session, *, create: bool) -> ListPollState | None:
    state = db.scalar(
        select(ListPollState).where(ListPollState.source_key == SOURCE_KEY)
    )
    if state is None and create:
        state = ListPollState(source_key=SOURCE_KEY, last_polled_at=None)
        db.add(state)
        db.flush()
    return state


def _scan_in_progress(state: ListPollState) -> bool:
    return (
        state.scan_started_at is not None
        or state.scan_target_at is not None
        or state.scan_next_offset is not None
        or state.scan_next_limit is not None
    )


def _bootstrap_research_watermark(db: Session, *, fallback: datetime) -> datetime:
    created_at = db.scalar(
        select(ResearchCase.created_at).order_by(ResearchCase.created_at).limit(1)
    )
    target = _aware_utc(created_at) or _aware_utc(fallback)
    fallback_utc = _aware_utc(fallback)
    if target is not None and fallback_utc is not None and target > fallback_utc:
        return fallback_utc
    return target or fallback


def _complete_global_scan(state: ListPollState, next_watermark: datetime) -> None:
    state.last_polled_at = next_watermark
    state.scan_started_at = None
    state.scan_target_at = None
    state.scan_next_offset = None
    state.scan_next_limit = None


def _validate_report_page(
    page: GpwReportListPage,
    *,
    request_offset: int,
    request_limit: int,
    previous_published_at: datetime | None,
) -> datetime:
    if not page.reports:
        raise GpwReportParseError("empty GPW report list")

    last = previous_published_at
    for summary in page.reports:
        published_at = _aware_utc(summary.published_at)
        if last is not None and published_at is not None and published_at > last:
            raise GpwReportParseError("GPW report timestamps are not descending")
        last = published_at

    if page.next_offset is None:
        if page.next_limit is not None:
            raise GpwReportParseError("invalid GPW pager limit without offset")
        return last or _aware_utc(page.reports[-1].published_at)

    if page.next_offset <= request_offset:
        raise GpwReportParseError("GPW pager cursor is not forward")
    expected_offset = request_offset + request_limit
    if page.next_offset != expected_offset:
        raise GpwReportParseError("GPW pager cursor is not continuous")
    if page.next_limit is None or page.next_limit <= 0:
        raise GpwReportParseError("invalid GPW pager limit")
    return last or _aware_utc(page.reports[-1].published_at)


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _upsert_event_report(
    db: Session,
    company: Company,
    summary: GpwReportSummary,
    detail: GpwReportDetail | None,
) -> tuple[EventReport, bool]:
    existing = db.scalar(
        select(EventReport).where(
            EventReport.source == summary.source,
            EventReport.external_id == summary.external_id,
        )
    )
    parsed = _merged_parsed(existing.parsed if existing else None, summary, detail)
    if existing is None:
        report = EventReport(
            company_id=company.id,
            source=summary.source,
            external_id=summary.external_id,
            raw_url=summary.detail_url,
            published_at=summary.published_at,
            title=summary.title,
            raw_text=detail.raw_text if detail else None,
            parsed=parsed,
            materiality={
                "level": "unreviewed",
                "reason": (
                    "Source report ingested; Codex verifier has not triaged "
                    "materiality."
                ),
            },
        )
        db.add(report)
        db.flush()
        _ensure_evidence_event(db, company, summary, report)
        return report, True

    existing.company_id = company.id
    existing.raw_url = summary.detail_url
    existing.published_at = summary.published_at
    existing.title = summary.title
    if detail is not None and not (existing.raw_text or "").strip():
        existing.raw_text = detail.raw_text
    existing.parsed = parsed
    _ensure_evidence_event(db, company, summary, existing)
    return existing, False


def _ensure_evidence_event(
    db: Session,
    company: Company,
    summary: GpwReportSummary,
    report: EventReport,
) -> None:
    """Link a stored ESPI detail to the immutable evidence/event ledger."""
    raw_text = (report.raw_text or "").strip()
    if not raw_text:
        # Metadata-only polling deliberately does not create a false evidence
        # document; the next detail-enabled poll will complete the bridge.
        return

    parsed = dict(report.parsed or {})
    version_id = parsed.get("evidence_source_version_id")
    version = db.get(DocumentVersion, version_id) if version_id else None
    if version is None:
        recorded = record_document_version(
            db,
            company,
            source_name="GPW",
            source_type="espi_ebi",
            scope_key=summary.external_id,
            requested_url=summary.detail_url,
            effective_url=summary.detail_url,
            content=raw_text.encode("utf-8"),
            text=raw_text,
            response_status=200,
            mime_type="text/plain",
            parser_version="gpw-espi-detail@1",
        )
        version = recorded.version
        mark_parse_result(version, success=True)
        parsed["evidence_source_version_id"] = version.id
        report.parsed = parsed

    event = db.scalar(
        select(Event).where(
            Event.source_version_id == version.id,
            Event.event_type == "espi_ebi_report",
        )
    )
    if event is not None:
        return

    detail = parsed.get("detail") if isinstance(parsed.get("detail"), dict) else {}
    claims = [
        {
            "claim_id": "report_metadata",
            "text": summary.title,
            "source_version_id": version.id,
            "locator": {"section": "report-metadata", "field": "title"},
            "verification_state": "unverified",
        },
        {
            "claim_id": "report_subject",
            "text": detail.get("subject") or summary.title,
            "source_version_id": version.id,
            "locator": {"section": "report-data", "field": "subject"},
            "verification_state": "unverified",
        },
    ]
    db.add(
        Event(
            company_id=company.id,
            company_ticker=company.ticker,
            source_version_id=version.id,
            event_type="espi_ebi_report",
            title=summary.title,
            published_at=summary.published_at,
            known_at=version.fetched_at,
            claims=claims,
            verification_state="unverified",
        )
    )


def _merged_parsed(
    current: dict | None,
    summary: GpwReportSummary,
    detail: GpwReportDetail | None,
) -> dict:
    parsed = dict(current or {})
    summary_fields = {
        "gpw_id": summary.report_id,
        "report_no": summary.report_no,
        "report_type": summary.report_type,
        "issuer_name": summary.issuer_name,
        "isin": summary.isin,
        "source_title": summary.title,
    }
    for key, value in summary_fields.items():
        if key not in parsed or parsed[key] in (None, ""):
            parsed[key] = value
    if detail is not None and "detail" not in parsed:
        parsed["detail"] = detail.parsed
    return parsed


def _researched_companies(db: Session, *, ticker: str | None) -> list[Company]:
    stmt = select(Company)
    if ticker:
        stmt = stmt.where(Company.ticker == ticker.upper())
    else:
        stmt = stmt.join(ResearchCase, ResearchCase.company_id == Company.id).where(
            ResearchCase.state != "closed"
        )
    return list(db.scalars(stmt.order_by(Company.ticker).distinct()))


def _matching_company(issuer_name: str, companies: Iterable[Company]) -> Company | None:
    issuer_key = _name_key(issuer_name)
    for company in companies:
        candidates = [company.name or "", company.ticker]
        for candidate in candidates:
            candidate_key = _name_key(candidate)
            if candidate_key and (
                candidate_key in issuer_key or issuer_key in candidate_key
            ):
                return company
    return None


def _name_key(value: str) -> str:
    ascii_text = unicode_normalize("NFKD", value).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_text.casefold())
    return " ".join(word for word in words if word not in LEGAL_SUFFIX_WORDS)


def _query_value(url: str, key: str) -> str | None:
    values = parse_qs(urlparse(url).query).get(key)
    return values[0] if values else None


def _parse_issuer(value: str) -> tuple[str, str | None]:
    match = re.search(r"\(([^()]+)\)\s*$", value)
    if match:
        return value[: match.start()].strip(), match.group(1).strip()
    return value.strip(), None


def _parse_next_page(
    soup: BeautifulSoup,
    *,
    request_offset: int,
    request_limit: int,
) -> tuple[int | None, int | None]:
    pager_candidates = soup.select(
        "a.more, a[data-type='pager'], a[data-offset], a[data-limit]"
    )
    pager = None
    for candidate in pager_candidates:
        if (
            candidate.get("data-type") == "pager"
            or candidate.has_attr("data-offset")
            or candidate.has_attr("data-limit")
        ):
            pager = candidate
            break
    if pager is None:
        return None, None
    if not pager.has_attr("data-offset") or not pager.has_attr("data-limit"):
        raise GpwReportParseError("malformed GPW pager")
    try:
        offset = int(pager.get("data-offset") or "")
    except ValueError as exc:
        raise GpwReportParseError("invalid GPW pager offset") from exc
    try:
        limit = int(pager.get("data-limit") or "")
    except ValueError as exc:
        raise GpwReportParseError("invalid GPW pager limit") from exc
    if offset <= request_offset:
        raise GpwReportParseError("GPW pager cursor is not forward")
    if offset != request_offset + request_limit:
        raise GpwReportParseError("GPW pager cursor is not continuous")
    if limit <= 0:
        raise GpwReportParseError("invalid GPW pager limit")
    return offset, limit


def _clean_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _label_value(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}:\s*(.+)", text)
    return match.group(1).strip() if match else None


def _label_value_any(text: str, labels: list[str]) -> str | None:
    for label in labels:
        value = _label_value(text, label)
        if value:
            return value
    return None


def _report_body_text(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        before, separator, after = line.partition(":")
        label = before.casefold().strip()
        if label in {"treść raportu", "tresc raportu", "report content", "report body"}:
            body_parts = []
            if separator and after.strip():
                body_parts.append(after.strip())
            body_parts.extend(lines[index + 1 :])
            body = "\n".join(body_parts).strip()
            return body or None
    return None


def _looks_like_detail_placeholder(body: str) -> bool:
    normalized = re.sub(r"\s+", " ", body).strip().casefold()
    if len(re.findall(r"[a-ząćęłńóśźż]", normalized)) < 20:
        return True
    placeholders = (
        "service temporarily unavailable",
        "temporarily unavailable",
        "try again later",
        "access denied",
    )
    return any(marker in normalized for marker in placeholders)


def _find_after(text: str, labels: list[str]) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if any(line.casefold() == label.casefold() for label in labels):
            for candidate in lines[index + 1 : index + 4]:
                if candidate and not any(
                    candidate.casefold() == label.casefold() for label in labels
                ):
                    return candidate
    return None
