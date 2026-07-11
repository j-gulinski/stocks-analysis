"""Stage CX provider-neutral run storage and read API."""
from datetime import datetime, timedelta, timezone
import io
import json

import pytest

from tests.conftest import load_fixture


def test_agent_and_analysis_runs_are_listed_for_company(client, db):
    from app.db.models import AgentRun, AnalysisRun, Company, EventReport

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()

    agent = AgentRun(
        workflow="stock-quick-analysis",
        trigger="manual",
        status="completed",
        company_id=company.id,
        model_role="worker_standard",
        model="gpt-5.5",
        orchestrator_model="gpt-5.5",
        inputs={"ticker": "SNT"},
        outputs={"analysis_run_id": 1},
    )
    db.add(agent)
    db.commit()

    analysis = AnalysisRun(
        company_id=company.id,
        agent_run_id=agent.id,
        source="codex_skill",
        workflow="stock-quick-analysis",
        model_role="worker_standard",
        model="gpt-5.5",
        status="verified",
        verification_status="pass",
        input_snapshot={"company": {"ticker": "SNT"}},
        output={"summary_pl": "Zweryfikowany odczyt testowy.", "alignment_score": 72},
        verification={"verdict": "pass"},
        alignment_score=72,
        created_by="codex",
    )
    event = EventReport(
        company_id=company.id,
        source="espi",
        external_id="SNT-2026-001",
        raw_url="https://example.invalid/report",
        published_at=datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc),
        title="Raport bieżący",
        parsed={"kind": "contract"},
        materiality={"level": "watch"},
    )
    db.add_all([analysis, event])
    db.commit()

    runs = client.get("/api/agent-runs").json()
    assert runs[0]["workflow"] == "stock-quick-analysis"
    assert runs[0]["model_role"] == "worker_standard"
    assert runs[0]["model"] == "gpt-5.5"

    analyses = client.get("/api/companies/SNT/analysis-runs").json()
    assert analyses[0]["source"] == "codex_skill"
    assert analyses[0]["status"] == "verified"
    assert analyses[0]["verification_status"] == "pass"
    assert analyses[0]["model_role"] == "worker_standard"
    assert analyses[0]["output"]["alignment_score"] == 72

    events = client.get("/api/companies/SNT/event-reports").json()
    assert events[0]["source"] == "espi"
    assert events[0]["external_id"] == "SNT-2026-001"
    assert events[0]["materiality"]["level"] == "watch"


def test_analysis_runs_filter_by_status_and_verification(client, db):
    from app.db.models import AnalysisRun, Company

    company = Company(ticker="DEC", name="DECORA")
    db.add(company)
    db.commit()

    db.add_all(
        [
            AnalysisRun(
                company_id=company.id,
                source="codex_skill",
                workflow="stock-quick-analysis",
                model_role="worker_standard",
                model="gpt-5.5",
                status="verified",
                verification_status="pass",
                input_snapshot={},
                output={"summary_pl": "pass"},
                verification={},
            ),
            AnalysisRun(
                company_id=company.id,
                source="codex_skill",
                workflow="stock-quick-analysis",
                model_role="worker_standard",
                model="gpt-5.5",
                status="rejected",
                verification_status="fail",
                input_snapshot={},
                output={"summary_pl": "fail"},
                verification={"reason": "fabricated number"},
            ),
        ]
    )
    db.commit()

    verified = client.get(
        "/api/companies/DEC/analysis-runs",
        params={"status": "verified", "verification_status": "pass"},
    ).json()
    assert len(verified) == 1
    assert verified[0]["status"] == "verified"
    assert verified[0]["verification_status"] == "pass"


