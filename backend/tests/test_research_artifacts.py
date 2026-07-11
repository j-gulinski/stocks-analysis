"""P1 immutable research artifact contract and save-gate tests."""

from copy import deepcopy
from datetime import timedelta
import json
import sys

from sqlalchemy import func, select


def _document(db, company, *, ticker=None):
    from app.db.models import DocumentVersion, SourceDocument, utcnow

    now = utcnow()
    document = SourceDocument(
        company_id=company.id if ticker is None else None,
        company_ticker=ticker or company.ticker,
        source_name="issuer",
        source_type="report",
        scope_key=f"report-{ticker or company.ticker}",
        canonical_url="https://example.test/report",
        first_seen_at=now,
        last_fetched_at=now,
        latest_content_hash="a" * 64,
        mime_type="text/html",
        parser_version="fixture-v1",
        last_fetch_status=200,
    )
    db.add(document)
    db.flush()
    version = DocumentVersion(
        source_document_id=document.id,
        content_hash="a" * 64,
        fetched_at=now,
        requested_url=document.canonical_url,
        effective_url=document.canonical_url,
        response_status=200,
        mime_type="text/html",
        parser_version="fixture-v1",
        parse_status="parsed",
        byte_size=6,
        raw_content="report",
    )
    db.add(version)
    db.commit()
    return version


def _claimed_case(client, db, ticker="SNT"):
    from app.db.models import Company
    from app.services.agent_queue import claim_agent_run

    created = client.post("/api/research-cases", json={"ticker": ticker}).json()
    case_id = created["research_case"]["id"]
    run_id = created["agent_run"]["id"]
    run = claim_agent_run(db, agent_run_id=run_id, worker_id="test-worker")
    company = db.get(Company, created["research_case"]["company_id"])
    return case_id, run, company


