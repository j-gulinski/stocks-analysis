"""Append-only decision journal API and model behavior."""
def _company(db, ticker="SNT"):
    from app.db.models import Company

    company = Company(ticker=ticker, name="Test company")
    db.add(company)
    db.commit()
    return company


def _payload(thesis="Teza testowa"):
    return {
        "decision": "holding",
        "confidence": 72,
        "thesis": thesis,
        "invalidation": "Marża spada przez dwa kolejne raporty.",
        "next_check": "Sprawdzić raport kwartalny i konwersję gotówki.",
        "review_date": "2026-08-10",
        "thesis_snapshot": {
            "thesis_read": thesis,
            "strategy": {"id": "malik_v1", "label": "Malik / OBS"},
        },
    }


def test_decision_journal_is_append_only_and_keeps_thesis_snapshot(client, db):
    _company(db)

    first = client.post("/api/companies/SNT/decision-journal", json=_payload())
    second = client.post(
        "/api/companies/SNT/decision-journal",
        json=_payload("Nowa teza po raporcie."),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    first_payload = first.json()
    assert first_payload["ticker"] == "SNT"
    assert first_payload["confidence"] == 72
    assert first_payload["thesis_snapshot"]["strategy"]["id"] == "malik_v1"
    assert len(first_payload["thesis_hash"]) == 64
    assert first_payload["created_by"] is None

    listed = client.get("/api/companies/SNT/decision-journal").json()
    assert [row["id"] for row in listed] == [second.json()["id"], first_payload["id"]]
    assert listed[1]["thesis"] == "Teza testowa"

    # There is no update path: history is corrected by adding another entry.
    assert client.patch(
        f"/api/companies/SNT/decision-journal/{first_payload['id']}",
        json={"confidence": 10},
    ).status_code in {404, 405}


def test_decision_journal_validates_confidence_and_unknown_company(client, db):
    _company(db, "DEC")

    invalid = client.post(
        "/api/companies/DEC/decision-journal",
        json={**_payload(), "confidence": 101},
    )
    assert invalid.status_code == 422

    missing = client.get("/api/companies/NOPE/decision-journal")
    assert missing.status_code == 404


def test_empty_thesis_snapshot_is_honest_and_supported(client, db):
    _company(db, "KRU")
    response = client.post(
        "/api/companies/KRU/decision-journal",
        json={**_payload(), "thesis_snapshot": {}},
    )

    assert response.status_code == 201
    assert response.json()["thesis_snapshot"] == {}
    assert response.json()["thesis_hash"] is None
