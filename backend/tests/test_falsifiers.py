"""Explicit falsifier state and thesis-at-risk queue tests."""


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


def test_watchlist_orders_fired_then_warning_then_unflagged(client, db):
    from app.db.models import ThesisFalsifier, WatchlistItem

    fired_company = _company(db, "FIR")
    warning_company = _company(db, "WAR")
    clean_company = _company(db, "CLR")
    db.add_all(
        [
            WatchlistItem(company_id=fired_company.id),
            WatchlistItem(company_id=warning_company.id),
            WatchlistItem(company_id=clean_company.id),
            ThesisFalsifier(
                company_id=fired_company.id,
                key="risk",
                statement="Risk",
                status="fired",
                reason="Evidence",
            ),
            ThesisFalsifier(
                company_id=warning_company.id,
                key="risk",
                statement="Risk",
                status="warning",
                reason="Evidence",
            ),
        ]
    )
    db.commit()

    rows = client.get("/api/watchlist").json()
    assert [row["ticker"] for row in rows] == ["FIR", "WAR", "CLR"]
    assert rows[0]["fired_falsifiers"] == 1
    assert rows[1]["warning_falsifiers"] == 1
    assert rows[2]["risk_level"] == "none"
