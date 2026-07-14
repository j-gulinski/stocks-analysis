"""Immutable portfolio sync, read, mapping, analytics and auth contracts."""

import hashlib
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.db.models import (
    Company,
    InstrumentMapping,
    Portfolio,
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
    PortfolioSync,
    ResearchCase,
    CompanyProfile,
    ResearchSnapshot,
    ValuationSnapshot,
    AgentRun,
    VerificationRun,
    PortfolioReviewSnapshot,
    Price,
    ThesisFalsifier,
)
from app.services.agent_queue import claim_agent_run
from app.services.portfolio import normalize_myfund
from app.services.valuation_engine import canonical_hash


def payload(*, snt_value=6000.0):
    total = snt_value + 4000
    return {
        "status": {"code": 0, "text": "OK"},
        "portfel": {
            "wartosc": str(total),
            "zysk": "1000",
            "waluta": "PLN",
            "benchName": "WIG",
        },
        "tickers": {
            "1": {
                "tickerClear": "SNT",
                "nazwa": "Synektik (SNT)",
                "typOrg": "Akcje GPW",
                "waluta": "PLN",
                "data": "2026-07-10",
                "close": "300",
                "liczbaJednostek": "20",
                "wartosc": str(snt_value),
                "zysk": "500",
                "udzial": str(snt_value / total * 100),
                "sektor": "Ochrona zdrowia",
            },
            "2": {
                "tickerClear": "FUND-X",
                "nazwa": "Fundusz X",
                "typOrg": "Fundusz",
                "waluta": "PLN",
                "wartosc": "3000",
                "zysk": "400",
                "udzial": str(3000 / total * 100),
            },
            "3": {
                "tickerClear": "PLN",
                "nazwa": "Gotówka PLN",
                "typOrg": "Gotówka",
                "waluta": "PLN",
                "wartosc": "1000",
                "zysk": "0",
                "udzial": str(1000 / total * 100),
            },
        },
        "wartoscWCzasie": [
            ["2026-07-09", str(total - 100)],
            ["2026-07-10", str(total)],
        ],
        "wkladWCzasie": {"2026-07-09": "9000", "2026-07-10": "9000"},
        "zyskWCzasie": {"a": {"data": "2026-07-10", "wartosc": "1000"}},
        "stopaZwrotuWCzasie": {"2026-07-10": "11.11"},
        "benchWCzasie": {"2026-07-10": "4.2"},
    }


def settings():
    return SimpleNamespace(
        myfund_api_key="secret",
        myfund_portfolio="IKE",
        myfund_base_url="https://myfund.pl/",
        api_token=None,
    )


class Response:
    def __init__(self, value):
        self.value = value

    def json(self):
        return self.value


def test_normalizer_accepts_scalar_status_and_tuple_series_and_rejects_bad_values():
    raw = payload()
    raw["status"] = 0
    normalized = normalize_myfund(raw)
    assert normalized.summary["total_value"] == 10000
    assert normalized.history[0]["value"] == 9900
    raw = payload()
    raw["tickers"]["1"]["wartosc"] = "nan"
    with pytest.raises(ValueError):
        normalize_myfund(raw)
    with pytest.raises(ValueError):
        normalize_myfund({"status": 7})


def test_valuation_snapshot_metadata_keeps_named_run_and_verification_uniqueness():
    names = {constraint.name for constraint in ValuationSnapshot.__table__.constraints}
    assert "uq_valuation_snapshot_agent_run" in names
    assert "uq_valuation_snapshot_verification_run" in names


def test_normalizer_reports_each_malformed_history_series_point():
    raw = payload()
    raw["benchWCzasie"] = {
        "bad-date": "4.2",
        "2026-07-09": "nan",
        "2026-07-10": "3.1",
    }
    normalized = normalize_myfund(raw)
    assert normalized.history[-1]["benchmark_return_pct"] == 3.1
    assert (
        "Historia benchmark_return_pct: pominięto 2 z 3 błędnych punktów."
        in normalized.gaps
    )


def test_current_cost_and_profit_come_only_from_complete_position_rows():
    raw = payload()
    raw["portfel"]["zysk"] = "90610.01"
    normalized = normalize_myfund(raw)
    assert normalized.summary["profit"] == 900
    assert normalized.summary["cost_basis"] == 9100
    assert (
        normalized.summary["cost_basis"] + normalized.summary["profit"]
        == normalized.summary["total_value"]
    )
    assert normalized.history[-1]["profit"] == 1000

    raw["tickers"]["2"].pop("zysk")
    incomplete = normalize_myfund(raw)
    assert incomplete.summary["profit"] is None
    assert incomplete.summary["cost_basis"] is None
    assert any("nie każda pozycja ma wynik" in gap for gap in incomplete.gaps)


def test_empty_portfolio_has_zero_current_result_but_missing_positive_rows_do_not():
    empty = payload()
    empty["portfel"]["wartosc"] = "0"
    empty["portfel"]["zysk"] = "123"
    empty["tickers"] = {}
    normalized_empty = normalize_myfund(empty)
    assert normalized_empty.summary["profit"] == 0
    assert normalized_empty.summary["cost_basis"] == 0
    assert normalized_empty.positions == []
    assert not any("bez pozycji składowych" in gap for gap in normalized_empty.gaps)

    missing = payload()
    missing["portfel"]["wartosc"] = "100"
    missing["tickers"] = {}
    normalized_missing = normalize_myfund(missing)
    assert normalized_missing.summary["profit"] is None
    assert normalized_missing.summary["cost_basis"] is None
    assert any("bez pozycji składowych" in gap for gap in normalized_missing.gaps)


def test_dict_native_keys_prevent_duplicate_ticker_mapping_collision(
    client, db, monkeypatch
):
    from app.api import portfolios

    company = Company(ticker="DUP", name="Duplicate GPW")
    db.add(company)
    db.commit()
    raw = payload()
    raw["portfel"]["wartosc"] = "150"
    pln = {
        "tickerClear": "DUP",
        "nazwa": "Duplicate GPW (DUP)",
        "typOrg": "Akcje GPW",
        "waluta": "PLN",
        "wartosc": "100",
    }
    usd = {
        "tickerClear": "DUP",
        "nazwa": "Duplicate ETF",
        "typOrg": "ETF",
        "waluta": "USD",
        "wartosc": "50",
    }
    raw["tickers"] = {"provider-stock-17": pln, "provider-etf-91": usd}
    reversed_raw = {
        **raw,
        "tickers": {"provider-etf-91": usd, "provider-stock-17": pln},
    }
    monkeypatch.setattr(portfolios, "get_settings", settings)
    values = [raw, reversed_raw]
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(values.pop(0))
    )
    first = client.post("/api/portfolios/sync/myfund")
    assert first.status_code == 200, first.text
    positions = first.json()["positions"]
    assert len({row["mapping_id"] for row in positions}) == 2
    pln_row = next(row for row in positions if row["currency"] == "PLN")
    usd_row = next(row for row in positions if row["currency"] == "USD")
    assert pln_row["mapping_kind"] == "company" and pln_row["company_id"] == company.id
    assert (
        usd_row["mapping_kind"] == "other" and usd_row["mapping_status"] == "unmatched"
    )
    mappings = list(
        db.scalars(select(InstrumentMapping).order_by(InstrumentMapping.provider_key))
    )
    assert {row.provider_key for row in mappings} == {
        "myfund:native:provider-stock-17",
        "myfund:native:provider-etf-91",
    }
    assert all(len(row.provider_key) <= 200 for row in mappings)
    reordered = client.post("/api/portfolios/sync/myfund").json()
    assert reordered["sync"]["reused_snapshot"] is True
    usd_again = next(row for row in reordered["positions"] if row["currency"] == "USD")
    assert usd_again["mapping_id"] == usd_row["mapping_id"]
    assert usd_again["mapping_status"] == "unmatched"


