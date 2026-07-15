"""Durable Research Lab identity and lifecycle contract."""

from sqlalchemy import func, select

def test_legacy_company_research_forecast_and_dossier_routes_are_deleted(client):
    routes = {
        (path, method.upper())
        for path, operations in client.app.openapi()["paths"].items()
        for method in operations
    }

    assert ("/api/research-cases", "POST") in routes
    assert ("/api/companies/{ticker}/refresh", "POST") in routes
    assert ("/api/companies/{ticker}/info", "GET") in routes
    assert ("/api/companies/{ticker}/research-case", "GET") not in routes
    assert ("/api/companies/{ticker}/research-case", "POST") not in routes
    assert ("/api/companies/{ticker}/research-case", "PATCH") not in routes
    assert ("/api/companies/{ticker}/research-case/history", "GET") not in routes
    assert ("/api/companies/{ticker}/research-case/assumptions", "GET") not in routes
    assert ("/api/companies/{ticker}/research-case/assumptions", "POST") not in routes
    assert ("/api/companies/{ticker}/forecast-defaults", "GET") not in routes
    assert ("/api/companies/{ticker}/forecasts", "GET") not in routes
    assert ("/api/companies/{ticker}/forecasts", "POST") not in routes
    assert ("/api/companies/{ticker}", "GET") not in routes


def test_research_lab_creates_one_idempotent_manual_case_and_initial_job(client, db):
    from app.db.models import (
        AgentRun,
        Company,
        ResearchCase,
        ResearchCaseStepHistory,
    )

    first = client.post("/api/research-cases", json={"ticker": "dek"})

    assert first.status_code == 200
    body = first.json()
    assert body["created_company"] is True
    assert body["created_case"] is True
    assert body["reactivated_case"] is False
    assert body["created_job"] is True
    assert body["research_case"]["ticker"] == "DEK"
    assert body["research_case"]["name"] is None
    assert body["research_case"]["state"] == "ingesting"
    assert body["research_case"]["current_step"] == "ingest"
    assert body["research_case"]["phase"] == "collecting"
    assert body["research_case"]["phase_label"] == "Zbieranie"
    assert body["research_case"]["collection_progress"]["state"] == "waiting"
    run = db.get(AgentRun, body["agent_run"]["id"])
    company = db.scalar(select(Company).where(Company.ticker == "DEK"))
    assert company.name is None
    assert company.br_slug is None
    assert run.workflow == "stock-initial-research"
    assert run.company_id == company.id
    assert run.model_role == "worker_standard"
    assert run.model == "gpt-5.6-terra"
    assert run.idempotency_key == (
        f"research-case-initial-research:{body['research_case']['id']}"
    )
    assert "source_document_version_id" not in run.inputs
    assert "discovery_origin" not in run.inputs
    assert run.inputs["task"]["skill"] == "company-research"
    assert run.inputs["task"]["skill_version"] == "company-research-v3"
    assert run.inputs["task"]["output_contract_version"] == "research-snapshot-v3"
    assert run.inputs["task"]["company_profile_schema_version"] == "company-profile-v2"
    assert run.inputs["task"]["archetype_contract_version"] == "archetype-packs-v1"
    assert run.inputs["task"]["required_verification"] == "verifier_strict"

    duplicate = client.post("/api/research-cases", json={"ticker": "DEK"})
    assert duplicate.status_code == 200
    repeated = duplicate.json()
    assert repeated["created_company"] is False
    assert repeated["created_case"] is False
    assert repeated["reactivated_case"] is False
    assert repeated["created_job"] is False
    assert repeated["research_case"]["id"] == body["research_case"]["id"]
    assert repeated["agent_run"]["id"] == body["agent_run"]["id"]
    assert db.scalar(select(func.count()).select_from(Company)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchCaseStepHistory)) == 1
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1

    listed = client.get("/api/research-cases")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == body["research_case"]["id"]
    assert listed.json()[0]["ticker"] == "DEK"
    assert listed.json()[0]["phase"] == "collecting"
    assert listed.json()[0]["collection_progress"]["state"] == "waiting"


