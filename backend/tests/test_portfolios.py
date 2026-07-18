"""Immutable portfolio sync, read, mapping, analytics and auth contracts."""

import copy
import hashlib
from types import SimpleNamespace
from datetime import date, datetime, timedelta, timezone

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
    PortfolioOperation,
    Price,
    ThesisFalsifier,
)
from app.services.agent_queue import claim_agent_run
from app.services.portfolio import (
    _solve_xirr,
    calculate_portfolio_performance,
    normalize_myfund,
)
from app.services.valuation_engine import canonical_hash


def _canonical_research_verifier_result() -> dict:
    return {
        "model_role": "verifier_strict",
        "verifier_model": "test",
        "verdict": "pass",
        "findings": [],
        "justifications": {
            "evidence_and_claim_fit": "Fixture evidence stays bound to the stored source inputs for this deterministic portfolio contract test.",
            "company_specificity": "The fixture uses this company identity only and does not infer a reusable cross-company research result.",
            "outlook_and_thesis_plausibility": "The fixture retains only the bounded point-in-time research state required for portfolio eligibility.",
        },
        "summary": "Canonical Research verification fixture.",
    }


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


def operations_csv() -> str:
    return "\n".join(
        [
            "Data;Operacja;Konto;Walor;Waluta;Liczba jednostek;Cena;Prowizja;Podatek;Wartość;Stan konta po operacji",
            "2026-07-09;Wpłata;mBank;Gotówka;;;;;;9000;9000",
            "2026-07-10;Wpłata;mBank;Gotówka;;;;;;1000;3995",
            "2026-07-10;Kupno;mBank;SYNEKTIK (SNT);PLN;20;300;5;0;-6005;2995",
        ]
    )


def _append_valuation(
    db,
    *,
    company: Company,
    case: ResearchCase,
    research: ResearchSnapshot,
    version: int,
    status: str,
    weighted_price: float | None,
    fingerprint: str,
) -> ValuationSnapshot:
    run = AgentRun(
        workflow="stock-company-valuation",
        status="completed",
        company_id=company.id,
        inputs={},
        outputs={},
    )
    db.add(run)
    db.flush()
    verification_id = None
    if status == "verified":
        verification = VerificationRun(
            agent_run_id=run.id,
            model_role="verifier_strict",
            verifier_model="test",
            verdict="pass",
            checks={},
        )
        db.add(verification)
        db.flush()
        verification_id = verification.id
    valuation = ValuationSnapshot(
        research_case_id=case.id,
        research_snapshot_id=research.id,
        agent_run_id=run.id,
        verification_run_id=verification_id,
        version=version,
        contract_version="valuation-snapshot-v3",
        status=status,
        as_of=datetime(2026, 7, 10, tzinfo=timezone.utc),
        template_id="industrial",
        template_version="v1",
        calculation_engine_version="valuation-engine-v4",
        assumptions={},
        base_values={},
        deterministic_outputs={
            "scenarios": [
                {"kind": "negative", "target_price_pln": 100},
                {"kind": "base", "target_price_pln": 200},
                {"kind": "positive", "target_price_pln": 400},
            ],
            "probability_weighted": {"price_pln": weighted_price},
        },
        codex_judgment={},
        input_manifest={},
        gaps=[],
        input_fingerprint=fingerprint,
        calculation_fingerprint=fingerprint,
        artifact_fingerprint=fingerprint,
        verifier_result={},
    )
    db.add(valuation)
    db.commit()
    return valuation


def test_sync_coverage_is_idempotent_logged_prioritized_and_drives_research_read(
    client, db, monkeypatch
):
    from app.api import portfolios
    from app.services.research_queue import ensure_research_case

    db.add(Company(ticker="SNT", name="Synektik", market="GPW"))
    db.commit()
    manual = ensure_research_case(db, ticker="SNT", origin="manual")
    db.commit()
    original_agent_id = manual.agent.id
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )

    first = client.post("/api/portfolios/sync/myfund")
    assert first.status_code == 200, first.text
    first_body = first.json()
    included = [
        row for row in first_body["sync"]["coverage_decisions"] if row["included"]
    ]
    excluded = [
        row for row in first_body["sync"]["coverage_decisions"] if not row["included"]
    ]
    assert len(included) == 1
    assert included[0]["company_id"] == manual.company.id
    assert included[0]["research_origin"] == "manual"
    assert included[0]["agent_run_id"] == original_agent_id
    assert included[0]["created_job"] is False
    assert included[0]["staleness_days"] == 31
    assert included[0]["weight_pct"] == 60
    assert included[0]["priority_score"] == 1860
    assert excluded
    assert {reason for row in excluded for reason in row["reasons"]} == {
        "mapping_not_company"
    }
    db.refresh(manual.agent)
    assert float(manual.agent.queue_priority) == 1860
    assert manual.agent.inputs["portfolio_coverage"]["portfolio_sync_id"] == first_body[
        "sync"
    ]["id"]

    repeated = client.post("/api/portfolios/sync/myfund")
    assert repeated.status_code == 200, repeated.text
    repeated_body = repeated.json()
    assert repeated_body["sync"]["reused_snapshot"] is True
    repeated_decision = next(
        row for row in repeated_body["sync"]["coverage_decisions"] if row["included"]
    )
    assert repeated_decision["agent_run_id"] == original_agent_id
    assert repeated_decision["created_job"] is False
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == 1

    ensure_research_case(
        db,
        ticker="DIS",
        origin="discover",
        discovery_origin={"candidate": {"name": "Discover SA"}},
    )
    ensure_research_case(db, ticker="MAN", origin="manual")
    db.commit()
    before = {
        "syncs": db.scalar(select(func.count()).select_from(PortfolioSync)),
        "cases": db.scalar(select(func.count()).select_from(ResearchCase)),
        "runs": db.scalar(select(func.count()).select_from(AgentRun)),
    }
    listed = client.get("/api/research-cases")
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["ticker"] for row in rows] == ["SNT", "DIS", "MAN"]
    holding = rows[0]
    assert holding["origin"] == "manual"
    assert holding["is_portfolio_holding"] is True
    assert holding["portfolio_weight_pct"] == 60
    assert holding["portfolio_priority_score"] == 1860
    assert holding["portfolio_staleness_days"] == 31
    assert holding["portfolio_coverage_state"] == "research_pending"
    assert any("zweryfikowanego Research" in reason for reason in holding["agenda_reasons"])
    assert all("job" not in reason.casefold() for reason in holding["agenda_reasons"])
    after = {
        "syncs": db.scalar(select(func.count()).select_from(PortfolioSync)),
        "cases": db.scalar(select(func.count()).select_from(ResearchCase)),
        "runs": db.scalar(select(func.count()).select_from(AgentRun)),
    }
    assert after == before


