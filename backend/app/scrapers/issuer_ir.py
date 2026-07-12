"""Polite issuer-IR index ingestion for the bounded RT2.3 pilot."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
from io import BytesIO
import re
import socket
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Company, DocumentVersion, Fact, FetchLog, SourceDocument
from app.scrapers import http
from app.services.evidence import (
    mark_parse_result,
    record_document_version,
    record_text_fact,
)

PARSER_VERSION = "issuer-ir-index@4"
EXTRACTOR_VERSION = "issuer-ir-links@4"
MAX_LINKS_PER_INDEX = 30
MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_PAGE_CLAIMS = 30
MAX_CLAIM_CHARS = 4000
MAX_REDIRECTS = 3
REDIRECT_STATUSES = {301, 302, 303, 307, 308}

ISSUER_IR_SOURCES = {
    "SNT": "https://synektik.com.pl/centrum-inwestora/raporty-biezace/",
    "ABS": "https://assecobs.pl/inwestor/raporty-biezace/",
    "OPM": "https://opteam.pl/firma/relacje-inwestorskie",
    "ASB": "https://investor.asbis.com/news/financial-reports-archive/financial-reports-2026",
}

REPORT_TERMS = re.compile(
    r"raport|sprawozd|wynik|prezentac|walne|akcjon|dywidend|governance|ład korpor"
    r"|financial|interim|annual|quarterly|quarter|report",
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
    root = soup.select_one(".ncont-content") or soup.find("main") or soup.body or soup
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
        container = anchor.find_parent(["article", "section", "li", "tr", "div"])
        heading_text = _clean_text(
            heading.get_text(" ", strip=True)
            if heading is not None and container is not None and container.find(heading.name) is heading
            else ""
        )
        parent_text = _clean_text(
            anchor.parent.get_text(" ", strip=True)
            if anchor.parent is not None and anchor.parent is not root
            else ""
        )
        context = " ".join(value for value in (heading_text, direct, parent_text, href) if value)
        if not REPORT_TERMS.search(context):
            continue
        absolute = urljoin(base_url, href)
        parsed_url = urlparse(absolute)
        target_host = parsed_url.netloc.removeprefix("www.")
        if (
            parsed_url.scheme not in {"http", "https"}
            or target_host != source_host
            or '"' in absolute
            or "%22" in absolute.lower()
        ):
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


def ingest_issuer_ir_report(
    db: Session,
    ticker: str,
    report_url: str,
    *,
    force: bool = False,
) -> dict:
    """Fetch one previously discovered issuer PDF and store page-level claims."""
    ticker = ticker.upper()
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if company is None:
        raise ValueError(f"Unknown company {ticker}.")
    source_fact = _issuer_link_fact(db, company, report_url)
    if source_fact is None:
        raise ValueError("Report URL is not present in this company's issuer-IR index evidence.")
    if not _is_allowed_issuer_url(ticker, report_url):
        raise ValueError("Report URL is outside the registered issuer-IR host.")
    if not report_url.lower().split("?", 1)[0].endswith(".pdf"):
        raise ValueError("The bounded RT2.3 detail pilot currently accepts PDF reports only.")

    scope_key = f"report:{hashlib.sha256(report_url.encode('utf-8')).hexdigest()[:24]}"
    if not force:
        cached = _cached_report_result(db, ticker, report_url, scope_key)
        if cached is not None:
            return cached

    try:
        response, effective_url = _fetch_report_response(ticker, report_url)
    except (http.FetchError, requests.RequestException) as exc:
        status_match = re.search(r"HTTP\s+(\d{3})", str(exc))
        status = int(status_match.group(1)) if status_match else None
        db.add(FetchLog(url=report_url, status=status))
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "temporarily_unavailable",
            "retry_later": True,
            "source_url": report_url,
            "error": str(exc),
        }
    except ValueError as exc:
        db.add(FetchLog(url=report_url, status=None))
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "rejected",
            "source_url": report_url,
            "error": str(exc),
        }
    fetch_log = FetchLog(url=report_url, status=response.status_code)
    db.add(fetch_log)
    if response.status_code >= 400:
        response.close()
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "source_not_found" if response.status_code in {404, 410} else "temporarily_unavailable",
            "retry_later": response.status_code not in {404, 410},
            "source_url": report_url,
            "error": f"Issuer report returned HTTP {response.status_code}.",
        }
    try:
        content = _read_bounded_content(response)
    except ValueError as exc:
        response.close()
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "rejected",
            "source_url": report_url,
            "error": str(exc),
        }
    finally:
        response.close()
    if not content.startswith(b"%PDF"):
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "parse_failed",
            "source_url": report_url,
            "error": "Response is not a PDF document.",
        }
    parse_error: str | None = None
    try:
        pages = extract_pdf_pages(content)
    except Exception as exc:  # PDF parsers must not be allowed to stop the queue worker.
        pages = []
        parse_error = f"{type(exc).__name__}: {exc}"
    extracted_text = "\n\n".join(page for page in pages if page)
    recorded = record_document_version(
        db,
        company,
        source_name=f"{company.name or ticker} issuer IR",
        source_type="issuer_ir_report",
        scope_key=scope_key,
        requested_url=report_url,
        effective_url=effective_url,
        content=content,
        text=extracted_text,
        response_status=response.status_code,
        mime_type="application/pdf",
        parser_version="issuer-ir-pdf@2",
        fetched_at=fetch_log.fetched_at,
    )
    recorded.document.title = source_fact.text_value
    if not recorded.version_created and recorded.version.parse_status != "pending":
        fetch_log.document_version_id = recorded.version.id
        db.commit()
        return _report_version_result(
            ticker,
            report_url,
            recorded.document,
            recorded.version,
        )
    if parse_error is not None:
        mark_parse_result(recorded.version, success=False, error=parse_error[:1000])
        fetch_log.document_version_id = recorded.version.id
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "parse_failed",
            "source_url": report_url,
            "document_version_id": recorded.version.id,
            "error": parse_error,
        }
    if not extracted_text.strip():
        recorded.version.parse_status = "needs_ocr"
        recorded.version.parse_error = (
            "PDF contains no extractable text; bounded OCR is not configured."
        )
        fetch_log.document_version_id = recorded.version.id
        db.commit()
        return {
            "ok": False,
            "ticker": ticker,
            "status": "needs_ocr",
            "source_url": report_url,
            "document_version_id": recorded.version.id,
            "page_count": len(pages),
        }
    claim_count = 0
    for page_number, page_text in enumerate(pages[:MAX_PAGE_CLAIMS], start=1):
        if not page_text.strip():
            continue
        record_text_fact(
            db,
            company,
            recorded.version,
            fact_type="issuer_ir_page",
            fact_key=f"issuer_ir.page.{page_number}",
            text=page_text[:MAX_CLAIM_CHARS],
            locator={
                "url": report_url,
                "page": page_number,
                "text_truncated": len(page_text) > MAX_CLAIM_CHARS,
                "extracted_chars": min(len(page_text), MAX_CLAIM_CHARS),
            },
            verification_state="unverified",
            extractor_version="issuer-ir-pdf-pages@2",
        )
        claim_count += 1
    partial = len(pages) > MAX_PAGE_CLAIMS or any(
        len(page) > MAX_CLAIM_CHARS for page in pages[:MAX_PAGE_CLAIMS]
    )
    if partial:
        recorded.version.parse_status = "partial"
        recorded.version.parse_error = (
            f"Extraction bounded to {MAX_PAGE_CLAIMS} pages and "
            f"{MAX_CLAIM_CHARS} characters per page."
        )
    else:
        mark_parse_result(recorded.version, success=True)
    fetch_log.document_version_id = recorded.version.id
    db.commit()
    return {
        "ok": True,
        "ticker": ticker,
        "status": "fetched_partial" if partial else "fetched",
        "source_url": report_url,
        "document_id": recorded.document.id,
        "document_version_id": recorded.version.id,
        "version_created": recorded.version_created,
        "page_count": len(pages),
        "page_claim_count": claim_count,
        "title": source_fact.text_value,
    }


def extract_pdf_pages(content: bytes) -> list[str]:
    reader = PdfReader(BytesIO(content), strict=False)
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise ValueError("Encrypted PDF cannot be read without a password.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDF exceeds {MAX_PDF_PAGES} page pilot limit.")
    return [_clean_text(page.extract_text() or "") for page in reader.pages]


def _issuer_link_fact(db: Session, company: Company, report_url: str) -> Fact | None:
    facts = db.scalars(
        select(Fact)
        .join(DocumentVersion, DocumentVersion.id == Fact.source_version_id)
        .join(SourceDocument, SourceDocument.id == DocumentVersion.source_document_id)
        .where(
            Fact.company_id == company.id,
            Fact.fact_type == "issuer_ir_link",
            Fact.extractor_version == EXTRACTOR_VERSION,
            DocumentVersion.parse_status == "parsed",
            SourceDocument.source_type == "issuer_ir",
            SourceDocument.scope_key == "reports-index",
            SourceDocument.company_id == company.id,
            SourceDocument.company_ticker == company.ticker,
        )
    ).all()
    return next(
        (
            fact
            for fact in facts
            if isinstance(fact.locator, dict) and fact.locator.get("url") == report_url
        ),
        None,
    )


def _is_allowed_issuer_url(ticker: str, url: str) -> bool:
    source_url = ISSUER_IR_SOURCES.get(ticker)
    if source_url is None:
        return False
    parsed = urlparse(url)
    source = urlparse(source_url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and port in {None, 443}
        and parsed.hostname.removeprefix("www.")
        == (source.hostname or "").removeprefix("www.")
    )


def _host_resolves_public(url: str) -> bool:
    hostname = urlparse(url).hostname
    if hostname is None:
        return False
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror:
        return False
    return _addresses_are_public(addresses)


def _addresses_are_public(addresses: set[str]) -> bool:
    return bool(addresses) and all(_address_is_public(value) for value in addresses)


def _address_is_public(value: str) -> bool:
    return ipaddress.ip_address(value).is_global


def _fetch_report_response(ticker: str, report_url: str) -> tuple[requests.Response, str]:
    current_url = report_url
    for _hop in range(MAX_REDIRECTS + 1):
        if not _is_allowed_issuer_url(ticker, current_url):
            raise ValueError("Report URL or redirect left the registered issuer-IR host.")
        if not _host_resolves_public(current_url):
            raise ValueError("Registered issuer-IR host did not resolve only to public addresses.")
        response = http.fetch(current_url, allow_redirects=False, stream=True)
        peer_is_public = _peer_is_public(response)
        location = response.headers.get("location")
        current_host = (urlparse(current_url).hostname or "").removeprefix("www.")
        redirect_host = (
            (urlparse(urljoin(current_url, location)).hostname or "").removeprefix("www.")
            if location
            else ""
        )
        empty_same_host_redirect = (
            response.status_code in REDIRECT_STATUSES
            and response.headers.get("content-length") == "0"
            and redirect_host == current_host
        )
        if not peer_is_public and not empty_same_host_redirect:
            response.close()
            raise ValueError("Issuer report connection peer is not a public address.")
        if response.status_code not in REDIRECT_STATUSES:
            return response, current_url
        response.close()
        if not location:
            raise ValueError("Issuer report redirect did not include a Location header.")
        next_url = urljoin(current_url, location)
        parsed_next = urlparse(next_url)
        if (
            parsed_next.scheme == "http"
            and (parsed_next.hostname or "").removeprefix("www.") == current_host
        ):
            next_url = parsed_next._replace(scheme="https").geturl()
        current_url = next_url
    raise ValueError(f"Issuer report exceeded {MAX_REDIRECTS} redirects.")


def _peer_is_public(response: requests.Response) -> bool:
    """Validate the connected socket, not only a pre-request DNS answer."""
    try:
        connection = response.raw._connection  # requests/urllib3 transport state
        peer = connection.sock.getpeername()[0]
    except (AttributeError, OSError, TypeError):
        return False
    return _address_is_public(peer)


def _read_bounded_content(response: requests.Response) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_PDF_BYTES:
                raise ValueError(f"PDF exceeds {MAX_PDF_BYTES} byte pilot limit.")
        except ValueError as exc:
            if "exceeds" in str(exc):
                raise
    chunks: list[bytes] = []
    byte_count = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        byte_count += len(chunk)
        if byte_count > MAX_PDF_BYTES:
            raise ValueError(f"PDF exceeds {MAX_PDF_BYTES} byte pilot limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def _cached_report_result(
    db: Session, ticker: str, report_url: str, scope_key: str
) -> dict | None:
    if not _is_fresh(db, report_url):
        return None
    document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.company_ticker == ticker,
            SourceDocument.source_type == "issuer_ir_report",
            SourceDocument.scope_key == scope_key,
        )
    )
    if document is None:
        return None
    version = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.source_document_id == document.id)
        .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
        .limit(1)
    )
    if version is None:
        return None
    return _report_version_result(ticker, report_url, document, version)


def _report_version_result(
    ticker: str,
    report_url: str,
    document: SourceDocument,
    version: DocumentVersion,
) -> dict:
    statuses = {
        "parsed": (True, "cached"),
        "partial": (True, "cached_partial"),
        "needs_ocr": (False, "needs_ocr"),
        "failed": (False, "parse_failed"),
    }
    ok, status = statuses.get(version.parse_status, (False, version.parse_status))
    return {
        "ok": ok,
        "ticker": ticker,
        "status": status,
        "source_url": report_url,
        "document_id": document.id,
        "document_version_id": version.id,
        "error": version.parse_error,
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
    if (
        "raport" in lowered
        or "sprawozd" in lowered
        or "wynik" in lowered
        or "financial" in lowered
        or "interim" in lowered
        or "annual" in lowered
        or "quarter" in lowered
        or "report" in lowered
    ):
        return "periodic_report"
    if "prezentac" in lowered:
        return "presentation"
    if "walne" in lowered or "akcjon" in lowered or "governance" in lowered or "ład" in lowered:
        return "governance"
    return "other"