def test_list_identity_is_order_stable_and_duplicate_rows_share_mapping_identity():
    row_a = {
        "tickerClear": "AAA",
        "nazwa": "Alpha",
        "typOrg": "Akcje",
        "waluta": "PLN",
        "konto": "IKE",
        "wartosc": "100",
    }
    row_b = {
        "tickerClear": "BBB",
        "nazwa": "Beta",
        "typOrg": "ETF",
        "waluta": "USD",
        "konto": "IKE",
        "wartosc": "50",
    }
    first = payload()
    first["portfel"]["wartosc"] = "150"
    first["tickers"] = [row_a, row_b]
    second = payload()
    second["portfel"]["wartosc"] = "150"
    second["tickers"] = [row_b, row_a]
    normalized_first = normalize_myfund(first)
    normalized_second = normalize_myfund(second)
    keys_first = {
        row["ticker"]: row["provider_key"] for row in normalized_first.positions
    }
    keys_second = {
        row["ticker"]: row["provider_key"] for row in normalized_second.positions
    }
    assert keys_first == keys_second
    assert normalized_first.fingerprint == normalized_second.fingerprint
    duplicate = payload()
    duplicate["portfel"]["wartosc"] = "200"
    duplicate["tickers"] = [row_a, row_a]
    rows = normalize_myfund(duplicate).positions
    assert rows[0]["provider_key"] == rows[1]["provider_key"]
    assert rows[0]["row_key"] != rows[1]["row_key"]


def test_sequential_dict_keys_are_positions_not_native_identity():
    row_a = {
        "tickerClear": "ALPHA",
        "nazwa": "Alpha (AAA)",
        "typOrg": "Akcje GPW",
        "waluta": "PLN",
        "kontoInvName": "IKE",
        "wartosc": "100",
        "zysk": "10",
    }
    row_b = {
        "tickerClear": "BETA",
        "nazwa": "Beta (BBB)",
        "typOrg": "Akcje GPW",
        "waluta": "PLN",
        "kontoInvName": "IKE",
        "wartosc": "50",
        "zysk": "5",
    }
    first = payload()
    first["portfel"]["wartosc"] = "150"
    first["tickers"] = {"0": row_a, "1": row_b}
    reordered = payload()
    reordered["portfel"]["wartosc"] = "150"
    reordered["tickers"] = {"0": row_b, "1": row_a}
    normalized_first = normalize_myfund(first)
    normalized_reordered = normalize_myfund(reordered)
    assert normalized_first.fingerprint == normalized_reordered.fingerprint
    assert {
        row["ticker"]: row["provider_key"] for row in normalized_first.positions
    } == {row["ticker"]: row["provider_key"] for row in normalized_reordered.positions}
    assert all(
        row["provider_key"].startswith("myfund:canonical-sha256:")
        for row in normalized_first.positions
    )

    duplicate = payload()
    duplicate["portfel"]["wartosc"] = "200"
    duplicate["tickers"] = {"0": row_a, "1": row_a}
    duplicate_rows = normalize_myfund(duplicate).positions
    assert duplicate_rows[0]["provider_key"] == duplicate_rows[1]["provider_key"]
    assert duplicate_rows[0]["row_key"] != duplicate_rows[1]["row_key"]

    second_account = {**row_a, "kontoInvName": "Zwykły"}
    accounts = payload()
    accounts["portfel"]["wartosc"] = "200"
    accounts["tickers"] = {"0": row_a, "1": second_account}
    account_rows = normalize_myfund(accounts).positions
    assert account_rows[0]["provider_key"] != account_rows[1]["provider_key"]


def test_live_display_identity_matches_only_an_existing_company(
    client, db, monkeypatch
):
    from app.api import portfolios

    company = Company(ticker="SNT", name="Synektik")
    db.add(company)
    db.commit()
    raw = payload()
    raw["portfel"]["wartosc"] = "150"
    raw["tickers"] = {
        "0": {
            "tickerClear": "SYNEKTIK",
            "ticker": "SYNEKTIK (SNT)",
            "typOrg": "Akcje GPW",
            "waluta": "PLN",
            "wartosc": "100",
            "zysk": "10",
        },
        "1": {
            "tickerClear": "ALPHA",
            "ticker": "ALPHA (ABC)",
            "typOrg": "Akcje GPW",
            "waluta": "PLN",
            "wartosc": "50",
            "zysk": "5",
        },
    }
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    synced = client.post("/api/portfolios/sync/myfund").json()
    by_name = {row["name"]: row for row in synced["positions"]}
    assert by_name["SYNEKTIK (SNT)"]["company_id"] == company.id
    assert by_name["ALPHA (ABC)"]["mapping_status"] == "unmatched"
    assert db.scalar(select(Company).where(Company.ticker == "ABC")) is None
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == 0
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0


def test_native_provider_keys_preserve_case_identity():
    raw = payload()
    row = {
        "tickerClear": "AAA",
        "nazwa": "Alpha",
        "typOrg": "Akcje",
        "waluta": "PLN",
        "wartosc": "25",
    }
    raw["portfel"]["wartosc"] = "100"
    raw["tickers"] = {
        "ABC": row,
        "abc": row,
        "account  1": row,
        "account 1": row,
    }
    positions = normalize_myfund(raw).positions
    assert {item["provider_key"] for item in positions} == {
        "myfund:native:ABC",
        "myfund:native:abc",
        "myfund:native:account  1",
        "myfund:native:account 1",
    }
    long_key = "  AbC  " * 40
    long_raw = payload()
    long_raw["portfel"]["wartosc"] = "25"
    long_raw["tickers"] = {long_key: row}
    long_provider_key = normalize_myfund(long_raw).positions[0]["provider_key"]
    assert long_provider_key == (
        "myfund:native-sha256:" + hashlib.sha256(long_key.encode("utf-8")).hexdigest()
    )
    assert len(long_provider_key) <= 200