def test_agent_run_queue_api_creates_and_filters_by_ticker(client, db):
    from app.db.models import Company

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()

    created = client.post(
        "/api/agent-runs",
        json={
            "workflow": "stock-quick-analysis",
            "ticker": "snt",
            "trigger": "ui-request",
            "model_role": "worker_standard",
            "orchestrator_model": "gpt-5.5",
            "inputs": {"objective": "test quick read"},
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["workflow"] == "stock-quick-analysis"
    assert payload["status"] == "queued"
    assert payload["model_role"] == "worker_standard"
    assert payload["model"] == "gpt-5.5"
    assert payload["orchestrator_model"] == "gpt-5.5"
    assert payload["inputs"]["ticker"] == "SNT"
    assert payload["inputs"]["objective"] == "test quick read"

    filtered = client.get("/api/agent-runs", params={"ticker": "SNT"}).json()
    assert [row["id"] for row in filtered] == [payload["id"]]

    rejected = client.post("/api/agent-runs", json={"workflow": "anything-goes"})
    assert rejected.status_code == 400


def test_process_one_agent_run_claims_oldest_queue_item_and_stops_at_boundary(client, db):
    from app.db.models import AgentRun, Company

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.flush()
    queued = AgentRun(
        workflow="stock-quick-analysis",
        trigger="manual",
        status="queued",
        company_id=company.id,
        inputs={"ticker": "SNT"},
        outputs={},
    )
    db.add(queued)
    db.commit()

    response = client.post("/api/agent-runs/process-one")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["attempted"] is True
    assert payload["agent_run"]["id"] == queued.id
    assert payload["agent_run"]["status"] == "running"
    assert payload["agent_run"]["lease_owner"]
    assert payload["agent_run"]["heartbeat_at"]
    assert payload["agent_run"]["lease_expires_at"]
    assert payload["agent_run"]["attempt_count"] == 1
    assert db.get(AgentRun, queued.id).status == "running"


def test_process_one_agent_run_reports_empty_queue_without_mutation(client, db):
    response = client.post("/api/agent-runs/process-one")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "attempted": False,
        "message": "Brak oczekujących zleceń w kolejce.",
        "agent_run": None,
    }


def test_pre_session_api_fetches_espi_and_queues_brief(client, db, monkeypatch):
    from app.db.models import AgentRun, Company, EventReport, WatchlistItem
    from app.scrapers import espi

    company = Company(ticker="KRU", name="KRUK")
    db.add(company)
    db.commit()
    db.add(WatchlistItem(company_id=company.id, note=None))
    db.commit()

    monkeypatch.setattr(
        espi,
        "fetch_report_list_page",
        lambda **_kwargs: espi.GpwReportListPage(
            reports=espi.parse_report_list(load_fixture("gpw_espi_list.html")),
            next_offset=None,
            next_limit=None,
        ),
    )
    monkeypatch.setattr(
        espi,
        "fetch_report_detail",
        lambda _url: espi.parse_report_detail(load_fixture("gpw_espi_detail.html")),
    )

    response = client.post(
        "/api/agent-runs/pre-session",
        json={
            "ticker": "KRU",
            "trigger": "ui-request",
            "orchestrator_model": "gpt-5.5",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ok"] is True
    assert payload["espi_poll"]["matched"] == 1
    assert payload["espi_poll"]["new"] == 1
    assert payload["agent_run"]["workflow"] == "stock-pre-session-brief"
    assert payload["agent_run"]["status"] == "queued"
    assert payload["agent_run"]["model_role"] == "orchestrator"

    assert db.query(EventReport).count() == 1
    agent = db.get(AgentRun, payload["agent_run"]["id"])
    assert agent.inputs["espi_poll"]["reports"][0]["ticker"] == "KRU"


def test_pre_session_api_does_not_queue_after_incomplete_espi_poll(
    client, db, monkeypatch
):
    from app.db.models import AgentRun, Company, WatchlistItem
    from app.scrapers import espi

    company = Company(ticker="KRU", name="KRUK")
    db.add(company)
    db.commit()
    db.add(WatchlistItem(company_id=company.id, note=None))
    db.commit()

    def fail_page(**_kwargs):
        raise espi.GpwReportParseError("malformed first page")

    monkeypatch.setattr(espi, "fetch_report_list_page", fail_page)

    response = client.post(
        "/api/agent-runs/pre-session",
        json={"ticker": "KRU", "trigger": "ui-request"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["agent_run"] is None
    assert payload["espi_poll"]["complete"] is False
    assert payload["espi_poll"]["incomplete_reason"].startswith("list_page_error:")
    assert db.query(AgentRun).count() == 0


def test_pre_session_api_empty_watchlist_returns_200_without_queue_or_state(
    client, db, monkeypatch
):
    from app.db.models import AgentRun, Company, ListPollState
    from app.scrapers import espi

    db.add(Company(ticker="KRU", name="KRUK"))
    db.commit()

    def fail_fetch(**_kwargs):
        raise AssertionError("empty watchlist must not fetch")

    monkeypatch.setattr(espi, "fetch_report_list_page", fail_fetch)

    response = client.post(
        "/api/agent-runs/pre-session",
        json={"trigger": "ui-request"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["agent_run"] is None
    assert payload["espi_poll"]["incomplete_reason"] == "empty_watchlist"
    assert db.query(AgentRun).count() == 0
    assert db.query(ListPollState).count() == 0


def test_pre_session_api_no_queue_complete_poll_returns_200_without_run(
    client, db, monkeypatch
):
    from app.db.models import AgentRun, Company, EventReport, WatchlistItem
    from app.scrapers import espi

    company = Company(ticker="KRU", name="KRUK")
    db.add(company)
    db.commit()
    db.add(WatchlistItem(company_id=company.id, note=None))
    db.commit()
    monkeypatch.setattr(
        espi,
        "fetch_report_list_page",
        lambda **_kwargs: espi.GpwReportListPage(
            reports=espi.parse_report_list(load_fixture("gpw_espi_list.html")),
            next_offset=None,
            next_limit=None,
        ),
    )
    monkeypatch.setattr(
        espi,
        "fetch_report_detail",
        lambda _url: espi.parse_report_detail(load_fixture("gpw_espi_detail.html")),
    )

    response = client.post(
        "/api/agent-runs/pre-session",
        json={"ticker": "KRU", "trigger": "ui-request", "queue": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["agent_run"] is None
    assert payload["espi_poll"]["complete"] is True
    assert db.query(AgentRun).count() == 0
    assert db.query(EventReport).count() == 1


def test_codex_save_analysis_script_round_trips_to_api(client, db, monkeypatch, capsys):
    from app.db.models import AgentRun, AnalysisRun, Company
    from scripts import codex_save_analysis

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()

    payload = {
        "input_snapshot": {"company": {"ticker": "SNT"}},
        "output": {
            "summary_pl": "Codex zapisał zweryfikowany wynik.",
            "alignment_score": 81,
            "prediction": {
                "direction": "positive",
                "horizon_days": 365,
                "source_fields": ["valuation.potential.value_pct"],
            },
            "potential": {
                "value_pct": 18.0,
                "range_pct": [5.0, 30.0],
                "source": "dossier.valuation.potential.value_pct",
            },
            "result_quality": {
                "result_cause": "Wzrost wynika z poprawy przychodów i marży brutto.",
                "one_off_risk": "niski według one_off_share_pct",
                "scenario_validity": "valid",
                "scenario_warnings": [],
            },
        },
        "verification": {"verdict": "pass", "checks": {"numbers": "ok"}},
    }
    monkeypatch.setattr(
        "sys.argv",
        [
            "codex_save_analysis.py",
            "SNT",
            "--workflow",
            "stock-quick-analysis",
            "--model-role",
            "worker_standard",
            "--model",
            "gpt-5.5",
            "--verification-status",
            "pass",
        ],
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert codex_save_analysis.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["verification_status"] == "pass"

    agent = db.get(AgentRun, out["agent_run_id"])
    analysis = db.get(AnalysisRun, out["analysis_run_id"])
    assert agent.workflow == "stock-quick-analysis"
    assert agent.model_role == "worker_standard"
    assert analysis.status == "verified"
    assert analysis.alignment_score == 81

    rows = client.get("/api/companies/SNT/analysis-runs").json()
    assert rows[0]["id"] == analysis.id
    assert rows[0]["output"]["summary_pl"] == "Codex zapisał zweryfikowany wynik."


def test_codex_save_analysis_rejects_verified_output_without_prediction(
    db, monkeypatch
):
    from app.db.models import Company
    from scripts import codex_save_analysis

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()

    payload = {
        "input_snapshot": {"company": {"ticker": "SNT"}},
        "output": {
            "summary_pl": "Brakuje struktury predykcji.",
            "alignment_score": 70,
        },
        "verification": {"verdict": "pass"},
    }
    monkeypatch.setattr(
        "sys.argv",
        [
            "codex_save_analysis.py",
            "SNT",
            "--workflow",
            "stock-quick-analysis",
            "--model-role",
            "worker_standard",
            "--model",
            "gpt-5.3-codex-spark",
            "--verification-status",
            "pass",
        ],
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    with pytest.raises(codex_save_analysis.ScriptError) as exc:
        codex_save_analysis.main()
    assert "output.prediction is required" in str(exc.value)


def test_codex_save_analysis_closes_existing_agent_run(client, db, monkeypatch, capsys):
    from app.db.models import AgentRun, Company
    from scripts import codex_save_analysis

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()
    agent = AgentRun(
        workflow="stock-quick-analysis",
        trigger="ui-request",
        status="running",
        company_id=company.id,
        model_role="worker_standard",
        model="gpt-5.3-codex-spark",
        inputs={"ticker": "SNT"},
        outputs={},
    )
    db.add(agent)
    db.commit()

    payload = {
        "input_snapshot": {"company": {"ticker": "SNT"}},
        "output": {
            "summary_pl": "Wynik wymaga człowieka.",
            "alignment_score": 55,
        },
        "verification": {"verdict": "needs-human", "checks": {"sources": "partial"}},
    }
    monkeypatch.setattr(
        "sys.argv",
        [
            "codex_save_analysis.py",
            "SNT",
            "--workflow",
            "stock-quick-analysis",
            "--model-role",
            "worker_standard",
            "--model",
            "gpt-5.3-codex-spark",
            "--verification-status",
            "needs-human",
            "--agent-run-id",
            str(agent.id),
        ],
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert codex_save_analysis.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["agent_run_id"] == agent.id

    db.refresh(agent)
    assert agent.status == "needs-human"
    assert agent.finished_at is not None
    assert agent.outputs["analysis_run_id"] == out["analysis_run_id"]
    assert agent.outputs["verification_status"] == "needs-human"

    rows = client.get("/api/agent-runs", params={"ticker": "SNT"}).json()
    assert rows[0]["status"] == "needs-human"


def test_codex_pick_agent_run_claims_next_queue_item(db, monkeypatch, capsys):
    from app.db.models import AgentRun, Company
    from scripts import codex_pick_agent_run

    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.commit()
    agent = AgentRun(
        workflow="stock-quick-analysis",
        trigger="ui-request",
        status="queued",
        company_id=company.id,
        model_role="worker_standard",
        orchestrator_model="gpt-5.5",
        inputs={"ticker": "SNT", "objective": "test queue worker"},
        outputs={},
    )
    db.add(agent)
    db.commit()

    monkeypatch.setattr(
        "sys.argv",
        [
            "codex_pick_agent_run.py",
            "--claim",
            "--model",
            "gpt-5.3-codex-spark",
        ],
    )

    assert codex_pick_agent_run.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["action"] == "claimed"
    assert out["agent_run"]["id"] == agent.id
    assert out["agent_run"]["status"] == "running"
    assert out["agent_run"]["model"] == "gpt-5.3-codex-spark"
    assert out["execution_contract"]["skill"] == "stock-quick-analysis"
    assert out["execution_contract"]["must_save_result"] is True

    db.refresh(agent)
    assert agent.status == "running"
    assert agent.started_at is not None
    assert agent.lease_owner is not None
    assert agent.heartbeat_at is not None
    assert agent.lease_expires_at is not None
    assert agent.attempt_count == 1


def test_agent_run_lease_heartbeat_and_bounded_recovery(db):
    from app.db.models import AgentRun
    from app.services.agent_queue import (
        AgentQueueError,
        claim_agent_run,
        heartbeat_agent_run,
        recover_expired_agent_runs,
    )

    first = AgentRun(
        workflow="stock-quick-analysis",
        trigger="test",
        status="queued",
        inputs={"ticker": "SNT"},
        outputs={},
    )
    exhausted = AgentRun(
        workflow="stock-deep-analysis",
        trigger="test",
        status="running",
        attempt_count=3,
        lease_owner="dead-worker",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        inputs={"ticker": "OPM"},
        outputs={},
    )
    db.add_all([first, exhausted])
    db.commit()

    claimed = claim_agent_run(db, agent_run_id=first.id, worker_id="worker-a")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempt_count == 1
    old_expiry = claimed.lease_expires_at

    with pytest.raises(AgentQueueError, match="another worker"):
        heartbeat_agent_run(db, claimed.id, worker_id="worker-b")
    refreshed = heartbeat_agent_run(db, claimed.id, worker_id="worker-a")
    assert refreshed.lease_expires_at > old_expiry

    refreshed.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    refreshed.updated_at = refreshed.lease_expires_at
    db.commit()
    recovered = recover_expired_agent_runs(db)
    assert {row.id for row in recovered} == {claimed.id, exhausted.id}
    db.refresh(claimed)
    db.refresh(exhausted)
    assert claimed.status == "queued"
    assert claimed.lease_owner is None
    assert exhausted.status == "needs-human"
    assert exhausted.finished_at is not None


def test_deep_analysis_pick_contract_requires_research_resolution(db):
    from app.db.models import AgentRun
    from scripts.codex_pick_agent_run import _execution_contract

    contract = _execution_contract(
        AgentRun(
            id=99,
            workflow="stock-deep-analysis",
            status="running",
            model_role="orchestrator",
            model="gpt-5.3-codex-spark",
            inputs={"ticker": "SNT"},
            outputs={},
        )
    )
    steps = " ".join(contract["steps"])

    assert "catalyst" in steps
    assert "backlog" in steps
    assert "management/governance" in steps
    assert "research_resolution" in steps
    assert "not a company risk" in steps
    assert "stock-result-verifier" in steps


def test_codex_complete_agent_run_script_closes_queue_item(db, monkeypatch, capsys):
    from app.db.models import AgentRun
    from scripts import codex_complete_agent_run

    agent = AgentRun(
        workflow="stock-candidate-scout",
        trigger="ui-request",
        status="running",
        model_role="worker_standard",
        model="gpt-5.3-codex-spark",
        inputs={"objective": "rank stored companies"},
        outputs={},
    )
    db.add(agent)
    db.commit()

    payload = {
        "output": {
            "workflow": "stock-candidate-scout",
            "candidates": [],
        },
        "verification": {"verdict": "needs-human"},
    }
    monkeypatch.setattr(
        "sys.argv",
        [
            "codex_complete_agent_run.py",
            "--agent-run-id",
            str(agent.id),
            "--model-role",
            "worker_standard",
            "--model",
            "gpt-5.3-codex-spark",
            "--verification-status",
            "needs-human",
        ],
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert codex_complete_agent_run.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["agent_run_id"] == agent.id
    assert out["status"] == "needs-human"

    db.refresh(agent)
    assert agent.status == "needs-human"
    assert agent.finished_at is not None
    assert agent.outputs["output"]["workflow"] == "stock-candidate-scout"


def test_candidate_pickup_consumes_frozen_discovery_shortlist(
    db, monkeypatch, capsys
):
    from app.db.models import AgentRun
    from scripts import codex_pick_agent_run

    agent = AgentRun(
        workflow="stock-candidate-scout",
        trigger="discovery-refresh",
        status="queued",
        model_role="worker_standard",
        model="gpt-5.3-codex-spark",
        inputs={
            "source": "biznesradar-market-rating",
            "candidates": [{"ticker": "DEK", "br_rating": "AAA"}],
            "evaluation_budget": 1,
        },
        outputs={},
    )
    db.add(agent)
    db.commit()
    monkeypatch.setattr(
        "sys.argv",
        ["codex_pick_agent_run.py", "--agent-run-id", str(agent.id)],
    )

    assert codex_pick_agent_run.main() == 0
    out = json.loads(capsys.readouterr().out)
    first_step = out["execution_contract"]["steps"][0]
    assert "inputs.candidates" in first_step
    assert "do not broad-refresh" in first_step


def test_codex_contract_scripts_return_json(client, db, monkeypatch, capsys):
    from sqlalchemy import func, select

    from app.db.models import AgentRun, Company, CompanyMarketData
    from scripts import (
        codex_candidate_scan,
        codex_complete_agent_run,
        codex_evaluate_agent_runs,
        codex_get_dossier,
        codex_pick_agent_run,
        codex_poll_espi,
        codex_run_backtest,
    )

    db.add(Company(ticker="DEC", name="DECORA"))
    db.commit()

    monkeypatch.setattr("sys.argv", ["codex_candidate_scan.py", "--ticker", "DEC"])
    assert codex_candidate_scan.main() == 0
    candidate = json.loads(capsys.readouterr().out)
    assert candidate["ok"] is True
    assert candidate["workflow"] == "stock-candidate-scout"
    assert candidate["candidates"][0]["ticker"] == "DEC"

    monkeypatch.setattr("sys.argv", ["codex_get_dossier.py", "DEC"])
    market_rows_before = db.scalar(select(func.count()).select_from(CompanyMarketData))
    assert codex_get_dossier.main() == 0
    dossier = json.loads(capsys.readouterr().out)
    assert dossier["ok"] is True
    assert dossier["ticker"] == "DEC"
    assert isinstance(dossier["dossier"], dict)
    assert "prescore" in dossier["dossier"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CompanyMarketData)) == market_rows_before

    monkeypatch.setattr(
        codex_poll_espi.espi,
        "fetch_report_list_page",
        lambda **_kwargs: codex_poll_espi.espi.GpwReportListPage(
            reports=codex_poll_espi.espi.parse_report_list(load_fixture("gpw_espi_list.html")),
            next_offset=None,
            next_limit=None,
        ),
    )
    monkeypatch.setattr("sys.argv", ["codex_poll_espi.py", "--ticker", "DEC"])
    assert codex_poll_espi.main() == 0
    espi = json.loads(capsys.readouterr().out)
    assert espi["ok"] is True
    assert espi["capability"] == "live-ingestion"

    monkeypatch.setattr(
        "sys.argv",
        [
            "codex_run_backtest.py",
            "--strategy",
            "malik_v1",
            "--from-date",
            "2024-01-01",
            "--to-date",
            "2025-01-01",
        ],
    )
    assert codex_run_backtest.main() == 0
    backtest = json.loads(capsys.readouterr().out)
    assert backtest["ok"] is True
    assert backtest["status"] == "completed"
    assert backtest["strategy"] == "malik_v1"
    assert backtest["summary"]["observation_count"] == 0

    monkeypatch.setattr("sys.argv", ["codex_pick_agent_run.py"])
    assert codex_pick_agent_run.main() == 0
    queue = json.loads(capsys.readouterr().out)
    assert queue["ok"] is True
    assert queue["action"] == "listed"

    monkeypatch.setattr("sys.argv", ["codex_evaluate_agent_runs.py", "--ticker", "DEC"])
    assert codex_evaluate_agent_runs.main() == 0
    evaluation = json.loads(capsys.readouterr().out)
    assert evaluation["ok"] is True
    assert evaluation["workflow"] == "stock-agent-evaluation"

    agent = AgentRun(
        workflow="stock-candidate-scout",
        trigger="script-contract",
        status="running",
        model_role="worker_standard",
        model="gpt-5.3-codex-spark",
        inputs={},
        outputs={},
    )
    db.add(agent)
    db.commit()
    monkeypatch.setattr(
        "sys.argv",
        [
            "codex_complete_agent_run.py",
            "--agent-run-id",
            str(agent.id),
            "--verification-status",
            "needs-human",
        ],
    )
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "output": {"workflow": "stock-candidate-scout"},
                    "verification": {"verdict": "needs-human"},
                }
            )
        ),
    )
    assert codex_complete_agent_run.main() == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["ok"] is True
    assert completed["status"] == "needs-human"


def test_codex_poll_espi_cli_exits_nonzero_for_incomplete_result(
    db, monkeypatch, capsys
):
    from scripts import codex_poll_espi

    monkeypatch.setattr(
        codex_poll_espi.espi,
        "poll_watchlist_reports",
        lambda *_args, **_kwargs: {
            "ok": False,
            "complete": False,
            "cap_reached": True,
            "incomplete_reason": "hard_page_cap_reached_before_watermark",
        },
    )
    monkeypatch.setattr("sys.argv", ["codex_poll_espi.py"])

    assert codex_poll_espi.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["complete"] is False


def test_codex_poll_espi_no_details_is_honest_metadata_only(
    db, monkeypatch, capsys
):
    from scripts import codex_poll_espi

    monkeypatch.setattr(
        codex_poll_espi.espi,
        "poll_watchlist_reports",
        lambda *_args, **_kwargs: {
            "ok": False,
            "complete": False,
            "metadata_only": True,
            "incomplete_reason": "details_skipped_metadata_only",
        },
    )
    monkeypatch.setattr("sys.argv", ["codex_poll_espi.py", "--no-details"])

    assert codex_poll_espi.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["complete"] is False
    assert payload["metadata_only"] is True


def test_codex_pre_session_cli_exits_nonzero_for_metadata_only(
    db, monkeypatch, capsys
):
    from scripts import codex_pre_session

    monkeypatch.setattr(
        codex_pre_session.stock_tools,
        "prepare_pre_session_brief",
        lambda *_args, **_kwargs: {
            "ok": False,
            "espi_poll": {
                "complete": False,
                "metadata_only": True,
                "incomplete_reason": "details_skipped_metadata_only",
            },
            "agent_run": None,
        },
    )
    monkeypatch.setattr("sys.argv", ["codex_pre_session.py", "--no-details"])

    assert codex_pre_session.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["agent_run"] is None
