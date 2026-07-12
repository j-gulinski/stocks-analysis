"""M1 source-frozen, read-only Research method catalog contracts."""

from hashlib import sha256
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_catalog_freezes_retained_malik_sources_and_keeps_other_authors_draft():
    from app.services.research_method_catalog import list_research_method_catalog

    catalog = list_research_method_catalog()
    assert [item["id"] for item in catalog] == [
        "malik_obs_v1",
        "areczeks_v1",
        "elendix_v1",
    ]
    malik, areczeks, elendix = catalog
    assert malik["stages"] == {
        "discover": {
            "status": "planned",
            "reason": "Brak zachowanego, rynkowego snapshotu wszystkich wymaganych czynników.",
        },
        "research": {
            "status": "supported",
            "reason": "Perspektywę można utworzyć wyłącznie jawną komendą dla zachowanego snapshotu Research.",
        },
        "valuation": {"status": "supported", "reason": None},
    }
    assert malik["evaluation_maturity"] == "untested"
    assert malik["version"] == "malik-obs-method-v2"
    assert malik["research_output_schema_version"] == "research-method-perspective-v1"
    assert malik["required_verifier_role"] == "verifier_strict"
    assert [item["id"] for item in malik["required_checks"]] == [
        "result-change-mechanism",
        "revenue-margin-cost-bridge",
        "durable-versus-one-off",
        "catalyst-horizon-falsifier",
        "cash-working-capital-capex-debt",
    ]
    assert [item["locator"] for item in malik["source_manifest"]] == [
        "OBS — 2021-02-02T14:56:44+00:00",
        "OBS — 2024-08-15T15:37:00+00:00",
        "00:00–11:07; część „Budowanie szybkiej prognozy na kolejny kwartał”",
    ]
    assert malik["source_manifest"][2]["publication_at"] is None
    assert "metadane lokalnego DOCX" in malik["source_manifest"][2]["date_note"]
    for source in malik["source_manifest"]:
        assert source["retention_status"] == "retained"
        assert source["repo_path"] is not None and source["sha256"] is not None
        assert sha256((ROOT / source["repo_path"]).read_bytes()).hexdigest() == source["sha256"]
    for draft in (areczeks, elendix):
        assert {stage["status"] for stage in draft["stages"].values()} == {"draft"}
        assert draft["source_manifest"] == []
        assert draft["gaps"]


def test_retained_method_source_schema_rejects_weak_provenance():
    from pydantic import ValidationError

    from app.api.schemas import ResearchMethodSourceOut
    from app.services.research_method_catalog import list_research_method_catalog

    source = dict(list_research_method_catalog()[0]["source_manifest"][0])
    for patch in (
        {"sha256": "x" * 64},
        {"repo_path": None},
        {"publication_at": "2021-02-02T14:56:44"},
        {"publication_at": None, "known_at": None, "date_note": None},
    ):
        with pytest.raises(ValidationError):
            ResearchMethodSourceOut.model_validate({**source, **patch})
    known_only = ResearchMethodSourceOut.model_validate(
        {
            **source,
            "publication_at": None,
            "known_at": "2026-07-13T12:00:00+00:00",
            "date_note": None,
        }
    )
    assert known_only.known_at is not None


def test_research_workspace_catalog_read_is_zero_write(client, db):
    from sqlalchemy import func, select

    from app.db.models import AgentRun, CompanyProfile, ResearchSnapshot

    created = client.post("/api/research-cases", json={"ticker": "SNT"})
    assert created.status_code == 200
    counts = tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (AgentRun, CompanyProfile, ResearchSnapshot)
    )
    first = client.get("/api/research-cases/by-ticker/SNT")
    second = client.get("/api/research-cases/by-ticker/SNT")
    assert first.status_code == second.status_code == 200
    catalog = first.json()["method_catalog"]
    assert catalog[0]["id"] == "malik_obs_v1"
    assert catalog[0]["stages"]["research"]["status"] == "supported"
    assert [entry["stages"]["research"]["status"] for entry in catalog[1:]] == [
        "draft",
        "draft",
    ]
    assert counts == tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (AgentRun, CompanyProfile, ResearchSnapshot)
    )
