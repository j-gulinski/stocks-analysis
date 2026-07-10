"""Read-only position ledger and explicit CSV mapping tests."""


CSV = """ticker,instrument,entry_date,entry_price,quantity,size_pln,sizing_rule_flag,source_ref
SNT,Test instrument,2026-07-01,100.5,10,1005,true,pos-1
UNKNOWN,Unmatched,2026-07-01,1,2,2,false,pos-2
,No mapping,2026-07-01,1,2,2,false,pos-3
"""


def test_csv_import_surfaces_unmatched_and_is_idempotent(client, db):
    from app.db.models import Company

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()

    first = client.post(
        "/api/positions/import/csv",
        json={"portfolio": "IKE", "csv_text": CSV},
    )
    assert first.status_code == 200
    payload = first.json()
    assert payload["imported"] == 1
    assert payload["skipped_duplicates"] == 0
    assert len(payload["unmatched"]) == 2
    assert payload["positions"][0]["sizing_rule_flag"] is True

    second = client.post(
        "/api/positions/import/csv",
        json={"portfolio": "IKE", "csv_text": CSV},
    )
    assert second.status_code == 200
    assert second.json()["imported"] == 0
    assert second.json()["skipped_duplicates"] == 1

    listed = client.get("/api/positions", params={"ticker": "snt"}).json()
    assert len(listed) == 1
    assert listed[0]["ticker"] == "SNT"
    assert listed[0]["size_pln"] == 1005.0
