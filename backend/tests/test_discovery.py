"""S1: one immutable multi-page market batch and its single sieve."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.db.models import (
    AgentRun,
    Company,
    DocumentVersion,
    MarketFactorBatch,
    MarketFactorRow,
)
from app.scrapers.biznesradar import ParseError, parse_market_factor_page, parse_market_rating
from app.api.discovery import _expectation_payload
from app.services.discovery import (
    MARKET_PAGE_SPECS,
    _derive_discontinued_score_normalizations,
)
from app.services.workbench_sieve import SCORE_COMPONENT_COUNT, evaluate_workbench_sieve
from tests.conftest import FakeResponse, load_fixture


def _rating_page(
    *,
    include_universe: bool = True,
    extra_count: int = 95,
    extra_f_score: str = "1",
) -> str:
    rows = [
        ("GOOD", "GOODCO", "AAA (8,0)", "6"),
        ("DEBT", "DEBTCO", "AAA (8,0)", "7"),
        ("LOST", "LOSTCO", "AAA (3,0)", "5"),
        ("EQUIT", "EQUITCO", "AAA (8,0)", "6"),
        ("DECAY", "DECAYCO", "AAA (8,0)", "7"),
    ]
    if include_universe:
        rows.extend(
            (f"T{index:03}", f"TEST{index:03}", "AAA (8,0)", extra_f_score)
            for index in range(extra_count)
        )
    body = "".join(
        f'<tr><td><a href="/notowania/{name}">{ticker} ({name})</a></td>'
        f"<td>2026/Q1</td><td>{rating}</td><td>{f_score}</td></tr>"
        for ticker, name, rating, f_score in rows
    )
    return (
        "<table class='table table--accent-header'><thead><tr>"
        "<th>Profil</th><th>Raport</th><th>Altman EM-Score</th>"
        "<th>Piotroski F-Score</th></tr></thead><tbody>"
        f"{body}</tbody></table>"
    )


def _factor_page(
    metric: str,
    values: dict[str, tuple[str, str]],
    *,
    include_universe: bool = True,
    extra_count: int = 95,
    extra_delta: str = "0,0%",
) -> str:
    html = load_fixture("br_market_factor_page.html").replace("__METRIC__", metric)
    for ticker, (value, delta) in values.items():
        html = html.replace(f"__{ticker}_VALUE__", value).replace(
            f"__{ticker}_DELTA__", delta
        )
    if not include_universe:
        return html
    extra_rows = "".join(
        f'<tr><td><a href="/wskazniki/TEST{index:03}">T{index:03} (TEST{index:03})</a></td>'
        f"<td>2026/Q1</td><td>1,0</td><td>{extra_delta}</td></tr>"
        for index in range(extra_count)
    )
    return html.replace("</tbody>", f"{extra_rows}</tbody>")


def _market_pages(
    *,
    good_cz: str = "10,0",
    include_universe: bool = True,
    extra_count: int = 95,
    extra_f_score: str = "1",
    extra_delta: str = "0,0%",
) -> dict[str, str]:
    values = {
        "cz": ("Cena / Zysk", {ticker: (good_cz if ticker == "GOOD" else "12,0", "-5,0%") for ticker in ("GOOD", "DEBT", "LOST", "EQUIT", "DECAY")}),
        "operating_margin": ("Marża zysku operacyjnego", {"GOOD": ("12,0%", "+2,0%"), "DEBT": ("10,0%", "+1,0%"), "LOST": ("8,0%", "+1,0%"), "EQUIT": ("9,0%", "+1,0%"), "DECAY": ("4,0%", "-2,0%")}),
        "net_debt_ebitda": ("Dług netto / EBITDA", {"GOOD": ("1,0", ""), "DEBT": ("7,0", ""), "LOST": ("1,0", ""), "EQUIT": ("1,0", ""), "DECAY": ("1,0", "")}),
        "revenue": ("Przychody ze sprzedaży", {"GOOD": ("100 000", "+8,0%"), "DEBT": ("100 000", "+6,0%"), "LOST": ("100 000", "+4,0%"), "EQUIT": ("100 000", "+3,0%"), "DECAY": ("100 000", "-4,0%")}),
        "net_income": ("Zysk netto", {"GOOD": ("5 000", "+8,0%"), "DEBT": ("5 000", "+6,0%"), "LOST": ("-100", "-3,0%"), "EQUIT": ("5 000", "+2,0%"), "DECAY": ("5 000", "-4,0%")}),
        "equity": ("Kapitał własny", {"GOOD": ("20 000", "+1,0%"), "DEBT": ("20 000", "+1,0%"), "LOST": ("20 000", "+1,0%"), "EQUIT": ("-1", "-1,0%"), "DECAY": ("20 000", "+1,0%")} ),
    }
    pages = {
        "rating": _rating_page(
            include_universe=include_universe,
            extra_count=extra_count,
            extra_f_score=extra_f_score,
        )
    }
    pages.update({
        key: _factor_page(
            metric,
            rows,
            include_universe=include_universe,
            extra_count=extra_count,
            extra_delta=extra_delta,
        )
        for key, (metric, rows) in values.items()
    })
    return pages


def _fetch_from_pages(pages: dict[str, str], calls: list[str]):
    by_url = {spec.url: pages[spec.id] for spec in MARKET_PAGE_SPECS}

    def fake_fetch(url, **_kwargs):
        calls.append(url)
        response = FakeResponse(by_url[url])
        response.url = url
        return response

    return fake_fetch


def test_market_factor_parser_keeps_value_delta_and_missing_value():
    html = _factor_page(
        "Marża zysku operacyjnego",
        {
            "GOOD": ("12,5%", "+1,2%"),
            "DEBT": ("—", ""),
            "LOST": ("8,0%", "-1,0%"),
            "EQUIT": ("9,0%", "+1,0%"),
            "DECAY": ("4,0%", "-2,0%"),
        },
    )
    entries = parse_market_factor_page(html, expected_header="marża zysku operacyjnego")

    assert [(item.ticker, item.name, item.report_period) for item in entries[:2]] == [
        ("GOOD", "GOODCO", "2026Q1"),
        ("DEBT", "DEBTCO", "2026Q1"),
    ]
    assert entries[0].value == 12.5
    assert entries[0].delta_rr_pct == 1.2
    assert entries[1].value is None


def test_market_factor_parser_rejects_wrong_headers():
    try:
        parse_market_factor_page(
            "<table><tr><th>Profil</th><th>Raport</th><th>Inny wskaźnik</th></tr></table>",
            expected_header="marża zysku operacyjnego",
        )
    except ParseError:
        pass
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("wrong market page must not become a factor vector")


def test_market_rating_parser_keeps_source_fields_and_missing_values():
    candidates = parse_market_rating(load_fixture("br_market_rating.html"))

    assert [candidate.ticker for candidate in candidates] == ["DEK", "RBW", "VGO", "XTB", "SHD"]
    assert candidates[0].name == "DEKPOL"
    assert candidates[0].br_slug == "DEKPOL"
    assert candidates[0].report_period == "2026Q1"
    assert candidates[0].rating_value == 8.6
    assert candidates[-1].piotroski_f_score is None


def test_refresh_publishes_one_complete_batch_and_get_is_zero_write(
    client, db, monkeypatch, no_sleep
):
    calls: list[str] = []
    monkeypatch.setattr("app.scrapers.http.fetch", _fetch_from_pages(_market_pages(), calls))

    first = client.post("/api/discovery/refresh")

    assert first.status_code == 200
    body = first.json()
    assert body["sieve"]["id"] == "workbench_sieve_v1"
    assert body["sieve"]["status"] == "available"
    assert body["sieve"]["batch_id"] is not None
    assert "A6" in body["sieve"]["coverage_label"]
    assert body["sieve"]["coverage_count"] == 100
    assert body["sieve"]["coverage_pct"] == 100.0
    assert len(body["sieve"]["sources"]) == len(MARKET_PAGE_SPECS)
    assert body["universe_count"] == 100
    assert [candidate["ticker"] for candidate in body["candidates"]] == ["GOOD"]
    assert {"DEBT", "LOST", "EQUIT", "DECAY"}.issubset(
        {item["ticker"] for item in body["excluded"]}
    )
    reasons = {item["ticker"]: item["kill_reasons"] for item in body["excluded"]}
    assert any(reason.startswith("A5") for reason in reasons["DEBT"])
    assert any(reason.startswith("A1") for reason in reasons["LOST"])
    assert any(reason.startswith("A3") for reason in reasons["EQUIT"])
    assert any(reason.startswith("A4") for reason in reasons["DECAY"])
    assert len(calls) == len(MARKET_PAGE_SPECS)
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == len(MARKET_PAGE_SPECS)
    assert db.scalar(select(func.count()).select_from(MarketFactorBatch)) == 1
    good_row = db.scalar(
        select(MarketFactorRow).where(MarketFactorRow.ticker == "GOOD")
    )
    assert good_row.op_margin_delta_pp == pytest.approx(12.0 - 12.0 / 1.02)
    assert db.scalar(select(func.count()).select_from(Company)) == 0
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0

    stored = client.get("/api/discovery")
    assert stored.status_code == 200
    assert stored.json() == body
    assert len(calls) == len(MARKET_PAGE_SPECS)
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0


def test_discovery_returns_only_top_100_and_handoff_uses_the_same_boundary(
    client, monkeypatch, no_sleep
):
    calls: list[str] = []
    pages = _market_pages(
        extra_count=105,
        extra_f_score="9",
        extra_delta="+1,0%",
    )
    monkeypatch.setattr("app.scrapers.http.fetch", _fetch_from_pages(pages, calls))

    response = client.post("/api/discovery/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["universe_count"] == 110
    assert body["sieve"]["survivor_count"] == 106
    assert body["sieve"]["excluded_count"] == 4
    assert body["result_count"] == 100
    assert len(body["candidates"]) == 100
    assert [item["ticker"] for item in body["candidates"][:2]] == ["GOOD", "T000"]
    assert body["candidates"][-1]["ticker"] == "T098"
    assert body["candidates"][-1]["rank"] == 100

    rejected = client.post(
        "/api/research-cases",
        json={
            "ticker": "T104",
            "discovery": {
                "batch_id": body["sieve"]["batch_id"],
                "sieve_id": "workbench_sieve_v1",
                "sieve_version": "workbench-sieve-v1",
            },
        },
    )

    assert rejected.status_code == 409
    assert "surfaced top Discover results" in rejected.json()["detail"]


def test_refresh_rejects_a_truncated_market_universe(client, db, monkeypatch, no_sleep):
    calls: list[str] = []
    monkeypatch.setattr(
        "app.scrapers.http.fetch",
        _fetch_from_pages(_market_pages(include_universe=False), calls),
    )

    response = client.post("/api/discovery/refresh")

    assert response.status_code == 503
    assert "only 5 rows" in response.json()["detail"]
    assert db.scalar(select(func.count()).select_from(MarketFactorBatch)) == 0
    assert len(calls) == len(MARKET_PAGE_SPECS)

def test_changed_page_creates_new_batch_and_uses_prior_cz_history(
    client, db, monkeypatch, no_sleep
):
    calls: list[str] = []
    first_pages = _market_pages(good_cz="10,0")
    second_pages = _market_pages(good_cz="8,0")
    responses = [
        {spec.url: first_pages[spec.id] for spec in MARKET_PAGE_SPECS},
        {spec.url: second_pages[spec.id] for spec in MARKET_PAGE_SPECS},
    ]

    def fake_fetch(url, **_kwargs):
        page_set = responses[len(calls) // len(MARKET_PAGE_SPECS)]
        calls.append(url)
        response = FakeResponse(page_set[url])
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    first = client.post("/api/discovery/refresh").json()
    first_batch = db.get(MarketFactorBatch, first["sieve"]["batch_id"])
    first_batch.as_of -= timedelta(days=31)
    db.commit()
    second_response = client.post("/api/discovery/refresh")

    assert second_response.status_code == 200
    second = second_response.json()
    assert first["sieve"]["batch_id"] != second["sieve"]["batch_id"]
    good = second["candidates"][0]
    assert "B4 · C/Z poniżej własnej mediany snapshotów" in good["improvement_signals"]
    valuation = next(
        factor for factor in good["factors"] if factor["id"] == "valuation_vs_own_history"
    )
    first_cz_document_id = next(
        source["document_version_id"] for source in first["sieve"]["sources"] if source["id"] == "cz"
    )
    assert valuation["history_median"] == 10.0
    assert valuation["history_batch_ids"] == [first["sieve"]["batch_id"]]
    assert valuation["history_document_version_ids"] == [first_cz_document_id]
    assert db.scalar(select(func.count()).select_from(MarketFactorBatch)) == 2
    # Only the C/Z immutable source changed; the other six versions were reused.
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == len(MARKET_PAGE_SPECS) + 1


def test_same_day_refresh_does_not_create_cz_history(
    client, db, monkeypatch, no_sleep
):
    calls: list[str] = []
    first_pages = _market_pages(good_cz="10,0")
    second_pages = _market_pages(good_cz="8,0")
    responses = [
        {spec.url: first_pages[spec.id] for spec in MARKET_PAGE_SPECS},
        {spec.url: second_pages[spec.id] for spec in MARKET_PAGE_SPECS},
    ]

    def fake_fetch(url, **_kwargs):
        page_set = responses[len(calls) // len(MARKET_PAGE_SPECS)]
        calls.append(url)
        response = FakeResponse(page_set[url])
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    client.post("/api/discovery/refresh")
    second_response = client.post("/api/discovery/refresh")

    assert second_response.status_code == 200
    second = second_response.json()
    good = next(item for item in second["candidates"] if item["ticker"] == "GOOD")
    assert "B4 · C/Z poniżej własnej mediany snapshotów" not in good["improvement_signals"]
    valuation = next(
        factor for factor in good["factors"] if factor["id"] == "valuation_vs_own_history"
    )
    assert valuation["history_median"] is None
    assert valuation["history_batch_ids"] == []
    assert valuation["history_document_version_ids"] == []
    assert any("starszej o co najmniej 30 dni" in gap for gap in good["factor_gaps"])


def test_partial_refresh_keeps_previous_complete_batch(client, db, monkeypatch, no_sleep):
    calls: list[str] = []
    monkeypatch.setattr("app.scrapers.http.fetch", _fetch_from_pages(_market_pages(), calls))
    first = client.post("/api/discovery/refresh").json()

    bad_pages = _market_pages()
    bad_pages["operating_margin"] = "<html><h1>maintenance</h1></html>"
    monkeypatch.setattr("app.scrapers.http.fetch", _fetch_from_pages(bad_pages, calls))
    failed = client.post("/api/discovery/refresh")

    assert failed.status_code == 503
    stored = client.get("/api/discovery")
    assert stored.status_code == 200
    assert stored.json()["sieve"]["batch_id"] == first["sieve"]["batch_id"]
    assert stored.json()["freshness"]["last_failed_refresh_at"] is not None
    assert (
        stored.json()["freshness"]["last_successful_source_check_at"]
        < stored.json()["freshness"]["last_failed_refresh_at"]
    )
    assert db.scalar(select(func.count()).select_from(MarketFactorBatch)) == 1


def test_discovery_handoff_recomputes_membership_and_freezes_origin(
    client, db, monkeypatch, no_sleep
):
    calls: list[str] = []
    first_pages = _market_pages(good_cz="10,0")
    second_pages = _market_pages(good_cz="8,0")
    responses = [
        {spec.url: first_pages[spec.id] for spec in MARKET_PAGE_SPECS},
        {spec.url: second_pages[spec.id] for spec in MARKET_PAGE_SPECS},
    ]

    def fake_fetch(url, **_kwargs):
        page_set = responses[len(calls) // len(MARKET_PAGE_SPECS)]
        calls.append(url)
        response = FakeResponse(page_set[url])
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    first = client.post("/api/discovery/refresh").json()
    first_batch = db.get(MarketFactorBatch, first["sieve"]["batch_id"])
    first_batch.as_of -= timedelta(days=31)
    db.commit()
    body = client.post("/api/discovery/refresh").json()
    batch_id = body["sieve"]["batch_id"]
    payload = {
        "ticker": "GOOD",
        "discovery": {
            "batch_id": batch_id,
            "sieve_id": "workbench_sieve_v1",
            "sieve_version": "workbench-sieve-v1",
        },
    }

    created = client.post("/api/research-cases", json=payload)
    assert created.status_code == 200
    run = db.get(AgentRun, created.json()["agent_run"]["id"])
    assert run.inputs["discovery_origin"]["batch_id"] == batch_id
    assert run.inputs["discovery_origin"]["candidate"]["ticker"] == "GOOD"
    assert run.inputs["discovery_origin"]["page_document_versions"]
    frozen_valuation = next(
        factor
        for factor in run.inputs["discovery_origin"]["candidate"]["factors"]
        if factor["id"] == "valuation_vs_own_history"
    )
    assert frozen_valuation["history_batch_ids"]
    assert frozen_valuation["history_document_version_ids"]

    rejected = client.post(
        "/api/research-cases",
        json={**payload, "ticker": "DEBT"},
    )
    assert rejected.status_code == 409

    repeated = client.post("/api/research-cases", json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["created_job"] is False
    assert db.get(AgentRun, run.id).inputs["discovery_origin"] == run.inputs["discovery_origin"]


def test_discovery_handoff_rejects_a_pre_repair_batch(client, db, monkeypatch, no_sleep):
    calls: list[str] = []
    monkeypatch.setattr("app.scrapers.http.fetch", _fetch_from_pages(_market_pages(), calls))
    body = client.post("/api/discovery/refresh").json()
    batch = db.get(MarketFactorBatch, body["sieve"]["batch_id"])
    batch.parser_version = "workbench-market-batch@2"
    db.commit()

    rejected = client.post(
        "/api/research-cases",
        json={
            "ticker": "GOOD",
            "discovery": {
                "batch_id": batch.id,
                "sieve_id": "workbench_sieve_v1",
                "sieve_version": "workbench-sieve-v1",
            },
        },
    )

    assert rejected.status_code == 409
    assert "current sieve source contract" in rejected.json()["detail"]


def test_negative_cz_never_counts_as_b4_cheapness():
    row = SimpleNamespace(
        ticker="NEGPE",
        name="Negative P/E",
        report_period="2026Q1",
        altman_value=8.0,
        piotroski_f=6.0,
        cz=-5.0,
        cz_delta_rr_pct=None,
        op_margin_pct=1.0,
        op_margin_delta_pp=-1.0,
        revenue_dyn_rr_pct=0.0,
        net_income_dyn_rr_pct=0.0,
        net_debt_ebitda=1.0,
        net_income_ttm_pln_thousands=-1.0,
        equity_pln_thousands=100.0,
        turnover_present=None,
    )

    result = evaluate_workbench_sieve([row], prior_cz_by_ticker={"NEGPE": [10.0]})

    assert result.candidates == ()
    assert result.excluded[0].kill_reasons == (
        "stagnacja · mniej niż dwa sygnały poprawy B1–B5.",
    )
    valuation = next(
        factor for factor in result.excluded[0].factors if factor.id == "valuation_vs_own_history"
    )
    assert valuation.delta is None
    assert any("C/Z nie jest dodatnie" in gap for gap in result.excluded[0].factor_gaps)


def test_a7_stays_a_gap_without_point_in_time_trailing_income():
    assert any(spec.id == "net_income" for spec in MARKET_PAGE_SPECS)
    row = SimpleNamespace(
        ticker="TTMOK",
        name="Positive trailing income",
        report_period="2026Q1",
        altman_value=8.0,
        piotroski_f=5.0,
        cz=10.0,
        cz_delta_rr_pct=None,
        op_margin_pct=1.0,
        op_margin_delta_pp=2.0,
        revenue_dyn_rr_pct=3.0,
        net_income_dyn_rr_pct=4.0,
        net_debt_ebitda=1.0,
        net_income_ttm_pln_thousands=None,
        equity_pln_thousands=100.0,
        turnover_present=None,
    )

    result = evaluate_workbench_sieve([row])

    assert result.candidates[0].ticker == "TTMOK"
    assert result.candidates[0].potential_score == 50.0
    assert len(result.candidates[0].score_components) == SCORE_COMPONENT_COUNT
    assert result.excluded == ()


def test_potential_score_normalizes_five_measurable_factors_to_one_scale():
    rows = [
        SimpleNamespace(
            ticker=ticker,
            name=ticker,
            report_period="2026Q1",
            altman_value=8.0,
            piotroski_f=6.0,
            cz=cz,
            cz_delta_rr_pct=None,
            op_margin_pct=margin_level,
            op_margin_delta_pp=margin_delta,
            revenue_dyn_rr_pct=revenue_growth,
            net_income_dyn_rr_pct=net_income_growth,
            net_debt_ebitda=debt,
            net_income_ttm_pln_thousands=None,
            equity_pln_thousands=100.0,
            turnover_present=None,
        )
        for ticker, revenue_growth, net_income_growth, margin_delta, margin_level, debt, cz in (
            ("TOP", 20.0, 30.0, 5.0, 30.0, 0.5, 5.0),
            ("MID", 10.0, 15.0, 3.0, 15.0, 2.0, 8.0),
            ("LOW", 1.0, 2.0, 1.0, 5.0, 4.0, 9.5),
        )
    ]

    result = evaluate_workbench_sieve(
        rows,
        prior_cz_by_ticker={ticker: [10.0] for ticker in ("TOP", "MID", "LOW")},
    )

    assert [item.ticker for item in result.candidates] == ["TOP", "MID", "LOW"]
    assert [item.potential_score for item in result.candidates] == [100.0, 50.0, 0.0]
    assert all(
        len(item.score_components) == SCORE_COMPONENT_COUNT
        for item in result.candidates
    )
    assert all(
        component.weight == 0.2
        for item in result.candidates
        for component in item.score_components
    )
    assert {component.id for component in result.candidates[0].score_components} == {
        "revenue_growth",
        "net_income_growth",
        "operating_margin_change",
        "operating_margin",
        "current_pe",
    }
    assert "nie jest prawdopodobieństwem" in result.candidates[0].rank_basis[0]


def test_potential_score_bounds_low_base_outliers_before_ranking():
    rows = [
        SimpleNamespace(
            ticker=ticker,
            name=ticker,
            report_period="2026Q1",
            altman_value=8.0,
            piotroski_f=6.0,
            cz=9.0,
            cz_delta_rr_pct=None,
            op_margin_pct=margin_level,
            op_margin_delta_pp=margin_change,
            revenue_dyn_rr_pct=revenue_growth,
            net_income_dyn_rr_pct=net_income_growth,
            net_debt_ebitda=1.0,
            net_income_ttm_pln_thousands=None,
            equity_pln_thousands=100.0,
            turnover_present=None,
        )
        for ticker, revenue_growth, net_income_growth, margin_change, margin_level in (
            ("BOUND", 100.0, 100.0, 20.0, 40.0),
            ("OUTLIER", 1550.0, 9700.0, 50.0, 80.0),
        )
    ]

    result = evaluate_workbench_sieve(
        rows,
        prior_cz_by_ticker={"BOUND": [10.0], "OUTLIER": [10.0]},
    )
    outlier = next(item for item in result.candidates if item.ticker == "OUTLIER")

    assert outlier.potential_score == 50.0
    assert [component.percentile for component in outlier.score_components] == [50.0] * 5
    components = {component.id: component for component in outlier.score_components}
    assert components["revenue_growth"].raw_value == 1550.0
    assert components["revenue_growth"].ranking_value == 100.0
    assert components["net_income_growth"].ranking_value == 100.0
    assert components["operating_margin_change"].ranking_value == 20.0
    assert components["operating_margin"].ranking_value == 40.0


def test_discontinued_result_normalization_recomputes_growth_and_trailing_pe():
    def value(amount: float, fact_id: int) -> dict:
        return {
            "value": amount,
            "fact_id": fact_id,
            "source_version_id": 30,
        }

    row = SimpleNamespace(
        cz=5.97,
        net_income_dyn_rr_pct=1953.65,
        extras={"source_periods": {"net_income": "2026Q2"}},
    )
    quarterly = {
        "2025Q2": {
            "IncomeNetProfit": value(14_431, 1),
            "IncomeDiscontinuedProfit": value(-7_604, 2),
        },
        "2025Q3": {
            "IncomeNetProfit": value(23_712, 3),
            "IncomeDiscontinuedProfit": value(-6_829, 4),
        },
        "2025Q4": {
            "IncomeNetProfit": value(31_656, 5),
            "IncomeDiscontinuedProfit": value(-8_658, 6),
        },
        "2026Q1": {
            "IncomeNetProfit": value(34_971, 7),
            "IncomeDiscontinuedProfit": value(-8_100, 8),
        },
        "2026Q2": {
            "IncomeNetProfit": value(296_362, 9),
            "IncomeDiscontinuedProfit": value(256_562, 10),
        },
    }

    result = _derive_discontinued_score_normalizations(
        row,
        quarterly_values=quarterly,
        market_cap={
            "value": 3_346_830_134,
            "fact_id": 11,
            "source_version_id": 29,
        },
    )
    by_component = {item["component_id"]: item for item in result}

    assert by_component["net_income_growth"]["reported_value"] == 1953.65
    assert by_component["net_income_growth"]["normalized_value"] == pytest.approx(
        80.6217
    )
    assert by_component["current_pe"]["reported_value"] == 5.97
    assert by_component["current_pe"]["normalized_value"] == pytest.approx(21.7714)
    assert by_component["current_pe"]["discontinued_share_pct"] == pytest.approx(
        86.5705
    )
    assert by_component["current_pe"]["source_document_version_ids"] == [29, 30]
    assert by_component["current_pe"]["source_fact_ids"] == list(range(3, 12))


def test_sieve_uses_frozen_normalized_values_instead_of_one_off_market_values():
    normalizations = [
        {
            "component_id": "net_income_growth",
            "label": "Dynamika zysku działalności kontynuowanej r/r",
            "reported_value": 1953.65,
            "normalized_value": 80.6217,
            "discontinued_share_pct": 86.5714,
            "period": "2026Q2",
            "reason": "Materialny wynik działalności zaniechanej.",
            "source_fact_ids": [1, 2, 9, 10],
            "source_document_version_ids": [30],
        },
        {
            "component_id": "current_pe",
            "label": "C/Z działalności kontynuowanej (niżej lepiej)",
            "reported_value": 5.97,
            "normalized_value": 21.7714,
            "discontinued_share_pct": 86.5714,
            "period": "2026Q2",
            "reason": "Materialny wynik działalności zaniechanej.",
            "source_fact_ids": list(range(3, 12)),
            "source_document_version_ids": [29, 30],
        },
    ]
    row = SimpleNamespace(
        ticker="SNT",
        name="Synektik",
        report_period="2026Q2",
        altman_value=8.0,
        piotroski_f=7.0,
        cz=5.97,
        cz_delta_rr_pct=None,
        op_margin_pct=20.0,
        op_margin_delta_pp=4.0,
        revenue_dyn_rr_pct=40.0,
        net_income_dyn_rr_pct=1953.65,
        net_debt_ebitda=1.0,
        net_income_ttm_pln_thousands=None,
        equity_pln_thousands=100.0,
        turnover_present=None,
        extras={
            "source_periods": {
                "revenue": "2026Q2",
                "net_income": "2026Q2",
                "operating_margin": "2026Q2",
                "cz": "2026Q2",
            },
            "score_normalizations": normalizations,
        },
    )

    candidate = evaluate_workbench_sieve([row]).candidates[0]
    components = {component.id: component for component in candidate.score_components}

    assert components["net_income_growth"].raw_value == pytest.approx(80.6217)
    assert components["current_pe"].raw_value == pytest.approx(21.7714)
    assert components["net_income_growth"].label.startswith("Dynamika zysku działalności")
    assert candidate.score_normalizations[0].reported_value == 5.97
    assert candidate.frozen_evidence()["score_normalizations"]


def test_potential_score_uses_unrounded_percentiles_before_final_rounding():
    rows = [
        SimpleNamespace(
            ticker=ticker,
            name=ticker,
            report_period="2026Q1",
            altman_value=8.0,
            piotroski_f=6.0,
            cz=cz,
            cz_delta_rr_pct=None,
            op_margin_pct=margin_level,
            op_margin_delta_pp=margin_delta,
            revenue_dyn_rr_pct=revenue_growth,
            net_income_dyn_rr_pct=net_income_growth,
            net_debt_ebitda=debt,
            net_income_ttm_pln_thousands=None,
            equity_pln_thousands=100.0,
            turnover_present=None,
        )
        for ticker, revenue_growth, net_income_growth, margin_delta, margin_level, debt, cz in (
            ("TARGET", 0.0, 5.0, 2.0, 5.0, 2.0, 9.0),
            ("LOWER", 1.0, 1.0, 1.0, 1.0, 3.0, 10.0),
            ("HIGH1", 10.0, 10.0, 3.0, 10.0, 1.0, 8.0),
            ("HIGH2", 20.0, 20.0, 4.0, 20.0, 0.0, 7.0),
        )
    ]

    result = evaluate_workbench_sieve(
        rows,
        prior_cz_by_ticker={row.ticker: [10.0] for row in rows},
    )
    target = next(item for item in result.candidates if item.ticker == "TARGET")

    assert [component.percentile for component in target.score_components] == pytest.approx([
        0.0,
        100.0 / 3.0,
        100.0 / 3.0,
        100.0 / 3.0,
        100.0 / 3.0,
    ])
    assert target.potential_score == 26.7


def test_equal_potential_scores_use_ticker_only_and_missing_scores_follow():
    rows = [
        SimpleNamespace(
            ticker=ticker,
            name=ticker,
            report_period="2026Q1",
            altman_value=8.0,
            piotroski_f=6.0,
            cz=cz,
            cz_delta_rr_pct=None,
            op_margin_pct=margin_level,
            op_margin_delta_pp=margin_delta,
            revenue_dyn_rr_pct=revenue_growth,
            net_income_dyn_rr_pct=net_income_growth,
            net_debt_ebitda=debt,
            net_income_ttm_pln_thousands=None,
            equity_pln_thousands=100.0,
            turnover_present=None,
        )
        for ticker, revenue_growth, net_income_growth, margin_delta, margin_level, debt, cz in (
            ("ZETA", 10.0, 10.0, 2.0, 10.0, 1.0, 8.0),
            ("ALFA", 10.0, 10.0, 2.0, 10.0, 1.0, 8.0),
            ("CHARLIE", 5.0, 5.0, 1.0, 5.0, 2.0, 9.0),
            ("DELTA", 20.0, 20.0, 3.0, 20.0, 0.0, 7.0),
        )
    ]
    history = {row.ticker: [10.0] for row in rows}

    result = evaluate_workbench_sieve(rows, prior_cz_by_ticker=history)
    by_ticker = {item.ticker: item for item in result.candidates}

    assert by_ticker["ALFA"].potential_score == by_ticker["ZETA"].potential_score
    ordered_tie = [
        item.ticker
        for item in result.candidates
        if item.potential_score == by_ticker["ALFA"].potential_score
    ]
    assert ordered_tie == ["ALFA", "ZETA"]

    missing_rows = [
        SimpleNamespace(
            ticker=ticker,
            name=ticker,
            report_period="2026Q1",
            altman_value=8.0,
            piotroski_f=8.0,
            cz=9.0 if ticker == "COMPLETE" else None,
            cz_delta_rr_pct=None,
            op_margin_pct=10.0,
            op_margin_delta_pp=2.0,
            revenue_dyn_rr_pct=5.0,
            net_income_dyn_rr_pct=4.0,
            net_debt_ebitda=1.0,
            net_income_ttm_pln_thousands=None,
            equity_pln_thousands=100.0,
            turnover_present=None,
        )
        for ticker in ("COMPLETE", "MISSING")
    ]
    missing_result = evaluate_workbench_sieve(
        missing_rows,
        prior_cz_by_ticker={"COMPLETE": [10.0]},
    )

    assert missing_result.candidates[0].ticker == "COMPLETE"
    assert missing_result.candidates[0].potential_score == 50.0
    assert missing_result.candidates[-1].ticker == "MISSING"
    assert missing_result.candidates[-1].potential_score is None


def test_factor_output_preserves_its_own_source_period():
    row = SimpleNamespace(
        ticker="PERIOD",
        name="Period lineage",
        report_period="2026Q1",
        altman_value=8.0,
        piotroski_f=6.0,
        cz=10.0,
        cz_delta_rr_pct=None,
        op_margin_pct=1.0,
        op_margin_delta_pp=2.0,
        revenue_dyn_rr_pct=3.0,
        net_income_dyn_rr_pct=4.0,
        net_debt_ebitda=1.0,
        net_income_ttm_pln_thousands=None,
        equity_pln_thousands=100.0,
        turnover_present=None,
        extras={
            "source_periods": {
                "cz": "2025Q4",
                "revenue": "2025Q4",
                "net_income": "2025Q3",
                "equity": "2025Q4",
            }
        },
    )

    result = evaluate_workbench_sieve([row])
    factors = {factor.id: factor for factor in result.candidates[0].factors}

    assert factors["revenue_growth"].period == "2025Q4"
    assert factors["net_income_growth"].period == "2025Q3"
    assert factors["equity"].period == "2025Q4"
    assert factors["current_pe"].period == "2025Q4"
    assert factors["valuation_vs_own_history"].period == "2025Q4"
    assert factors["piotroski_f_score"].period == "2026Q1"


def test_stale_or_misaligned_periods_remain_visible_but_do_not_affect_score():
    common = {
        "altman_value": 8.0,
        "piotroski_f": 6.0,
        "cz_delta_rr_pct": None,
        "op_margin_pct": 12.0,
        "op_margin_delta_pp": 2.0,
        "revenue_dyn_rr_pct": 8.0,
        "net_income_dyn_rr_pct": 9.0,
        "net_debt_ebitda": 1.0,
        "net_income_ttm_pln_thousands": None,
        "equity_pln_thousands": 100.0,
        "turnover_present": None,
    }
    fresh = SimpleNamespace(
        ticker="FRESH",
        name="Fresh",
        report_period="2026Q1",
        cz=10.0,
        **common,
    )
    stale = SimpleNamespace(
        ticker="STALE",
        name="Stale",
        report_period="2024Q4",
        cz=5.0,
        extras={
            "source_periods": {
                "revenue": "2016Q2",
                "net_income": "2016Q2",
                "operating_margin": "2024Q4",
                "cz": "2024Q4",
            }
        },
        **common,
    )
    stale_missing = SimpleNamespace(
        ticker="STALEMISS",
        name="Stale and incomplete",
        report_period="2024Q4",
        cz=None,
        extras=stale.extras,
        **common,
    )

    result = evaluate_workbench_sieve([fresh, stale, stale_missing])
    by_ticker = {item.ticker: item for item in result.candidates}

    assert [item.ticker for item in result.candidates] == [
        "FRESH",
        "STALE",
        "STALEMISS",
    ]
    assert by_ticker["FRESH"].potential_score == 50.0
    assert [component.percentile for component in by_ticker["FRESH"].score_components] == [
        50.0
    ] * SCORE_COMPONENT_COUNT
    assert by_ticker["STALE"].potential_score is None
    assert by_ticker["STALE"].score_components == ()
    assert any("najstarszy składnik" in gap for gap in by_ticker["STALE"].factor_gaps)
    assert any("okresy składników różnią się" in gap for gap in by_ticker["STALE"].factor_gaps)
    assert any(
        "najstarszy składnik" in gap
        for gap in by_ticker["STALEMISS"].factor_gaps
    )
    assert by_ticker["STALEMISS"].potential_score is None


def test_discover_expectation_curve_exposes_growth_count_range_and_dispersion():
    record = SimpleNamespace(
        updated_at=None,
        forecast_consensus={
            "2026": {
                "revenue": {
                    "value": 923_600,
                    "unit": "tys. PLN",
                    "growth_pct": 35.5,
                    "growth_base_period": "2025",
                    "forecast_count": 6,
                    "range_min": 903_800,
                    "range_max": 960_500,
                    "source_document_version_id": 36,
                    "source_as_of": "2026-07-14T22:26:36+00:00",
                },
                "net_income": {
                    "value": 158_300,
                    "unit": "tys. PLN",
                    "growth_pct": 53.84,
                    "growth_base_period": "2025",
                    "forecast_count": 6,
                    "range_min": 152_000,
                    "range_max": 168_300,
                },
            }
        },
    )

    result = _expectation_payload(record)
    revenue = next(
        metric
        for metric in result["periods"][0]["metrics"]
        if metric["metric"] == "revenue"
    )

    assert result["status"] == "available"
    assert revenue["growth_pct"] == 35.5
    assert revenue["forecast_count"] == 6
    assert revenue["dispersion_pct"] == 6.14
    assert result["source_document_version_id"] == 36


def test_missing_discover_consensus_is_neutral_coverage_gap():
    result = _expectation_payload(None)
    assert result["status"] == "unavailable"
    assert "nie negatywna" in result["note"]
