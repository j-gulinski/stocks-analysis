"""R0 backfill replays immutable financial-report documents without HTTP."""

from __future__ import annotations

from sqlalchemy import delete, func, select

from app.db.models import Company, DocumentVersion, Fact, FetchLog, SourceDocument
from app.services import evidence, publication_dates
from tests.conftest import FakeResponse
from tests.test_api_phase1 import fake_fetch


def _statement_versions(db) -> list[DocumentVersion]:
    return list(
        db.scalars(
            select(DocumentVersion)
            .join(
                SourceDocument,
                DocumentVersion.source_document_id == SourceDocument.id,
            )
            .where(SourceDocument.source_type == "financial_report")
            .order_by(DocumentVersion.id)
        )
    )


def _forbid_http(*_args, **_kwargs):
    raise AssertionError("publication-date backfill must not make HTTP requests")


def test_backfill_rejects_an_explicit_blank_ticker_without_scanning(db):
    result = publication_dates.backfill_statement_publication_facts(db, ticker="  ")
    assert result == {
        "ok": False,
        "ticker": "",
        "versions_scanned": 0,
        "versions_succeeded": 0,
        "versions_failed": 0,
        "facts_created": 0,
        "facts_reused": 0,
        "failures": [
            {
                "company_ticker": "",
                "scope_key": None,
                "document_version_id": None,
                "error": "Ticker filter must not be empty.",
            }
        ],
    }


def test_backfill_replays_stored_versions_without_http_and_is_idempotent(
    client, db, monkeypatch
):
    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    assert client.post("/api/companies/DEC/refresh").status_code == 200

    versions_before = {
        version.id: (version.content_hash, version.raw_content, version.parse_status)
        for version in _statement_versions(db)
    }
    fetch_count_before = db.scalar(select(func.count()).select_from(FetchLog))
    assert len(versions_before) == 4

    db.execute(
        delete(Fact).where(Fact.fact_type == publication_dates.PUBLICATION_FACT_TYPE)
    )
    db.flush()
    monkeypatch.setattr("app.scrapers.http.fetch", _forbid_http)

    first = publication_dates.backfill_statement_publication_facts(db)
    assert first == {
        "ok": True,
        "ticker": None,
        "versions_scanned": 4,
        "versions_succeeded": 4,
        "versions_failed": 0,
        "facts_created": 20,
        "facts_reused": 0,
        "failures": [],
    }

    second = publication_dates.backfill_statement_publication_facts(db)
    assert second["ok"] is True
    assert second["versions_scanned"] == 4
    assert second["facts_created"] == 0
    assert second["facts_reused"] == 20

    facts = db.scalars(
        select(Fact).where(Fact.fact_type == publication_dates.PUBLICATION_FACT_TYPE)
    ).all()
    assert len(facts) == 20
    assert len({fact.fact_hash for fact in facts}) == 20
    assert {
        version.id: (version.content_hash, version.raw_content, version.parse_status)
        for version in _statement_versions(db)
    } == versions_before
    assert db.scalar(select(func.count()).select_from(FetchLog)) == fetch_count_before


def test_backfill_covers_all_historical_versions_and_isolates_parse_failures(
    client, db, monkeypatch
):
    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    assert client.post("/api/companies/DEC/refresh").status_code == 200

    def changed_fetch(url, *, session=None, timeout=None):
        response = fake_fetch(url, session=session, timeout=timeout)
        if url.endswith("/raporty-finansowe-rachunek-zyskow-i-strat/DEC,Q"):
            return FakeResponse(
                response.text.replace("50\u00a0000", "51\u00a000", 1),
                200,
            )
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", changed_fetch)
    assert client.post("/api/companies/DEC/refresh?force=true").status_code == 200

    company = db.scalar(select(Company).where(Company.ticker == "DEC"))
    income_document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.company_ticker == "DEC",
            SourceDocument.source_type == "financial_report",
            SourceDocument.scope_key == "income_q",
        )
    )
    malformed = evidence.record_document_version(
        db,
        company,
        source_name="biznesradar",
        source_type="financial_report",
        scope_key="income_q",
        requested_url=income_document.canonical_url,
        effective_url=income_document.canonical_url,
        content=b"<html><body>stored malformed report</body></html>",
        text="<html><body>stored malformed report</body></html>",
        response_status=200,
        mime_type="text/html",
    )
    evidence.mark_parse_result(malformed.version, success=True)
    db.flush()

    db.execute(
        delete(Fact).where(Fact.fact_type == publication_dates.PUBLICATION_FACT_TYPE)
    )
    db.flush()
    version_state_before = {
        version.id: (version.content_hash, version.raw_content, version.parse_status)
        for version in _statement_versions(db)
    }
    monkeypatch.setattr("app.scrapers.http.fetch", _forbid_http)

    result = publication_dates.backfill_statement_publication_facts(db, ticker="dec")
    assert result["ok"] is False
    assert result["ticker"] == "DEC"
    assert result["versions_scanned"] == 6
    assert result["versions_succeeded"] == 5
    assert result["versions_failed"] == 1
    assert result["facts_created"] == 29
    assert result["facts_reused"] == 0
    assert result["failures"] == [
        {
            "company_ticker": "DEC",
            "scope_key": "income_q",
            "document_version_id": malformed.version.id,
            "error": "No report table found on page.",
        }
    ]

    income_versions = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.source_document_id == income_document.id)
        .order_by(DocumentVersion.id)
    ).all()
    facts_per_version = {
        version.id: db.scalar(
            select(func.count())
            .select_from(Fact)
            .where(
                Fact.source_version_id == version.id,
                Fact.fact_type == publication_dates.PUBLICATION_FACT_TYPE,
            )
        )
        for version in income_versions
    }
    assert facts_per_version == {
        income_versions[0].id: 9,
        income_versions[1].id: 9,
        malformed.version.id: 0,
    }
    assert {
        version.id: (version.content_hash, version.raw_content, version.parse_status)
        for version in _statement_versions(db)
    } == version_state_before
