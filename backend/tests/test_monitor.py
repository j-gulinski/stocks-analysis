"""Deterministic monitor snapshot and diff tests."""
from app.services.monitor import build_snapshot, diff_snapshots, snapshot_hash


def dossier(*, verdict="pass", thesis="Teza A", value=10):
    return {
        "prescore": {"checks": [{"id": "profit", "verdict": verdict}]},
        "thesis": {
            "entry_quality": {"code": "neutral"},
            "thesis_read": thesis,
            "verify_next": [{"id": "cash", "text": "cash"}],
        },
        "result_quality": {
            "cause_status": "not_applicable",
            "is_material": False,
            "valuation_basis": "reported",
        },
        "valuation": {
            "potential": {"value_pct": value, "range_pct": [0, 20]},
            "confidence": {"level": "medium"},
        },
        "pe_history": {"current": 12, "median": 14},
    }


def test_monitor_snapshot_hash_is_order_independent_and_diff_is_explicit():
    first = build_snapshot(dossier(), [{"external_id": "ESPI-1", "title": "Raport"}])
    reordered = build_snapshot(dossier(), [{"title": "Raport", "external_id": "ESPI-1"}])
    changed = build_snapshot(
        dossier(verdict="fail", thesis="Teza B", value=4),
        [{"external_id": "ESPI-1", "title": "Raport"}, {"external_id": "ESPI-2", "title": "Nowy"}],
    )

    assert snapshot_hash(first) == snapshot_hash(reordered)
    assert diff_snapshots(first, reordered) == []
    changes = diff_snapshots(first, changed)
    assert {row["kind"] for row in changes} == {"check", "thesis", "valuation", "event"}
    assert all("before" in row and "after" in row for row in changes)


def test_monitor_api_saves_one_change_card_and_deduplicates_unchanged_state(
    client, db, monkeypatch
):
    from app.api import monitor as monitor_api
    from app.db.models import Company, MonitorChange

    company = Company(ticker="SNT", name="Test company")
    db.add(company)
    db.commit()
    current = {"value": 10}

    def fake_dossier(*_args, **_kwargs):
        return dossier(value=current["value"])

    monkeypatch.setattr(monitor_api.dossier_service, "build_dossier", fake_dossier)

    baseline = client.post("/api/companies/SNT/monitor/check")
    assert baseline.status_code == 200
    assert baseline.json()["baseline_exists"] is False
    assert baseline.json()["changed"] is False

    current["value"] = 4
    changed = client.post("/api/companies/SNT/monitor/check")
    assert changed.status_code == 200
    assert changed.json()["baseline_exists"] is True
    assert changed.json()["changed"] is True
    assert changed.json()["change"]["changes"]
    assert db.query(MonitorChange).count() == 1

    unchanged = client.post("/api/companies/SNT/monitor/check")
    assert unchanged.status_code == 200
    assert unchanged.json()["changed"] is False
    assert db.query(MonitorChange).count() == 1

    listed = client.get("/api/companies/SNT/monitor/changes").json()
    assert len(listed) == 1