def test_cash_requires_exact_provider_asset_type_not_free_text(client, db, monkeypatch):
    from app.api import portfolios

    raw = payload()
    raw["portfel"]["wartosc"] = "60"
    raw["tickers"] = {
        "etf": {
            "tickerClear": "CASHETF",
            "nazwa": "WisdomTree US Cash ETF",
            "typOrg": "ETF",
            "waluta": "USD",
            "wartosc": "20",
        },
        "company": {
            "tickerClear": "CFS",
            "nazwa": "Cash flow Systems SA",
            "typOrg": "Akcje",
            "waluta": "PLN",
            "wartosc": "30",
        },
        "cash": {
            "tickerClear": "PLN",
            "nazwa": "Dowolna etykieta",
            "typOrg": "Konta gotówkowe",
            "waluta": "PLN",
            "wartosc": "10",
        },
    }
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    body = client.post("/api/portfolios/sync/myfund").json()
    by_ticker = {row["ticker"]: row for row in body["positions"]}
    assert (
        by_ticker["PLN"]["mapping_kind"] == "cash"
        and by_ticker["PLN"]["mapping_status"] == "exact"
    )
    assert by_ticker["CASHETF"]["mapping_kind"] == "other"
    assert by_ticker["CFS"]["mapping_kind"] == "other"
    assert by_ticker["CASHETF"]["mapping_status"] == "unmatched"
    assert by_ticker["CFS"]["mapping_status"] == "unmatched"


def test_unreconciled_snapshot_warns_keeps_partial_analytics_and_allows_review(
    client, db, monkeypatch
):
    from app.api import portfolios

    raw = payload()
    raw["portfel"]["wartosc"] = "100"
    raw["tickers"] = {
        "1": {"tickerClear": "A", "nazwa": "A", "waluta": "PLN", "wartosc": "100"},
        "2": {"tickerClear": "B", "nazwa": "B", "waluta": "PLN", "wartosc": "100"},
    }
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    synced = client.post("/api/portfolios/sync/myfund")
    assert synced.status_code == 200, synced.text
    body = synced.json()
    assert {
        key: body["reconciliation"][key]
        for key in ("status", "retained_value", "provider_total", "delta", "tolerance")
    } == {
        "status": "unreconciled",
        "retained_value": 200.0,
        "provider_total": 100.0,
        "delta": 100.0,
        "tolerance": 0.1,
    }
    assert body["reconciliation"]["affected_figures"]
    assert body["concentration"] == {
        "status": "partial",
        "basis": "retained_positions_total",
        "basis_value": 200.0,
        "top1_pct": 50.0,
        "top3_pct": 100.0,
        "hhi": 0.5,
        "sectors": [
            {"label": "Nieokreślony", "value": 200.0, "allocation_pct": 100.0}
        ],
        "asset_types": [
            {"label": "Inne", "value": 200.0, "allocation_pct": 100.0}
        ],
    }
    assert isinstance(body["liquidity"], list)
    assert body["scenario_sensitivity"] is not None
    assert body["scenario_sensitivity"]["reconciliation_status"] == "unreconciled"
    assert body["risk_context"] is not None
    assert body["coverage"]["mapped_company_value_pct"] == 0
    assert body["coverage"]["retained_position_value_pct"] == 200
    assert body["coverage"]["analytics_available"] is True
    assert body["coverage"]["analytics_status"] == "partial"

    queued = client.post("/api/portfolios/review-runs")
    assert queued.status_code == 201, queued.text
    agent = db.get(AgentRun, queued.json()["agent_run_id"])
    frozen = agent.inputs["portfolio_review"]
    assert frozen["analytics"]["reconciliation"]["status"] == "unreconciled"
    assert frozen["analytics"]["concentration"]["status"] == "partial"
    assert any("podstawę częściową" in gap for gap in frozen["gaps"])


def test_workspace_get_is_zero_write_and_never_fetches(client, db, monkeypatch):
    from app.api import portfolios

    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http,
        "fetch",
        lambda *a, **k: pytest.fail("GET fetched provider"),
    )
    before = (
        db.scalar(select(func.count()).select_from(Portfolio)),
        db.scalar(select(func.count()).select_from(PortfolioSync)),
    )
    response = client.get("/api/portfolios/workspace")
    assert response.status_code == 200
    assert response.json()["configured"] is True and response.json()["snapshot"] is None
    db.expire_all()
    assert before == (
        db.scalar(select(func.count()).select_from(Portfolio)),
        db.scalar(select(func.count()).select_from(PortfolioSync)),
    )


def test_sync_preserves_unknowns_reuses_identical_and_versions_changes(
    client, db, monkeypatch
):
    from app.api import portfolios

    db.add(Company(ticker="SNT", name="Synektik", sector="Ochrona zdrowia"))
    db.commit()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    values = [payload(), payload(), payload(snt_value=7000), payload()]
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(values.pop(0))
    )
    first = client.post("/api/portfolios/sync/myfund")
    assert first.status_code == 200
    body = first.json()
    assert body["snapshot"]["version"] == 1
    assert len(body["positions"]) == 3
    assert {p["mapping_status"] for p in body["positions"]} == {"exact", "unmatched"}
    assert body["snapshot"]["cash_value"] == 1000
    assert body["performance_methods"]["twr"] == "unavailable"
    assert body["scenario_sensitivity"]["coverage_value_pct"] == 0
    assert any(
        x.get("latest_status") is None
        for x in body["scenario_sensitivity"]["exclusions"]
    )
    second = client.post("/api/portfolios/sync/myfund").json()
    assert (
        second["sync"]["reused_snapshot"] is True and second["snapshot"]["version"] == 1
    )
    third = client.post("/api/portfolios/sync/myfund").json()
    assert third["snapshot"]["version"] == 2
    reverted = client.post("/api/portfolios/sync/myfund").json()
    assert (
        reverted["sync"]["reused_snapshot"] is False
        and reverted["snapshot"]["version"] == 3
    )
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(PortfolioSync)) == 4
    assert db.scalar(select(func.count()).select_from(PortfolioSnapshot)) == 3
    assert db.scalar(select(func.count()).select_from(PortfolioPositionSnapshot)) == 9


def test_cash_value_distinguishes_absent_row_from_explicit_zero(
    client, db, monkeypatch
):
    from app.api import portfolios

    no_cash = payload()
    no_cash["tickers"].pop("3")
    no_cash["portfel"]["wartosc"] = "9000"
    explicit_zero = payload()
    explicit_zero["tickers"]["3"]["wartosc"] = "0"
    explicit_zero["portfel"]["wartosc"] = "9000"
    monkeypatch.setattr(portfolios, "get_settings", settings)
    values = [no_cash, explicit_zero]
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(values.pop(0))
    )
    absent = client.post("/api/portfolios/sync/myfund")
    assert absent.status_code == 200, absent.text
    assert absent.json()["reconciliation"]["status"] == "reconciled"
    assert absent.json()["snapshot"]["cash_value"] is None
    zero = client.post("/api/portfolios/sync/myfund")
    assert zero.status_code == 200, zero.text
    assert zero.json()["reconciliation"]["status"] == "reconciled"
    assert zero.json()["snapshot"]["cash_value"] == 0


