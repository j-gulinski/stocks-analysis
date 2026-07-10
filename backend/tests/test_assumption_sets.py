"""RT4.2a case-linked assumption-set provenance contract."""


def _create_case(client, ticker="SNT"):
    from app.db.models import Company

    return client.post(f"/api/companies/{ticker}/research-case", json={})


def test_assumption_sets_are_case_scoped_and_provenance_explicit(client, db):
    from app.db.models import Company

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()
    assert _create_case(client).status_code == 201

    created = client.post(
        "/api/companies/SNT/research-case/assumptions",
        headers={"X-User-Email": "researcher@example.test"},
        json={
            "scenario_kind": "base",
            "label": "Mediana",
            "assumptions": [
                {
                    "key": "revenue_growth",
                    "value": 0.12,
                    "unit": "ratio",
                    "provenance": "human_assumption",
                    "rationale": "Konserwatywne założenie do pierwszej wersji.",
                },
                {
                    "key": "eps",
                    "value": 14.2,
                    "unit": "PLN/share",
                    "provenance": "evidence",
                    "source_ref": "fact:123",
                    "rationale": "Wartość z zamrożonego faktu.",
                },
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["research_case_id"]
    assert body["status"] == "draft"
    assert body["created_by"] == "researcher@example.test"
    assert body["assumptions"][0]["provenance"] == "human_assumption"
    assert client.get("/api/companies/SNT/research-case/assumptions").json() == [body]

    duplicate = client.post(
        "/api/companies/SNT/research-case/assumptions",
        json={"scenario_kind": "base", "label": "Drugi", "assumptions": []},
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/api/companies/SNT/research-case/assumptions/{body['id']}",
        json={"status": "approved", "label": "Mediana zatwierdzona"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "approved"
    assert updated.json()["label"] == "Mediana zatwierdzona"


def test_assumption_set_requires_case_and_valid_provenance(client, db):
    from app.db.models import Company

    db.add(Company(ticker="DEC", name="DECORA"))
    db.commit()
    missing_case = client.get("/api/companies/DEC/research-case/assumptions")
    assert missing_case.status_code == 404

    assert _create_case(client, "DEC").status_code == 201
    invalid = client.post(
        "/api/companies/DEC/research-case/assumptions",
        json={
            "scenario_kind": "positive",
            "label": "Wzrost",
            "assumptions": [
                {"key": "margin", "value": 0.4, "provenance": "guess", "rationale": "Brak"}
            ],
        },
    )
    assert invalid.status_code == 422
