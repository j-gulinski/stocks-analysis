"""Phase 3 end-to-end: refresh from fixtures → dossier, forecast endpoints.

Numbers asserted here are the same hand-checked values as in the unit tests —
if these pass, the whole pipeline (parse → upsert → canonical mapping → math →
DTO) is consistent.
"""
import pytest

from app.services import dossier as dossier_service
from tests.test_api_phase1 import fake_fetch


@pytest.fixture()
def refreshed(client, monkeypatch):
    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    response = client.post("/api/companies/DEC/refresh")
    assert response.status_code == 200
    return client


def test_dossier(refreshed, monkeypatch):
    # Freeze "today" so the recorded quote is deterministically older than the
    # seven-day insight threshold. Without this, the assertion changes with the
    # wall clock whenever a price fixture is refreshed.
    from datetime import date as real_date

    class FixedDate(real_date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 15)

    monkeypatch.setattr("app.services.dossier.date", FixedDate)
    dossier = refreshed.get("/api/companies/DEC").json()

    assert dossier["company"]["name"] == "DECORA"
    assert dossier["freshness"]["financials_scraped_at"] is not None
    # The current price chain uses the BiznesRadar archive fixture, not the
    # removed stooq CSV path. Keep this integration expectation tied to the
    # newest row in br_price_history.html.
    assert dossier["freshness"]["last_price_date"] == "2026-07-03"

    quarters = dossier["quarters"]
    assert quarters[-1]["period"] == "2025Q1"
    assert quarters[-1]["gross_margin_pct"] == 34.0
    assert quarters[-1]["revenue_yoy_pct"] == 14.0

    assert dossier["ttm"]["net_profit"] == 26892.0
    assert dossier["ttm"]["eps"] == 2.545
    assert dossier["ttm"]["pe"] == 9.74
    assert dossier["ttm"]["valuation_pe"] == 9.74
    assert dossier["ttm"]["valuation_basis"] == "reported"
    assert dossier["ttm"]["price"] == 24.80

    result_quality = dossier["result_quality"]
    assert result_quality["period"] == "2025Q1"
    assert result_quality["is_material"] is False
    assert result_quality["cause_status"] == "not_applicable"
    assert result_quality["valuation_basis"] == "reported"
    assert result_quality["source_fields"]

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
    # The recorded quote is older than the freshness threshold and must be
    # flagged rather than treated as current merely because it was re-parsed.
    assert any("Kurs sprzed" in note for note in insights["data_notes"])

    assert dossier["latest_forecast"] is None
    assert dossier["forum"] == {
        "topics": 0,
        "posts": 0,
        "last_post_at": None,
        "intelligence": None,
    }
    assert dossier["analysis_context_status"]["premium"]["has_enterprise_value"] is True


def test_dossier_exposes_only_approved_case_assumptions(refreshed):
    """The scenario context is a safe bridge: approved only, provenance intact."""
    created_case = refreshed.post(
        "/api/companies/DEC/research-case",
        json={"state": "scenarios", "current_step": "scenarios"},
    )
    assert created_case.status_code == 201

    approved = refreshed.post(
        "/api/companies/DEC/research-case/assumptions",
        headers={"X-User-Email": "analyst@example.test"},
        json={
            "scenario_kind": "base",
            "label": "Bazowe wejścia zatwierdzone",
            "status": "approved",
            "assumptions": [
                {
                    "key": "revenue_growth",
                    "value": 0.12,
                    "unit": "ratio",
                    "provenance": "evidence",
                    "source_ref": "fact:revenue-growth",
                    "rationale": "Wynika z zamrożonego źródła.",
                }
            ],
        },
    )
    assert approved.status_code == 201

    for scenario_kind, status in (("positive", "draft"), ("negative", "rejected")):
        response = refreshed.post(
            "/api/companies/DEC/research-case/assumptions",
            json={
                "scenario_kind": scenario_kind,
                "label": f"{scenario_kind} wejścia",
                "status": status,
                "assumptions": [],
            },
        )
        assert response.status_code == 201

    dossier = refreshed.get("/api/companies/DEC").json()
    visible = dossier["scenarios"]["approved_assumption_sets"]
    assert len(visible) == 1
    assert visible[0]["label"] == "Bazowe wejścia zatwierdzone"
    assert visible[0]["status"] == "approved"
    assert visible[0]["assumptions"][0]["provenance"] == "evidence"
    assert visible[0]["assumptions"][0]["source_ref"] == "fact:revenue-growth"


def test_consensus_eps_basis_uses_sane_biznesradar_net_income():
    market_snapshot = {
        "forecast_consensus": {
            "2026": {
                "net_income": {
                    "value": 10_000.0,
                    "unit": "tys. PLN",
                    "source": "biznesradar_forecasts",
                },
                "pe": {"value": 10.0, "unit": "x", "source": "biznesradar_forecasts"},
            }
        }
    }

    basis = dossier_service._consensus_eps_basis(
        market_snapshot,
        shares_outstanding=1_000_000,
        current_price=100.0,
    )

    assert basis == {
        "source": "biznesradar_forecasts",
        "source_field": "market_data.forecast_consensus.2026.net_income",
        "source_detail": "biznesradar_forecasts",
        "year": "2026",
        "net_income_tys_pln": 10_000.0,
        "eps": 10.0,
    }


def test_consensus_eps_basis_rejects_inconsistent_consensus_pe():
    market_snapshot = {
        "forecast_consensus": {
            "2026": {
                "net_income": {"value": 9_200_000.0, "unit": "tys. PLN"},
                "pe": {"value": 40.1, "unit": "x"},
            }
        }
    }

    assert (
        dossier_service._consensus_eps_basis(
            market_snapshot,
            shares_outstanding=10_566_435,
            current_price=24.8,
        )
        is None
    )


def test_dossier_read_never_calls_ai_refiners(refreshed, monkeypatch):
    """A GET must stay cheap, quota-free and reproducible even when providers
    are configured. Explicit analysis endpoints own all model calls."""

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("dossier GET attempted an AI refinement")

    monkeypatch.setattr("app.services.thesis_ai.refine_thesis", unexpected_call)
    monkeypatch.setattr("app.services.scenarios_ai.simulate_scenarios", unexpected_call)
    monkeypatch.setattr("app.services.valuation_ai.assess_potential", unexpected_call)

    response = refreshed.get("/api/companies/DEC")
    assert response.status_code == 200
    body = response.json()
    assert body["thesis"]["engine"] == "deterministic"
    assert body["scenarios"]["engine"] == "deterministic"
    assert body["valuation"]["engine"] == "deterministic"
    assert body["thesis"]["ai_notes"] is None
    assert body["scenarios"]["ai_notes"] is None
    assert body["valuation"]["ai_notes"] is None


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
    assert preview["result"]["forward"]["pe"] == 9.13
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

    # the dossier now uses forward P/E (9.13) for the valuation check
    dossier = refreshed.get("/api/companies/DEC").json()
    assert dossier["latest_forecast"]["result"]["forward"]["pe"] == 9.13
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