def test_failed_sync_is_committed_and_last_good_remains(client, db, monkeypatch):
    from app.api import portfolios

    monkeypatch.setattr(portfolios, "get_settings", settings)
    values = [payload(), {"status": 7, "text": "private provider detail"}]
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(values.pop(0))
    )
    assert client.post("/api/portfolios/sync/myfund").status_code == 200
    failed = client.post("/api/portfolios/sync/myfund")
    assert failed.status_code == 502 and "private" not in failed.text
    db.expire_all()
    rows = db.scalars(select(PortfolioSync).order_by(PortfolioSync.id)).all()
    assert [r.status for r in rows] == ["succeeded", "failed"]
    assert rows[-1].provider_status_code == "7" and "private" not in (
        rows[-1].error or ""
    )
    workspace = client.get("/api/portfolios/workspace").json()
    assert (
        workspace["snapshot"]["version"] == 1
        and workspace["last_sync_failure"]["status"] == "failed"
    )


def test_history_quality_is_partial_and_future_known_price_is_excluded(
    client, db, monkeypatch
):
    from app.api import portfolios

    company = Company(ticker="SNT", name="Synektik")
    db.add(company)
    db.commit()
    raw = payload()
    raw["benchWCzasie"] = {"bad-date": "4.2", "2026-07-10": "3.1"}
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    synced = client.post("/api/portfolios/sync/myfund").json()
    assert synced["history_quality"]["status"] == "partial"
    assert len(synced["history_quality"]["gaps"]) == 1
    snapshot = db.get(PortfolioSnapshot, synced["snapshot"]["id"])
    as_of = (
        snapshot.as_of.replace(tzinfo=timezone.utc)
        if snapshot.as_of.tzinfo is None
        else snapshot.as_of
    )
    for offset in range(1, 20):
        db.add(
            Price(
                company_id=company.id,
                date=as_of.date() - timedelta(days=offset),
                close=10,
                volume=1000,
                adjustment_status="raw_unverified",
                scraped_at=as_of - timedelta(days=1),
            )
        )
    future_known = Price(
        company_id=company.id,
        date=as_of.date(),
        close=10,
        volume=1000,
        adjustment_status="raw_unverified",
        scraped_at=as_of + timedelta(days=1),
    )
    db.add(future_known)
    db.commit()
    liquidity = client.get("/api/portfolios/workspace").json()["liquidity"]
    assert liquidity[0]["status"] == "unavailable"
    future_known.scraped_at = as_of - timedelta(hours=1)
    db.commit()
    liquidity = client.get("/api/portfolios/workspace").json()["liquidity"]
    assert liquidity[0]["status"] == "provisional"
    assert liquidity[0]["median_20d_traded_value_pln"] == 10000


def test_risk_context_freezes_research_profiles_current_falsifiers_and_coexposure(
    client, db, monkeypatch
):
    from app.api import portfolios

    companies = [
        Company(ticker="SNT", name="Synektik", sector="Zdrowie"),
        Company(ticker="ABS", name="ABS", sector="Zdrowie"),
    ]
    db.add_all(companies)
    db.commit()
    raw = payload()
    raw["tickers"]["2"].update(
        {
            "tickerClear": "ABS",
            "nazwa": "ABS (ABS)",
            "typOrg": "Akcje GPW",
        }
    )
    raw["tickers"]["1"]["sektor"] = "Zdrowie"
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    synced = client.post("/api/portfolios/sync/myfund").json()
    snapshot = db.get(PortfolioSnapshot, synced["snapshot"]["id"])
    as_of = (
        snapshot.as_of.replace(tzinfo=timezone.utc)
        if snapshot.as_of.tzinfo is None
        else snapshot.as_of
    )
    research_rows = []
    for company in companies:
        case = ResearchCase(
            company_id=company.id,
            purpose="investment-research",
            state="monitoring",
            current_step="research",
        )
        db.add(case)
        db.flush()
        profile = CompanyProfile(
            research_case_id=case.id,
            version=1,
            schema_version="v2",
            archetype="industrial-consumer",
            archetype_version="v1",
            company_overlay={},
            drivers=[{"key": "gross_margin"}],
            kpis=[],
        )
        db.add(profile)
        db.flush()
        run = AgentRun(
            workflow="stock-initial-research",
            status="completed",
            company_id=company.id,
            inputs={},
            outputs={},
        )
        db.add(run)
        db.flush()
        verification = VerificationRun(
            agent_run_id=run.id,
            model_role="verifier_strict",
            verifier_model="test",
            verdict="pass",
            checks={},
        )
        db.add(verification)
        db.flush()
        research = ResearchSnapshot(
            research_case_id=case.id,
            company_profile_id=profile.id,
            agent_run_id=run.id,
            verification_run_id=verification.id,
            version=1,
            contract_version="v2",
            status="verified",
            as_of=as_of - timedelta(days=30),
            input_fingerprint="i",
            artifact_fingerprint=("a" if company.ticker == "SNT" else "b") * 64,
            sections={},
            source_manifest=[],
            conflicts=[],
            gaps=["named-gap"] if company.ticker == "ABS" else [],
            next_checks=[],
            statement_provenance=[],
            verifier_result={},
        )
        db.add(research)
        research_rows.append(research)
    db.flush()
    snt_case = db.get(ResearchCase, research_rows[0].research_case_id)
    future_run = AgentRun(
        workflow="stock-initial-research",
        status="completed",
        company_id=companies[0].id,
        inputs={},
        outputs={},
    )
    db.add(future_run)
    db.flush()
    future_verification = VerificationRun(
        agent_run_id=future_run.id,
        model_role="verifier_strict",
        verifier_model="test",
        verdict="pass",
        checks={},
    )
    db.add(future_verification)
    db.flush()
    db.add(
        ResearchSnapshot(
            research_case_id=snt_case.id,
            company_profile_id=research_rows[0].company_profile_id,
            agent_run_id=future_run.id,
            verification_run_id=future_verification.id,
            version=2,
            contract_version="v2",
            status="verified",
            as_of=as_of + timedelta(days=1),
            input_fingerprint="future",
            artifact_fingerprint="f" * 64,
            sections={},
            source_manifest=[],
            conflicts=[],
            gaps=[],
            next_checks=[],
            statement_provenance=[],
            verifier_result={},
        )
    )
    falsifier = ThesisFalsifier(
        company_id=companies[0].id,
        key="margin",
        statement="Marża spada.",
        status="fired",
        reason="Bieżący sygnał.",
        review_date=as_of.date(),
        thesis_hash="c" * 64,
        created_at=as_of - timedelta(days=2),
        updated_at=as_of + timedelta(days=1),
    )
    known_falsifier = ThesisFalsifier(
        company_id=companies[1].id,
        key="debt",
        statement="Dług rośnie.",
        status="fired",
        reason="Znany przed snapshotem.",
        review_date=as_of.date(),
        thesis_hash="d" * 64,
        created_at=as_of - timedelta(days=5),
        updated_at=as_of - timedelta(days=1),
    )
    db.add_all([falsifier, known_falsifier])
    db.commit()
    context = client.get("/api/portfolios/workspace").json()["risk_context"]
    assert context["version"] == "portfolio-risk-context-v1"
    assert len(context["companies"]) == 2
    snt = next(row for row in context["companies"] if row["ticker"] == "SNT")
    assert snt["research"]["id"] == research_rows[0].id
    assert snt["profile"]["driver_keys"] == ["gross_margin"]
    assert snt["snapshot_known_fired_count"] == 0
    assert snt["snapshot_known_fired_falsifiers"] == []
    assert snt["current_only_fired_count"] == 1
    assert len(snt["current_only_fired_falsifiers"]) == 1
    assert snt["falsifiers"][0]["known_by_snapshot"] is False
    assert snt["falsifiers"][0]["changed_after_snapshot"] is True
    assert snt["falsifiers"][0]["status_basis"] == "current-only-no-history"
    abs_row = next(row for row in context["companies"] if row["ticker"] == "ABS")
    assert abs_row["snapshot_known_fired_count"] == 1
    assert abs_row["current_only_fired_count"] == 0
    assert abs_row["snapshot_known_fired_falsifiers"][0]["status_basis"] == (
        "snapshot-known-current-row-no-history"
    )
    assert context["snapshot_as_of"] == synced["snapshot"]["as_of"]
    assert context["context_generated_at"] == snt["falsifiers"][0]["updated_at"]
    group_types = {row["group_type"] for row in context["shared_groups"]}
    assert group_types == {"sector", "archetype"}
    assert {row["time_basis"] for row in context["shared_groups"]} == {
        "snapshot-known",
        "includes-current-only",
    }
    sector_group = next(
        row for row in context["shared_groups"] if row["group_type"] == "sector"
    )
    assert sector_group["time_basis"] == "includes-current-only"
    assert any(
        item["company_metadata_updated_at"] for item in sector_group["evidence_basis"]
    )
    assert all(
        "not covariance" in row["interpretation"] for row in context["shared_groups"]
    )
    queued = client.post("/api/portfolios/review-runs").json()
    frozen = db.get(AgentRun, queued["agent_run_id"]).inputs["portfolio_review"]
    frozen_context = frozen["analytics"]["risk_context"]
    frozen_snt = next(
        row for row in frozen_context["companies"] if row["ticker"] == "SNT"
    )
    assert frozen_snt["research"]["id"] == research_rows[0].id
    assert frozen_snt["falsifiers"][0]["changed_after_snapshot"] is True
    assert frozen["risk_context_fingerprint"] == canonical_hash(frozen_context)


