"""End-to-end Phase 1: refresh (with fetch stubbed to fixtures) → read endpoints.

No network is touched: app.scrapers.http.fetch is monkeypatched to serve the
committed fixture files, exercising the real parse → upsert → API pipeline.
"""
import pytest

from tests.conftest import FakeResponse, load_fixture

# Quarterly views are requested explicitly with ',Q' — the bare URL serves the
# ANNUAL view for some companies (production finding, CBF).
URL_TO_FIXTURE = {
    "/notowania/DEC": "br_profile.html",
    "/raporty-finansowe-rachunek-zyskow-i-strat/DEC,Y": "br_income_y.html",
    "/raporty-finansowe-rachunek-zyskow-i-strat/DEC,Q": "br_income_q.html",
    "/raporty-finansowe-bilans/DEC,Q": "br_balance_q.html",
    "/raporty-finansowe-przeplywy-pieniezne/DEC,Q": "br_cashflow_q.html",
    "/wskazniki-wartosci-rynkowej/DEC": "br_indicators_value.html",
    "/wskazniki-rentownosci/DEC": "br_indicators_profitability.html",
    "/dywidenda/DEC": "br_dividend.html",
    # /prognozy is a PUBLIC page (verified live 2026-07-09) — no premium
    # session needed; see app/services/refresh.py `_refresh_forecasts`.
    "/prognozy/DEC": "br_forecasts.html",
}


def fake_fetch(url, *, session=None, timeout=None):
    for suffix, fixture in URL_TO_FIXTURE.items():
        if url == f"https://www.biznesradar.pl{suffix}":
            return FakeResponse(load_fixture(fixture), 200)
    if url == "https://www.biznesradar.pl/notowania-historyczne/DEC":
        return FakeResponse(load_fixture("br_price_history.html"), 200)
    return FakeResponse("", 404)


@pytest.fixture()
def stub_fetch(monkeypatch):
    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_watchlist_crud(client):
    created = client.post("/api/watchlist", json={"ticker": "dec", "note": "test"})
    assert created.status_code == 201
    assert created.json()["ticker"] == "DEC"

    assert client.post("/api/watchlist", json={"ticker": "DEC"}).status_code == 409

    items = client.get("/api/watchlist").json()
    assert [item["ticker"] for item in items] == ["DEC"]
    assert client.get("/api/companies/DEC").status_code == 200

    assert client.delete("/api/watchlist/DEC").status_code == 204
    assert client.get("/api/companies/DEC").status_code == 200
    assert client.delete("/api/watchlist/DEC").status_code == 404

    recreated = client.post("/api/watchlist", json={"ticker": "DEC"})
    assert recreated.status_code == 201
    assert recreated.json()["name"] is None


def test_refresh_and_read_endpoints(client, stub_fetch):
    response = client.post("/api/companies/DEC/refresh")
    assert response.status_code == 200
    summary = response.json()["summary"]

    # profile now reports the parsed (reported) market cap
    assert summary["profile"] == "ok (mcap 259 mln zł)"
    assert summary["income_q"].startswith("ok (99 values")  # 11 rows × 9 quarters
    assert "11 rows × 9 periods; 2023Q1–2025Q1" in summary["income_q"]
    assert summary["income_y"].startswith("ok (4 values")
    assert summary["balance_q"].startswith("ok (25 values")
    assert summary["cashflow_q"].startswith("ok (12 values")
    # 5 mapped rows × 8 periods (cz, cwk, ev_ebitda, czo, cp); dropped rows
    # are now VISIBLE in the summary instead of silently ignored
    assert summary["indicators_value"].startswith("ok (40 values")
    assert "pominięte:" in summary["indicators_value"]
    assert "Grahama" in summary["indicators_value"]
    # 5 mapped rows × 4 periods; pretax "Marża zysku brutto" stays unmapped
    assert summary["indicators_profitability"].startswith("ok (20 values")
    assert "Marża zysku brutto" in summary["indicators_profitability"]
    assert summary["dividends"] == "ok (3 years)"
    # public /prognozy page (no premium session needed) — consensus years,
    # the O4K TTM facts, and the synthetic unmapped row all round-trip
    assert summary["forecasts"] == (
        "ok (2026, 2027, 2028 consensus); "
        "O4K: capex_ttm, depreciation_ttm, ebitda_ttm; "
        "pominięte: Dług netto / kapitał własny"
    )
    assert summary["prices"].startswith("ok (6 new days")
    assert "BR archiwum" in summary["prices"]
    # 8 BR financial/statement pages + forecasts + 1 BR price-history page
    assert summary["requests"] == "ok (10 HTTP)"

    info = client.get("/api/companies/DEC/info").json()
    assert info["name"] == "DECORA"
    assert info["shares_outstanding"] == 10_566_435
    # reported figures from the profile info box; the free-float row above
    # "Liczba akcji" in the fixture is the trap the old regex fell into
    assert info["market_cap"] == 258_877_658
    assert info["enterprise_value"] == 236_877_658

    financials = client.get(
        "/api/companies/DEC/financials", params={"statement": "income", "freq": "Q"}
    ).json()
    assert len(financials["periods"]) == 9
    assert financials["rows"][0]["field_code"] == "IncomeRevenues"  # source order kept
    assert financials["rows"][0]["values"][0] == 50000.0

    indicators = client.get("/api/companies/DEC/indicators").json()
    assert len(indicators["cz"]) == 8
    assert indicators["cz"][-1] == {"period": "2025Q1", "value": 9.8}
    # previously silently dropped: C/ZO, C/P and the margin history
    assert len(indicators["czo"]) == 8
    assert len(indicators["cp"]) == 8
    assert len(indicators["net_margin"]) == 4
    assert len(indicators["gross_margin"]) == 4
    assert "cena_wartosc_ksiegowa_grahama" not in indicators  # still excluded

    dividends = client.get("/api/companies/DEC/dividends").json()
    assert dividends[0]["year"] == 2025

    prices = client.get("/api/companies/DEC/prices").json()
    assert prices[-1]["close"] == 24.80  # chronological, newest from BR archive


