"""Explicit falsifier state tests."""


def _company(db, ticker):
    from app.db.models import Company

    row = Company(ticker=ticker, name=ticker)
    db.add(row)
    db.commit()
    return row


def _payload(key="margin", status="holding", reason="User-defined rule"):
    return {
        "key": key,
        "statement": "Marża nie może spadać przez dwa kolejne raporty.",
        "status": status,
        "reason": reason,
        "review_date": "2026-09-01",
    }


def test_falsifier_state_is_explicit_and_requires_a_reason(client, db):
    _company(db, "SNT")

    created = client.post("/api/companies/SNT/falsifiers", json=_payload())
    assert created.status_code == 201
    row = created.json()
    assert row["status"] == "holding"

    fired_without_reason = client.patch(
        f"/api/companies/SNT/falsifiers/{row['id']}",
        json={"status": "fired", "reason": ""},
    )
    assert fired_without_reason.status_code == 422

    fired = client.patch(
        f"/api/companies/SNT/falsifiers/{row['id']}",
        json={"status": "fired", "reason": "Raport pokazał spadek marży."},
    )
    assert fired.status_code == 200
    assert fired.json()["status"] == "fired"
    assert fired.json()["reason"] == "Raport pokazał spadek marży."
