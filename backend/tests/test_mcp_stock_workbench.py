"""CX.5 local MCP tool contract tests."""
import json

from tests.conftest import load_fixture


def test_mcp_lists_core_tools():
    from app.mcp.stock_workbench_server import handle_message

    response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in response["result"]["tools"]}

    assert {
        "get_company_dossier",
        "get_model_policy",
        "get_recent_source_deltas",
        "save_analysis_run",
        "list_queued_agent_runs",
        "queue_agent_run",
        "claim_agent_run",
        "mark_verification_result",
        "complete_agent_run",
        "prepare_pre_session_brief",
        "rank_candidates",
        "run_backtest",
        "evaluate_agent_runs",
        "poll_espi_watchlist",
    }.issubset(names)


def test_mcp_model_policy_is_provider_free_and_role_explicit():
    from app.mcp.stock_workbench_server import handle_message

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "tools/call",
            "params": {
                "name": "get_model_policy",
                "arguments": {"workflow": "stock-deep-analysis"},
            },
        }
    )
    policy = response["result"]["structuredContent"]["policy"]
    assert policy["status"] == "ready"
    assert policy["draft_role"] == "analyst_deep"
    assert policy["required_verifier_role"] == "verifier_strict"
    assert policy["provider_mode"] == "codex-host"
    assert policy["api_key_required"] is False
    assert "not exposed" in policy["concrete_model_source"]


def test_mcp_unknown_model_policy_stays_needs_human():
    from app.mcp.stock_workbench_server import handle_message

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 102,
            "method": "tools/call",
            "params": {
                "name": "get_model_policy",
                "arguments": {"workflow": "future-workflow"},
            },
        }
    )
    policy = response["result"]["structuredContent"]["policy"]
    assert policy["status"] == "needs-human"
    assert policy["draft_role"] is None


def test_mcp_run_backtest_schema_requires_date_boundaries():
    from app.mcp.stock_workbench_server import handle_message

    response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}

    assert tools["run_backtest"]["inputSchema"]["required"] == [
        "strategy",
        "from_date",
        "to_date",
    ]
    properties = tools["run_backtest"]["inputSchema"]["properties"]
    assert properties["financial_availability_policy"]["enum"] == [
        "scraped_at",
        "estimated_period_lag",
    ]
    assert properties["report_lag_days"]["default"] == 120


def test_mcp_queue_claim_and_list_agent_run(db):
    from app.db.models import Company
    from app.mcp.stock_workbench_server import handle_message

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()

    queued = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "queue_agent_run",
                "arguments": {
                    "workflow": "stock-quick-analysis",
                    "ticker": "SNT",
                    "model_role": "worker_standard",
                    "inputs": {"requested_by": "test"},
                },
            },
        }
    )
    queued_payload = queued["result"]["structuredContent"]
    assert queued_payload["ok"] is True
    assert queued_payload["agent_run"]["status"] == "queued"

    listed = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_queued_agent_runs", "arguments": {}},
        }
    )
    listed_payload = listed["result"]["structuredContent"]
    assert listed_payload["agent_runs"][0]["id"] == queued_payload["agent_run"]["id"]

    claimed = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "claim_agent_run",
                "arguments": {
                    "agent_run_id": queued_payload["agent_run"]["id"],
                    "model": "gpt-5.3-codex-spark",
                },
            },
        }
    )
    claimed_payload = claimed["result"]["structuredContent"]
    assert claimed_payload["agent_run"]["status"] == "running"
    assert claimed_payload["agent_run"]["model"] == "gpt-5.3-codex-spark"


def test_mcp_get_company_dossier_returns_ui_contract(db):
    from app.db.models import Company
    from app.mcp.stock_workbench_server import handle_message

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "get_company_dossier",
                "arguments": {"ticker": "SNT"},
            },
        }
    )
    payload = response["result"]["structuredContent"]

    assert payload["ok"] is True
    assert payload["ticker"] == "SNT"
    assert payload["dossier"]["company"]["ticker"] == "SNT"
    assert "prescore" in payload["dossier"]


