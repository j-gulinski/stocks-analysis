"""RT4.1a durable ResearchCase root contract."""


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
        json={"state": "thesis", "current_step": "thesis"},
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