def test_operations_csv_requires_preview_then_atomically_replaces_and_reconciles(
    client, db, monkeypatch
):
    from app.api import portfolios

    raw = payload()
    raw["wkladWCzasie"]["2026-07-10"] = "10000"
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(raw)
    )
    assert client.post("/api/portfolios/sync/myfund").status_code == 200
    file_payload = {"filename": "historia-operacji.csv", "content": operations_csv()}

    before = db.scalar(select(func.count()).select_from(PortfolioOperation))
    preview = client.post("/api/portfolios/operations/preview", json=file_payload)
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert db.scalar(select(func.count()).select_from(PortfolioOperation)) == before
    assert preview_body["version"] == "myfund-operations-csv-v1"
    assert len(preview_body["fingerprint"]) == 64
    assert preview_body["summary"] == {
        "row_count": 3,
        "date_from": "2026-07-09",
        "date_to": "2026-07-10",
        "deposit_total_pln": 10000,
        "withdrawal_total_pln": 0,
        "external_flow_count": 2,
        "unclassified_count": 0,
        "currency_defaulted_rows": 2,
    }

    stale = client.post(
        "/api/portfolios/operations/import",
        json={
            **file_payload,
            "expected_fingerprint": "0" * 64,
            "confirm_full_export": True,
        },
    )
    assert stale.status_code == 409
    assert db.scalar(select(func.count()).select_from(PortfolioOperation)) == 0

    imported = client.post(
        "/api/portfolios/operations/import",
        json={
            **file_payload,
            "expected_fingerprint": preview_body["fingerprint"],
            "confirm_full_export": True,
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["import"] == {
        "changed": True,
        "replaced_count": 0,
        "imported_count": 3,
        "fingerprint": preview_body["fingerprint"],
    }
    operations = imported.json()["workspace"]["operations"]
    assert operations["status"] == "imported"
    assert operations["count"] == 3
    assert operations["flow_reconciliation"] == {
        "status": "reconciled",
        "matched_days": 1,
        "mismatches": [],
        "provider_contribution_change_pln": 1000,
        "operation_external_flow_pln": 1000,
    }
    buy_operation = next(row for row in operations["recent"] if row["ticker"] == "SNT")
    assert buy_operation["commission"] == 5
    snt_position = next(
        row for row in imported.json()["workspace"]["positions"] if row["ticker"] == "SNT"
    )
    assert snt_position["operation_cost_basis_status"] == "reconciled"
    assert snt_position["operation_cost_basis"] == 6005
    assert snt_position["operation_profit"] == -5

    repeated = client.post(
        "/api/portfolios/operations/import",
        json={
            **file_payload,
            "expected_fingerprint": preview_body["fingerprint"],
            "confirm_full_export": True,
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["import"]["changed"] is False
    assert db.scalar(select(func.count()).select_from(PortfolioOperation)) == 3

    queued_review = client.post("/api/portfolios/review-runs").json()
    review_agent = claim_agent_run(
        db,
        agent_run_id=queued_review["agent_run_id"],
        worker_id="operations-review-drafter",
    )
    replacement_content = "\n".join(operations_csv().splitlines()[:-1])
    replacement_payload = {
        "filename": "historia-operacji.csv",
        "content": replacement_content,
    }
    replacement_preview = client.post(
        "/api/portfolios/operations/preview", json=replacement_payload
    ).json()
    assert (
        client.post(
            "/api/portfolios/operations/import",
            json={
                **replacement_payload,
                "expected_fingerprint": replacement_preview["fingerprint"],
                "confirm_full_export": True,
            },
        ).status_code
        == 200
    )
    changed_after_freeze = client.post(
        "/api/portfolios/review-verifications",
        json=_review_verification(_review_draft(review_agent)),
    )
    assert changed_after_freeze.status_code == 409
    assert "operations changed" in changed_after_freeze.json()["detail"]


def test_operations_csv_rejects_wrong_shape_or_sign_without_replacing_history(
    client, db, monkeypatch
):
    from app.api import portfolios

    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    assert client.post("/api/portfolios/sync/myfund").status_code == 200
    valid = {"filename": "operacje.csv", "content": operations_csv()}
    preview = client.post("/api/portfolios/operations/preview", json=valid).json()
    assert (
        client.post(
            "/api/portfolios/operations/import",
            json={
                **valid,
                "expected_fingerprint": preview["fingerprint"],
                "confirm_full_export": True,
            },
        ).status_code
        == 200
    )
    before_hashes = list(
        db.scalars(
            select(PortfolioOperation.content_hash).order_by(
                PortfolioOperation.content_hash
            )
        )
    )

    wrong_sign = operations_csv().replace(";-6005;2995", ";6005;2995")
    rejected = client.post(
        "/api/portfolios/operations/preview",
        json={"filename": "operacje.csv", "content": wrong_sign},
    )
    assert rejected.status_code == 422
    assert "znak Wartości" in rejected.json()["detail"]
    wrong_math = operations_csv().replace(";-6005;2995", ";-6004;2995")
    arithmetic_rejected = client.post(
        "/api/portfolios/operations/preview",
        json={"filename": "operacje.csv", "content": wrong_math},
    )
    assert arithmetic_rejected.status_code == 422
    assert "nie uzgadnia" in arithmetic_rejected.json()["detail"]
    missing_header = client.post(
        "/api/portfolios/operations/preview",
        json={"filename": "operacje.csv", "content": "Data;Operacja\n2026-07-10;Kupno"},
    )
    assert missing_header.status_code == 422
    assert list(
        db.scalars(
            select(PortfolioOperation.content_hash).order_by(
                PortfolioOperation.content_hash
            )
        )
    ) == before_hashes


def test_operation_cost_basis_is_withheld_for_ambiguous_same_day_buy_sell_order(
    client, monkeypatch
):
    from app.api import portfolios

    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    assert client.post("/api/portfolios/sync/myfund").status_code == 200
    header = operations_csv().splitlines()[0]
    ambiguous = "\n".join(
        [
            header,
            "2026-07-10;Kupno;mBank;SYNEKTIK (SNT);PLN;10;100;0;0;-1000;9000",
            "2026-07-10;Sprzedaż;mBank;SYNEKTIK (SNT);PLN;-5;200;0;0;1000;10000",
            "2026-07-10;Kupno;mBank;SYNEKTIK (SNT);PLN;15;300;0;0;-4500;5500",
        ]
    )
    file_payload = {"filename": "operacje.csv", "content": ambiguous}
    preview = client.post(
        "/api/portfolios/operations/preview", json=file_payload
    ).json()
    imported = client.post(
        "/api/portfolios/operations/import",
        json={
            **file_payload,
            "expected_fingerprint": preview["fingerprint"],
            "confirm_full_export": True,
        },
    )
    assert imported.status_code == 200, imported.text
    position = next(
        row for row in imported.json()["workspace"]["positions"] if row["ticker"] == "SNT"
    )
    assert position["operation_cost_basis_status"] == "unavailable"
    assert position["operation_cost_basis"] is None
    assert any(
        "pewną kolejność" in gap
        for gap in position["operation_cost_basis_gaps"]
    )


def test_operations_csv_preserves_timestamps_and_excludes_tax_from_value_math(
    client, monkeypatch
):
    from app.api import portfolios

    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    assert client.post("/api/portfolios/sync/myfund").status_code == 200
    header = operations_csv().splitlines()[0]
    timestamped = "\n".join(
        [
            header,
            "2026-07-10 11:00;Kupno;mBank;SYNEKTIK (SNT);PLN;15;300;0;0;-4500;5500",
            "2026-07-10 10:00;Sprzedaż;mBank;SYNEKTIK (SNT);PLN;-5;200;5;10;995;10000",
            "2026-07-10 09:00;Kupno;mBank;SYNEKTIK (SNT);PLN;10;100;0;0;-1000;9000",
        ]
    )
    file_payload = {"filename": "operacje.csv", "content": timestamped}
    preview = client.post(
        "/api/portfolios/operations/preview", json=file_payload
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["sample"][0]["occurred_at"] == "2026-07-10T11:00:00"
    reordered = "\n".join(
        [timestamped.splitlines()[0], *reversed(timestamped.splitlines()[1:])]
    )
    reordered_preview = client.post(
        "/api/portfolios/operations/preview",
        json={"filename": "operacje.csv", "content": reordered},
    )
    assert reordered_preview.status_code == 200, reordered_preview.text
    assert reordered_preview.json()["fingerprint"] != preview_body["fingerprint"]

    imported = client.post(
        "/api/portfolios/operations/import",
        json={
            **file_payload,
            "expected_fingerprint": preview_body["fingerprint"],
            "confirm_full_export": True,
        },
    )
    assert imported.status_code == 200, imported.text
    operations = imported.json()["workspace"]["operations"]
    assert [row["occurred_at"] for row in operations["recent"]] == [
        "2026-07-10T11:00:00",
        "2026-07-10T10:00:00",
        "2026-07-10T09:00:00",
    ]
    sale = next(row for row in operations["recent"] if row["kind"] == "sell")
    assert sale["occurred_at"] == "2026-07-10T10:00:00"
    assert sale["amount_pln"] == 995
    assert sale["commission"] == 5
    assert sale["tax"] == 10
    position = next(
        row
        for row in imported.json()["workspace"]["positions"]
        if row["ticker"] == "SNT"
    )
    assert position["operation_cost_basis_status"] == "reconciled"
    assert position["operation_cost_basis"] == 5000


def test_sync_coverage_queues_and_reuses_valuation_for_latest_verified_research(
    client, db, monkeypatch
):
    from app.api import portfolios
    from app.services import portfolio_coverage

    company = Company(ticker="SNT", name="Synektik", market="GPW")
    db.add(company)
    db.commit()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    assert client.post("/api/portfolios/sync/myfund").status_code == 200
    case = db.scalar(
        select(ResearchCase).where(ResearchCase.company_id == company.id)
    )
    assert case is not None
    profile = CompanyProfile(
        research_case_id=case.id,
        version=1,
        schema_version="company-profile-v2",
        archetype="industrial-consumer",
        archetype_version="archetype-packs-v1",
        company_overlay={},
        drivers=[],
        kpis=[],
        provenance="human-confirmed",
    )
    db.add(profile)
    db.flush()
    research_run = AgentRun(
        workflow="stock-company-review",
        status="verified",
        company_id=company.id,
        inputs={"research_case_id": case.id},
        outputs={},
    )
    db.add(research_run)
    db.flush()
    verification = VerificationRun(
        agent_run_id=research_run.id,
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
        agent_run_id=research_run.id,
        verification_run_id=verification.id,
        version=1,
        contract_version="research-snapshot-v3",
        status="verified",
        as_of=datetime.now(timezone.utc) - timedelta(minutes=1),
        input_fingerprint="coverage-research-input",
        artifact_fingerprint="c" * 64,
        sections={},
        source_manifest=[],
        conflicts=[],
        gaps=[],
        next_checks=[],
        statement_provenance=[],
        verifier_result=_canonical_research_verifier_result(),
    )
    db.add(research)
    db.commit()
    calls = []

    def fake_enqueue(db, *, case, research_snapshot_id, trigger, queue_priority,
                     portfolio_coverage, **_kwargs):
        calls.append(research_snapshot_id)
        run = AgentRun(
            workflow="stock-company-valuation",
            trigger=trigger,
            status="queued",
            company_id=case.company_id,
            idempotency_key=f"test-auto-valuation:{research_snapshot_id}",
            queue_priority=queue_priority,
            inputs={
                "research_case_id": case.id,
                "valuation": {"research_snapshot_id": research_snapshot_id},
                "portfolio_coverage": portfolio_coverage,
            },
            outputs={},
        )
        db.add(run)
        db.flush()
        return SimpleNamespace(
            agent=run, created=True, input_fingerprint="test-auto-valuation"
        )

    monkeypatch.setattr(portfolio_coverage, "enqueue_valuation", fake_enqueue)
    first = client.post("/api/portfolios/sync/myfund").json()
    decision = next(
        row for row in first["sync"]["coverage_decisions"] if row["included"]
    )
    assert decision["coverage_state"] == "valuation_queued"
    assert decision["research_snapshot_id"] == research.id
    assert calls == [research.id]
    valuation_run_id = decision["agent_run_id"]

    repeated = client.post("/api/portfolios/sync/myfund").json()
    decision = next(
        row for row in repeated["sync"]["coverage_decisions"] if row["included"]
    )
    assert decision["coverage_state"] == "valuation_pending"
    assert decision["agent_run_id"] == valuation_run_id
    assert calls == [research.id]
    assert db.scalar(
        select(func.count()).select_from(AgentRun).where(
            AgentRun.workflow == "stock-company-valuation"
        )
    ) == 1


@pytest.mark.parametrize(
    ("research_status", "age_days", "falsifier_fired", "expected_reason"),
    [
        ("verified", 31, False, "research_older_than_30_days"),
        ("verified", 0, True, "current_falsifier_fired"),
        ("provisional", 0, False, "current_research_provisional"),
    ],
)
def test_sync_coverage_queues_one_canonical_research_review_idempotently(
    client,
    db,
    monkeypatch,
    research_status,
    age_days,
    falsifier_fired,
    expected_reason,
):
    from app.api import portfolios

    company = Company(ticker="SNT", name="Synektik", market="GPW")
    db.add(company)
    db.commit()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(
        portfolios.polite_http, "fetch", lambda *a, **k: Response(payload())
    )
    assert client.post("/api/portfolios/sync/myfund").status_code == 200
    case = db.scalar(
        select(ResearchCase).where(ResearchCase.company_id == company.id)
    )
    initial = db.scalar(
        select(AgentRun).where(
            AgentRun.company_id == company.id,
            AgentRun.workflow == "stock-initial-research",
        )
    )
    assert case is not None and initial is not None
    initial.status = research_status
    initial.finished_at = datetime.now(timezone.utc)
    profile = CompanyProfile(
        research_case_id=case.id,
        version=1,
        schema_version="company-profile-v2",
        archetype="industrial-consumer",
        archetype_version="archetype-packs-v1",
        company_overlay={"source_questions": ["Co zmieniło się w backlogu?"]},
        drivers=[],
        kpis=[],
        provenance="human-confirmed",
    )
    db.add(profile)
    db.flush()
    verification = VerificationRun(
        agent_run_id=initial.id,
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
        agent_run_id=initial.id,
        verification_run_id=verification.id,
        version=1,
        contract_version="research-snapshot-v3",
        status=research_status,
        as_of=datetime.now(timezone.utc) - timedelta(days=age_days, minutes=1),
        input_fingerprint=f"coverage-{research_status}-{age_days}",
        artifact_fingerprint=("d" if research_status == "verified" else "e") * 64,
        sections={},
        source_manifest=[],
        conflicts=[],
        gaps=[],
        next_checks=[],
        statement_provenance=[],
        verifier_result=_canonical_research_verifier_result(),
    )
    db.add(research)
    if falsifier_fired:
        db.add(
            ThesisFalsifier(
                company_id=company.id,
                key="coverage-risk",
                statement="Current portfolio thesis condition failed.",
                status="fired",
                reason="Focused coverage producer test.",
            )
        )
    db.commit()

    first = client.post("/api/portfolios/sync/myfund").json()
    first_decision = next(
        row for row in first["sync"]["coverage_decisions"] if row["included"]
    )
    assert first_decision["coverage_state"] == "research_review_queued"
    assert expected_reason in first_decision["reasons"]
    review_id = first_decision["agent_run_id"]
    review = db.get(AgentRun, review_id)
    assert review.workflow == "stock-company-review"
    assert review.trigger == "portfolio-sync-coverage"
    assert review.inputs["review"]["prior_research_snapshot_id"] == research.id
    assert review.inputs["portfolio_coverage"]["reason"] == expected_reason

    repeated = client.post("/api/portfolios/sync/myfund").json()
    repeated_decision = next(
        row for row in repeated["sync"]["coverage_decisions"] if row["included"]
    )
    assert repeated_decision["coverage_state"] == "research_review_pending"
    assert repeated_decision["agent_run_id"] == review_id
    assert db.scalar(
        select(func.count()).select_from(AgentRun).where(
            AgentRun.workflow == "stock-company-review"
        )
    ) == 1
    research_row = client.get("/api/research-cases").json()[0]
    assert research_row["portfolio_coverage_state"] == "research_review_pending"
    assert any("odświeżenia Research" in reason for reason in research_row["agenda_reasons"])
    assert all("research_review" not in reason for reason in research_row["agenda_reasons"])


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


def test_twr_excludes_daily_contribution_changes_before_compounding():
    result = calculate_portfolio_performance(
        [
            {"date": "2026-01-01", "value": 100.0, "contributed": 100.0},
            {"date": "2026-01-02", "value": 110.0, "contributed": 100.0},
            {"date": "2026-01-03", "value": 165.0, "contributed": 150.0},
        ],
        terminal_value=165.0,
        terminal_date=date(2026, 1, 3),
    )

    assert result["twr_pct"] == pytest.approx(15.0)
    assert result["twr_status"] == "complete"
    assert result["external_flow_count"] == 1


def test_twr_excludes_withdrawal_and_ignores_benchmark_only_dates():
    result = calculate_portfolio_performance(
        [
            {"date": "2025-12-31", "benchmark_return_pct": 1.0},
            {"date": "2026-01-01", "value": 100.0, "contributed": 100.0},
            {"date": "2026-01-02", "value": 110.0, "contributed": 100.0},
            {"date": "2026-01-03", "value": 90.0, "contributed": 80.0},
        ],
        terminal_value=90.0,
        terminal_date=date(2026, 1, 3),
    )

    assert result["twr_pct"] == pytest.approx(10.0)
    assert result["observation_count"] == 3
    assert result["external_flow_count"] == 1


def test_xirr_uses_actual_dated_contribution_flows_and_terminal_value():
    start = date(2025, 1, 1)
    history = [
        {
            "date": start + timedelta(days=offset),
            "value": 110.0 if offset == 365 else 100.0,
            "contributed": 100.0,
        }
        for offset in range(366)
    ]
    result = calculate_portfolio_performance(
        history,
        terminal_value=110.0,
        terminal_date=date(2026, 1, 1),
    )

    assert result["twr_pct"] == pytest.approx(10.0)
    assert result["xirr_pct"] == pytest.approx(10.0)
    assert result["xirr_status"] == "complete"
    assert result["window_start"] == "2025-01-01"
    assert result["window_end"] == "2026-01-01"


def test_xirr_uses_actual_365_across_leap_year_and_aggregates_terminal_day_flow():
    start = date(2024, 1, 1)
    history = [
        {
            "date": start + timedelta(days=offset),
            "value": 160.0 if offset == 366 else 100.0,
            "contributed": 150.0 if offset == 366 else 100.0,
        }
        for offset in range(367)
    ]
    result = calculate_portfolio_performance(
        history,
        terminal_value=160.0,
        terminal_date=date(2025, 1, 1),
    )

    expected = ((110.0 / 100.0) ** (365.0 / 366.0) - 1.0) * 100.0
    assert result["twr_pct"] == pytest.approx(10.0)
    assert result["xirr_pct"] == pytest.approx(expected, abs=1e-6)
    assert result["external_flow_count"] == 1


def test_performance_does_not_smooth_missing_values_or_series_days():
    incomplete = calculate_portfolio_performance(
        [
            {"date": "2025-01-01", "value": 100.0, "contributed": 100.0},
            {"date": "2025-01-02", "value": 110.0, "contributed": None},
        ],
        terminal_value=110.0,
        terminal_date=date(2025, 1, 2),
    )
    assert incomplete["twr_pct"] is None
    assert incomplete["xirr_pct"] is None
    assert any("nie wygładzono" in gap for gap in incomplete["gaps"])

    missing_day = calculate_portfolio_performance(
        [
            {"date": "2025-01-01", "value": 100.0, "contributed": 100.0},
            {"date": "2025-01-03", "value": 110.0, "contributed": 100.0},
        ],
        terminal_value=110.0,
        terminal_date=date(2025, 1, 3),
    )
    assert missing_day["twr_pct"] is None
    assert missing_day["xirr_pct"] is None
    assert any("ciągłą serią dzienną" in gap for gap in missing_day["gaps"])


def test_performance_rejects_duplicate_days_nonfinite_values_and_ambiguous_xirr():
    duplicate = calculate_portfolio_performance(
        [
            {"date": "2026-01-01", "value": 100.0, "contributed": 100.0},
            {"date": "2026-01-01", "value": 110.0, "contributed": 100.0},
        ],
        terminal_value=110.0,
        terminal_date=date(2026, 1, 1),
    )
    nonfinite = calculate_portfolio_performance(
        [
            {"date": "2026-01-01", "value": 100.0, "contributed": 100.0},
            {"date": "2026-01-02", "value": float("nan"), "contributed": 100.0},
        ],
        terminal_value=110.0,
        terminal_date=date(2026, 1, 2),
    )
    start = date(2024, 1, 1)
    ambiguous_history = []
    for offset in range(731):
        contribution = 100.0
        if offset >= 365:
            contribution = -130.0
        if offset >= 730:
            contribution = 2.0
        ambiguous_history.append(
            {
                "date": start + timedelta(days=offset),
                "value": 0.0 if offset == 730 else 100.0,
                "contributed": contribution,
            }
        )
    ambiguous = calculate_portfolio_performance(
        ambiguous_history,
        terminal_value=0.0,
        terminal_date=start + timedelta(days=730),
    )

    assert duplicate["twr_pct"] is None
    assert any("ściśle rosnące" in gap for gap in duplicate["gaps"])
    assert nonfinite["twr_pct"] is None
    assert any("poza dozwolonym" in gap for gap in nonfinite["gaps"])
    assert ambiguous["xirr_pct"] is None
    assert any("jednego rozwiązania" in gap for gap in ambiguous["gaps"])


def test_xirr_rejects_three_tightly_clustered_roots_inside_one_legacy_scan_cell():
    result = _solve_xirr(
        [
            (date(2023, 1, 1), -565_525_438.6995369),
            (date(2024, 1, 1), 2_051_652_614.347875),
            (date(2024, 12, 31), -2_480_960_098.432616),
            (date(2025, 12, 31), 1_000_000_000.0),
        ]
    )

    assert result is None


def test_portfolio_openapi_enforces_the_performance_contract(client):
    document = client.get("/openapi.json").json()
    workspace = document["components"]["schemas"]["PortfolioWorkspaceOut"]
    performance_ref = workspace["properties"]["performance_methods"]["anyOf"][0][
        "$ref"
    ]
    performance = document["components"]["schemas"][performance_ref.rsplit("/", 1)[-1]]

    assert set(performance["required"]) == {
        "version",
        "provider_return_basis",
        "benchmark_basis",
        "twr_status",
        "twr_pct",
        "twr_method",
        "xirr_status",
        "xirr_pct",
        "xirr_method",
        "flow_timing",
        "day_count",
        "window_start",
        "window_end",
        "terminal_date",
        "terminal_value",
        "observation_count",
        "external_flow_count",
        "gaps",
    }
    assert performance["properties"]["version"]["const"] == (
        "portfolio-performance-v1"
    )


def test_xirr_opens_with_window_market_value_not_lifetime_contributions():
    start = date(2025, 1, 1)
    history = [
        {
            "date": start + timedelta(days=offset),
            "value": 110.0 if offset == 365 else 100.0,
            "contributed": 60.0,
        }
        for offset in range(366)
    ]
    result = calculate_portfolio_performance(
        history,
        terminal_value=110.0,
        terminal_date=date(2026, 1, 1),
    )

    assert result["xirr_pct"] == pytest.approx(10.0)
    assert result["external_flow_count"] == 0


def test_xirr_requires_terminal_history_to_match_current_value():
    result = calculate_portfolio_performance(
        [
            {"date": "2025-01-01", "value": 100.0, "contributed": 100.0},
            {"date": "2025-01-02", "value": 109.0, "contributed": 100.0},
        ],
        terminal_value=110.0,
        terminal_date=date(2025, 1, 2),
    )

    assert result["twr_pct"] == pytest.approx(9.0)
    assert result["xirr_pct"] is None
    assert result["twr_status"] == "partial"
    assert any("końcowa wartość historii" in gap for gap in result["gaps"])


def test_stale_history_keeps_twr_but_does_not_attach_current_value_to_old_date():
    result = calculate_portfolio_performance(
        [
            {"date": "2026-01-01", "value": 100.0, "contributed": 100.0},
            {"date": "2026-01-02", "value": 105.0, "contributed": 100.0},
        ],
        terminal_value=105.0,
        terminal_date=date(2026, 1, 3),
    )

    assert result["twr_pct"] == pytest.approx(5.0)
    assert result["xirr_pct"] is None
    assert result["twr_status"] == "partial"
    assert any("nie dochodzi do daty" in gap for gap in result["gaps"])


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


def test_terminal_gpw_identity_creates_minimal_company_with_coverage_jobs(
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
    assert by_name["ALPHA (ABC)"]["mapping_status"] == "exact"
    created = db.scalar(select(Company).where(Company.ticker == "ABC"))
    assert created is not None and created.name == "ALPHA" and created.market == "GPW"
    included = [
        row for row in synced["sync"]["coverage_decisions"] if row["included"]
    ]
    assert {row["coverage_state"] for row in included} == {"research_queued"}
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == len(included)
    assert db.scalar(select(func.count()).select_from(AgentRun)) == len(included)
    assert all(row["research_origin"] == "portfolio" for row in included)


def test_identical_sync_repairs_current_name_mapping_without_rewriting_snapshot(
    client, db, monkeypatch
):
    from app.api import portfolios

    raw = payload()
    raw["portfel"]["wartosc"] = "100"
    raw["tickers"] = {
        "provider-alpha": {
            "tickerClear": "LAKA",
            "nazwa": "Spółka Łąka SA",
            "typOrg": "Akcje GPW",
            "waluta": "PLN",
            "wartosc": "100",
            "zysk": "10",
        }
    }
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    first = client.post("/api/portfolios/sync/myfund").json()
    first_position = first["positions"][0]
    assert first_position["mapping_status"] == "unmatched"
    frozen = db.scalar(
        select(PortfolioPositionSnapshot).where(
            PortfolioPositionSnapshot.id == first_position["id"]
        )
    )
    assert frozen is not None
    assert frozen.mapping_status == "unmatched" and frozen.company_id is None

    company = Company(ticker="ABC", name="Spolka Laka", market=None)
    db.add(company)
    db.commit()
    repeated = client.post("/api/portfolios/sync/myfund").json()
    repaired = repeated["positions"][0]

    assert repeated["sync"]["reused_snapshot"] is True
    assert repeated["snapshot"]["id"] == first["snapshot"]["id"]
    assert repaired["mapping_status"] == "exact"
    assert repaired["company_ticker"] == "ABC"
    assert repaired["mapping_reason"] == (
        "Jednoznaczna znormalizowana nazwa zapisanej spółki GPW."
    )
    db.refresh(frozen)
    db.refresh(company)
    assert frozen.mapping_status == "unmatched" and frozen.company_id is None
    assert company.market == "GPW"
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == 1
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
    assert repeated["sync"]["coverage_decisions"][0]["coverage_state"] == "research_queued"


def test_name_fallback_exposes_ambiguity_without_creating_identity_or_job(
    client, db, monkeypatch
):
    from app.api import portfolios

    db.add_all(
        [
            Company(ticker="ABC", name="Spółka Łąka SA", market="GPW"),
            Company(ticker="XYZ", name="Spolka Laka", market=None),
        ]
    )
    db.commit()
    raw = payload()
    raw["portfel"]["wartosc"] = "100"
    raw["tickers"] = {
        "provider-alpha": {
            "tickerClear": "LAKA",
            "nazwa": "SPÓŁKA ŁĄKA S.A.",
            "typOrg": "Akcje GPW",
            "waluta": "PLN",
            "wartosc": "100",
            "zysk": "10",
        }
    }
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))

    position = client.post("/api/portfolios/sync/myfund").json()["positions"][0]

    assert position["mapping_status"] == "unmatched"
    assert position["company_id"] is None
    assert position["mapping_reason"] == (
        "Nazwa pasuje do więcej niż jednej spółki GPW."
    )
    assert db.scalar(select(func.count()).select_from(Company)) == 2
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
    assert body["performance_methods"]["twr_pct"] == pytest.approx(
        (10000 / 9900 - 1) * 100
    )
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
    assert any(
        "benchmark_return_pct" in gap for gap in synced["history_quality"]["gaps"]
    )
    assert any(
        "nie dochodzi do daty" in gap for gap in synced["history_quality"]["gaps"]
    )
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
        case = db.scalar(
            select(ResearchCase).where(ResearchCase.company_id == company.id)
        )
        assert case is not None
        case.state = "monitoring"
        case.current_step = "research"
        profile = CompanyProfile(
            research_case_id=case.id,
            version=1,
            schema_version="company-profile-v2",
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
            contract_version="research-snapshot-v3",
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
            verifier_result=_canonical_research_verifier_result(),
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
            contract_version="research-snapshot-v3",
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
            verifier_result=_canonical_research_verifier_result(),
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

    db.add_all(
        [
            Company(ticker="SNT", name="Synektik"),
            Company(ticker="ABC", name="Alpha SA", market="GPW"),
        ]
    )
    db.commit()
    raw = payload()
    raw["tickers"]["2"].update(
        {
            "tickerClear": "ALPHA",
            "nazwa": "Provider Alpha instrument",
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
            json={"company_ticker": "ABC", "reason": "Błędna klasyfikacja"},
        ).status_code
        == 409
    )
    patched = client.patch(
        f"/api/portfolios/mappings/{unmatched['mapping_id']}",
        json={"company_ticker": "ABC", "reason": "Ręcznie potwierdzony instrument"},
    )
    assert (
        patched.status_code == 200 and patched.json()["mapping_status"] == "confirmed"
    )
    company = db.scalar(select(Company).where(Company.ticker == "ABC"))
    assert company is not None
    assert company.name == "Alpha SA" and company.market == "GPW"
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == 1
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
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
    assert interpreted["mapping_reason"] == (
        "Ręczna korekta: Ręcznie potwierdzony instrument"
    )
    ignored = client.patch(
        f"/api/portfolios/mappings/{unmatched['mapping_id']}",
        json={"ignored": True, "reason": "Poza analizą spółek"},
    )
    assert ignored.json()["mapping_status"] == "ignored"
    repeated_ignored = client.post("/api/portfolios/sync/myfund").json()
    ignored_position = next(
        p
        for p in repeated_ignored["positions"]
        if p["mapping_id"] == unmatched["mapping_id"]
    )
    assert repeated_ignored["sync"]["reused_snapshot"] is True
    assert ignored_position["mapping_status"] == "ignored"
    assert ignored_position["mapping_reason"] == "Ręcznie pominięto: Poza analizą spółek"
    corrected = client.patch(
        f"/api/portfolios/mappings/{unmatched['mapping_id']}",
        json={"company_ticker": "ABC", "reason": "Przywrócone mapowanie"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["company_id"] == company.id


def test_manual_mapping_rejects_non_gpw_provider_row_for_existing_gpw_company(
    client, db, monkeypatch
):
    from app.api import portfolios

    company = Company(ticker="ABC", name="Alpha SA", market="GPW")
    db.add(company)
    db.commit()
    raw = payload()
    raw["portfel"]["wartosc"] = "100"
    raw["tickers"] = {
        "provider-alpha": {
            "tickerClear": "ALPHA",
            "nazwa": "Provider Alpha instrument",
            "typOrg": "Fundusz",
            "waluta": "PLN",
            "wartosc": "100",
            "zysk": "10",
        }
    }
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    position = client.post("/api/portfolios/sync/myfund").json()["positions"][0]

    assert position["mapping_status"] == "unmatched"
    corrected = client.patch(
        f"/api/portfolios/mappings/{position['mapping_id']}",
        json={"company_ticker": "ABC", "reason": "Korekta typu dostawcy"},
    )

    assert corrected.status_code == 422
    assert "Akcje GPW w PLN" in corrected.json()["detail"]
    db.refresh(company)
    mapping = db.get(InstrumentMapping, position["mapping_id"])
    assert mapping is not None and mapping.mapping_status == "unmatched"


@pytest.mark.parametrize("reason", ["   ", " ok "])
def test_mapping_patch_rejects_blank_or_too_short_rationale(
    client, db, monkeypatch, reason
):
    from app.api import portfolios

    raw = payload()
    monkeypatch.setattr(portfolios, "get_settings", settings)
    monkeypatch.setattr(portfolios.polite_http, "fetch", lambda *a, **k: Response(raw))
    position = next(
        row
        for row in client.post("/api/portfolios/sync/myfund").json()["positions"]
        if row["mapping_status"] == "unmatched"
    )

    response = client.patch(
        f"/api/portfolios/mappings/{position['mapping_id']}",
        json={"ignored": True, "reason": reason},
    )

    assert response.status_code == 422
    mapping = db.get(InstrumentMapping, position["mapping_id"])
    assert mapping is not None and mapping.mapping_status == "unmatched"


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
        json={"company_ticker": confirmed, "reason": "Ręczna korekta testowa"},
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
    case = db.scalar(
        select(ResearchCase).where(ResearchCase.company_id == company.id)
    )
    assert case is not None
    case.state = "monitoring"
    case.current_step = "research"
    profile = CompanyProfile(
        research_case_id=case.id,
        version=1,
        schema_version="company-profile-v2",
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
        contract_version="research-snapshot-v3",
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
        verifier_result=_canonical_research_verifier_result(),
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
        contract_version="valuation-snapshot-v3",
        status="verified",
        as_of=datetime(2026, 7, 10, tzinfo=timezone.utc),
        template_id="industrial",
        template_version="v1",
        calculation_engine_version="valuation-engine-v4",
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
        contract_version="research-snapshot-v3",
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
        verifier_result=_canonical_research_verifier_result(),
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

    uncalibrated = _append_valuation(
        db,
        company=company,
        case=case,
        research=research,
        version=2,
        status="verified",
        weighted_price=None,
        fingerprint="f" * 64,
    )
    uncalibrated_result = client.get("/api/portfolios/workspace").json()[
        "scenario_sensitivity"
    ]
    assert uncalibrated_result["coverage_value_pct"] == 60
    assert uncalibrated_result["weighted_coverage_value_pct"] == 0
    assert uncalibrated_result["portfolio_values"] == {
        "negative": 6000,
        "base": 8000,
        "positive": 12000,
        "weighted": None,
    }
    assert uncalibrated_result["covered"][0]["weighted_value"] is None
    uncalibrated_review = client.post("/api/portfolios/review-runs").json()
    uncalibrated_agent = claim_agent_run(
        db,
        agent_run_id=uncalibrated_review["agent_run_id"],
        worker_id="uncalibrated-review-drafter",
    )
    assert uncalibrated_agent.inputs["portfolio_review"]["eligible_valuations"] == [
        {
            "position_snapshot_id": uncalibrated_result["covered"][0]["position_id"],
            "valuation_snapshot_id": uncalibrated.id,
            "valuation_fingerprint": uncalibrated.artifact_fingerprint,
        }
    ]
    uncalibrated_checked = client.post(
        "/api/portfolios/review-verifications",
        json=_review_verification(_review_draft(uncalibrated_agent)),
    )
    assert uncalibrated_checked.status_code == 200, uncalibrated_checked.text

    provisional = _append_valuation(
        db,
        company=company,
        case=case,
        research=research,
        version=3,
        status="provisional",
        weighted_price=250,
        fingerprint="9" * 64,
    )
    superseded_result = client.get("/api/portfolios/workspace").json()[
        "scenario_sensitivity"
    ]
    assert superseded_result["coverage_value_pct"] == 0
    assert superseded_result["covered"] == []
    assert superseded_result["portfolio_values"]["weighted"] is None
    assert any(
        row.get("latest_status") == provisional.status
        for row in superseded_result["exclusions"]
    )


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
        "reasoning_effort": "medium",
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
    assert frozen["history_method"]["version"] == "portfolio-performance-v1"
    assert frozen["history_method"]["twr_pct"] == pytest.approx(
        (10000 / 9900 - 1) * 100
    )
    assert frozen["history_method"]["twr_status"] == "partial"
    assert frozen["analytics_version"] == "portfolio-analytics-v3"
    assert len(frozen["analytics_fingerprint"]) == 64
    assert (
        client.get("/api/portfolios/workspace").json()["portfolio_review"][
            "active_run"
        ]["id"]
        == agent.id
    )


def test_review_verifier_recomputes_frozen_performance_instead_of_trusting_values(
    client, db, monkeypatch
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
    inputs = copy.deepcopy(agent.inputs)
    frozen = inputs["portfolio_review"]
    forged = float(frozen["history_method"]["twr_pct"]) + 1.0
    frozen["history_method"]["twr_pct"] = forged
    frozen["analytics"]["performance_methods"]["twr_pct"] = forged
    frozen["analytics_fingerprint"] = canonical_hash(frozen["analytics"])
    manifest = {key: value for key, value in frozen.items() if key != "input_fingerprint"}
    frozen["input_fingerprint"] = canonical_hash(manifest)
    agent.inputs = inputs
    db.commit()
    db.refresh(agent)

    response = client.post(
        "/api/portfolios/review-verifications",
        json=_review_verification(_review_draft(agent)),
    )

    assert response.status_code == 409, response.text


def test_review_verifier_rejects_consistently_refingerprinted_history_forgery(
    client, db, monkeypatch
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
    inputs = copy.deepcopy(agent.inputs)
    frozen = inputs["portfolio_review"]
    frozen["analytics"]["history"][0]["value"] = 9800.0
    snapshot = db.get(PortfolioSnapshot, frozen["snapshot"]["id"])
    forged_methods = calculate_portfolio_performance(
        frozen["analytics"]["history"],
        terminal_value=float(snapshot.total_value),
        terminal_date=snapshot.as_of.date(),
    )
    frozen["history_method"] = forged_methods
    frozen["analytics"]["performance_methods"] = forged_methods
    frozen["analytics_fingerprint"] = canonical_hash(frozen["analytics"])
    manifest = {key: value for key, value in frozen.items() if key != "input_fingerprint"}
    frozen["input_fingerprint"] = canonical_hash(manifest)
    agent.inputs = inputs
    db.commit()
    db.refresh(agent)

    response = client.post(
        "/api/portfolios/review-verifications",
        json=_review_verification(_review_draft(agent)),
    )

    assert response.status_code == 409, response.text


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
    assert saved.json()["draft_reasoning_effort"] == "medium"
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
        [
            Company(ticker="SNT", name="Synektik"),
            Company(ticker="ABS", name="ABS"),
            Company(ticker="ABC", name="Alpha SA", market="GPW"),
        ]
    )
    db.commit()
    raw = payload()
    raw["tickers"]["2"].update(
        {
            "tickerClear": "ALPHA",
            "nazwa": "Provider Alpha instrument",
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
            json={
                "company_ticker": "ABC",
                "reason": "Ręczna korekta po zamrożeniu przeglądu",
            },
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
        "analytics_version": "portfolio-analytics-v3",
        "draft_model_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "medium",
        "verifier_model_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
    }
    policy = get_model_policy("stock-portfolio-review")
    assert (
        policy["draft_model"] == "gpt-5.6-terra"
        and policy["verifier_model"] == "gpt-5.6-sol"
        and policy["draft_reasoning_effort"] == "medium"
        and policy["verifier_reasoning_effort"] == "high"
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