def _payload(run_id, version_id, *, status="verified", lease_owner="test-worker"):
    from app.db.models import utcnow

    gaps = [] if status == "verified" else [
        {"topic": "backlog", "description": "Brak aktualnego backlogu.", "impact": "Niższa pewność przychodów.", "focus_tags": ["backlog"]}
    ]
    payload = {
        "contract_version": "research-snapshot-v2",
        "agent_run_id": run_id,
        "lease_owner": lease_owner,
        "version": 1,
        "as_of": utcnow().isoformat(),
        "profile": {
            "schema_version": "company-profile-v2",
            "version": 1,
            "archetype": "industrial-consumer",
            "archetype_version": "industrial-consumer-v1",
            "company_overlay": {
                "segments": ["Sprzęt medyczny"],
                "competitors": [],
                "source_questions": ["Jaki jest backlog?"],
                "unusual_risks": [],
            },
            "drivers": [
                {
                    "key": key,
                    "label": key,
                    "mechanism": f"{key} wpływa na wyniki.",
                    "source_document_version_ids": [version_id],
                    "focus_tags": [key],
                }
                for key in (
                    "volume", "price_mix", "fixed_costs", "working_capital", "capex",
                    *(["backlog"] if status == "verified" else []),
                )
            ],
            "kpis": [{
                "key": "gross_margin", "label": "Marża brutto", "unit": "%",
                "rationale": "Pokazuje miks i presję kosztową.", "source_document_version_ids": [version_id],
                "focus_tags": ["gross_margin"],
            }],
        },
        "sections": {
            "brief": {
                "current_understanding": "Spółka rośnie dzięki wolumenowi.",
                "freshness": "Raport bieżący.", "main_gap": "Brak backlogu.",
                "next_action": "Sprawdzić prezentację.",
            },
            "business_and_drivers": {
                "business_model": "Sprzedaż i serwis urządzeń.", "revenue_model": "Kontrakty i serwis.",
                "driver_keys": ["volume"], "claims": [{"text": "Wolumen jest istotny.", "kind": "fact", "source_document_version_ids": [version_id]}],
            },
            "performance": {
                "summary": "Marża pozostaje kluczowa.", "result_bridge": ["wolumen -> przychody"],
                "kpi_keys": ["gross_margin"], "claims": [],
            },
            "evidence": {
                "summary": "Raport emitenta.", "primary_document_version_ids": [version_id], "claims": [],
            },
            "thesis": {
                "why_now": "Rosnący popyt.", "counter_thesis": "Słabszy miks.", "catalysts": ["wyniki"],
                "risks": ["koszty"], "governance": "Brak stwierdzonych problemów.",
                "falsifiers": ["spadek marży"], "next_checks": ["backlog"], "claims": [],
            },
            "history": {"changes_since_previous": [], "prior_snapshot_id": None, "claims": []},
        },
        "source_manifest": [{"document_version_id": version_id, "role": "primary", "purpose": "Raport okresowy"}],
        "conflicts": [], "gaps": gaps,
        "next_checks": [{"question": "Jaki jest backlog?", "suggested_source": "Prezentacja wynikowa"}],
    }
    statements = {
        "/profile/archetype": payload["profile"]["archetype"],
        "/profile/company_overlay/segments/0": payload["profile"]["company_overlay"]["segments"][0],
        "/sections/brief/current_understanding": payload["sections"]["brief"]["current_understanding"],
        "/sections/brief/freshness": payload["sections"]["brief"]["freshness"],
        "/sections/brief/main_gap": payload["sections"]["brief"]["main_gap"],
        "/sections/brief/next_action": payload["sections"]["brief"]["next_action"],
        "/sections/business_and_drivers/business_model": payload["sections"]["business_and_drivers"]["business_model"],
        "/sections/business_and_drivers/revenue_model": payload["sections"]["business_and_drivers"]["revenue_model"],
        "/sections/performance/summary": payload["sections"]["performance"]["summary"],
        "/sections/performance/result_bridge/0": payload["sections"]["performance"]["result_bridge"][0],
        "/sections/evidence/summary": payload["sections"]["evidence"]["summary"],
        "/sections/thesis/why_now": payload["sections"]["thesis"]["why_now"],
        "/sections/thesis/counter_thesis": payload["sections"]["thesis"]["counter_thesis"],
        "/sections/thesis/catalysts/0": payload["sections"]["thesis"]["catalysts"][0],
        "/sections/thesis/risks/0": payload["sections"]["thesis"]["risks"][0],
        "/sections/thesis/governance": payload["sections"]["thesis"]["governance"],
        "/sections/thesis/falsifiers/0": payload["sections"]["thesis"]["falsifiers"][0],
    }
    payload["statement_provenance"] = [
        {
            "path": path,
            "claim": {
                "text": text,
                "kind": "fact",
                "source_document_version_ids": [version_id],
            },
        }
        for path, text in statements.items()
    ]
    return payload


def _verifier_result(status="verified", *, checks=None):
    verdict = {
        "verified": "pass",
        "provisional": "pass",
        "rejected": "fail",
        "needs-human": "needs-human",
    }[status]
    return {
        "model_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verdict": verdict,
        "checks": checks or {
            "schema_integrity": True,
            "source_integrity": True,
            "company_identity": True,
            "look_ahead": True,
            "math_integrity": True,
        },
        "summary": "Niezależna kontrola zakończona.",
    }


def _approve(
    client, case_id, draft, *, verifier_worker_id="test-verifier", verdict_status=None
):
    verdict_status = verdict_status or ("provisional" if draft["gaps"] else "verified")
    response = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={
            "verifier_worker_id": verifier_worker_id,
            "draft": draft,
            "verifier_result": _verifier_result(verdict_status),
        },
    )
    assert response.status_code == 200, response.text
    payload = deepcopy(draft)
    payload["verification_run_id"] = response.json()["id"]
    return payload


