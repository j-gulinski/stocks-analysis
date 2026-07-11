"""Polite issuer-IR index ingestion for the bounded RT2.3 pilot."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Company, Fact, FetchLog, SourceDocument
from app.scrapers import http
from app.services.evidence import (
    mark_parse_result,
    record_document_version,
    record_text_fact,
)

PARSER_VERSION = "issuer-ir-index@2"
EXTRACTOR_VERSION = "issuer-ir-links@2"
MAX_LINKS_PER_INDEX = 30

ISSUER_IR_SOURCES = {
    "SNT": "https://synektik.com.pl/centrum-inwestora/raporty-biezace/",
    "ABS": "https://assecobs.pl/inwestor/raporty-biezace/",
    "OPM": "https://opteam.pl/firma/relacje-inwestorskie",
}

REPORT_TERMS = re.compile(
    r"raport|sprawozd|wynik|prezentac|walne|akcjon|dywidend|governance|ład korpor",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IssuerIrLink:
    title: str
    url: str
    kind: str
    locator: dict


@dataclass(frozen=True)
class ParsedIssuerIrIndex:
    title: str
    links: list[IssuerIrLink]


def parse_issuer_ir_index(html: str, *, base_url: str) -> ParsedIssuerIrIndex:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("main") or soup.body or soup
    page_title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    if not page_title:
        heading = root.find(["h1", "h2"])
        page_title = _clean_text(heading.get_text(" ", strip=True) if heading else "Relacje inwestorskie")

    links: list[IssuerIrLink] = []
    seen: set[str] = set()
    source_host = urlparse(base_url).netloc.removeprefix("www.")
    for position, anchor in enumerate(root.find_all("a", href=True)):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        direct = _clean_text(anchor.get_text(" ", strip=True))
        heading = anchor.find_previous(["h1", "h2", "h3", "h4"])
        heading_text = _clean_text(heading.get_text(" ", strip=True) if heading else "")
        parent_text = _clean_text(anchor.parent.get_text(" ", strip=True) if anchor.parent else "")
        context = " ".join(value for value in (heading_text, direct, parent_text, href) if value)
        if not REPORT_TERMS.search(context):
            continue
        absolute = urljoin(base_url, href)
        target_host = urlparse(absolute).netloc.removeprefix("www.")
        if target_host != source_host or '"' in absolute or "%22" in absolute.lower():
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        title = direct if direct.lower() not in {"", "więcej", "more", "czytaj", "przeczytaj"} else heading_text
        title = title or parent_text or absolute
        if title.lower().startswith("www.") or absolute.rstrip("/") == base_url.rstrip("/"):
            continue
        links.append(
            IssuerIrLink(
                title=title[:500],
                url=absolute,
                kind=_link_kind(context),
                locator={"tag": "a", "href": href, "position": position},
            )
        )
        if len(links) >= MAX_LINKS_PER_INDEX:
            break
    return ParsedIssuerIrIndex(title=page_title[:500], links=links)


def ingest_issuer_ir_index(
    db: Session,
    ticker: str,
    *,
    force: bool = False,
) -> dict:
    ticker = ticker.upper()
    source_url = ISSUER_IR_SOURCES.get(ticker)
    if source_url is None:
        raise ValueError(f"Ticker {ticker} is not in the bounded RT2.3 issuer-IR pilot.")
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if company is None:
        raise ValueError(f"Unknown company {ticker}.")

    if not force and _is_fresh(db, source_url):
        document = db.scalar(
            select(SourceDocument).where(
                SourceDocument.company_ticker == ticker,
                SourceDocument.source_type == "issuer_ir",
                SourceDocument.scope_key == "reports-index",
            )
        )
        claim_count = 0
        if document is not None:
            claim_count = db.scalar(
                select(func.count())
                .select_from(Fact)
                .where(
                    Fact.company_id == company.id,
                    Fact.fact_type == "issuer_ir_link",
                )
            ) or 0
        return {
            "ok": True,
            "ticker": ticker,
            "status": "cached",
            "source_url": source_url,
            "document_id": document.id if document else None,
            "claim_count": claim_count,
        }

    try:
        response = http.fetch(source_url)
    except (http.FetchError, requests.RequestException) as exc:
        status_match = re.search(r"HTTP\s+(\d{3})", str(exc))
        status = int(status_match.group(1)) if status_match else None
        db.add(FetchLog(url=source_url, status=status))
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "temporarily_unavailable",
            "retry_later": True,
            "source_url": source_url,
            "error": str(exc),
            "claim_count": 0,
        }
    fetch_log = FetchLog(url=source_url, status=response.status_code)
    db.add(fetch_log)
    response.raise_for_status()
    parsed = parse_issuer_ir_index(response.text, base_url=str(response.url or source_url))
    content = response.content or response.text.encode("utf-8")
    recorded = record_document_version(
        db,
        company,
        source_name=f"{company.name or ticker} issuer IR",
        source_type="issuer_ir",
        scope_key="reports-index",
        requested_url=source_url,
        effective_url=str(response.url or source_url),
        content=content,
        text=response.text,
        response_status=response.status_code,
        mime_type=(response.headers.get("content-type", "text/html").split(";", 1)[0]),
        parser_version=PARSER_VERSION,
        fetched_at=fetch_log.fetched_at,
    )
    recorded.document.title = parsed.title
    if not parsed.links:
        mark_parse_result(recorded.version, success=False, error="No report links found.")
        fetch_log.document_version_id = recorded.version.id
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "parse_failed",
            "source_url": source_url,
            "document_version_id": recorded.version.id,
            "claim_count": 0,
        }

    for link in parsed.links:
        key_hash = hashlib.sha256(link.url.encode("utf-8")).hexdigest()[:16]
        record_text_fact(
            db,
            company,
            recorded.version,
            fact_type="issuer_ir_link",
            fact_key=f"issuer_ir.{link.kind}.{key_hash}",
            text=link.title,
            locator={**link.locator, "url": link.url},
            verification_state="unverified",
            extractor_version=EXTRACTOR_VERSION,
        )
    mark_parse_result(recorded.version, success=True)
    fetch_log.document_version_id = recorded.version.id
    db.commit()
    return {
        "ok": True,
        "ticker": ticker,
        "status": "fetched",
        "source_url": source_url,
        "document_id": recorded.document.id,
        "document_version_id": recorded.version.id,
        "version_created": recorded.version_created,
        "claim_count": len(parsed.links),
        "claims": [
            {"title": link.title, "url": link.url, "kind": link.kind}
            for link in parsed.links
        ],
    }


def _is_fresh(db: Session, url: str) -> bool:
    threshold = datetime.now(timezone.utc) - timedelta(
        hours=get_settings().scrape_cache_hours
    )
    fetched_at = db.scalar(
        select(FetchLog.fetched_at)
        .where(FetchLog.url == url, FetchLog.status == 200)
        .order_by(FetchLog.fetched_at.desc())
        .limit(1)
    )
    if fetched_at is None:
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return fetched_at >= threshold


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _link_kind(value: str) -> str:
    lowered = value.lower()
    if "raport" in lowered and ("bieżą" in lowered or "biez" in lowered or "espi" in lowered):
        return "current_report"
    if "raport" in lowered or "sprawozd" in lowered or "wynik" in lowered:
        return "periodic_report"
    if "prezentac" in lowered:
        return "presentation"
    if "walne" in lowered or "akcjon" in lowered or "governance" in lowered or "ład" in lowered:
        return "governance"
    return "other"