def test_mcp_save_analysis_run_round_trips_to_api(client, db):
    from app.db.models import AnalysisRun, Company
    from app.mcp.stock_workbench_server import handle_message

    db.add(Company(ticker="DEC", name="DECORA"))
    db.commit()

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "save_analysis_run",
                "arguments": {
                    "ticker": "DEC",
                    "workflow": "stock-quick-analysis",
                    "model_role": "worker_standard",
                    "model": "gpt-5.5",
                    "verification_status": "pass",
                    "input_snapshot": {"company": {"ticker": "DEC"}},
                    "output": {
                        "summary_pl": "Zweryfikowana analiza z MCP.",
                        "alignment_score": 77,
                        "prediction": {
                            "direction": "negative",
                            "horizon_days": 365,
                            "source_fields": ["valuation.potential.value_pct"],
                        },
                        "potential": {
                            "value_pct": -12.0,
                            "range_pct": [-25.0, -4.0],
                            "source": "dossier.valuation.potential.value_pct",
                        },
                        "result_quality": {
                            "result_cause": "Wynik wymaga potwierdzenia w kolejnych raportach.",
                            "one_off_risk": "niski według dostępnego one_off_share_pct",
                            "scenario_validity": "limited",
                            "scenario_warnings": [
                                "Scenariusze mają ujemną wartość oczekiwaną."
                            ],
                        },
                    },
                    "verification": {"verdict": "pass"},
                },
            },
        }
    )
    payload = response["result"]["structuredContent"]
    assert payload["ok"] is True

    analysis = db.get(AnalysisRun, payload["analysis_run_id"])
    assert analysis.status == "verified"
    assert analysis.source == "codex_mcp"
    assert analysis.alignment_score == 77

    rows = client.get("/api/companies/DEC/analysis-runs").json()
    assert rows[0]["id"] == analysis.id
    assert rows[0]["verification_status"] == "pass"


def test_mcp_save_analysis_run_rejects_pass_without_prediction(db):
    from app.db.models import Company
    from app.mcp.stock_workbench_server import handle_message

    db.add(Company(ticker="DEC", name="DECORA"))
    db.commit()

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 50,
            "method": "tools/call",
            "params": {
                "name": "save_analysis_run",
                "arguments": {
                    "ticker": "DEC",
                    "workflow": "stock-quick-analysis",
                    "model_role": "worker_standard",
                    "model": "gpt-5.3-codex-spark",
                    "verification_status": "pass",
                    "input_snapshot": {"company": {"ticker": "DEC"}},
                    "output": {"summary_pl": "Brak predykcji."},
                    "verification": {"verdict": "pass"},
                },
            },
        }
    )
    payload = response["result"]["structuredContent"]
    assert payload["ok"] is False
    assert "output.prediction is required" in payload["error"]


def _verified_scenario_simulation_payload(*, fingerprint="bridge:fixture"):
    scenario_set = {
        "engine": "deterministic",
        "current_price": 25.0,
        "weighted_expected_price": 25.0,
        "weighted_expected_upside_pct": 0.0,
        "framing": "To punkt wejścia w analizę, nie sygnał kupna/sprzedaży.",
        "disclaimer": "Analiza nie jest rekomendacją inwestycyjną.",
        "simulation_verification": {"strict_verification_required": True},
        "scenarios": [
            {
                "id": "negative",
                "kind": "negative",
                "probability": 0.25,
                "target_price": 20.0,
                "implied_upside_pct": -20.0,
                "company_outcome": {"direction": "negative", "mode": "qualitative"},
            },
            {
                "id": "base",
                "kind": "base",
                "probability": 0.50,
                "target_price": 25.0,
                "implied_upside_pct": 0.0,
                "company_outcome": {"direction": "neutral", "mode": "qualitative"},
            },
            {
                "id": "positive",
                "kind": "positive",
                "probability": 0.25,
                "target_price": 30.0,
                "implied_upside_pct": 20.0,
                "company_outcome": {"direction": "positive", "mode": "qualitative"},
            },
        ],
    }
    return {
        "scenario_set": scenario_set,
        "priced_operating_outcomes": {
            "status": "approved",
            "input_fingerprint": fingerprint,
        },
    }