def test_verified_snapshot_is_immutable_terminal_and_read_only(client, db):
    from app.db.models import AgentRun, CompanyProfile, ResearchSnapshot, VerificationRun

    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    draft = _payload(run.id, version.id)
    payload = _approve(client, case_id, draft)

    saved = client.post(f"/api/research-cases/{case_id}/snapshots", json=payload)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["contract_version"] == "research-snapshot-v2"
    assert body["status"] == "verified"
    assert len(body["artifact_fingerprint"]) == 64
    assert db.query(CompanyProfile).one().version == 1
    assert db.query(ResearchSnapshot).one().agent_run_id == run.id
    assert db.query(VerificationRun).one().verdict == "pass"
    db.refresh(run)
    assert run.status == "verified"
    assert run.finished_at is not None
    assert run.lease_owner is None and run.lease_expires_at is None

    counts = tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (AgentRun, CompanyProfile, ResearchSnapshot, VerificationRun)
    )
    workspace = client.get("/api/research-cases/by-ticker/SNT")
    assert workspace.status_code == 200
    assert workspace.json()["latest_snapshot"]["id"] == body["id"]
    assert workspace.json()["profile"]["archetype"] == "industrial-consumer"
    assert workspace.json()["history"] == [{
        "id": body["id"], "version": 1, "status": "verified",
        "as_of": body["as_of"], "profile_version": 1, "created_at": body["created_at"],
    }]
    assert counts == tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (AgentRun, CompanyProfile, ResearchSnapshot, VerificationRun)
    )

    replay = client.post(f"/api/research-cases/{case_id}/snapshots", json=payload)
    assert replay.status_code == 200
    changed = deepcopy(payload)
    changed["sections"]["brief"]["current_understanding"] = "Changed replay."
    assert client.post(f"/api/research-cases/{case_id}/snapshots", json=changed).status_code == 409


def test_schema_and_verifier_gates_reject_invalid_payload(client, db):
    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    payload = _payload(run.id, version.id, status="provisional")
    provisional = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": payload, "verifier_result": _verifier_result("provisional")},
    )
    assert provisional.status_code == 200
    assert provisional.json()["checks"]["final_status"] == "provisional"
    rejected = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge-reject", "draft": payload, "verifier_result": _verifier_result("rejected")},
    )
    assert rejected.status_code == 200
    assert rejected.json()["checks"]["final_status"] == "rejected"
    needs_human = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge-human", "draft": payload, "verifier_result": _verifier_result("needs-human")},
    )
    assert needs_human.status_code == 200
    assert needs_human.json()["checks"]["final_status"] == "needs-human"
    payload = _payload(run.id, version.id, status="provisional")
    checks = _verifier_result("provisional")["checks"]
    checks["source_integrity"] = False
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": payload, "verifier_result": _verifier_result("provisional", checks=checks)},
    ).status_code == 422
    payload["profile"]["archetype"] = "generic"
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": payload, "verifier_result": _verifier_result("provisional")},
    ).status_code == 422


def test_provisional_snapshot_with_named_gaps_passes_and_profile_can_be_reused(client, db):
    from app.db.models import AgentRun, CompanyProfile, ResearchSnapshot
    from app.services.agent_queue import claim_agent_run

    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    first_payload = _approve(
        client, case_id, _payload(run.id, version.id, status="provisional")
    )
    first = client.post(f"/api/research-cases/{case_id}/snapshots", json=first_payload)
    assert first.status_code == 200, first.text
    assert first.json()["gaps"][0]["topic"] == "backlog"
    db.refresh(run)
    assert run.status == "provisional"

    review = AgentRun(
        workflow="stock-thesis-review",
        trigger="test",
        status="queued",
        company_id=company.id,
        inputs={
            "research_case_id": case_id,
            "task": {
                "skill": "company-research",
                "skill_version": "company-research-v2",
                "output_contract_version": "research-snapshot-v2",
                "company_profile_schema_version": "company-profile-v2",
                "archetype_contract_version": "archetype-packs-v1",
            },
        },
        outputs={},
    )
    db.add(review)
    db.commit()
    review = claim_agent_run(db, agent_run_id=review.id, worker_id="review-worker")
    second_payload = _payload(
        review.id, version.id, status="provisional", lease_owner="review-worker"
    )
    second_payload["version"] = 2
    second_payload["sections"]["history"]["prior_snapshot_id"] = first.json()["id"]
    second_payload["sections"]["history"]["changes_since_previous"] = ["Doprecyzowano źródła."]
    second_payload["statement_provenance"].append({
        "path": "/sections/history/changes_since_previous/0",
        "claim": {"text": "Doprecyzowano źródła.", "kind": "fact", "source_document_version_ids": [version.id]},
    })
    second_payload = _approve(client, case_id, second_payload, verifier_worker_id="review-judge")
    second = client.post(f"/api/research-cases/{case_id}/snapshots", json=second_payload)
    assert second.status_code == 200, second.text
    assert db.scalar(select(func.count()).select_from(ResearchSnapshot)) == 2
    assert db.scalar(select(func.count()).select_from(CompanyProfile)) == 1

