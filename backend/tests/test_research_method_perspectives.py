"""M1 immutable source-frozen Research method perspective contracts."""

from copy import deepcopy

from sqlalchemy import func, select

from tests.test_research_artifacts import _approve, _claimed_case, _document, _payload


def _parent_snapshot(client, db, *, ticker="SNT"):
    case_id, run, company = _claimed_case(client, db, ticker=ticker)
    document = _document(db, company)
    draft = _payload(run.id, document.id)
    saved = client.post(
        f"/api/research-cases/{case_id}/snapshots",
        json=_approve(client, case_id, draft),
    )
    assert saved.status_code == 200, saved.text
    return case_id, company, document, saved.json()


def _perspective_draft(run, document_id, snapshot, *, applicable=True):
    context = run.inputs["method_perspective"]
    manifest = context["method_manifest"]
    findings = []
    for check in manifest["required_checks"]:
        if applicable:
            findings.append(
                {
                    "required_check_id": check["id"],
                    "status": "supports",
                    "claim": {
                        "text": f"Źródło wspiera kontrolę: {check['label']}",
                        "kind": "fact",
                        "source_document_version_ids": [document_id],
                    },
                }
            )
        else:
            findings.append(
                {
                    "required_check_id": check["id"],
                    "status": "not-applicable",
                    "claim": {
                        "text": f"Brak danych pozwalających zastosować kontrolę: {check['label']}",
                        "kind": "unknown",
                        "basis": "Zamrożony snapshot nie zawiera potrzebnego miernika.",
                    },
                }
            )
    return {
        "contract_version": "research-method-perspective-v1",
        "agent_run_id": run.id,
        "lease_owner": run.lease_owner,
        "research_snapshot_id": snapshot["id"],
        "method_pack_id": manifest["id"],
        "method_pack_version": manifest["version"],
        "method_manifest": manifest,
        "method_manifest_fingerprint": context["method_manifest_fingerprint"],
        "as_of": context["research_snapshot"]["snapshot"]["as_of"],
        "applicability": {
            "status": "applicable" if applicable else "not-applicable",
            "reason": (
                {
                    "text": "Model biznesowy pozwala zastosować kontrolę metody.",
                    "kind": "fact",
                    "source_document_version_ids": [document_id],
                }
                if applicable
                else {
                    "text": "Brak mierników koniecznych do zastosowania metody.",
                    "kind": "unknown",
                    "basis": "Zamrożony snapshot nie zawiera wymaganych danych.",
                }
            ),
        },
        "conclusion": (
            {
                "text": "Zamrożone źródła pozwalają odczytać tę perspektywę bez rekomendacji.",
                "kind": "calculation",
                "source_document_version_ids": [document_id],
                "basis": "Klasyfikacja opiera się wyłącznie na źródłach zamrożonego snapshotu.",
            }
            if applicable
            else None
        ),
        "findings": findings,
        "blind_spots": manifest["blind_spots"],
        "falsifiers": [
            {
                "text": "Kolejny raport nie potwierdzi mechanizmu wyniku.",
                "kind": "fact",
                "source_document_version_ids": [document_id],
            }
        ],
        "next_checks": [
            {
                "question": "Czy następny raport potwierdza mechanizm?",
                "suggested_source": "Raport okresowy emitenta",
            }
        ],
        "gaps": (
            []
            if applicable
            else [
                {
                    "topic": "method-inputs",
                    "description": "Brak mierników wymaganych do zastosowania metody.",
                    "impact": "Perspektywa pozostaje ograniczona.",
                    "focus_tags": [],
                }
            ]
        ),
    }


def _verifier_result(status="verified"):
    return {
        "model_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verdict": "pass" if status in {"verified", "provisional"} else status,
        "checks": {
            "schema_integrity": True,
            "source_integrity": True,
            "snapshot_binding": True,
            "method_manifest_integrity": True,
            "attribution": True,
            "non_impersonation": True,
            "applicability": True,
            "unknown_handling": True,
            "no_hidden_blend": True,
            "look_ahead": True,
        },
        "summary": "Niezależna kontrola perspektywy zakończona.",
    }


def _queue_and_claim(client, db, case_id, snapshot_id):
    from app.services.agent_queue import claim_agent_run

    queued = client.post(
        f"/api/research-cases/{case_id}/method-perspective-runs",
        json={"research_snapshot_id": snapshot_id, "method_pack_id": "malik_obs_v1"},
    )
    assert queued.status_code == 201, queued.text
    run = claim_agent_run(
        db, agent_run_id=queued.json()["agent_run_id"], worker_id="perspective-drafter"
    )
    return queued.json(), run