def _strict_scenario_verification(*, fingerprint="bridge:fixture"):
    return {
        "model_role": "verifier_strict",
        "verifier_model": "fixture-verifier",
        "verdict": "pass",
        "checks": {
            "representative_archetypes": {
                "archetypes": ["industrial", "financial", "event-driven"]
            },
            "no_lookahead": {"passed": True},
            "math_reconciliation": {"passed": True},
            "source_lineage": {"passed": True},
            "scenario_input_match": {"passed": True, "fingerprint": fingerprint},
        },
    }


def test_mcp_scenario_simulation_pass_requires_strict_snapshot_and_verifier(db):
    from app.db.models import AnalysisRun, Company, VerificationRun
    from app.mcp.stock_workbench_server import handle_message

    db.add(Company(ticker="DEC", name="DECORA"))
    db.commit()
    output = _verified_scenario_simulation_payload()

    saved = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 51,
            "method": "tools/call",
            "params": {
                "name": "save_analysis_run",
                "arguments": {
                    "ticker": "DEC",
                    "workflow": "scenario-simulation",
                    "model_role": "analyst_deep",
                    "model": "fixture-analyst",
                    "verification_status": "needs-human",
                    "input_snapshot": {
                        "operating_bridge_fingerprint": "bridge:fixture",
                        "scenario_set": output["scenario_set"],
                    },
                    "output": output,
                },
            },
        }
    )
    saved_payload = saved["result"]["structuredContent"]
    assert saved_payload["ok"] is True

    verified = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 52,
            "method": "tools/call",
            "params": {
                "name": "mark_verification_result",
                "arguments": {
                    "analysis_run_id": saved_payload["analysis_run_id"],
                    **_strict_scenario_verification(),
                    "summary": "Fixture-only strict scenario contract.",
                },
            },
        }
    )
    verified_payload = verified["result"]["structuredContent"]
    assert verified_payload["ok"] is True

    analysis = db.get(AnalysisRun, saved_payload["analysis_run_id"])
    assert analysis.status == "verified"
    assert analysis.verification_status == "pass"
    assert db.query(VerificationRun).one().verdict == "pass"


def test_mcp_scenario_simulation_rejects_stale_bridge_on_strict_pass(db):
    from app.db.models import AnalysisRun, Company
    from app.mcp.stock_workbench_server import handle_message

    db.add(Company(ticker="DEC", name="DECORA"))
    db.commit()
    output = _verified_scenario_simulation_payload()
    saved = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 53,
            "method": "tools/call",
            "params": {
                "name": "save_analysis_run",
                "arguments": {
                    "ticker": "DEC",
                    "workflow": "scenario-simulation",
                    "model_role": "analyst_deep",
                    "model": "fixture-analyst",
                    "verification_status": "needs-human",
                    "input_snapshot": {
                        "operating_bridge_fingerprint": "bridge:old",
                        "scenario_set": output["scenario_set"],
                    },
                    "output": output,
                },
            },
        }
    )
    saved_payload = saved["result"]["structuredContent"]
    assert saved_payload["ok"] is True

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 54,
            "method": "tools/call",
            "params": {
                "name": "mark_verification_result",
                "arguments": {
                    "analysis_run_id": saved_payload["analysis_run_id"],
                    **_strict_scenario_verification(),
                },
            },
        }
    )
    payload = response["result"]["structuredContent"]
    assert payload["ok"] is False
    assert "operating_bridge_fingerprint" in payload["error"]
    analysis = db.get(AnalysisRun, saved_payload["analysis_run_id"])
    assert analysis.verification_status == "needs-human"


