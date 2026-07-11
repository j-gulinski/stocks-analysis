"""Evidence-dated default exclusions for the Discover universe."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentVersion, SourceDocument
from app.scrapers import http as polite_http
from app.scrapers.gpw_benchmark import parse_index_portfolio
from app.services import evidence

_SPECS = {
    "WIG20": "PL9999999987",
    "mWIG40": "PL9999999912",
}
_BASE = "https://gpwbenchmark.pl/ajaxindex.php?action=GPWIndexes&start=ajaxPortfolio&format=html&lang=PL"


def _norm(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def refresh_membership(db: Session, index_name: str) -> dict:
    isin = _SPECS[index_name]
    url = f"{_BASE}&isin={isin}&cmng_id=1010"
    response = polite_http.fetch(url)
    response.raise_for_status()
    content = getattr(response, "content", None) or response.text.encode()
    portfolio = parse_index_portfolio(response.text)
    expected_count = 20 if index_name == "WIG20" else 40
    if len(portfolio.instruments) != expected_count:
        raise ValueError(f"{index_name} source returned {len(portfolio.instruments)} instruments, expected {expected_count}.")
    recorded = evidence.record_market_document_version(
        db, market_key="__GPW__", source_name="gpw_benchmark",
        source_type="index_portfolio", scope_key=index_name,
        requested_url=url, effective_url=str(getattr(response, "url", None) or url),
        content=content, text=response.text, response_status=response.status_code,
        mime_type="text/html", parser_version="gpw-benchmark-portfolio@1",
        fetched_at=datetime.now(timezone.utc),
    )
    evidence.mark_parse_result(recorded.version, success=True)
    db.commit()
    return {"index": index_name, "source_version_id": recorded.version.id, "as_of": portfolio.as_of.isoformat(), "source_url": url, "instruments": sorted(portfolio.instruments)}


def policy_for_candidates(db: Session, candidates) -> dict:
    memberships: dict[str, dict] = {}
    for index_name in _SPECS:
        version = db.scalar(select(DocumentVersion).join(SourceDocument).where(
            SourceDocument.company_ticker == "__GPW__", SourceDocument.source_name == "gpw_benchmark",
            SourceDocument.source_type == "index_portfolio", SourceDocument.scope_key == index_name,
            DocumentVersion.parse_status == "parsed",
        ).order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc()).limit(1))
        if version is None:
            memberships[index_name] = {"status": "missing", "instruments": set()}
        else:
            parsed = parse_index_portfolio(version.raw_content)
            memberships[index_name] = {"status": "ready", "as_of": parsed.as_of.isoformat(), "source_version_id": version.id, "instruments": parsed.instruments}
    rows = []
    for candidate in candidates:
        identity = {_norm(candidate.ticker), _norm(candidate.name)}
        excluded_by = [name for name, item in memberships.items() if identity & {_norm(value) for value in item["instruments"]}]
        rows.append({"ticker": candidate.ticker, "included": not excluded_by, "reason": f"Default exclusion: {', '.join(excluded_by)}." if excluded_by else "Not in the stored default-exclusion portfolios.", "excluded_by": excluded_by})
    return {"default_exclusions": list(_SPECS), "memberships": [{key: value for key, value in item.items() if key != "instruments"} | {"index": name} for name, item in memberships.items()], "rows": rows}