def test_research_lab_rejects_unbound_discovery_provenance(client, db):
    from app.db.models import AgentRun, Company, ResearchCase

    manual = client.post("/api/research-cases", json={"ticker": " snt "})
    assert manual.status_code == 200
    assert manual.json()["research_case"]["ticker"] == "SNT"
    assert manual.json()["research_case"]["name"] is None

    rejected = client.post(
        "/api/research-cases",
        json={"ticker": "SNT", "source_document_version_id": 1},
    )
    assert rejected.status_code == 422
    assert db.scalar(select(func.count()).select_from(Company)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == 1
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1

    unbound_new_case = client.post(
        "/api/research-cases",
        json={"ticker": "DEK", "source_document_version_id": 999999},
    )
    assert unbound_new_case.status_code == 422

    generic_review = client.post(
        "/api/agent-runs",
        json={
            "workflow": "stock-company-review",
            "trigger": "manual",
            "ticker": "SNT",
            "inputs": {"research_case_id": manual.json()["research_case"]["id"]},
        },
    )
    assert generic_review.status_code == 405
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1


def test_research_lab_reactivates_a_closed_case_without_duplicate_initial_job(
    client, db
):
    from app.db.models import AgentRun, Company, ResearchCase, ResearchCaseStepHistory

    company = Company(ticker="ABS", name="ASSECOBS")
    db.add(company)
    db.flush()
    research_case = ResearchCase(
        company_id=company.id,
        purpose="investment-research",
        state="closed",
        current_step="monitoring",
    )
    db.add(research_case)
    db.flush()
    agent = AgentRun(
        workflow="stock-initial-research",
        trigger="research-lab",
        status="verified",
        company_id=company.id,
        model_role="worker_standard",
        model="gpt-5.6-terra",
        orchestrator_model="gpt-5.6-terra",
        idempotency_key=f"research-case-initial-research:{research_case.id}",
        inputs={"ticker": "ABS"},
        outputs={},
    )
    db.add(agent)
    db.commit()

    response = client.post("/api/research-cases", json={"ticker": "ABS"})

    assert response.status_code == 200
    body = response.json()
    assert body["created_case"] is False
    assert body["reactivated_case"] is True
    assert body["created_job"] is False
    assert body["research_case"]["state"] == "monitoring"
    assert body["research_case"]["current_step"] == "monitoring"
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
    histories = db.scalars(
        select(ResearchCaseStepHistory).where(
            ResearchCaseStepHistory.research_case_id == research_case.id
        )
    ).all()
    assert len(histories) == 1
    assert histories[0].from_state == "closed"


def test_research_lab_reuses_a_legacy_unkeyed_initial_job_on_reactivation(client, db):
    from app.db.models import AgentRun, Company, ResearchCase

    company = Company(ticker="ABS", name="ASSECOBS")
    db.add(company)
    db.flush()
    research_case = ResearchCase(
        company_id=company.id,
        purpose="investment-research",
        state="closed",
        current_step="monitoring",
    )
    db.add(research_case)
    db.flush()
    legacy_agent = AgentRun(
        workflow="stock-initial-research",
        trigger="research-lab",
        status="provisional",
        company_id=company.id,
        model_role="worker_standard",
        model="gpt-5.6-terra",
        orchestrator_model="gpt-5.6-terra",
        inputs={"ticker": "ABS", "research_case_id": research_case.id},
        outputs={},
    )
    db.add(legacy_agent)
    db.commit()

    listed = client.get("/api/research-cases")
    assert listed.status_code == 200
    assert listed.json()[0]["phase"] == "collecting"
    assert listed.json()[0]["collection_progress"]["state"] == "waiting"

    response = client.post("/api/research-cases", json={"ticker": "ABS"})

    assert response.status_code == 200
    body = response.json()
    assert body["created_case"] is False
    assert body["reactivated_case"] is True
    assert body["created_job"] is False
    assert body["agent_run"]["id"] == legacy_agent.id
    assert body["research_case"]["state"] == "monitoring"
    assert body["research_case"]["current_step"] == "monitoring"
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