def test_source_identity_agent_case_and_version_gates(client, db):
    from app.db.models import AgentRun, Company
    from app.services.agent_queue import claim_agent_run

    case_id, run, company = _claimed_case(client, db)
    other = Company(ticker="DEC", name="DECORA")
    db.add(other)
    db.commit()
    foreign_version = _document(db, other)
    payload = _payload(run.id, foreign_version.id)
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": payload, "verifier_result": _verifier_result()},
    ).status_code == 409

    unknown = _payload(run.id, 999999)
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": unknown, "verifier_result": _verifier_result()},
    ).status_code == 404

    own_version = _document(db, company, ticker="SNT")
    wrong = AgentRun(
        workflow="stock-initial-research", trigger="test", status="queued", company_id=other.id,
        inputs={"research_case_id": case_id}, outputs={},
    )
    db.add(wrong)
    db.commit()
    wrong = claim_agent_run(db, agent_run_id=wrong.id, worker_id="wrong-worker")
    payload = _payload(wrong.id, own_version.id, lease_owner="wrong-worker")
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": payload, "verifier_result": _verifier_result()},
    ).status_code == 409

    wrong_case = AgentRun(
        workflow="stock-thesis-review", trigger="test", status="queued", company_id=company.id,
        inputs={"research_case_id": case_id + 1000}, outputs={},
    )
    db.add(wrong_case)
    db.commit()
    wrong_case = claim_agent_run(db, agent_run_id=wrong_case.id, worker_id="wrong-case-worker")
    payload = _payload(wrong_case.id, own_version.id, lease_owner="wrong-case-worker")
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": payload, "verifier_result": _verifier_result()},
    ).status_code == 409

    payload = _payload(run.id, own_version.id)
    payload["version"] = 2
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": payload, "verifier_result": _verifier_result()},
    ).status_code == 409


def test_save_requires_live_claimed_lease(client, db):
    from app.db.models import utcnow

    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    run.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": _payload(run.id, version.id), "verifier_result": _verifier_result()},
    ).status_code == 409


def test_provenance_contract_and_exact_text_are_mandatory(client, db):
    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    draft = _payload(run.id, version.id)
    draft["statement_provenance"].pop()
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 422

    draft = _payload(run.id, version.id)
    draft["statement_provenance"][0]["claim"]["text"] = "Different claim."
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 422

    draft = _payload(run.id, version.id)
    draft["profile"]["drivers"][0]["source_document_version_ids"] = []
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 422


def test_frozen_contract_owner_time_and_exact_verification_are_enforced(client, db):
    from app.db.models import utcnow

    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    draft = _payload(run.id, version.id)
    draft["lease_owner"] = "other-worker"
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 409

    draft = _payload(run.id, version.id)
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "test-worker", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 409

    draft["as_of"] = (version.fetched_at - timedelta(seconds=1)).isoformat()
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 409

    draft = _payload(run.id, version.id)
    draft["as_of"] = (utcnow() + timedelta(minutes=5)).isoformat()
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 422

    draft = _payload(run.id, version.id)
    verification = _approve(client, case_id, draft)
    original_inputs = deepcopy(run.inputs)
    run.inputs = {**run.inputs, "changed_after_verification": True}
    db.commit()
    assert client.post(
        f"/api/research-cases/{case_id}/snapshots", json=verification
    ).status_code == 409
    run.inputs = original_inputs
    db.commit()

    verification["sections"]["brief"]["current_understanding"] = "Changed after review."
    for item in verification["statement_provenance"]:
        if item["path"] == "/sections/brief/current_understanding":
            item["claim"]["text"] = "Changed after review."
    assert client.post(
        f"/api/research-cases/{case_id}/snapshots", json=verification
    ).status_code == 409

    run.inputs["task"]["skill_version"] = "wrong-version"
    db.commit()
    draft = _payload(run.id, version.id)
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge-2", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 409


