"""Phase 3 end-to-end: refresh from fixtures → dossier, forecast endpoints.

Numbers asserted here are the same hand-checked values as in the unit tests —
if these pass, the whole pipeline (parse → upsert → canonical mapping → math →
DTO) is consistent.
"""
import pytest

from tests.test_api_phase1 import fake_fetch


@pytest.fixture()
def refreshed(client, monkeypatch):
    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    response = client.post("/api/companies/DEC/refresh")
    assert response.status_code == 200
    return client


def test_dossier(refreshed):
    dossier = refreshed.get("/api/companies/DEC").json()

    assert dossier["company"]["name"] == "DECORA"
    assert dossier["freshness"]["financials_scraped_at"] is not None
    assert dossier["freshness"]["last_price_date"] == "2025-07-01"

    quarters = dossier["quarters"]
    assert quarters[-1]["period"] == "2025Q1"
    assert quarters[-1]["gross_margin_pct"] == 34.0
    assert quarters[-1]["revenue_yoy_pct"] == 14.0

    assert dossier["ttm"]["net_profit"] == 26892.0
    assert dossier["ttm"]["eps"] == 2.545
    assert dossier["ttm"]["pe"] == 9.63
    assert dossier["ttm"]["price"] == 24.50

    assert dossier["pe_history"]["median"] == 11.35
    assert dossier["pe_history"]["percentile"] == 0.0

    assert dossier["net_cash"]["value"] == 22000.0

    prescore = dossier["prescore"]
    assert prescore["passed"] == 8 and prescore["total"] == 8
    small_cap = next(c for c in prescore["checks"] if c["id"] == "small_cap")
    # 259 mln zł comes from the REPORTED profile figure now
    assert "wg BiznesRadar" in small_cap["evidence"]

    # dynamic per-company layer: DEC = small industrial → gross margin leads
    insights = dossier["insights"]
    assert insights["size_code"] == "small"
    assert insights["sector_group"] == "industrial"
    indicator_ids = [i["id"] for i in insights["key_indicators"]]
    assert indicator_ids[0] == "gross_margin"
    assert all(i["verdict"] in ("good", "neutral", "bad", "unknown")
               for i in insights["key_indicators"])
    assert insights["summary"]  # non-empty, honest Polish summary
    assert insights["coverage"]["available"] >= 5
    # stale fixture price (2025-07-01) must be flagged, not glossed over
    assert any("Kurs sprzed" in note for note in insights["data_notes"])

    assert dossier["latest_forecast"] is None
    assert dossier["forum"] == {"topics": 0, "posts": 0, "last_post_at": None}


def test_income_series_prefers_parent_net_profit(refreshed, db):
    """Group vs parent-shareholders net profit: the PARENT row must win
    regardless of row order — EPS/P/E were incomparable between companies
    when 'first row wins' silently depended on the page layout."""
    from sqlalchemy import select

    from app.db.models import Company, ReportValue, utcnow
    from app.services import dossier as dossier_service

    company = db.scalar(select(Company).where(Company.ticker == "DEC"))

    # An isolated period (not in the fixture range) with the parent row AFTER
    # the group row — the old first-row-wins kept the group figure (99 999).
    db.add(ReportValue(
        company_id=company.id, statement="income", freq="Q", period="2019Q4",
        field_code="IncomeNetProfit", field_label="Zysk netto",
        position=90, value=99_999.0, scraped_at=utcnow(),
    ))
    db.add(ReportValue(
        company_id=company.id, statement="income", freq="Q", period="2019Q4",
        field_code="zysk_netto_akcjonariuszy_jednostki_dominujacej",
        field_label="Zysk netto akcjonariuszy jednostki dominującej",
        position=91, value=88_888.0, scraped_at=utcnow(),
    ))
    db.commit()

    series = dossier_service.load_income_series(db, company.id)
    assert series["2019Q4"]["net_profit"] == 88_888.0


def test_forecast_defaults_endpoint(refreshed):
    defaults = refreshed.get("/api/companies/DEC/forecast-defaults").json()
    assert defaults["period"] == "2025Q2"
    assert defaults["revenue"] == 62700.0
    assert defaults["gross_margin_pct"] == 34.0
    assert defaults["selling_costs_pct"] == 12.0
    assert defaults["financial_net"] == -150.0


def test_forecast_preview_compute_save_and_dossier_pickup(refreshed):
    assumptions = {
        "period": "2025Q2", "revenue": 64000, "gross_margin_pct": 33.5,
        "selling_costs_pct": 12.0, "admin_costs": 3900,
        "other_operating": 49.0, "financial_net": -150.0, "depreciation": 2000,
    }

    # preview: computed, not persisted
    preview = refreshed.post(
        "/api/companies/DEC/forecasts",
        json={"assumptions": assumptions, "save": False},
    ).json()
    assert preview["id"] is None
    assert preview["result"]["pnl"]["net_profit"] == 7904.8
    assert preview["result"]["forward"]["pe"] == 9.02
    assert refreshed.get("/api/companies/DEC/forecasts").json() == []

    # save: persisted with attribution from the proxy header
    saved = refreshed.post(
        "/api/companies/DEC/forecasts",
        json={"assumptions": assumptions, "label": "bazowy"},
        headers={"X-User-Email": "kuba@example.com"},
    ).json()
    assert saved["id"] is not None
    assert saved["label"] == "bazowy"

    forecasts = refreshed.get("/api/companies/DEC/forecasts").json()
    assert len(forecasts) == 1

    # the dossier now uses forward P/E (9.02) for the valuation check
    dossier = refreshed.get("/api/companies/DEC").json()
    assert dossier["latest_forecast"]["result"]["forward"]["pe"] == 9.02
    pe_check = next(
        c for c in dossier["prescore"]["checks"] if c["id"] == "pe_vs_history"
    )
    assert "prognozowane" in pe_check["evidence"]
    assert pe_check["verdict"] == "pass"


def test_forecast_defaults_without_data_conflict(client):
    client.post("/api/watchlist", json={"ticker": "EMPTY"})
    response = client.get("/api/companies/EMPTY/forecast-defaults")
    assert response.status_code == 409
    assert "refresh" in response.json()["detail"].lower()


def test_dossier_unknown_company_404(client):
    assert client.get("/api/companies/NOPE").status_code == 404
