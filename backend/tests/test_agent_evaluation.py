from datetime import date, datetime, timezone
import json


def _adjusted_price(**kwargs):
    from app.db.models import Price

    values = {
        "source_name": "test_verified_prices",
        "series_key": "test:verified:split:v1",
        "adjustment_status": "split_adjusted",
        "basis_version": "v1",
    }
    values.update(kwargs)
    return Price(**values)


def test_agent_evaluation_scores_structured_potential(db):
    from app.db.models import AnalysisRun, Company, Price
    from app.services import agent_evaluation

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()
    db.add_all(
        [
            _adjusted_price(company_id=company.id, date=date(2024, 1, 2), close=100, volume=None, scraped_at=datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc)),
            _adjusted_price(company_id=company.id, date=date(2024, 2, 1), close=116, volume=None),
        ]
    )
    analysis = AnalysisRun(
        company_id=company.id,
        source="codex_skill",
        workflow="stock-quick-analysis",
        model_role="worker_standard",
        model="gpt-5.3-codex-spark",
        status="draft",
        verification_status="needs-human",
        input_snapshot={"company": {"ticker": "SNT"}},
        output={
            "summary_pl": "Structured test output.",
            "potential": {"value_pct": 18.0},
            "confidence": "medium",
        },
        verification={"verdict": "needs-human"},
        created_at=datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
    )
    db.add(analysis)
    db.commit()

    result = agent_evaluation.run_agent_evaluation(
        db,
        from_date=analysis.created_at.date(),
        to_date=analysis.created_at.date(),
        ticker="SNT",
        outcome_windows=[30],
    )

    assert result["ok"] is True
    assert result["summary"]["observation_count"] == 1
    assert result["summary"]["hit_windows"] == 1
    assert result["summary"]["hit_rate_pct"] == 100.0
    observation = result["observations"][0]
    assert observation["known_inputs"]["ticker"] == "SNT"
    assert observation["prediction"]["direction"] == "positive"
    assert observation["outcome"]["windows"]["30"]["return_pct"] == 16.0
    assert observation["score"]["windows"]["30"]["hit"] is True