def test_refresh_never_runs_forum_expectation_model_inline(
    client, stub_fetch, monkeypatch
):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("forum interpretation must run only in a claimed AgentRun")

    monkeypatch.setattr(
        "app.services.refresh._refresh_forum_expectations",
        forbidden,
    )

    response = client.post("/api/companies/DEC/refresh")

    assert response.status_code == 200
    assert response.json()["summary"]["forum_expectations"] == (
        "pominięto (wykonuje kolejka Codex)"
    )


def test_refresh_reports_empty_forecast_consensus_columns(client, db, monkeypatch):
    from sqlalchemy import select
    from app.db.models import CompanyMarketData

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    assert client.post("/api/companies/DEC/refresh").status_code == 200

    def fetch_with_empty_forecasts(url, *, session=None, timeout=None):
        if url == "https://www.biznesradar.pl/prognozy/DEC":
            return FakeResponse(load_fixture("br_forecasts_empty_consensus.html"), 200)
        return fake_fetch(url, session=session, timeout=timeout)

    monkeypatch.setattr("app.scrapers.http.fetch", fetch_with_empty_forecasts)

    summary = client.post("/api/companies/DEC/refresh?force=true").json()["summary"]

    assert summary["forecasts"].startswith(
        "ok (kolumny konsensusu bez wartości: 2026, 2027, 2028)"
    )
    assert "O4K: capex_ttm, depreciation_ttm, ebitda_ttm" in summary["forecasts"]
    market_row = db.scalar(select(CompanyMarketData))
    assert market_row.forecast_consensus == {}


def test_second_refresh_uses_cache(client, stub_fetch):
    assert client.post("/api/companies/DEC/refresh").status_code == 200
    summary = client.post("/api/companies/DEC/refresh").json()["summary"]

    for page in URL_TO_FIXTURE_PAGES:
        assert summary[page] == "cached", page
    # Thin history (< MIN_PRICE_HISTORY_ROWS) keeps trying the BR history page;
    # repeat fetch replaces the partial history so duplicates never accumulate.
    assert summary["prices"].startswith("ok (6 new days")
    assert summary["requests"] == "ok (1 HTTP)"


URL_TO_FIXTURE_PAGES = [
    "profile", "income_q", "income_y", "balance_q", "cashflow_q",
    "indicators_value", "indicators_profitability", "dividends", "forecasts",
]


def test_refresh_unknown_ticker_returns_404(client, stub_fetch):
    response = client.post("/api/companies/XXX/refresh")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_refresh_survives_missing_profile_page(client, monkeypatch):
    """Production regression: one wrong/missing page must never blank the
    whole refresh — statements still load when the profile 404s."""

    def fetch_without_profile(url, *, session=None, timeout=None):
        if "/notowania/" in url:
            return FakeResponse("", 404)
        return fake_fetch(url, session=session, timeout=timeout)

    monkeypatch.setattr("app.scrapers.http.fetch", fetch_without_profile)
    response = client.post("/api/companies/DEC/refresh")
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["profile"].startswith("error")
    assert summary["income_q"].startswith("ok (99 values")
    # data is readable even though the profile failed
    assert len(client.get("/api/companies/DEC/financials").json()["periods"]) == 9


def test_mapping_report(client, stub_fetch):
    client.post("/api/companies/DEC/refresh")
    report = client.get("/api/companies/DEC/mapping-report").json()

    income = {row["label"]: row["canonical"] for row in report["statements"]["income"]}
    assert income["Przychody netto ze sprzedaży"] == "revenue"
    assert income["Zysk brutto ze sprzedaży"] == "gross_profit"
    assert income["Wynik na pozostałej działalności operacyjnej"] is None  # unmapped, visible
    assert report["unmapped_statement_rows"] >= 1
    assert "cz" in report["indicators_stored"]


def test_scrapers_health(client, stub_fetch):
    client.post("/api/companies/DEC/refresh")
    health = client.get("/api/health/scrapers").json()
    assert health["biznesradar.pl"]["last_ok_at"] is not None
    assert health["biznesradar.pl"]["status"] == "healthy"
    assert health["biznesradar.pl"]["errors_24h"] == 0
    assert health["portalanaliz.pl"]["last_ok_at"] is None  # nothing synced yet
    assert health["portalanaliz.pl"]["status"] == "unknown"


