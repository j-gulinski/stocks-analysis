"""Durable Research Lab identity and lifecycle contract."""

from sqlalchemy import func, select

from tests.conftest import FakeResponse, load_fixture


def test_research_lab_creates_one_idempotent_case_and_initial_job_from_discovery(
    client, db, monkeypatch, no_sleep
):
    from app.db.models import (
        AgentRun,
        Company,
        ResearchCase,
        ResearchCaseStepHistory,
        WatchlistItem,
    )

    def fake_fetch(url, **_kwargs):
        response = FakeResponse(load_fixture("br_market_rating.html"))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    snapshot = client.post("/api/discovery/refresh")
    assert snapshot.status_code == 200
    source_version_id = snapshot.json()["source_version_id"]

    first = client.post(
        "/api/research-cases",
        json={"ticker": "dek", "source_document_version_id": source_version_id},
    )

    assert first.status_code == 200
    body = first.json()
    assert body["created_company"] is True
    assert body["created_case"] is True
    assert body["reactivated_case"] is False
    assert body["created_job"] is True
    assert body["research_case"]["ticker"] == "DEK"
    assert body["research_case"]["name"] == "DEKPOL"
    assert body["research_case"]["state"] == "ingesting"
    assert body["research_case"]["current_step"] == "ingest"
    assert body["research_case"]["initial_research_status"] == "queued"
    run = db.get(AgentRun, body["agent_run"]["id"])
    company = db.scalar(select(Company).where(Company.ticker == "DEK"))
    assert company.name == "DEKPOL"
    assert company.br_slug == "DEKPOL"
    assert run.workflow == "stock-initial-research"
    assert run.company_id == company.id
    assert run.model_role == "worker_standard"
    assert run.model == "gpt-5.6-terra"
    assert run.idempotency_key == (
        f"research-case-initial-research:{body['research_case']['id']}"
    )
    assert run.inputs["source_document_version_id"] == source_version_id
    assert run.inputs["task"]["skill"] == "company-research"
    assert run.inputs["task"]["skill_version"] == "company-research-v2"
    assert run.inputs["task"]["output_contract_version"] == "research-snapshot-v2"
    assert run.inputs["task"]["company_profile_schema_version"] == "company-profile-v2"
    assert run.inputs["task"]["archetype_contract_version"] == "archetype-packs-v1"
    assert run.inputs["task"]["required_verification"] == "verifier_strict"
    assert db.scalar(select(func.count()).select_from(WatchlistItem)) == 0

    duplicate = client.post(
        "/api/research-cases",
        json={"ticker": "DEK", "source_document_version_id": source_version_id},
    )
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
    assert listed.json()[0]["initial_research_run_id"] == body["agent_run"]["id"]
    assert listed.json()[0]["initial_research_status"] == "queued"


def test_research_lab_accepts_manual_ticker_and_rejects_wrong_frozen_candidate(
    client, db, monkeypatch, no_sleep
):
    from app.db.models import AgentRun, Company, ResearchCase

    manual = client.post("/api/research-cases", json={"ticker": " snt "})
    assert manual.status_code == 200
    assert manual.json()["research_case"]["ticker"] == "SNT"
    assert manual.json()["research_case"]["name"] is None

    def fake_fetch(url, **_kwargs):
        response = FakeResponse(load_fixture("br_market_rating.html"))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    source_version_id = client.post("/api/discovery/refresh").json()["source_version_id"]
    rejected = client.post(
        "/api/research-cases",
        json={"ticker": "SNT", "source_document_version_id": source_version_id},
    )
    assert rejected.status_code == 422
    assert db.scalar(select(func.count()).select_from(Company)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchCase)) == 1
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1

    missing_version = client.post(
        "/api/research-cases",
        json={"ticker": "DEK", "source_document_version_id": 999999},
    )
    assert missing_version.status_code == 404


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


def test_research_case_lifecycle_is_explicit_and_idempotent(client, db):
    from app.db.models import Company, ResearchCase

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()

    missing = client.get("/api/companies/SNT/research-case")
    assert missing.status_code == 404

    created = client.post(
        "/api/companies/SNT/research-case",
        json={"purpose": "investment-research", "state": "new", "current_step": "ingest"},
    )
    assert created.status_code == 201
    assert created.json()["state"] == "new"
    assert created.json()["current_step"] == "ingest"

    duplicate = client.post("/api/companies/SNT/research-case", json={})
    assert duplicate.status_code == 409

    updated = client.patch(
        "/api/companies/SNT/research-case",
        json={
            "state": "blocked",
            "current_step": "data_review",
            "blocked_reason": "Brak raportu pierwotnego.",
            "change_reason": "Raport nie został jeszcze potwierdzony.",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["state"] == "blocked"
    assert body["current_step"] == "data_review"
    assert body["blocked_reason"] == "Brak raportu pierwotnego."
    assert db.query(ResearchCase).count() == 1

    reopened = client.patch(
        "/api/companies/SNT/research-case",
        json={
            "state": "thesis",
            "current_step": "thesis",
            "change_reason": "Źródła wejściowe są już wystarczające.",
        },
    )
    assert reopened.status_code == 200
    assert reopened.json()["blocked_reason"] is None

    alternate = client.post(
        "/api/companies/SNT/research-case",
        json={"purpose": "watchlist-review"},
    )
    assert alternate.status_code == 201
    assert client.get(
        "/api/companies/SNT/research-case", params={"purpose": "watchlist-review"}
    ).json()["purpose"] == "watchlist-review"


def test_blocked_case_requires_named_reason(client, db):
    from app.db.models import Company

    db.add(Company(ticker="DEC", name="DECORA"))
    db.commit()
    response = client.post(
        "/api/companies/DEC/research-case",
        json={"state": "blocked", "current_step": "ingest"},
    )
    assert response.status_code == 422