def test_source_non_null_company_id_cannot_be_overridden_by_ticker(client, db):
    from app.db.models import Company, SourceDocument

    case_id, run, company = _claimed_case(client, db)
    other = Company(ticker="DEC", name="DECORA")
    db.add(other)
    db.commit()
    version = _document(db, other)
    document = db.get(SourceDocument, version.source_document_id)
    document.company_ticker = company.ticker
    db.commit()
    draft = _payload(run.id, version.id)
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": draft, "verifier_result": _verifier_result()},
    ).status_code == 409


def test_mcp_save_research_snapshot_is_a_thin_domain_adapter(client, db):
    from app.mcp.stock_workbench_server import handle_message

    listed = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tool_names = {item["name"] for item in listed["result"]["tools"]}
    assert {"verify_research_snapshot", "save_research_snapshot"}.issubset(tool_names)
    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    draft = _payload(run.id, version.id)
    verified = handle_message({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "verify_research_snapshot", "arguments": {
            "case_id": case_id,
            "payload": {"verifier_worker_id": "mcp-judge", "draft": draft, "verifier_result": _verifier_result()},
        }},
    })
    verification_content = verified["result"]["structuredContent"]
    assert verification_content["ok"] is True
    draft["verification_run_id"] = verification_content["verification_run"]["id"]
    result = handle_message({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "save_research_snapshot", "arguments": {
            "case_id": case_id, "payload": draft,
        }},
    })
    content = result["result"]["structuredContent"]
    assert content["ok"] is True
    assert content["research_snapshot"]["status"] == "verified"


def test_json_save_script_uses_the_same_domain_gate(client, db, monkeypatch, capsys):
    from scripts import codex_save_research_snapshot, codex_verify_research_snapshot

    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    draft = _payload(run.id, version.id)
    monkeypatch.setattr(
        sys,
        "argv", ["codex_verify_research_snapshot.py", "--case-id", str(case_id)],
    )
    raw = json.dumps({
        "verifier_worker_id": "script-judge",
        "draft": draft,
        "verifier_result": _verifier_result(),
    })
    monkeypatch.setattr(sys, "stdin", type("Input", (), {"read": lambda _self: raw})())
    assert codex_verify_research_snapshot.main() == 0
    verification_output = json.loads(capsys.readouterr().out)
    draft["verification_run_id"] = verification_output["verification_run"]["id"]
    monkeypatch.setattr(
        sys,
        "argv", ["codex_save_research_snapshot.py", "--case-id", str(case_id)],
    )
    raw = json.dumps(draft)
    monkeypatch.setattr(sys, "stdin", type("Input", (), {"read": lambda _self: raw})())
    assert codex_save_research_snapshot.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["research_snapshot"]["research_case_id"] == case_id


def test_archetype_registry_requires_canonical_complete_known_focus(client, db):
    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)

    wrong_version = _payload(run.id, version.id)
    wrong_version["profile"]["archetype_version"] = "industrial-consumer-v0"
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": wrong_version, "verifier_result": _verifier_result()},
    ).status_code == 422

    legacy_write_alias = _payload(run.id, version.id)
    legacy_write_alias["profile"]["archetype"] = "software-services"
    legacy_write_alias["profile"]["archetype_version"] = "software-services-v1-provisional"
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": legacy_write_alias, "verifier_result": _verifier_result()},
    ).status_code == 422

    unknown_tag = _payload(run.id, version.id)
    unknown_tag["profile"]["drivers"][0]["focus_tags"].append("magic_score")
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": unknown_tag, "verifier_result": _verifier_result()},
    ).status_code == 422

    missing = _payload(run.id, version.id)
    capex = next(
        item for item in missing["profile"]["drivers"] if item["key"] == "capex"
    )
    capex["focus_tags"] = []
    response = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": missing, "verifier_result": _verifier_result()},
    )
    assert response.status_code == 422
    assert "capex" in response.json()["detail"]