def _verify_and_save(client, case_id, draft):
    verified = client.post(
        f"/api/research-cases/{case_id}/method-perspective-verifications",
        json={
            "verifier_worker_id": "perspective-verifier",
            "draft": draft,
            "verifier_result": _verifier_result(
                "provisional" if draft["gaps"] else "verified"
            ),
        },
    )
    assert verified.status_code == 200, verified.text
    payload = deepcopy(draft)
    payload["verification_run_id"] = verified.json()["id"]
    saved = client.post(
        f"/api/research-cases/{case_id}/method-perspectives", json=payload
    )
    assert saved.status_code == 200, saved.text
    return saved.json(), payload


def test_explicit_perspective_command_freezes_parent_and_is_idempotent(client, db):
    from app.db.models import AgentRun, CompanyProfile, ResearchMethodPerspective, ResearchSnapshot

    case_id, _, document, snapshot = _parent_snapshot(client, db)
    counts = tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (AgentRun, CompanyProfile, ResearchSnapshot, ResearchMethodPerspective)
    )
    first, run = _queue_and_claim(client, db, case_id, snapshot["id"])
    assert first["created"] is True
    assert run.workflow == "stock-research-method-perspective"
    assert run.trigger == "method-perspective-command"
    assert len(run.idempotency_key) <= 160
    assert run.inputs["method_perspective"]["research_snapshot"]["snapshot"]["id"] == snapshot["id"]
    assert tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (CompanyProfile, ResearchSnapshot, ResearchMethodPerspective)
    ) == counts[1:]
    repeated = client.post(
        f"/api/research-cases/{case_id}/method-perspective-runs",
        json={"research_snapshot_id": snapshot["id"], "method_pack_id": "malik_obs_v1"},
    )
    assert repeated.status_code == 201
    assert repeated.json()["created"] is False
    assert repeated.json()["agent_run_id"] == run.id

    saved, payload = _verify_and_save(
        client, case_id, _perspective_draft(run, document.id, snapshot)
    )
    assert saved["status"] == "verified"
    assert saved["research_snapshot_id"] == snapshot["id"]
    assert len(saved["artifact_fingerprint"]) == 64
    assert client.post(
        f"/api/research-cases/{case_id}/method-perspectives", json=payload
    ).json()["id"] == saved["id"]
    db.refresh(run)
    assert run.status == "verified" and run.lease_owner is None
    parent = db.get(ResearchSnapshot, snapshot["id"])
    assert parent.artifact_fingerprint == snapshot["artifact_fingerprint"]
    workspace = client.get("/api/research-cases/by-ticker/SNT")
    assert workspace.status_code == 200
    assert workspace.json()["method_perspectives"][0]["id"] == saved["id"]


def test_perspective_rejects_draft_pack_and_source_outside_parent(client, db):
    case_id, _, document, snapshot = _parent_snapshot(client, db)
    unsupported = client.post(
        f"/api/research-cases/{case_id}/method-perspective-runs",
        json={"research_snapshot_id": snapshot["id"], "method_pack_id": "areczeks_v1"},
    )
    assert unsupported.status_code == 409
    _, run = _queue_and_claim(client, db, case_id, snapshot["id"])
    bad = _perspective_draft(run, document.id, snapshot)
    bad["findings"][0]["claim"]["source_document_version_ids"] = [999999]
    response = client.post(
        f"/api/research-cases/{case_id}/method-perspective-verifications",
        json={
            "verifier_worker_id": "perspective-verifier",
            "draft": bad,
            "verifier_result": _verifier_result(),
        },
    )
    assert response.status_code == 422
    assert "outside its parent snapshot" in response.json()["detail"]


def test_perspective_rejects_assumption_or_lead_as_support_and_skill_drift(client, db):
    case_id, _, document, snapshot = _parent_snapshot(client, db)
    _, run = _queue_and_claim(client, db, case_id, snapshot["id"])
    assumption = _perspective_draft(run, document.id, snapshot)
    assumption["findings"][0]["claim"] = {
        "text": "Niezweryfikowane założenie nie może wspierać metody.",
        "kind": "assumption",
        "basis": "Założenie robocze.",
        "source_document_version_ids": [document.id],
    }
    response = client.post(
        f"/api/research-cases/{case_id}/method-perspective-verifications",
        json={
            "verifier_worker_id": "perspective-verifier",
            "draft": assumption,
            "verifier_result": _verifier_result(),
        },
    )
    assert response.status_code == 422
    assert "factual or calculation" in response.json()["detail"]
    run.inputs["task"]["skill_version"] = "unexpected"
    db.commit()
    drifted = _perspective_draft(run, document.id, snapshot)
    response = client.post(
        f"/api/research-cases/{case_id}/method-perspective-verifications",
        json={
            "verifier_worker_id": "perspective-verifier",
            "draft": drifted,
            "verifier_result": _verifier_result(),
        },
    )
    assert response.status_code == 409
    assert "skill/version/output contract" in response.json()["detail"]