def test_mapping_patch_reinterprets_workspace_and_survives_identical_sync(
    client, db, monkeypatch
):
    from app.api import portfolios

    db.add(Company(ticker="SNT", name="Synektik"))
    db.commit()
    raw = payload()
    raw["tickers"]["2"].update(
        {
            "tickerClear": "ALPHA",
            "nazwa": "Alpha SA (ABC)",
            "typOrg": "Akcje GPW",
            "waluta": "PLN",
        }
    )
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    body = client.post("/api/portfolios/sync/myfund").json()
    unmatched = next(p for p in body["positions"] if p["mapping_status"] == "unmatched")
    cash = next(p for p in body["positions"] if p["mapping_kind"] == "cash")
    assert (
        client.patch(
            f"/api/portfolios/mappings/{cash['mapping_id']}",
            json={"company_ticker": "ABC"},
        ).status_code
        == 409
    )
    patched = client.patch(
        f"/api/portfolios/mappings/{unmatched['mapping_id']}",
        json={"company_ticker": "ABC"},
    )
    assert (
        patched.status_code == 200 and patched.json()["mapping_status"] == "confirmed"
    )
    company = db.scalar(select(Company).where(Company.ticker == "ABC"))
    assert company is not None
    assert company.name == "Alpha SA" and company.market == "GPW"
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == 0
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0
    reread = client.get("/api/portfolios/workspace").json()
    interpreted = next(
        p for p in reread["positions"] if p["mapping_id"] == unmatched["mapping_id"]
    )
    assert (
        interpreted["mapping_status"] == "confirmed"
        and interpreted["company_id"] is not None
        and interpreted["company_ticker"] == "ABC"
    )
    repeated = client.post("/api/portfolios/sync/myfund").json()
    assert repeated["sync"]["reused_snapshot"] is True
    interpreted = next(
        p for p in repeated["positions"] if p["mapping_id"] == unmatched["mapping_id"]
    )
    assert interpreted["mapping_status"] == "confirmed"
    ignored = client.patch(
        f"/api/portfolios/mappings/{unmatched['mapping_id']}", json={"ignored": True}
    )
    assert ignored.json()["mapping_status"] == "ignored"
    corrected = client.patch(
        f"/api/portfolios/mappings/{unmatched['mapping_id']}",
        json={"company_ticker": "ABC"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["company_id"] == company.id


@pytest.mark.parametrize(
    ("name", "asset_type", "currency", "confirmed", "expected_status"),
    [
        ("Alpha SA (ABC)", "Akcje GPW", "PLN", "XYZ", 422),
        ("Alpha SA (ABC) (XYZ)", "Akcje GPW", "PLN", "XYZ", 422),
        ("Alpha SA (ABC)", "ETF", "PLN", "ABC", 422),
        ("Alpha SA (ABC)", "Akcje GPW", "USD", "ABC", 422),
    ],
)
def test_mapping_patch_rejects_mismatch_ambiguous_or_non_gpw_identity(
    client,
    db,
    monkeypatch,
    name,
    asset_type,
    currency,
    confirmed,
    expected_status,
):
    from app.api import portfolios

    raw = payload()
    raw["portfel"]["wartosc"] = "100"
    raw["tickers"] = {
        "provider-row": {
            "tickerClear": "ALPHA",
            "nazwa": name,
            "typOrg": asset_type,
            "waluta": currency,
            "wartosc": "100",
            "zysk": "10",
        }
    }
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    synced = client.post("/api/portfolios/sync/myfund").json()
    mapping_id = synced["positions"][0]["mapping_id"]
    response = client.patch(
        f"/api/portfolios/mappings/{mapping_id}",
        json={"company_ticker": confirmed},
    )
    assert response.status_code == expected_status
    assert db.scalar(select(Company).where(Company.ticker == confirmed)) is None


def test_verified_scenario_aggregation_is_point_in_time_and_arithmetic(
    client, db, monkeypatch
):
    from app.api import portfolios

    company = Company(ticker="SNT", name="Synektik")
    db.add(company)
    db.commit()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    synced = client.post("/api/portfolios/sync/myfund").json()
    snapshot_id = synced["snapshot"]["id"]
    case = ResearchCase(
        company_id=company.id,
        purpose="investment-research",
        state="monitoring",
        current_step="research",
    )
    db.add(case)
    db.flush()
    profile = CompanyProfile(
        research_case_id=case.id,
        version=1,
        schema_version="v2",
        archetype="industrial_consumer",
        archetype_version="v1",
        company_overlay={},
        drivers=[],
        kpis=[],
    )
    db.add(profile)
    db.flush()
    research_run = AgentRun(
        workflow="stock-initial-research",
        status="completed",
        company_id=company.id,
        inputs={},
        outputs={},
    )
    db.add(research_run)
    db.flush()
    research_verify = VerificationRun(
        agent_run_id=research_run.id,
        model_role="verifier_strict",
        verifier_model="test",
        verdict="pass",
        checks={},
    )
    db.add(research_verify)
    db.flush()
    research = ResearchSnapshot(
        research_case_id=case.id,
        company_profile_id=profile.id,
        agent_run_id=research_run.id,
        verification_run_id=research_verify.id,
        version=1,
        contract_version="v2",
        status="verified",
        as_of=datetime(2026, 7, 10, tzinfo=timezone.utc),
        input_fingerprint="i",
        artifact_fingerprint="a" * 64,
        sections={},
        source_manifest=[],
        conflicts=[],
        gaps=[],
        next_checks=[],
        statement_provenance=[],
        verifier_result={},
    )
    db.add(research)
    db.flush()
    val_run = AgentRun(
        workflow="stock-company-valuation",
        status="completed",
        company_id=company.id,
        inputs={},
        outputs={},
    )
    db.add(val_run)
    db.flush()
    val_verify = VerificationRun(
        agent_run_id=val_run.id,
        model_role="verifier_strict",
        verifier_model="test",
        verdict="pass",
        checks={},
    )
    db.add(val_verify)
    db.flush()
    valuation = ValuationSnapshot(
        research_case_id=case.id,
        research_snapshot_id=research.id,
        agent_run_id=val_run.id,
        verification_run_id=val_verify.id,
        version=1,
        contract_version="v1",
        status="verified",
        as_of=datetime(2026, 7, 10, tzinfo=timezone.utc),
        template_id="industrial",
        template_version="v1",
        calculation_engine_version="v2",
        assumptions={},
        base_values={},
        deterministic_outputs={
            "scenarios": [
                {"kind": "negative", "target_price_pln": 100},
                {"kind": "base", "target_price_pln": 200},
                {"kind": "positive", "target_price_pln": 400},
            ],
            "probability_weighted": {"price_pln": 250},
        },
        codex_judgment={},
        input_manifest={},
        gaps=[],
        input_fingerprint="b" * 64,
        calculation_fingerprint="c" * 64,
        artifact_fingerprint="d" * 64,
        verifier_result={},
    )
    db.add(valuation)
    db.commit()
    # A future Research version must not invalidate an older frozen portfolio read.
    future_run = AgentRun(
        workflow="stock-initial-research",
        status="completed",
        company_id=company.id,
        inputs={},
        outputs={},
    )
    db.add(future_run)
    db.flush()
    future_verify = VerificationRun(
        agent_run_id=future_run.id,
        model_role="verifier_strict",
        verifier_model="test",
        verdict="pass",
        checks={},
    )
    db.add(future_verify)
    db.flush()
    future = ResearchSnapshot(
        research_case_id=case.id,
        company_profile_id=profile.id,
        agent_run_id=future_run.id,
        verification_run_id=future_verify.id,
        version=2,
        contract_version="v2",
        status="verified",
        as_of=datetime(2027, 1, 1, tzinfo=timezone.utc),
        input_fingerprint="future",
        artifact_fingerprint="e" * 64,
        sections={},
        source_manifest=[],
        conflicts=[],
        gaps=[],
        next_checks=[],
        statement_provenance=[],
        verifier_result={},
    )
    db.add(future)
    db.commit()
    result = client.get("/api/portfolios/workspace").json()["scenario_sensitivity"]
    assert result["coverage_value_pct"] == 60
    assert result["portfolio_values"] == {
        "negative": 6000,
        "base": 8000,
        "positive": 12000,
        "weighted": 9000,
    }
    assert result["covered"][0]["valuation_snapshot_id"] == valuation.id
    assert len(result["covered"][0]["valuation_fingerprint"]) == 64
    queued = client.post("/api/portfolios/review-runs").json()
    agent = claim_agent_run(
        db, agent_run_id=queued["agent_run_id"], worker_id="scenario-review-drafter"
    )
    frozen = agent.inputs["portfolio_review"]
    assert frozen["eligible_valuations"] == [
        {
            "position_snapshot_id": result["covered"][0]["position_id"],
            "valuation_snapshot_id": valuation.id,
            "valuation_fingerprint": valuation.artifact_fingerprint,
        }
    ]
    checked = client.post(
        "/api/portfolios/review-verifications",
        json=_review_verification(_review_draft(agent)),
    )
    assert checked.status_code == 200, checked.text


def test_configured_backend_token_protects_api_but_not_health(client, monkeypatch):
    from app import main

    monkeypatch.setattr(
        main, "get_settings", lambda: SimpleNamespace(api_token="token")
    )
    assert client.get("/api/portfolios/workspace").status_code == 401
    assert (
        client.get(
            "/api/portfolios/workspace", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/portfolios/workspace", headers={"Authorization": "Bearer token"}
        ).status_code
        == 200
    )
    assert client.get("/api/health").status_code == 200


def _review_draft(
    agent,
    *,
    summary="Portfel ma skoncentrowaną ekspozycję i niepełne pokrycie scenariuszami.",
):
    frozen = agent.inputs["portfolio_review"]
    return {
        "contract_version": "portfolio-review-v1",
        "agent_run_id": agent.id,
        "lease_owner": agent.lease_owner,
        "version": 1,
        "portfolio_id": frozen["portfolio"]["id"],
        "portfolio_snapshot_id": frozen["snapshot"]["id"],
        "as_of": frozen["snapshot"]["as_of"],
        "input_manifest": {
            key: value for key, value in frozen.items() if key != "input_fingerprint"
        },
        "gaps": frozen["gaps"],
        "input_fingerprint": frozen["input_fingerprint"],
        "analytics_fingerprint": frozen["analytics_fingerprint"],
        "sections": {
            "summary": summary,
            "concentration": ["Największa pozycja wyznacza główne skupienie."],
            "liquidity": ["Płynność części pozycji ma niepełną podstawę."],
            "history": ["Historia i benchmark zachowują etykiety dostawcy."],
            "scenario_exposure": [
                "Scenariusze są wyrównaną wrażliwością, nie wspólnym prawdopodobieństwem."
            ],
            "risks": ["Niezmapowane pozycje ograniczają interpretację."],
            "next_checks": ["Uzupełnić mapowanie i zweryfikowane wyceny."],
        },
        "requested_model_role": "worker_standard",
        "requested_model": "gpt-5.6-terra",
        "reasoning_effort": "high",
        "actual_host_model": "host deployment not exposed",
        "substitution_or_escalation": None,
    }


def _review_verification(draft, *, verdict="pass", findings=None):
    justification = (
        "Sprawdzono zamrożone dane, obliczenia backendu i dowody portfela; "
        "wniosek wskazuje wykorzystaną podstawę oraz wszystkie istotne ograniczenia."
    )
    return {
        "verifier_worker_id": "portfolio-verifier",
        "draft": draft,
        "verifier_result": {
            "requested_model_role": "verifier_strict",
            "requested_model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "actual_host_model": "host deployment not exposed",
            "substitution_or_escalation": None,
            "verdict": verdict,
            "findings": findings or [],
            "justifications": {
                "concentration_and_liquidity": justification,
                "history_and_scenario_exposure": justification,
                "risks_and_decision_support_boundary": justification,
            },
            "summary": "Niezależna kontrola zamrożonego portfela.",
        },
    }


def test_review_queue_is_json_safe_content_idempotent_and_zero_fetch(
    client, db, monkeypatch
):
    from app.api import portfolios

    db.add(Company(ticker="SNT", name="Synektik"))
    db.commit()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    assert client.post("/api/portfolios/sync/myfund").status_code == 200
    monkeypatch.setattr(
        portfolios.polite_http,
        "fetch",
        lambda *a, **k: pytest.fail("review fetched provider"),
    )
    first = client.post("/api/portfolios/review-runs")
    assert first.status_code == 201 and first.json()["created"] is True
    second = client.post("/api/portfolios/review-runs")
    assert (
        second.status_code == 200
        and second.json()["agent_run_id"] == first.json()["agent_run_id"]
    )
    db.expire_all()
    agent = db.get(AgentRun, first.json()["agent_run_id"])
    frozen = agent.inputs["portfolio_review"]
    assert frozen["input_fingerprint"] == canonical_hash(
        {k: v for k, v in frozen.items() if k != "input_fingerprint"}
    )
    assert {row["current_mapping_status"] for row in frozen["positions"]} == {
        "exact",
        "unmatched",
    }
    assert frozen["history_method"]["twr"] == "unavailable"
    assert frozen["analytics_version"] == "portfolio-analytics-v1"
    assert len(frozen["analytics_fingerprint"]) == 64
    assert (
        client.get("/api/portfolios/workspace").json()["portfolio_review"][
            "active_run"
        ]["id"]
        == agent.id
    )


@pytest.mark.parametrize(
    ("actual_host_model", "substitution_or_escalation"),
    [
        ("host deployment not exposed", None),
        ("codex-host-disclosed-model", "Host substituted the requested deployment."),
    ],
)
def test_exact_review_verification_and_atomic_provisional_save(
    client, db, monkeypatch, actual_host_model, substitution_or_escalation
):
    from app.api import portfolios

    db.add(Company(ticker="SNT", name="Synektik"))
    db.commit()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    client.post("/api/portfolios/sync/myfund")
    queued = client.post("/api/portfolios/review-runs").json()
    agent = claim_agent_run(
        db, agent_run_id=queued["agent_run_id"], worker_id="portfolio-drafter"
    )
    draft = _review_draft(agent)
    draft["actual_host_model"] = actual_host_model
    draft["substitution_or_escalation"] = substitution_or_escalation
    self_check = _review_verification(draft)
    self_check["verifier_worker_id"] = "portfolio-drafter"
    self_response = client.post("/api/portfolios/review-verifications", json=self_check)
    assert self_response.status_code == 409, self_response.text
    verification_payload = _review_verification(draft)
    verification_payload["verifier_result"]["actual_host_model"] = actual_host_model
    verification_payload["verifier_result"][
        "substitution_or_escalation"
    ] = substitution_or_escalation
    verified = client.post(
        "/api/portfolios/review-verifications", json=verification_payload
    )
    assert verified.status_code == 200, verified.text
    saved = client.post(
        "/api/portfolios/review-snapshots",
        json={**draft, "verification_run_id": verified.json()["id"]},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["status"] == "provisional"
    assert saved.json()["draft_requested_model_role"] == "worker_standard"
    assert saved.json()["draft_requested_model"] == "gpt-5.6-terra"
    assert saved.json()["draft_reasoning_effort"] == "high"
    assert saved.json()["draft_actual_host_model"] == actual_host_model
    assert (
        saved.json()["draft_substitution_or_escalation"] == substitution_or_escalation
    )
    assert saved.json()["verifier_result"]["requested_model"] == "gpt-5.6-sol"
    assert saved.json()["verifier_result"]["reasoning_effort"] == "high"
    assert saved.json()["verifier_result"]["actual_host_model"] == actual_host_model
    assert (
        saved.json()["verifier_result"]["substitution_or_escalation"]
        == substitution_or_escalation
    )
    retry = client.post(
        "/api/portfolios/review-snapshots",
        json={**draft, "verification_run_id": verified.json()["id"]},
    )
    assert retry.status_code == 201 and retry.json()["id"] == saved.json()["id"]
    changed = {
        **draft,
        "sections": {**draft["sections"], "summary": "Inny szkic."},
        "verification_run_id": verified.json()["id"],
    }
    assert (
        client.post("/api/portfolios/review-snapshots", json=changed).status_code == 409
    )
    db.refresh(agent)
    assert agent.status == "provisional" and agent.lease_owner is None
    assert db.scalar(select(func.count()).select_from(PortfolioReviewSnapshot)) == 1
    workspace = client.get("/api/portfolios/workspace").json()["portfolio_review"]
    assert workspace["active_run"] is None
    assert workspace["latest"]["id"] == saved.json()["id"]
    assert workspace["history"][0]["status"] == "provisional"


def test_mapping_change_after_claim_requires_needs_human_artifact(
    client, db, monkeypatch
):
    from app.api import portfolios

    db.add_all(
        [Company(ticker="SNT", name="Synektik"), Company(ticker="ABS", name="ABS")]
    )
    db.commit()
    raw = payload()
    raw["tickers"]["2"].update(
        {
            "tickerClear": "ALPHA",
            "nazwa": "Alpha SA (ABC)",
            "typOrg": "Akcje GPW",
        }
    )
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    synced = client.post("/api/portfolios/sync/myfund").json()
    queued = client.post("/api/portfolios/review-runs").json()
    agent = claim_agent_run(
        db, agent_run_id=queued["agent_run_id"], worker_id="portfolio-drafter"
    )
    draft = _review_draft(agent)
    unmatched = next(
        row for row in synced["positions"] if row["mapping_status"] == "unmatched"
    )
    assert (
        client.patch(
            f"/api/portfolios/mappings/{unmatched['mapping_id']}",
            json={"company_ticker": "ABC"},
        ).status_code
        == 200
    )
    passing = client.post(
        "/api/portfolios/review-verifications", json=_review_verification(draft)
    )
    assert passing.status_code == 409, passing.text
    needs_human = client.post(
        "/api/portfolios/review-verifications",
        json=_review_verification(
            draft,
            verdict="needs-human",
            findings=[
                {
                    "severity": "blocking",
                    "area": "mapping-set",
                    "detail": (
                        "Zestaw mapowań zmienił się po zamrożeniu szkicu i wymaga "
                        "ponownego przygotowania na aktualnym stanie."
                    ),
                }
            ],
        ),
    )
    assert needs_human.status_code == 200, needs_human.text
    saved = client.post(
        "/api/portfolios/review-snapshots",
        json={**draft, "verification_run_id": needs_human.json()["id"]},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["status"] == "needs-human"
    db.refresh(agent)
    assert agent.status == "needs-human" and agent.lease_owner is None


def test_review_contract_policy_scripts_and_transaction_advice_gate(
    client, db, monkeypatch
):
    from pathlib import Path
    from app.api import portfolios
    from app.services.model_policy import get_model_policy
    from scripts.codex_pick_agent_run import _execution_contract

    db.add(Company(ticker="SNT", name="Synektik"))
    db.commit()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    client.post("/api/portfolios/sync/myfund")
    queued = client.post("/api/portfolios/review-runs").json()
    agent = claim_agent_run(
        db, agent_run_id=queued["agent_run_id"], worker_id="portfolio-drafter"
    )
    contract = _execution_contract(agent)
    assert contract["skill"] == "portfolio-review"
    assert "codex_verify_portfolio_review.py" in contract["verify_command"]
    assert contract["provenance_contract"] == {
        "skill_version": "portfolio-review-v1",
        "output_contract_version": "portfolio-review-v1",
        "analytics_version": "portfolio-analytics-v1",
        "draft_model_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "high",
        "verifier_model_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
    }
    policy = get_model_policy("stock-portfolio-review")
    assert (
        policy["draft_model"] == "gpt-5.6-terra"
        and policy["verifier_model"] == "gpt-5.6-sol"
    )
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    assert (scripts / "codex_verify_portfolio_review.py").is_file()
    assert (scripts / "codex_save_portfolio_review.py").is_file()
    wrong_verifier = _review_verification(_review_draft(agent))
    wrong_verifier["verifier_result"]["requested_model"] = "gpt-5.6-terra"
    assert (
        client.post(
            "/api/portfolios/review-verifications", json=wrong_verifier
        ).status_code
        == 409
    )
    wrong_reasoning = _review_verification(_review_draft(agent))
    wrong_reasoning["verifier_result"]["reasoning_effort"] = "medium"
    assert (
        client.post(
            "/api/portfolios/review-verifications", json=wrong_reasoning
        ).status_code
        == 422
    )
    inconsistent_draft = _review_draft(agent)
    inconsistent_draft["actual_host_model"] = "codex-host-disclosed-model"
    assert (
        client.post(
            "/api/portfolios/review-verifications",
            json=_review_verification(inconsistent_draft),
        ).status_code
        == 422
    )
    inconsistent_verifier = _review_verification(_review_draft(agent))
    inconsistent_verifier["verifier_result"][
        "actual_host_model"
    ] = "different-disclosed-verifier"
    assert (
        client.post(
            "/api/portfolios/review-verifications", json=inconsistent_verifier
        ).status_code
        == 422
    )
    for field in ("requested_model", "actual_host_model"):
        blank_draft = _review_draft(agent)
        blank_draft[field] = "   "
        blank_draft["substitution_or_escalation"] = "Explicit substitution note."
        assert (
            client.post(
                "/api/portfolios/review-verifications",
                json=_review_verification(blank_draft),
            ).status_code
            == 422
        )
        blank_verifier = _review_verification(_review_draft(agent))
        blank_verifier["verifier_result"][field] = "   "
        blank_verifier["verifier_result"][
            "substitution_or_escalation"
        ] = "Explicit substitution note."
        assert (
            client.post(
                "/api/portfolios/review-verifications", json=blank_verifier
            ).status_code
            == 422
        )
    exact_identity = _review_verification(_review_draft(agent))
    exact_identity["draft"]["actual_host_model"] = "gpt-5.6-terra"
    exact_identity["verifier_result"]["actual_host_model"] = "gpt-5.6-sol"
    assert (
        client.post(
            "/api/portfolios/review-verifications", json=exact_identity
        ).status_code
        == 200
    )
    for phrase in (
        "Kup tę pozycję po synchronizacji.",
        "Warto sprzedać tę pozycję.",
        "Powinieneś zamknąć pozycję.",
        "Pozbądź się tej spółki.",
        "Zredukuj pozycję.",
        "Zwiększ pozycję.",
        "Rekomenduję sprzedaż tej pozycji.",
        "Proponuję dokupienie akcji.",
        "Najlepiej wyjść z tej pozycji.",
        "Rozważ sprzedaż tej pozycji.",
        "Sugeruję sprzedaż pozycji.",
        "Redukuj pozycję.",
        "Wyjdź z tej pozycji.",
        "Nie sprzedawaj teraz.",
        "Powinieneś rozważyć sprzedaż tej pozycji.",
        "Nie należy kupować tej pozycji.",
        "Unikaj dokupowania tej pozycji.",
        "Zalecam sprzedaż tej pozycji.",
        "Rekomenduję, aby sprzedać tę pozycję.",
        "Sugeruję, żeby zwiększyć pozycję.",
        "Warto zredukować tę pozycję.",
        "Należy sprzedać tę pozycję.",
        "Trzeba sprzedać tę pozycję.",
        "Powinno się sprzedać tę pozycję.",
        "Rozważ sprzedaż.",
        "Nie sprzedawaj.",
        "Nie redukuj pozycji.",
        "Nie wychodź z tej pozycji.",
    ):
        advice = _review_draft(agent, summary=phrase)
        assert (
            client.post(
                "/api/portfolios/review-verifications",
                json=_review_verification(advice),
            ).status_code
            == 422
        )
    for phrase in (
        "Zwiększ uwagę na płynność.",
        "Zmniejsz ryzyko błędu przez weryfikację źródeł.",
        "Zachowaj ostrożność przy interpretacji benchmarku.",
        "Spółka może sprzedać aktywa, co zmieni profil ryzyka.",
        "Ryzyko sprzedaży przy niskiej płynności wymaga sprawdzenia.",
        "Warto zwiększyć nakłady na badania i rozwój.",
        "Rekomenduję zwiększyć częstotliwość kontroli źródeł.",
        "Warto zamknąć lukę w danych przed interpretacją.",
        "Warto sprzedać nierentowny segment działalności.",
        "Warto kupić czas na analizę źródeł.",
        "Rekomenduję sprzedaż aktywów przez spółkę.",
        "Nie zamykaj luki bez źródła.",
        "Nie sprzedawaj danych osobowych.",
    ):
        neutral = _review_draft(agent, summary=phrase)
        assert (
            client.post(
                "/api/portfolios/review-verifications",
                json=_review_verification(neutral),
            ).status_code
            == 200
        )


def test_review_rejects_claim_model_override(client, db, monkeypatch):
    from app.api import portfolios

    db.add(Company(ticker="SNT", name="Synektik"))
    db.commit()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    client.post("/api/portfolios/sync/myfund")
    queued = client.post("/api/portfolios/review-runs").json()
    agent = claim_agent_run(
        db,
        agent_run_id=queued["agent_run_id"],
        worker_id="wrong-model",
        model_role="analyst_deep",
        model="gpt-5.6-sol",
    )
    response = client.post(
        "/api/portfolios/review-verifications",
        json=_review_verification(_review_draft(agent)),
    )
    assert response.status_code == 409