def test_mcp_save_analysis_run_closes_existing_agent_run(db):
    from app.db.models import AgentRun, Company
    from app.mcp.stock_workbench_server import handle_message

    company = Company(ticker="DEC", name="DECORA")
    db.add(company)
    db.commit()
    agent = AgentRun(
        workflow="stock-quick-analysis",
        trigger="ui-request",
        status="running",
        company_id=company.id,
        model_role="worker_standard",
        model="gpt-5.3-codex-spark",
        inputs={"ticker": "DEC"},
        outputs={},
    )
    db.add(agent)
    db.commit()

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "tools/call",
            "params": {
                "name": "save_analysis_run",
                "arguments": {
                    "ticker": "DEC",
                    "workflow": "stock-quick-analysis",
                    "model_role": "worker_standard",
                    "model": "gpt-5.3-codex-spark",
                    "verification_status": "needs-human",
                    "agent_run_id": agent.id,
                    "input_snapshot": {"company": {"ticker": "DEC"}},
                    "output": {
                        "summary_pl": "MCP wynik wymaga kontroli.",
                        "alignment_score": 52,
                    },
                    "verification": {"verdict": "needs-human"},
                },
            },
        }
    )
    payload = response["result"]["structuredContent"]
    assert payload["ok"] is True

    db.refresh(agent)
    assert agent.status == "needs-human"
    assert agent.finished_at is not None
    assert agent.outputs["analysis_run_id"] == payload["analysis_run_id"]
    assert agent.outputs["verification_status"] == "needs-human"


def test_mcp_complete_agent_run_closes_watchlist_level_job(db):
    from app.db.models import AgentRun
    from app.mcp.stock_workbench_server import handle_message

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

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 17,
            "method": "tools/call",
            "params": {
                "name": "complete_agent_run",
                "arguments": {
                    "agent_run_id": agent.id,
                    "verification_status": "needs-human",
                    "output": {
                        "workflow": "stock-candidate-scout",
                        "candidates": [],
                    },
                    "verification": {"verdict": "needs-human"},
                },
            },
        }
    )
    payload = response["result"]["structuredContent"]
    assert payload["ok"] is True

    db.refresh(agent)
    assert agent.status == "needs-human"
    assert agent.finished_at is not None
    assert agent.outputs["output"]["workflow"] == "stock-candidate-scout"
    assert agent.outputs["verification_status"] == "needs-human"


def test_mcp_rejects_bad_tool_input(db):
    from app.mcp.stock_workbench_server import handle_message

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "save_analysis_run",
                "arguments": {
                    "ticker": "SNT",
                    "workflow": "stock-quick-analysis",
                },
            },
        }
    )

    assert response["result"]["isError"] is True
    assert response["result"]["structuredContent"]["ok"] is False


def test_mcp_stdio_entrypoint_speaks_json_rpc():
    from app.mcp.stock_workbench_server import handle_message

    response = handle_message(
        {"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {}}
    )

    assert response["result"]["serverInfo"]["name"] == "stock-analysis-workbench"
    assert "tools" in response["result"]["capabilities"]
    assert handle_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ) is None


def test_mcp_contract_and_espi_tools_return_honest_status(db, monkeypatch):
    from app.db.models import Company
    from app.mcp import stock_tools
    from app.mcp.stock_workbench_server import handle_message
    from app.scrapers import espi as espi_scraper

    db.add(Company(ticker="DGN", name="DIGITAL NETWORK"))
    db.commit()

    backtest = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "run_backtest",
                "arguments": {
                    "strategy": "malik_v1",
                    "from_date": "2024-01-01",
                    "to_date": "2025-01-01",
                },
            },
        }
    )["result"]["structuredContent"]
    assert backtest["status"] == "completed"
    assert backtest["summary"]["observation_count"] == 0

    candidates = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "rank_candidates", "arguments": {"ticker": "DGN"}},
        }
    )["result"]["structuredContent"]
    assert candidates["workflow"] == "stock-candidate-scout"
    assert candidates["candidates"][0]["ticker"] == "DGN"

    monkeypatch.setattr(
        stock_tools.espi,
        "fetch_report_list_page",
        lambda **_kwargs: stock_tools.espi.GpwReportListPage(
            reports=espi_scraper.parse_report_list(load_fixture("gpw_espi_list.html")),
            next_offset=None,
            next_limit=None,
        ),
    )
    monkeypatch.setattr(
        stock_tools.espi,
        "fetch_report_detail",
        lambda _url: espi_scraper.parse_report_detail(load_fixture("gpw_espi_detail.html")),
    )

    espi = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "poll_espi_watchlist", "arguments": {"ticker": "DGN"}},
        }
    )["result"]["structuredContent"]
    assert espi["capability"] == "live-ingestion"
    assert espi["matched"] == 0

    brief = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "prepare_pre_session_brief",
                "arguments": {"ticker": "DGN", "orchestrator_model": "gpt-5.5"},
            },
        }
    )["result"]["structuredContent"]
    assert brief["ok"] is True
    assert brief["agent_run"]["workflow"] == "stock-pre-session-brief"