def test_perspective_rejects_lead_only_support(client, db):
    from app.db.models import DocumentVersion, SourceDocument, utcnow

    case_id, run, company = _claimed_case(client, db)
    primary = _document(db, company)
    now = utcnow()
    source = SourceDocument(
        company_id=company.id,
        company_ticker=company.ticker,
        source_name="forum",
        source_type="forum",
        scope_key=f"lead-{company.ticker}",
        canonical_url="https://example.test/forum-lead",
        first_seen_at=now,
        last_fetched_at=now,
        latest_content_hash="b" * 64,
        mime_type="text/html",
        parser_version="fixture-v1",
        last_fetch_status=200,
    )
    db.add(source)
    db.flush()
    lead = DocumentVersion(
        source_document_id=source.id,
        content_hash="b" * 64,
        fetched_at=now,
        requested_url=source.canonical_url,
        effective_url=source.canonical_url,
        response_status=200,
        mime_type="text/html",
        parser_version="fixture-v1",
        parse_status="parsed",
        byte_size=4,
        raw_content="lead",
    )
    db.add(lead)
    db.commit()
    draft = _payload(run.id, primary.id)
    draft["source_manifest"].append(
        {"document_version_id": lead.id, "role": "lead", "purpose": "Nieskorygowany trop."}
    )
    snapshot_response = client.post(
        f"/api/research-cases/{case_id}/snapshots",
        json=_approve(client, case_id, draft),
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    snapshot = snapshot_response.json()
    _, perspective_run = _queue_and_claim(client, db, case_id, snapshot["id"])
    perspective = _perspective_draft(perspective_run, primary.id, snapshot)
    perspective["findings"][0]["claim"]["source_document_version_ids"] = [lead.id]
    response = client.post(
        f"/api/research-cases/{case_id}/method-perspective-verifications",
        json={
            "verifier_worker_id": "perspective-verifier",
            "draft": perspective,
            "verifier_result": _verifier_result(),
        },
    )
    assert response.status_code == 422
    assert "non-lead parent source" in response.json()["detail"]


def test_mcp_cannot_enqueue_unfrozen_method_perspective(client, db):
    from app.db.models import Company
    from app.mcp.stock_workbench_server import handle_message

    db.add(Company(ticker="SNT", name="SYNEKTIK"))
    db.commit()
    response = handle_message({
        "jsonrpc": "2.0", "id": 81, "method": "tools/call",
        "params": {"name": "queue_agent_run", "arguments": {
            "workflow": "stock-research-method-perspective", "ticker": "SNT",
        }},
    })
    content = response["result"]["structuredContent"]
    assert content["ok"] is False
    assert "parent snapshot" in content["error"]


def test_unlike_fixtures_keep_method_findings_separate_and_get_read_stays_zero_write(client, db):
    from app.db.models import AgentRun, ResearchMethodPerspective

    first_case, _, first_document, first_snapshot = _parent_snapshot(client, db, ticker="SNT")
    _, first_run = _queue_and_claim(client, db, first_case, first_snapshot["id"])
    first, _ = _verify_and_save(
        client, first_case, _perspective_draft(first_run, first_document.id, first_snapshot)
    )
    second_case, _, second_document, second_snapshot = _parent_snapshot(client, db, ticker="DEC")
    _, second_run = _queue_and_claim(client, db, second_case, second_snapshot["id"])
    second, _ = _verify_and_save(
        client,
        second_case,
        _perspective_draft(second_run, second_document.id, second_snapshot, applicable=False),
    )
    assert first["applicability"]["status"] == "applicable"
    assert {item["status"] for item in first["findings"]} == {"supports"}
    assert second["applicability"]["status"] == "not-applicable"
    assert {item["status"] for item in second["findings"]} == {"not-applicable"}
    assert second["status"] == "provisional"
    counts = tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (AgentRun, ResearchMethodPerspective)
    )
    assert client.get("/api/research-cases/by-ticker/SNT").status_code == 200
    assert client.get("/api/research-cases/by-ticker/SNT").status_code == 200
    assert counts == tuple(
        db.scalar(select(func.count()).select_from(model))
        for model in (AgentRun, ResearchMethodPerspective)
    )