def test_archetype_focus_mapping_rejects_bundles_mismatches_duplicates_and_overlap(
    client, db
):
    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)

    bundled = _payload(run.id, version.id)
    bundled["profile"]["drivers"][0]["focus_tags"].append("price_mix")
    response = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": bundled, "verifier_result": _verifier_result()},
    )
    assert response.status_code == 422
    assert "at most one" in response.json()["detail"]

    mismatched = _payload(run.id, version.id)
    mismatched["profile"]["drivers"][0]["focus_tags"] = ["price_mix"]
    response = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": mismatched, "verifier_result": _verifier_result()},
    )
    assert response.status_code == 422
    assert "same focus tag as its key" in response.json()["detail"]

    duplicate_evidence = _payload(run.id, version.id)
    duplicate_evidence["profile"]["kpis"].append({
        "key": "volume",
        "label": "Drugi wolumen",
        "rationale": "Duplikat mapowania do testu.",
        "source_document_version_ids": [version.id],
        "focus_tags": ["volume"],
    })
    response = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": duplicate_evidence, "verifier_result": _verifier_result()},
    )
    assert response.status_code == 422
    assert "only one driver or KPI" in response.json()["detail"]

    duplicate_gap = _payload(run.id, version.id, status="provisional")
    duplicate_gap["gaps"].append({
        "topic": "backlog",
        "description": "Drugi opis tej samej luki.",
        "impact": "Nie zmienia zakresu.",
        "focus_tags": ["backlog"],
    })
    response = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": duplicate_gap, "verifier_result": _verifier_result("provisional")},
    )
    assert response.status_code == 422
    assert "only one explicit gap" in response.json()["detail"]

    overlap = _payload(run.id, version.id)
    overlap["gaps"].append({
        "topic": "backlog",
        "description": "Backlog równocześnie oznaczono jako pokryty.",
        "impact": "Niejednoznaczny stan.",
        "focus_tags": ["backlog"],
    })
    response = client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge", "draft": overlap, "verifier_result": _verifier_result("provisional")},
    )
    assert response.status_code == 422
    assert "cannot be both" in response.json()["detail"]


def test_archetype_registry_exposes_all_versioned_required_marker_sets():
    from app.services.archetype_packs import PACKS, known_marker_ids

    expected = {
        "industrial-consumer": {"volume", "price_mix", "gross_margin", "fixed_costs", "backlog", "working_capital", "capex"},
        "bank-financial": {"loan_deposit_volume", "nim", "fees", "cost_of_risk", "capital", "roe"},
        "developer-real-estate": {"presales", "handovers", "asp", "land_bank", "nav", "net_debt"},
        "software-services": {"recurring_revenue", "retention", "utilization", "wages", "cash_conversion"},
        "gaming-event": {"launch_timing", "units", "price", "platform_share", "pipeline", "runway"},
        "energy-resources": {"volume", "commodity_spread", "availability", "unit_costs", "capex", "debt"},
        "holding-biotech": {"asset_value", "runway", "milestones", "dilution", "risk_adjusted_value"},
    }
    assert set(PACKS) == set(expected)
    for archetype, markers in expected.items():
        pack = PACKS[archetype]
        assert pack.version == f"{archetype}-v1"
        assert known_marker_ids(pack) == markers
        assert all(marker.label for marker in pack.required_markers)


def test_gap_markers_address_pack_scope_without_claiming_evidence(client, db):
    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    draft = _payload(run.id, version.id, status="provisional")
    saved = client.post(
        f"/api/research-cases/{case_id}/snapshots",
        json=_approve(client, case_id, draft),
    )
    assert saved.status_code == 200, saved.text

    pack = client.get("/api/research-cases/by-ticker/SNT").json()["archetype_pack"]
    assert pack["coverage_count"] == 7
    assert pack["coverage_pct"] == 100.0
    assert pack["gap_markers"] == ["backlog"]
    assert "backlog" not in pack["covered_markers"]
    backlog = next(row for row in pack["required_markers"] if row["id"] == "backlog")
    assert backlog == {
        "id": "backlog", "label": "Portfel zamówień", "covered": False, "state": "gap"
    }
    assert pack["sourced_count"] == 6
    assert pack["assumption_count"] == 0
    assert pack["gap_count"] == 1


