"""GPW ESPI/EBI report ingestion.

First CX.6 slice: parse the server-rendered first page from GPW and fetch report
details only for watchlist companies matched by issuer name. Pagination and
advanced materiality triage stay out of the scraper.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Iterable
from unicodedata import normalize as unicode_normalize
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, EventReport, WatchlistItem
from app.scrapers import http

GPW_BASE_URL = "https://www.gpw.pl/"
GPW_REPORTS_URL = urljoin(GPW_BASE_URL, "espi-ebi-reports")
WARSAW_TZ = ZoneInfo("Europe/Warsaw")

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


def fetch_latest_reports() -> list[GpwReportSummary]:
    response = http.fetch(GPW_REPORTS_URL)
    response.raise_for_status()
    return parse_report_list(response.text)


def fetch_report_detail(url: str) -> GpwReportDetail:
    response = http.fetch(url)
    response.raise_for_status()
    return parse_report_detail(response.text)


def parse_report_list(html: str) -> list[GpwReportSummary]:
    soup = BeautifulSoup(html, "html.parser")
    reports: list[GpwReportSummary] = []
    for item in soup.select("ul#search-result > li"):
        date_el = item.select_one("span.date")
        issuer_link = item.select_one("strong.name a[href]")
        title_el = item.find("p")
        if date_el is None or issuer_link is None or title_el is None:
            continue

        date_parts = [part.strip() for part in date_el.get_text(" ", strip=True).split("|")]
        if len(date_parts) < 4:
            continue
        published_at = datetime.strptime(date_parts[0], "%d-%m-%Y %H:%M:%S").replace(
            tzinfo=WARSAW_TZ
        )
        source = date_parts[2].lower()
        href = issuer_link.get("href") or ""
        report_id = _query_value(href, "geru_id")
        if not report_id:
            continue
        issuer_name, isin = _parse_issuer(issuer_link.get_text(" ", strip=True))
        reports.append(
            GpwReportSummary(
                report_id=report_id,
                source=source,
                report_type=date_parts[1],
                report_no=date_parts[3],
                published_at=published_at,
                issuer_name=issuer_name,
                isin=isin,
                title=title_el.get_text(" ", strip=True),
                detail_url=urljoin(GPW_BASE_URL, href),
            )
        )
    return reports


def parse_report_detail(html: str) -> GpwReportDetail:
    soup = BeautifulSoup(html, "html.parser")
    report_data = soup.select_one(".report-data")
    source = report_data or soup
    raw_text = _clean_text(source.get_text("\n", strip=True))
    parsed = {
        "company": _label_value(raw_text, "Firma"),
        "date": _label_value(raw_text, "Data"),
        "subject": _find_after(raw_text, ["Temat", "Subject"]),
        "legal_basis": _find_after(raw_text, ["Podstawa prawna", "Legal basis"]),
    }
    return GpwReportDetail(raw_text=raw_text, parsed={k: v for k, v in parsed.items() if v})


def poll_watchlist_reports(
    db: Session,
    *,
    ticker: str | None = None,
    fetch_details: bool = True,
) -> dict:
    companies = _watched_companies(db, ticker=ticker)
    summaries = fetch_latest_reports()
    rows = []
    new_count = 0
    matched_count = 0
    for summary in summaries:
        company = _matching_company(summary.issuer_name, companies)
        if company is None:
            continue
        matched_count += 1
        detail = fetch_report_detail(summary.detail_url) if fetch_details else None
        existing = db.scalar(
            select(EventReport).where(
                EventReport.source == summary.source,
                EventReport.external_id == summary.external_id,
            )
        )
        parsed = {
            "gpw_id": summary.report_id,
            "report_no": summary.report_no,
            "report_type": summary.report_type,
            "issuer_name": summary.issuer_name,
            "isin": summary.isin,
            "source_title": summary.title,
        }
        if detail is not None:
            parsed["detail"] = detail.parsed
        materiality = {
            "level": "unreviewed",
            "reason": "Source report ingested; Codex verifier has not triaged materiality.",
        }
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
                materiality=materiality,
            )
            db.add(report)
            db.flush()
            new_count += 1
        else:
            report = existing
            report.company_id = company.id
            report.raw_url = summary.detail_url
            report.published_at = summary.published_at
            report.title = summary.title
            if detail is not None:
                report.raw_text = detail.raw_text
            report.parsed = parsed
            report.materiality = materiality
        rows.append(
            {
                "ticker": company.ticker,
                "event_report_id": report.id,
                "source": report.source,
                "external_id": report.external_id,
                "title": report.title,
                "status": "new" if existing is None else "updated",
            }
        )
    db.commit()
    return {
        "ok": True,
        "workflow": "stock-pre-session-brief",
        "source": "gpw-espi-ebi",
        "capability": "live-ingestion",
        "matched": matched_count,
        "new": new_count,
        "reports": rows,
    }


def _watched_companies(db: Session, *, ticker: str | None) -> list[Company]:
    stmt = select(Company)
    if ticker:
        stmt = stmt.where(Company.ticker == ticker.upper())
    else:
        stmt = stmt.join(WatchlistItem, WatchlistItem.company_id == Company.id)
    return list(db.scalars(stmt.order_by(Company.ticker)))


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


def _clean_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _label_value(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}:\s*(.+)", text)
    return match.group(1).strip() if match else None


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
