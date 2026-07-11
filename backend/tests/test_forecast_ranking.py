"""DISC.1 deterministic two-year consensus-growth ranking."""
from datetime import datetime, timezone


def _add_company(
    db,
    ticker,
    revenue,
    operating,
    *,
    net_income=None,
    years=(2026, 2027),
    fetched_at=None,
):
    from app.db.models import Company
    from app.services import evidence

    company = Company(ticker=ticker, name=f"{ticker} SA", br_slug=ticker)
    db.add(company)
    db.flush()
    recorded = evidence.record_document_version(
        db,
        company,
        source_name="biznesradar",
        source_type="analyst_forecast",
        scope_key="consensus",
        requested_url=f"https://www.biznesradar.pl/prognozy/{ticker}",
        effective_url=f"https://www.biznesradar.pl/prognozy/{ticker}",
        content=f"{ticker}-{years}".encode(),
        text="fixture",
        response_status=200,
        mime_type="text/html",
        fetched_at=fetched_at or datetime(2026, 7, 11, tzinfo=timezone.utc),
    )
    metrics = {"revenue": revenue, "operating_profit": operating}
    if net_income is not None:
        metrics["net_income"] = net_income
    for metric, values in metrics.items():
        for year, value in zip(years, values):
            evidence.record_numeric_fact(
                db,
                company,
                recorded.version,
                fact_type="analyst_forecast",
                fact_key=f"forecast.{metric}",
                value=value,
                unit="tys. PLN",
                period=str(year),
                locator={"row": metric, "column": str(year)},
                extractor_version="biznesradar-forecasts@1",
            )
    evidence.mark_parse_result(recorded.version, success=True)


def test_forecast_growth_ranking_orders_one_fresh_adjacent_snapshot(client, db):
    _add_company(db, "FAST", (100, 140), (10, 20), net_income=(5, 10))
    _add_company(db, "SLOW", (100, 110), (10, 11), net_income=(5, 5.5))
    _add_company(db, "TURN", (100, 150), (-5, 5), net_income=(-2, 4))
    db.commit()

    response = client.get("/api/discovery/forecast-growth")

    assert response.status_code == 200
    payload = response.json()
    assert [row["ticker"] for row in payload["candidates"]] == ["FAST", "SLOW"]
    assert payload["universe_count"] == 3
    assert payload["ranked_count"] == 2
    assert payload["insufficient_count"] == 1
    assert payload["analyst_count_available"] is False
    assert payload["candidates"][0]["metrics"]["revenue"]["growth_pct"] == 40.0
    assert payload["candidates"][0]["metric_coverage"] == 3
    assert payload["candidates"][0]["source_version_id"] is not None
    assert payload["candidates"][0]["freshness_status"] == "fresh"


def test_forecast_growth_rejects_stale_or_non_adjacent_versions(db):
    from app.services.forecast_ranking import build_forecast_growth_ranking

    _add_company(
        db,
        "STALE",
        (100, 140),
        (10, 20),
        fetched_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    _add_company(db, "GAP", (100, 140), (10, 20), years=(2026, 2028))
    db.commit()

    result = build_forecast_growth_ranking(
        db,
        now=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )

    assert result["candidates"] == []
    assert result["stale_count"] == 1
    assert result["insufficient_count"] == 1


def test_forecast_growth_caps_outlier_only_in_composite(db):
    from app.services.forecast_ranking import build_forecast_growth_ranking

    _add_company(db, "CAP", (1, 10), (1, 10))
    db.commit()

    row = build_forecast_growth_ranking(
        db,
        now=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )["candidates"][0]

    assert row["metrics"]["revenue"]["growth_pct"] == 900.0
    assert row["composite_growth_pct"] == 200.0


def test_forecast_transitions_and_non_finite_values_are_not_ranked(db):
    from app.services.forecast_ranking import _finite_float, build_forecast_growth_ranking

    _add_company(db, "LOSS", (100, 110), (-10, -5), net_income=(-10, 5))
    db.commit()

    result = build_forecast_growth_ranking(
        db,
        now=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )

    assert result["candidates"] == []
    assert _finite_float(float("nan")) is None
    assert _finite_float(float("inf")) is None