def test_basis_only_profile_marker_is_an_assumption_not_sourced_coverage(client, db):
    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    draft = _payload(run.id, version.id)
    capex = next(item for item in draft["profile"]["drivers"] if item["key"] == "capex")
    capex["source_document_version_ids"] = []
    capex["basis"] = "Założenie analityka do potwierdzenia w raporcie inwestycyjnym."
    saved = client.post(
        f"/api/research-cases/{case_id}/snapshots",
        json=_approve(client, case_id, draft),
    )
    assert saved.status_code == 200, saved.text

    pack = client.get("/api/research-cases/by-ticker/SNT").json()["archetype_pack"]
    capex_marker = next(row for row in pack["required_markers"] if row["id"] == "capex")
    assert capex_marker["state"] == "assumption"
    assert capex_marker["covered"] is False
    assert "capex" in pack["assumption_markers"]
    assert "capex" not in pack["sourced_markers"]
    assert pack["sourced_count"] == 6
    assert pack["assumption_count"] == 1
    assert pack["coverage_count"] == 7


def test_frozen_v1_job_keeps_legacy_write_contract_while_new_jobs_use_v2(client, db):
    case_id, run, company = _claimed_case(client, db)
    version = _document(db, company)
    legacy_inputs = deepcopy(run.inputs)
    legacy_inputs["task"]["skill_version"] = "company-research-v1"
    legacy_inputs["task"]["output_contract_version"] = "research-snapshot-v1"
    legacy_inputs["task"].pop("company_profile_schema_version")
    legacy_inputs["task"].pop("archetype_contract_version")
    run.inputs = legacy_inputs
    db.commit()

    v2_draft = _payload(run.id, version.id)
    assert client.post(
        f"/api/research-cases/{case_id}/snapshot-verifications",
        json={"verifier_worker_id": "judge-v2", "draft": v2_draft, "verifier_result": _verifier_result()},
    ).status_code == 409

    legacy = _payload(run.id, version.id)
    legacy["contract_version"] = "research-snapshot-v1"
    legacy["profile"]["schema_version"] = "company-profile-v1"
    for item in [*legacy["profile"]["drivers"], *legacy["profile"]["kpis"]]:
        item.pop("focus_tags", None)
    for gap in legacy["gaps"]:
        gap.pop("focus_tags", None)
    saved = client.post(
        f"/api/research-cases/{case_id}/snapshots",
        json=_approve(client, case_id, legacy, verifier_worker_id="legacy-judge"),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["contract_version"] == "research-snapshot-v1"
    assert saved.json()["status"] == "verified"


def test_existing_abs_profile_alias_is_read_without_mutation(client, db):
    from app.db.models import CompanyProfile

    case_id, run, company = _claimed_case(client, db, ticker="ABS")
    version = _document(db, company)
    saved = client.post(
        f"/api/research-cases/{case_id}/snapshots",
        json=_approve(client, case_id, _payload(run.id, version.id)),
    )
    assert saved.status_code == 200
    profile = db.query(CompanyProfile).one()
    profile.archetype = "software-services"
    profile.archetype_version = "software-services-v1-provisional"
    profile.drivers = [
        {"key": key, "label": key, "mechanism": "test", "basis": "legacy"}
        for key in ("recurring_revenue", "retention", "utilization", "wages")
    ]
    profile.kpis = [{
        "key": "cash_conversion", "label": "cash", "rationale": "test", "basis": "legacy"
    }]
    db.commit()

    workspace = client.get("/api/research-cases/by-ticker/ABS")
    assert workspace.status_code == 200, workspace.text
    body = workspace.json()
    assert body["profile"]["archetype_version"] == "software-services-v1-provisional"
    assert body["archetype_pack"]["version"] == "software-services-v1"
    assert body["archetype_pack"]["coverage_count"] == 5
    db.refresh(profile)
    assert profile.archetype_version == "software-services-v1-provisional"


def test_archetype_pack_script_and_mcp_are_thin_read_adapters(monkeypatch, capsys):
    from app.mcp import stock_tools
    from scripts import codex_get_archetype_pack

    monkeypatch.setattr(
        sys,
        "argv",
        ["codex_get_archetype_pack.py", "--archetype", "bank-financial"],
    )
    assert codex_get_archetype_pack.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["archetype_pack"]["version"] == "bank-financial-v1"
    assert output["archetype_pack"]["required_markers"][1] == {
        "id": "nim", "label": "Marża odsetkowa netto"
    }
    assert stock_tools.get_archetype_pack({"archetype": "bank-financial"}) == output