def test_mcp_pre_session_no_details_returns_poll_without_queue(db, monkeypatch):
    from app.db.models import AgentRun, Company, EventReport, WatchlistItem
    from app.mcp import stock_tools
    from app.scrapers import espi as espi_scraper

    company = Company(ticker="KRU", name="KRUK")
    db.add(company)
    db.commit()
    db.add(WatchlistItem(company_id=company.id))
    db.commit()

    monkeypatch.setattr(
        stock_tools.espi,
        "fetch_report_list_page",
        lambda **_kwargs: stock_tools.espi.GpwReportListPage(
            reports=espi_scraper.parse_report_list(load_fixture("gpw_espi_list.html")),
            next_offset=None,
            next_limit=None,
        ),
    )

    def fail_detail(_url):
        raise AssertionError("no-details must not fetch report detail")

    monkeypatch.setattr(stock_tools.espi, "fetch_report_detail", fail_detail)

    result = stock_tools.prepare_pre_session_brief(
        {"ticker": "KRU", "fetch_details": False, "queue": True}
    )

    assert result["ok"] is False
    assert result["agent_run"] is None
    assert result["espi_poll"]["complete"] is False
    assert result["espi_poll"]["metadata_only"] is True
    assert db.query(AgentRun).count() == 0
    report = db.query(EventReport).one()
    assert report.raw_text is None


def test_mcp_unknown_ticker_poll_fails_without_fetch(db, monkeypatch):
    from app.mcp import stock_tools

    def fail_fetch(**_kwargs):
        raise AssertionError("unknown ticker must not fetch")

    monkeypatch.setattr(stock_tools.espi, "fetch_report_list_page", fail_fetch)

    poll = stock_tools.poll_espi_watchlist({"ticker": "NOPE"})
    brief = stock_tools.prepare_pre_session_brief({"ticker": "NOPE"})

    assert poll["ok"] is False
    assert poll["incomplete_reason"] == "unknown_ticker"
    assert brief["ok"] is False
    assert brief["agent_run"] is None


def test_mcp_empty_watchlist_pre_session_does_not_queue(db, monkeypatch):
    from app.db.models import AgentRun, Company, ListPollState
    from app.mcp import stock_tools

    db.add(Company(ticker="KRU", name="KRUK"))
    db.commit()

    def fail_fetch(**_kwargs):
        raise AssertionError("empty watchlist must not fetch")

    monkeypatch.setattr(stock_tools.espi, "fetch_report_list_page", fail_fetch)

    result = stock_tools.prepare_pre_session_brief({"queue": True})

    assert result["ok"] is False
    assert result["agent_run"] is None
    assert result["espi_poll"]["incomplete_reason"] == "empty_watchlist"
    assert db.query(AgentRun).count() == 0
    assert db.query(ListPollState).count() == 0


def test_mcp_tool_result_text_is_json(db):
    from app.mcp.stock_workbench_server import handle_message

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "list_queued_agent_runs", "arguments": {}},
        }
    )
    text = response["result"]["content"][0]["text"]
    assert json.loads(text)["ok"] is True