def test_scrapers_health_distinguishes_recovery_from_active_failure(client, db):
    from datetime import datetime, timedelta, timezone

    from app.db.models import FetchLog

    now = datetime.now(timezone.utc)
    db.add(
        FetchLog(
            url="https://www.biznesradar.pl/notowania/OLD",
            status=404,
            fetched_at=now - timedelta(minutes=5),
        )
    )
    db.add(
        FetchLog(
            url="https://www.biznesradar.pl/notowania/NEW-SLUG",
            status=200,
            fetched_at=now - timedelta(minutes=2),
        )
    )
    db.commit()

    recovered = client.get("/api/health/scrapers").json()["biznesradar.pl"]
    assert recovered["status"] == "recovered"
    assert recovered["errors_24h"] == 1

    db.add(
        FetchLog(
            url="https://www.biznesradar.pl/notowania/BROKEN",
            status=503,
            fetched_at=now,
        )
    )
    db.commit()

    degraded = client.get("/api/health/scrapers").json()["biznesradar.pl"]
    assert degraded["status"] == "degraded"
    assert degraded["errors_24h"] == 2


def test_reads_for_unknown_company_return_404(client):
    assert client.get("/api/companies/ZZZ/financials").status_code == 404


def test_force_refresh_replaces_stale_periods(client, stub_fetch, db):
    """Production case: earlier runs stored mislabeled periods (annual data
    as quarters). A forced refresh is authoritative — it must PURGE them,
    and re-running must never raise UniqueViolation."""
    from sqlalchemy import select
    from app.db.models import Company, ReportValue

    client.post("/api/companies/DEC/refresh")
    company = db.scalar(select(Company).where(Company.ticker == "DEC"))
    db.add(
        ReportValue(
            company_id=company.id, statement="income", freq="Q",
            period="1999Q1", field_code="IncomeRevenues",
            field_label="Przychody ze sprzedaży", value=1.0,
        )
    )
    db.commit()

    # non-forced: cached pages → stale row survives
    client.post("/api/companies/DEC/refresh")
    periods = set(
        db.scalars(
            select(ReportValue.period).where(
                ReportValue.company_id == company.id,
                ReportValue.statement == "income",
                ReportValue.freq == "Q",
            )
        )
    )
    assert "1999Q1" in periods

    # forced: replace semantics purge it; summary stays healthy
    summary = client.post("/api/companies/DEC/refresh?force=true").json()["summary"]
    # refresh.py enriches the summary with table detail
    # ("ok (99 values; N rows × M periods; first–last)"), so match the stable
    # prefix rather than the exact old string.
    assert summary["income_q"].startswith("ok (99 values")
    assert "database" not in summary
    periods = set(
        db.scalars(
            select(ReportValue.period).where(
                ReportValue.company_id == company.id,
                ReportValue.statement == "income",
                ReportValue.freq == "Q",
            )
        )
    )
    assert "1999Q1" not in periods
    assert "2025Q1" in periods


def test_prices_skip_when_up_to_date(client, stub_fetch, db):
    """A stored price for today must produce ZERO provider requests —
    production once generated future provider-date requests."""
    from datetime import date
    from sqlalchemy import select
    from app.db.models import Company, Price

    import app.services.refresh as refresh_service

    client.post("/api/companies/DEC/refresh")
    company = db.scalar(select(Company).where(Company.ticker == "DEC"))
    db.add(Price(company_id=company.id, date=date.today(), close=25.0))
    db.commit()

    original = refresh_service.MIN_PRICE_HISTORY_ROWS
    refresh_service.MIN_PRICE_HISTORY_ROWS = 3  # 2 fixture days + today = enough
    try:
        summary = client.post("/api/companies/DEC/refresh").json()["summary"]
    finally:
        refresh_service.MIN_PRICE_HISTORY_ROWS = original
    assert summary["prices"].startswith("ok (aktualne")
    assert summary["requests"] == "ok (0 HTTP)"  # everything cached, prices skipped


def test_profile_price_fallback_when_history_unavailable(client, monkeypatch):
    """BR history unavailable → today's close comes from the fetched profile
    page, so kurs/mcap survive with no external CSV providers."""

    def fetch_without_history(url, *, session=None, timeout=None):
        if "notowania-historyczne" in url:
            return FakeResponse("", 404)
        if "/notowania/" in url:
            return FakeResponse(
                '<html><head><title>DECORA (DEC)</title>'
                '<meta itemprop="price" content="24.50"></head></html>',
                200,
            )
        return fake_fetch(url, session=session, timeout=timeout)

    monkeypatch.setattr("app.scrapers.http.fetch", fetch_without_history)
    summary = client.post("/api/companies/DEC/refresh").json()["summary"]
    assert summary["prices"].startswith("ok (fallback: 1 dzien")

    prices = client.get("/api/companies/DEC/prices").json()
    assert len(prices) == 1
    assert prices[0]["close"] == 24.5
