"""RT4.2c append-only ResearchCase step history contract."""


def test_case_creation_and_transitions_append_history(client, db):
    from app.db.models import Company, ResearchCaseStepHistory

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()
    created = client.post(
        "/api/companies/SNT/research-case",
        headers={"X-User-Email": "researcher@example.test"},
        json={},
    )
    assert created.status_code == 201
    history = client.get("/api/companies/SNT/research-case/history")
    assert history.status_code == 200
    assert history.json()[0]["reason"] == "Utworzono przypadek badawczy."
    assert history.json()[0]["from_state"] is None
    assert history.json()[0]["changed_by"] == "researcher@example.test"

    missing_reason = client.patch(
        "/api/companies/SNT/research-case",
        json={"state": "thesis", "current_step": "thesis"},
    )
    assert missing_reason.status_code == 422

    transitioned = client.patch(
        "/api/companies/SNT/research-case",
        headers={"X-User-Email": "reviewer@example.test"},
        json={
            "state": "thesis",
            "current_step": "thesis",
            "change_reason": "Dane wejściowe zostały sprawdzone.",
        },
    )
    assert transitioned.status_code == 200
    rows = client.get("/api/companies/SNT/research-case/history").json()
    assert len(rows) == 2
    assert rows[0]["from_state"] == "new"
    assert rows[0]["to_state"] == "thesis"
    assert rows[0]["reason"] == "Dane wejściowe zostały sprawdzone."
    assert rows[0]["changed_by"] == "reviewer@example.test"
    assert db.query(ResearchCaseStepHistory).count() == 2

    # Editing only the blocked reason is not a workflow transition.
    unchanged = client.patch(
        "/api/companies/SNT/research-case",
        json={"blocked_reason": "Dodatkowy kontekst."},
    )
    assert unchanged.status_code == 200
    assert len(client.get("/api/companies/SNT/research-case/history").json()) == 2
