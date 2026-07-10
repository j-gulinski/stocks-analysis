"""CX.8 deterministic backtest engine tests."""
from datetime import date, datetime, timezone


def _add_income_row(db, company_id: int, period: str, field_code: str, value: float, scraped_at):
    from app.db.models import ReportValue

    db.add(
        ReportValue(
            company_id=company_id,
            statement="income",
            freq="Q",
            period=period,
            field_code=field_code,
            field_label=field_code,
            position=1,
            value=value,
            scraped_at=scraped_at,
        )
    )


def test_backtest_excludes_future_scraped_financial_rows_but_attaches_outcomes(db):
    from app.db.models import Company, Price
    from app.services import backtest

    company = Company(ticker="DEC", name="DECORA", sector="consumer")
    db.add(company)
    db.commit()

    db.add_all(
        [
            Price(company_id=company.id, date=date(2024, 3, 31), close=10.0),
            Price(company_id=company.id, date=date(2024, 5, 1), close=15.0),
        ]
    )
    _add_income_row(
        db,
        company.id,
        "2023Q1",
        "IncomeRevenues",
        100.0,
        datetime(2024, 3, 1, tzinfo=timezone.utc),
    )
    _add_income_row(
        db,
        company.id,
        "2024Q1",
        "IncomeRevenues",
        200.0,
        datetime(2024, 4, 15, tzinfo=timezone.utc),
    )
    db.commit()

    result = backtest.run_strategy_backtest(
        db,
        strategy="malik_v1",
        from_date=date(2024, 3, 31),
        to_date=date(2024, 3, 31),
        tickers=["DEC"],
        outcome_windows=[30],
    )

    assert result["status"] == "completed"
    assert result["summary"]["observation_count"] == 1
    observation = result["observations"][0]
    assert observation["known_inputs"]["financials"]["latest_income_period"] == "2023Q1"
    assert observation["known_inputs"]["financials"]["revenue"] == 100.0
    assert observation["outcome"]["windows"]["30"]["price_date"] == date(2024, 5, 1)
    assert observation["outcome"]["windows"]["30"]["return_pct"] == 50.0

    from app.db.models import BacktestObservation, BacktestRun

    run = db.get(BacktestRun, result["backtest_run_id"])
    assert run.status == "completed"
    assert run.summary["observation_count"] == 1
    stored = db.query(BacktestObservation).one()
    assert stored.known_inputs["financials"]["latest_income_period"] == "2023Q1"
    assert stored.outcome["windows"]["30"]["return_pct"] == 50.0


def test_backtest_estimated_period_lag_is_opt_in_and_date_bounded(db):
    from app.db.models import Company, Price
    from app.services import backtest

    company = Company(ticker="LAG", name="LAG TEST", sector="test")
    db.add(company)
    db.commit()
    db.add_all(
        [
            Price(company_id=company.id, date=date(2024, 4, 28), close=10.0),
            Price(company_id=company.id, date=date(2024, 4, 29), close=11.0),
        ]
    )
    _add_income_row(
        db,
        company.id,
        "2023Q4",
        "IncomeRevenues",
        100.0,
        datetime(2026, 7, 9, tzinfo=timezone.utc),
    )
    db.commit()

    before = backtest.run_strategy_backtest(
        db,
        strategy="malik_v1",
        from_date=date(2024, 4, 28),
        to_date=date(2024, 4, 28),
        tickers=["LAG"],
        outcome_windows=[1],
        financial_availability_policy="estimated_period_lag",
        report_lag_days=120,
        persist=False,
    )
    assert before["observations"][0]["known_inputs"]["financials"][
        "latest_income_period"
    ] is None

    after = backtest.run_strategy_backtest(
        db,
        strategy="malik_v1",
        from_date=date(2024, 4, 29),
        to_date=date(2024, 4, 29),
        tickers=["LAG"],
        outcome_windows=[1],
        financial_availability_policy="estimated_period_lag",
        report_lag_days=120,
        persist=False,
    )
    observation = after["observations"][0]
    assert observation["known_inputs"]["financials"]["latest_income_period"] == "2023Q4"
    assert observation["known_inputs"]["availability"] == {
        "financial_policy": "estimated_period_lag",
        "report_lag_days": 120,
        "latest_income_available_at": date(2024, 4, 29),
    }
    assert after["summary"]["data_quality"]["research_only"] is True
    assert "Research-only" in after["summary"]["known_inputs_policy"]


def test_backtest_rejects_unknown_strategy(db):
    from app.services import backtest

    try:
        backtest.run_strategy_backtest(
            db,
            strategy="unknown",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
            persist=False,
        )
    except backtest.BacktestInputError as exc:
        assert "Unsupported strategy" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected BacktestInputError")


def test_backtest_api_creates_lists_and_reads_detail(client, db):
    from app.db.models import Company, Price

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()
    db.add(Price(company_id=company.id, date=date(2024, 3, 31), close=20.0))
    db.commit()

    created = client.post(
        "/api/backtest-runs",
        json={
            "strategy": "malik_v1",
            "ticker": "SNT",
            "from_date": "2024-03-01",
            "to_date": "2024-03-31",
            "outcome_windows": [30],
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["strategy"] == "malik_v1"
    assert payload["status"] == "completed"
    assert payload["summary"]["observation_count"] == 1
    assert payload["observations"][0]["signal"]["label"] == "insufficient_data"

    runs = client.get("/api/backtest-runs").json()
    assert runs[0]["id"] == payload["id"]
    detail = client.get(f"/api/backtest-runs/{payload['id']}").json()
    assert detail["observations"][0]["as_of_date"] == "2024-03-31"


def test_backtest_api_rejects_unknown_availability_policy(client, db):
    response = client.post(
        "/api/backtest-runs",
        json={
            "strategy": "malik_v1",
            "from_date": "2024-03-01",
            "to_date": "2024-03-31",
            "financial_availability_policy": "future_magic",
        },
    )

    assert response.status_code == 400
    assert "Unsupported financial availability policy" in response.json()["detail"]