def test_agent_evaluation_marks_missing_prediction_needs_human(client, db):
    from app.db.models import AnalysisRun, Company, Price

    company = Company(ticker="DEC", name="DECORA")
    db.add(company)
    db.commit()
    db.add(_adjusted_price(company_id=company.id, date=date(2024, 1, 2), close=50, volume=None, scraped_at=datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc)))
    db.add(
        AnalysisRun(
            company_id=company.id,
            source="codex_skill",
            workflow="stock-quick-analysis",
            model_role="worker_standard",
            model="gpt-5.3-codex-spark",
            status="draft",
            verification_status="needs-human",
            input_snapshot={"company": {"ticker": "DEC"}},
            output={"summary_pl": "No structured potential."},
            verification={"verdict": "needs-human"},
            created_at=datetime(2024, 1, 2, 9, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()

    response = client.post(
        "/api/agent-evaluation-runs",
        json={
            "ticker": "DEC",
            "from_date": "2024-01-02",
            "to_date": "2024-01-02",
            "outcome_windows": [30],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["verification_status"] == "needs-human"
    assert payload["summary"]["data_quality"]["unknown_predictions"] == 1
    assert payload["observations"][0]["prediction"]["direction"] == "unknown"

    listed = client.get("/api/agent-evaluation-runs").json()
    assert listed[0]["id"] == payload["id"]


def test_agent_evaluation_empty_cohort_needs_human(db):
    from app.services import agent_evaluation

    result = agent_evaluation.run_agent_evaluation(
        db,
        ticker="NO_SAVED_ANALYSES",
        outcome_windows=[30],
        persist=False,
    )

    assert result["summary"]["observation_count"] == 0
    assert result["verification_status"] == "needs-human"
    assert "No saved analysis runs matched" in result["summary"]["data_quality"]["warnings"][0]


def test_agent_evaluation_does_not_mix_price_adjustment_bases(db):
    from app.db.models import Company, Price
    from app.services.agent_evaluation import _outcome_windows

    company = Company(ticker="MIX", name="MIXED BASIS")
    db.add(company)
    db.flush()
    db.add_all(
        [
            _adjusted_price(
                company_id=company.id,
                date=date(2024, 1, 2),
                close=100,
                scraped_at=datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc),
            ),
            _adjusted_price(
                company_id=company.id,
                date=date(2024, 2, 1),
                close=116,
                source_name="test_total_return",
                series_key="test:total-return:v1",
                adjustment_status="total_return",
            ),
        ]
    )
    db.commit()

    outcome = _outcome_windows(
        db,
        company.id,
        datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
        [30],
    )

    assert outcome["adjustment_status"] == "split_adjusted"
    assert outcome["windows"]["30"]["return_pct"] is None


def test_agent_evaluation_excludes_base_price_learned_after_analysis(db):
    from app.db.models import Company
    from app.services.agent_evaluation import _outcome_windows

    company = Company(ticker="LATE", name="LATE PRICE")
    db.add(company)
    db.flush()
    db.add(
        _adjusted_price(
            company_id=company.id,
            date=date(2024, 1, 2),
            close=100,
            scraped_at=datetime(2024, 1, 2, 11, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()

    outcome = _outcome_windows(
        db,
        company.id,
        datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
        [30],
    )

    assert outcome["base_price"] is None
    assert outcome["windows"]["30"]["return_pct"] is None


def test_agent_evaluation_stratifies_mixed_return_bases():
    from app.services.agent_evaluation import _summarize

    observations = [
        {
            "prediction": {"direction": "positive"},
            "outcome": {"adjustment_status": basis},
            "score": {
                "scored_windows": 1,
                "hit_windows": hits,
                "missing_windows": 0,
            },
        }
        for basis, hits in (("split_adjusted", 1), ("total_return", 0))
    ]

    summary = _summarize(observations)

    assert summary["data_quality"]["mixed_return_bases"] is True
    assert summary["hit_rate_pct"] is None
    assert summary["score_by_return_basis"]["split_adjusted"]["hit_rate_pct"] == 100.0
    assert summary["score_by_return_basis"]["total_return"]["hit_rate_pct"] == 0.0


def test_codex_evaluate_agent_runs_script_and_mcp(db, monkeypatch, capsys):
    from app.db.models import AnalysisRun, Company, Price
    from app.mcp.stock_workbench_server import handle_message
    from scripts import codex_evaluate_agent_runs

    company = Company(ticker="CBF", name="CYBER_FOLKS")
    db.add(company)
    db.commit()
    db.add_all(
        [
            _adjusted_price(company_id=company.id, date=date(2024, 1, 2), close=200, volume=None, scraped_at=datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc)),
            _adjusted_price(company_id=company.id, date=date(2024, 4, 1), close=196, volume=None),
        ]
    )
    db.add(
        AnalysisRun(
            company_id=company.id,
            source="codex_skill",
            workflow="stock-deep-analysis",
            model_role="analyst_deep",
            model="gpt-5.5",
            status="draft",
            verification_status="needs-human",
            input_snapshot={"company": {"ticker": "CBF"}},
            output={
                "prediction": {"direction": "neutral"},
                "confidence": {"level": "low"},
            },
            verification={"verdict": "needs-human"},
            created_at=datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()

    monkeypatch.setattr(
        "sys.argv",
        [
            "codex_evaluate_agent_runs.py",
            "--ticker",
            "CBF",
            "--outcome-window",
            "90",
        ],
    )
    assert codex_evaluate_agent_runs.main() == 0
    script_payload = json.loads(capsys.readouterr().out)
    assert script_payload["ok"] is True
    assert script_payload["summary"]["hit_windows"] == 1

    mcp_payload = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "tools/call",
            "params": {
                "name": "evaluate_agent_runs",
                "arguments": {"ticker": "CBF", "outcome_windows": [90]},
            },
        }
    )["result"]["structuredContent"]
    assert mcp_payload["workflow"] == "stock-agent-evaluation"
    assert mcp_payload["summary"]["observation_count"] >= 1
