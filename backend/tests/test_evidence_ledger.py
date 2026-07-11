"""RT2 immutable evidence, lineage and point-in-time behavior."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.db.models import (
    DocumentVersion,
    DataConflict,
    Fact,
    FetchLog,
    IndicatorValue,
    ReportValue,
    SourceDocument,
)
from app.services import evidence
from tests.conftest import FakeResponse
from tests.test_api_phase1 import fake_fetch


@pytest.fixture()
def stub_fetch(monkeypatch):
    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)


def _counts(db) -> tuple[int, int, int]:
    return (
        db.scalar(select(func.count()).select_from(SourceDocument)),
        db.scalar(select(func.count()).select_from(DocumentVersion)),
        db.scalar(select(func.count()).select_from(Fact)),
    )


def test_refresh_creates_documents_facts_and_serving_lineage(client, db, stub_fetch):
    response = client.post("/api/companies/DEC/refresh")
    assert response.status_code == 200
    assert _counts(db) == (6, 6, 200)

    report_without_lineage = db.scalar(
        select(func.count())
        .select_from(ReportValue)
        .where(ReportValue.source_fact_id.is_(None))
    )
    indicator_without_lineage = db.scalar(
        select(func.count())
        .select_from(IndicatorValue)
        .where(IndicatorValue.source_fact_id.is_(None))
    )
    assert report_without_lineage == 0
    assert indicator_without_lineage == 0

    revenue = db.scalar(
        select(ReportValue).where(
            ReportValue.statement == "income",
            ReportValue.freq == "Q",
            ReportValue.period == "2023Q1",
            ReportValue.field_code == "IncomeRevenues",
        )
    )
    fact = db.get(Fact, revenue.source_fact_id)
    version = db.get(DocumentVersion, fact.source_version_id)
    assert float(fact.numeric_value) == float(revenue.value) == 50_000
    assert fact.unit == "tys_pln"
    assert fact.known_at == version.fetched_at
    assert "Przychody netto ze sprzedaży" in version.raw_content

    linked_fetches = db.scalar(
        select(func.count())
        .select_from(FetchLog)
        .where(FetchLog.document_version_id.is_not(None))
    )
    assert linked_fetches == 6

    documents = client.get("/api/companies/DEC/evidence/documents").json()
    assert len(documents) == 6
    assert all(document["version_count"] == 1 for document in documents)
    assert all(document["latest_parse_status"] == "parsed" for document in documents)
    assert all(document["quality"]["terms_status"] == "review_required" for document in documents)
    assert all(document["quality"]["limitation"] for document in documents)
    facts = client.get("/api/companies/DEC/evidence/facts").json()
    assert len(facts) == 200
    assert len(client.get(
        "/api/companies/DEC/evidence/facts", params={"fact_type": "indicator"}
    ).json()) == 60

    earliest = min(db.scalars(select(DocumentVersion.fetched_at)).all())
    before = earliest - timedelta(microseconds=1)
    assert client.get(
        "/api/companies/DEC/evidence/facts", params={"as_of": before.isoformat()}
    ).json() == []


def test_forced_identical_refresh_reuses_versions_and_facts(client, db, stub_fetch):
    assert client.post("/api/companies/DEC/refresh").status_code == 200
    assert client.post("/api/companies/DEC/refresh?force=true").status_code == 200
    assert _counts(db) == (6, 6, 200)


def test_record_document_version_reports_first_insert_and_identical_reuse(db):
    from app.db.models import Company

    company = Company(ticker="NEW", name="NEW TEST")
    db.add(company)
    db.flush()
    kwargs = {
        "source_name": "issuer",
        "source_type": "issuer_ir",
        "scope_key": "reports-index",
        "requested_url": "https://issuer.example/reports",
        "effective_url": "https://issuer.example/reports",
        "content": b"same bytes",
        "text": "same bytes",
        "response_status": 200,
        "mime_type": "text/html",
    }

    first = evidence.record_document_version(db, company, **kwargs)
    second = evidence.record_document_version(db, company, **kwargs)

    assert first.version_created is True
    assert second.version_created is False
    assert first.version.id == second.version.id


def test_changed_page_preserves_old_as_of_and_advances_serving_pointer(
    client, db, monkeypatch
):
    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    assert client.post("/api/companies/DEC/refresh").status_code == 200
    income_document = db.scalar(
        select(SourceDocument).where(SourceDocument.scope_key == "income_q")
    )
    first_version = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.source_document_id == income_document.id
        )
    )

    def changed_fetch(url, *, session=None, timeout=None):
        response = fake_fetch(url, session=session, timeout=timeout)
        if url.endswith("/raporty-finansowe-rachunek-zyskow-i-strat/DEC,Q"):
            return FakeResponse(response.text.replace("50\u00a0000", "51\u00a0000", 1), 200)
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", changed_fetch)
    assert client.post("/api/companies/DEC/refresh?force=true").status_code == 200

    assert _counts(db) == (6, 7, 299)
    current = db.scalar(
        select(ReportValue).where(
            ReportValue.statement == "income",
            ReportValue.freq == "Q",
            ReportValue.period == "2023Q1",
            ReportValue.field_code == "IncomeRevenues",
        )
    )
    assert float(current.value) == 51_000
    assert db.get(Fact, current.source_fact_id).source_version_id != first_version.id

    old_facts = client.get(
        "/api/companies/DEC/evidence/facts",
        params={"as_of": first_version.fetched_at.isoformat()},
    ).json()
    old_revenue = next(
        item
        for item in old_facts
        if item["fact_key"] == "income.IncomeRevenues"
        and item["period"] == "2023Q1"
    )
    assert old_revenue["numeric_value"] == 50_000

    latest_facts = client.get("/api/companies/DEC/evidence/facts").json()
    latest_revenue = next(
        item
        for item in latest_facts
        if item["fact_key"] == "income.IncomeRevenues"
        and item["period"] == "2023Q1"
    )
    assert latest_revenue["numeric_value"] == 51_000


def test_failed_changed_page_is_retained_but_does_not_blank_serving_data(
    client, db, monkeypatch
):
    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    assert client.post("/api/companies/DEC/refresh").status_code == 200

    def broken_income_fetch(url, *, session=None, timeout=None):
        if url.endswith("/raporty-finansowe-rachunek-zyskow-i-strat/DEC,Q"):
            return FakeResponse("<html><body>changed but no table</body></html>", 200)
        return fake_fetch(url, session=session, timeout=timeout)

    monkeypatch.setattr("app.scrapers.http.fetch", broken_income_fetch)
    response = client.post("/api/companies/DEC/refresh?force=true")
    assert response.status_code == 200
    assert response.json()["summary"]["income_q"].startswith("error")

    income_document = db.scalar(
        select(SourceDocument).where(SourceDocument.scope_key == "income_q")
    )
    versions = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.source_document_id == income_document.id)
        .order_by(DocumentVersion.fetched_at)
    ).all()
    assert [version.parse_status for version in versions] == ["parsed", "failed"]
    assert db.scalar(
        select(func.count())
        .select_from(ReportValue)
        .where(ReportValue.statement == "income", ReportValue.freq == "Q")
    ) == 99
    # Failed raw version creates no facts and is excluded from as-of reads.
    assert db.scalar(select(func.count()).select_from(Fact)) == 200
    assert len(client.get("/api/companies/DEC/evidence/facts").json()) == 200


def test_watchlist_removal_preserves_immutable_evidence(client, db, stub_fetch):
    assert client.post("/api/watchlist", json={"ticker": "DEC"}).status_code == 201
    assert client.post("/api/companies/DEC/refresh").status_code == 200
    before = _counts(db)

    assert client.delete("/api/watchlist/DEC").status_code == 204
    assert _counts(db) == before
    assert set(db.scalars(select(SourceDocument.company_ticker))) == {"DEC"}
    assert set(db.scalars(select(Fact.company_ticker))) == {"DEC"}


def test_cross_document_disagreement_creates_explicit_conflict(client, db):
    from app.db.models import Company

    company = Company(ticker="DEC", name="DECORA")
    db.add(company)
    db.flush()
    now = datetime.now(timezone.utc)
    first = evidence.record_document_version(
        db,
        company,
        source_name="source-a",
        source_type="market_indicators",
        scope_key="valuation",
        requested_url="https://a.example/dec",
        effective_url="https://a.example/dec",
        content=b"a",
        text="a",
        response_status=200,
        mime_type="text/html",
        fetched_at=now,
    )
    second = evidence.record_document_version(
        db,
        company,
        source_name="source-b",
        source_type="market_indicators",
        scope_key="valuation",
        requested_url="https://b.example/dec",
        effective_url="https://b.example/dec",
        content=b"b",
        text="b",
        response_status=200,
        mime_type="text/html",
        fetched_at=now,
    )
    evidence.mark_parse_result(first.version, success=True)
    evidence.mark_parse_result(second.version, success=True)
    left = evidence.record_numeric_fact(
        db,
        company,
        first.version,
        fact_type="indicator",
        fact_key="indicator.cz",
        value=10.0,
        unit="ratio",
        period="2025Q1",
        locator={"row": "C/Z"},
    )
    right = evidence.record_numeric_fact(
        db,
        company,
        second.version,
        fact_type="indicator",
        fact_key="indicator.cz",
        value=11.0,
        unit="ratio",
        period="2025Q1",
        locator={"row": "C/Z"},
    )

    conflict = evidence.record_conflict_if_needed(
        db, company, previous_fact_id=left.id, new_fact=right
    )
    duplicate = evidence.record_conflict_if_needed(
        db, company, previous_fact_id=left.id, new_fact=right
    )
    db.commit()

    assert conflict.id == duplicate.id
    assert db.scalar(select(func.count()).select_from(DataConflict)) == 1
    response = client.get("/api/companies/DEC/evidence/conflicts")
    assert response.status_code == 200
    assert response.json()[0]["left_value"] == 10.0
    assert response.json()[0]["right_value"] == 11.0
