"""Canonical P3 valuation engine, immutable inputs and verifier boundary."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.api.schemas import ValuationRequestIn, ValuationScenarioAssumptions
from app.db.models import (
    AgentRun,
    Company,
    CompanyProfile,
    DocumentVersion,
    Fact,
    Price,
    ResearchCase,
    ResearchSnapshot,
    SourceDocument,
    ValuationSnapshot,
    VerificationRun,
    utcnow,
)
from app.services.agent_queue import claim_agent_run
from app.services.valuation_engine import ValuationInputError, calculate_valuation


def _value(value, provenance="human_assumption", fact_ids=None):
    return {
        "value": value,
        "provenance": provenance,
        "rationale": "Jawne wejście scenariusza.",
        "source_fact_ids": fact_ids or [],
    }


def _scenario(kind, *, growth=10.0, margin=40.0, costs=20.0, cash=100.0, event=None):
    row = {
        "kind": kind,
        "label": kind,
        "quarter_revenue_growth_pct": _value(growth),
        "year_revenue_growth_pct": _value(growth),
        "gross_margin_pct": _value(margin),
        "operating_cost_ratio_pct": _value(costs),
        "financial_result_ratio_pct": _value(0.0),
        "tax_rate_pct": _value(20.0),
        "cash_conversion_pct": _value(cash),
        "capex_spend_ratio_pct": _value(5.0),
        "target_pe": _value(10.0),
    }
    if event is not None:
        row["event_one_off_net_pln_thousands"] = _value(event)
    return row


def _request(snapshot_id, as_of, *, scenarios=None, method="malik_obs_v1"):
    return {
        "research_snapshot_id": snapshot_id,
        "method_pack_id": method,
        "as_of": as_of.isoformat(),
        "assumptions": scenarios or [
            _scenario("negative", growth=-10),
            _scenario("base"),
            _scenario("positive", growth=20),
        ],
    }


def _research_fixture(db, *, ticker="ABS", archetype="software-services"):
    now = utcnow()
    company = Company(
        ticker=ticker,
        name=f"{ticker} SA",
        sector="Informatyka",
        shares_outstanding=1_000_000,
        market_cap=10_000_000,
        updated_at=now - timedelta(days=2),
    )
    db.add(company)
    db.flush()
    case = ResearchCase(company_id=company.id, purpose="investment-research")
    db.add(case)
    db.flush()
    profile = CompanyProfile(
        research_case_id=case.id,
        version=1,
        schema_version="company-profile-v2",
        archetype=archetype,
        archetype_version=f"{archetype}-v1",
        company_overlay={},
        drivers=[],
        kpis=[],
    )
    db.add(profile)
    db.flush()
    source = SourceDocument(
        company_id=None,
        company_ticker=ticker,
        source_name="fixture",
        source_type="financial_report",
        scope_key="income-q",
        canonical_url="https://example.test/report",
        first_seen_at=now - timedelta(days=2),
        last_fetched_at=now - timedelta(days=2),
        latest_content_hash="a" * 64,
        mime_type="text/html",
        parser_version="fixture-v1",
        last_fetch_status=200,
    )
    db.add(source)
    db.flush()
    version = DocumentVersion(
        source_document_id=source.id,
        content_hash="a" * 64,
        fetched_at=now - timedelta(days=2),
        requested_url=source.canonical_url,
        effective_url=source.canonical_url,
        response_status=200,
        mime_type="text/html",
        parser_version="fixture-v1",
        parse_status="parsed",
        byte_size=6,
        raw_content="report",
    )
    db.add(version)
    db.flush()
    fact_id = 0
    for index, period in enumerate(("2025Q1", "2025Q2", "2025Q3", "2025Q4"), 1):
        revenue = 1000.0 * index
        for key, value in (
            ("income.IncomeRevenues", revenue),
            ("income.IncomeCostOfSales", revenue * 0.6),
            ("income.IncomeShareholderNetProfit", revenue * 0.1),
            ("income.IncomeDiscontinuedProfit", 0.0),
        ):
            fact_id += 1
            db.add(Fact(
                company_id=None,
                company_ticker=ticker,
                source_version_id=version.id,
                fact_type="financial_statement",
                fact_key=key,
                fact_hash=f"{fact_id:064x}",
                numeric_value=value,
                text_value=None,
                unit="tys_pln",
                period=period,
                effective_date=None,
                known_at=now - timedelta(days=2),
                locator={"period": period, "key": key},
                extractor_version="fixture-v1",
                confidence=1,
                verification_state="parsed",
            ))
    research_agent = AgentRun(
        workflow="stock-initial-research", status="provisional", company_id=company.id,
        model_role="worker_standard", model="fixture", inputs={}, outputs={},
    )
    db.add(research_agent)
    db.flush()
    research_verifier = VerificationRun(
        agent_run_id=research_agent.id,
        model_role="verifier_strict",
        verifier_model="fixture",
        verdict="pass",
        checks={},
    )
    db.add(research_verifier)
    db.flush()
    snapshot = ResearchSnapshot(
        research_case_id=case.id,
        company_profile_id=profile.id,
        agent_run_id=research_agent.id,
        verification_run_id=research_verifier.id,
        version=1,
        contract_version="research-snapshot-v2",
        status="provisional",
        as_of=now - timedelta(days=1),
        input_fingerprint="i" * 64,
        artifact_fingerprint="r" * 64,
        sections={},
        source_manifest=[{"document_version_id": version.id, "role": "normalized", "purpose": "facts"}],
        conflicts=[], gaps=[{"topic": "primary"}], next_checks=[], statement_provenance=[],
        verifier_result={},
    )
    db.add(snapshot)
    db.add(Price(
        company_id=company.id,
        date=now.date() - timedelta(days=1),
        close=10,
        adjustment_status="raw_unverified",
        source_name="stooq",
        series_key=f"{ticker}.PL",
        basis_version="raw-close-v1",
        scraped_at=now - timedelta(hours=1),
    ))
    db.commit()
    return case, snapshot, now


def _append_duplicate_fact_version(
    db,
    snapshot,
    *,
    numeric_value=4000.0,
    unit="tys_pln",
    fact_key="income.IncomeRevenues",
    content_marker="b",
):
    prior_version_id = snapshot.source_manifest[0]["document_version_id"]
    prior = db.get(DocumentVersion, prior_version_id)
    source = db.get(SourceDocument, prior.source_document_id)
    version = DocumentVersion(
        source_document_id=source.id,
        content_hash=content_marker * 64,
        fetched_at=snapshot.as_of - timedelta(hours=1),
        requested_url=source.canonical_url,
        effective_url=source.canonical_url,
        response_status=200,
        mime_type="text/html",
        parser_version="fixture-v2",
        parse_status="parsed",
        byte_size=7,
        raw_content="report2",
    )
    db.add(version)
    db.flush()
    fact = Fact(
        company_id=None,
        company_ticker=source.company_ticker,
        source_version_id=version.id,
        fact_type="financial_statement",
        fact_key=fact_key,
        fact_hash=("f" if content_marker == "b" else "e") * 64,
        numeric_value=numeric_value,
        text_value=None,
        unit=unit,
        period="2025Q4",
        effective_date=None,
        known_at=version.fetched_at,
        locator={"period": "2025Q4"},
        extractor_version="fixture-v2",
        confidence=1,
        verification_state="parsed",
    )
    db.add(fact)
    snapshot.source_manifest = [
        *snapshot.source_manifest,
        {"document_version_id": version.id, "role": "normalized", "purpose": "new version"},
    ]
    db.commit()
    return fact


def test_engine_hand_calculation_and_positive_capex_outlay():
    base = {
        "company": {"shares_outstanding": 1_000_000},
        "price": {"close_pln": 10.0},
        "latest_quarter_revenue_pln_thousands": 1000.0,
        "forward_12m_revenue_base_pln_thousands": 4000.0,
    }
    assumptions = [ValuationScenarioAssumptions.model_validate(_scenario("base"))]
    result = calculate_valuation(base, assumptions)
    row = result["scenarios"][0]
    assert row["quarter"]["revenue_pln_thousands"] == 1100.0
    assert row["quarter"]["net_result_pln_thousands"] == 176.0
    assert row["forward_12m"]["cfo_pln_thousands"] == 704.0
    assert row["forward_12m"]["capex_spend_pln_thousands"] == 220.0
    assert row["forward_12m"]["fcf_pln_thousands"] == 484.0
    assert row["target_price_pln"] == 7.04
    assert row["return_pct"] == -29.6
    assert result["probability_weighted"] is None


def test_engine_does_not_price_non_positive_eps():
    base = {
        "company": {"shares_outstanding": 1_000_000},
        "price": {"close_pln": 10.0},
        "latest_quarter_revenue_pln_thousands": 1000.0,
        "forward_12m_revenue_base_pln_thousands": 4000.0,
    }
    assumptions = [ValuationScenarioAssumptions.model_validate(
        _scenario("negative", margin=-10, costs=100)
    )]
    row = calculate_valuation(base, assumptions)["scenarios"][0]
    assert row["target_price_pln"] is None
    assert row["return_pct"] is None
    assert row["valuation_status"] == "unavailable"


def test_assumption_contract_rejects_bad_signs_ranges_and_model_suggestions():
    invalid = _scenario("base")
    invalid["quarter_revenue_growth_pct"] = _value(-100)
    with pytest.raises(ValueError):
        ValuationScenarioAssumptions.model_validate(invalid)
    invalid = _scenario("base")
    invalid["capex_spend_ratio_pct"] = _value(-1)
    with pytest.raises(ValueError):
        ValuationScenarioAssumptions.model_validate(invalid)
    invalid = _scenario("base")
    invalid["target_pe"]["provenance"] = "model_suggestion"
    with pytest.raises(ValueError):
        ValuationScenarioAssumptions.model_validate(invalid)


def test_preview_uses_manifest_facts_without_serving_rows_and_writes_nothing(client, db):
    case, snapshot, now = _research_fixture(db)
    counts_before = (
        db.query(AgentRun).count(), db.query(ValuationSnapshot).count()
    )
    response = client.post(
        f"/api/research-cases/{case.id}/valuation-preview",
        json=_request(snapshot.id, now),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["template"]["id"] == "software-services-earnings-pe-v1"
    assert body["base_values"]["latest_quarter_revenue_pln_thousands"] == 4000.0
    assert len(body["input_manifest"]["fact_ids"]) >= 4
    assert counts_before == (db.query(AgentRun).count(), db.query(ValuationSnapshot).count())


@pytest.mark.parametrize(
    ("numeric_value", "unit"),
    [(4001.0, "tys_pln"), (4000.0, "PLN")],
)
def test_manifest_duplicate_conflict_is_rejected(client, db, numeric_value, unit):
    case, snapshot, now = _research_fixture(db, ticker="DUP")
    _append_duplicate_fact_version(db, snapshot, numeric_value=numeric_value, unit=unit)
    response = client.post(
        f"/api/research-cases/{case.id}/valuation-preview",
        json=_request(snapshot.id, now),
    )
    assert response.status_code == 409
    assert "Conflicting immutable facts" in response.text


def test_exact_duplicate_selects_only_latest_fact(client, db):
    case, snapshot, now = _research_fixture(db, ticker="SAME")
    latest = _append_duplicate_fact_version(db, snapshot)
    response = client.post(
        f"/api/research-cases/{case.id}/valuation-preview",
        json=_request(snapshot.id, now),
    )
    assert response.status_code == 200, response.text
    fact_ids = response.json()["input_manifest"]["fact_ids"]
    assert latest.id in fact_ids
    older = db.query(Fact).filter(
        Fact.fact_key == "income.IncomeRevenues", Fact.period == "2025Q4",
        Fact.source_version_id != latest.source_version_id,
    ).one()
    assert older.id not in fact_ids


def test_irrelevant_conflicting_indicator_does_not_block_valuation(client, db):
    case, snapshot, now = _research_fixture(db, ticker="CONTEXT")
    original_version_id = snapshot.source_manifest[0]["document_version_id"]
    db.add(Fact(
        company_id=None,
        company_ticker="CONTEXT",
        source_version_id=original_version_id,
        fact_type="indicator",
        fact_key="indicator.gross_margin",
        fact_hash="d" * 64,
        numeric_value=30.0,
        text_value=None,
        unit="%",
        period="2025Q4",
        effective_date=None,
        known_at=now - timedelta(days=2),
        locator={"period": "2025Q4"},
        extractor_version="fixture-v1",
        confidence=1,
        verification_state="parsed",
    ))
    db.commit()
    _append_duplicate_fact_version(
        db,
        snapshot,
        numeric_value=40.0,
        unit="%",
        fact_key="indicator.gross_margin",
    )
    response = client.post(
        f"/api/research-cases/{case.id}/valuation-preview",
        json=_request(snapshot.id, now),
    )
    assert response.status_code == 200, response.text
    assert response.json()["base_values"]["latest_quarter_revenue_pln_thousands"] == 4000.0


@pytest.mark.parametrize("close", [0.0, -1.0, float("inf")])
def test_raw_price_must_be_finite_and_positive(client, db, close):
    case, snapshot, now = _research_fixture(db, ticker="PRICE")
    price = db.query(Price).filter(Price.company_id == case.company_id).one()
    price.close = close
    db.commit()
    response = client.post(
        f"/api/research-cases/{case.id}/valuation-preview",
        json=_request(snapshot.id, now),
    )
    assert response.status_code == 409
    assert "finite and positive" in response.text


def test_reads_are_zero_write_and_blocked_packs_are_honest(client, db):
    case, snapshot, now = _research_fixture(db)
    before = db.query(AgentRun).count()
    packs = client.get("/api/valuation-method-packs").json()
    assert [row["status"] for row in packs] == ["ready", "blocked", "blocked"]
    assert all(row["reason"] for row in packs[1:])
    workspace = client.get(f"/api/research-cases/{case.id}/valuation-workspace")
    assert workspace.status_code == 200
    assert workspace.json()["template"]["id"] == "software-services-earnings-pe-v1"
    assert db.query(AgentRun).count() == before
    blocked = client.post(
        f"/api/research-cases/{case.id}/valuation-preview",
        json=_request(snapshot.id, now, method="areczeks_v1"),
    )
    assert blocked.status_code == 409


def _draft_from_run(agent):
    frozen = agent.inputs["valuation"]
    kinds = [row["kind"] for row in frozen["assumptions"]]
    return {
        "contract_version": "valuation-snapshot-v1",
        "engine_version": "valuation-engine-v2",
        "template_contract_version": "valuation-templates-v1",
        "agent_run_id": agent.id,
        "lease_owner": agent.lease_owner,
        "version": 1,
        **{key: frozen[key] for key in (
            "research_snapshot_id", "as_of", "method_pack_id",
            "method_pack_version", "template_id", "template_version", "assumptions",
            "base_values", "deterministic_outputs", "input_manifest", "gaps",
            "input_fingerprint", "calculation_fingerprint",
        )},
        "codex_judgment": {
            "method_read": "Jawny odczyt metody.",
            "scenarios": [{
                "kind": kind,
                "mechanism": "Jawny mechanizm wyniku.",
                "proposed_probability_pct": {"negative": 25, "base": 50, "positive": 25}.get(kind, 0),
                "probability_rationale": "Rationale oparte na zamrożonych wejściach.",
                "catalyst_or_counter_driver": "Konkretny driver.",
                "falsifier": "Jawny falsyfikator.",
                "gaps": [],
            } for kind in kinds],
            "catalysts": ["Driver"],
            "falsifiers": ["Falsifier"],
        },
    }


def _verifier(draft, *, verdict="pass", verifier="verifier-1"):
    probabilities = [] if verdict != "pass" else [
        {"kind": "negative", "probability_pct": 25, "rationale": "Downside."},
        {"kind": "base", "probability_pct": 50, "rationale": "Base."},
        {"kind": "positive", "probability_pct": 25, "rationale": "Upside."},
    ]
    return {
        "verifier_worker_id": verifier,
        "draft": draft,
        "verifier_result": {
            "model_role": "verifier_strict",
            "verifier_model": "gpt-5.6-sol",
            "verdict": verdict,
            "checks": {key: verdict == "pass" for key in (
                "schema_integrity", "source_integrity", "company_identity", "look_ahead",
                "math_integrity", "probability_coherence", "method_integrity",
            )},
            "final_probabilities": probabilities,
            "summary": "Independent verdict.",
        },
    }


def test_queue_is_idempotent_and_exact_independent_save_is_provisional(client, db):
    case, snapshot, now = _research_fixture(db)
    payload = _request(snapshot.id, now)
    first = client.post(f"/api/research-cases/{case.id}/valuation-runs", json=payload)
    assert first.status_code == 201, first.text
    second = client.post(f"/api/research-cases/{case.id}/valuation-runs", json=payload)
    assert second.json()["agent_run_id"] == first.json()["agent_run_id"]
    assert second.json()["created"] is False
    agent = claim_agent_run(db, agent_run_id=first.json()["agent_run_id"], worker_id="drafter")
    draft = _draft_from_run(agent)
    self_verification = client.post(
        f"/api/research-cases/{case.id}/valuation-verifications",
        json=_verifier(draft, verifier="drafter"),
    )
    assert self_verification.status_code == 409
    verified = client.post(
        f"/api/research-cases/{case.id}/valuation-verifications",
        json=_verifier(draft),
    )
    assert verified.status_code == 200, verified.text
    saved = client.post(
        f"/api/research-cases/{case.id}/valuation-snapshots",
        json={**draft, "verification_run_id": verified.json()["id"]},
    )
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["status"] == "provisional"
    assert body["deterministic_outputs"]["probability_weighted"]["status"] == "calculated"
    db.refresh(agent)
    assert agent.lease_owner is None and agent.status == "provisional"


def test_distinct_active_valuation_is_rejected_without_creating_peer(client, db):
    case, snapshot, now = _research_fixture(db, ticker="SERIAL")
    first_payload = _request(snapshot.id, now)
    first = client.post(
        f"/api/research-cases/{case.id}/valuation-runs", json=first_payload
    )
    assert first.status_code == 201
    second_payload = _request(snapshot.id, now)
    second_payload["assumptions"][2]["year_revenue_growth_pct"]["value"] = 21.0
    second = client.post(
        f"/api/research-cases/{case.id}/valuation-runs", json=second_payload
    )
    assert second.status_code == 409
    rows = db.query(AgentRun).filter(
        AgentRun.company_id == case.company_id,
        AgentRun.workflow == "stock-company-valuation",
    ).all()
    assert len(rows) == 1
    assert rows[0].id == first.json()["agent_run_id"]
    assert rows[0].status == "queued"


def test_fail_verdict_saves_rejected_without_probabilities(client, db):
    case, snapshot, now = _research_fixture(db, ticker="FAIL")
    queued = client.post(
        f"/api/research-cases/{case.id}/valuation-runs",
        json=_request(snapshot.id, now),
    ).json()
    agent = claim_agent_run(db, agent_run_id=queued["agent_run_id"], worker_id="drafter")
    draft = _draft_from_run(agent)
    verification = client.post(
        f"/api/research-cases/{case.id}/valuation-verifications",
        json=_verifier(draft, verdict="fail"),
    )
    assert verification.status_code == 200, verification.text
    saved = client.post(
        f"/api/research-cases/{case.id}/valuation-snapshots",
        json={**draft, "verification_run_id": verification.json()["id"]},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["status"] == "rejected"
    assert saved.json()["deterministic_outputs"]["probability_weighted"] is None


def test_policy_picker_mcp_and_script_contracts(client, db):
    from pathlib import Path

    from app.mcp import stock_tools
    from app.mcp.stock_workbench_server import TOOLS
    from app.services.model_policy import get_model_policy
    from scripts.codex_pick_agent_run import _execution_contract

    case, snapshot, now = _research_fixture(db, ticker="WIRE")
    queued = client.post(
        f"/api/research-cases/{case.id}/valuation-runs",
        json=_request(snapshot.id, now),
    ).json()
    agent = db.get(AgentRun, queued["agent_run_id"])
    contract = _execution_contract(agent)
    assert contract["skill"] == "company-valuation"
    assert "codex_verify_valuation_snapshot.py" in contract["verify_command"]
    policy = get_model_policy("stock-company-valuation")
    assert policy["draft_model"] == "gpt-5.6-terra"
    assert policy["draft_role"] == "worker_standard"
    assert policy["required_verifier_role"] == "verifier_strict"
    assert [row["status"] for row in stock_tools.get_valuation_method_packs()["method_packs"]] == [
        "ready", "blocked", "blocked"
    ]
    assert {"get_valuation_method_packs", "verify_valuation_snapshot", "save_valuation_snapshot"}.issubset(TOOLS)
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    assert (scripts / "codex_verify_valuation_snapshot.py").is_file()
    assert (scripts / "codex_save_valuation_snapshot.py").is_file()
