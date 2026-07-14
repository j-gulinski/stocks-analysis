"""Adversarial computed-evidence tests for VISION V4 valuation gates."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from itertools import combinations_with_replacement
import json

import pytest

from app.api.schemas import ValuationSnapshotDraftIn
from app.db.models import ValuationSnapshot
from app.services.agent_queue import claim_agent_run
from app.services.valuation_gates import (
    KNOWN_DEFAULT_PROBABILITY_FINGERPRINTS,
    evaluate_structural_gates,
)
from tests.test_valuation_v1 import (
    _draft_from_run,
    _queue_request,
    _research_fixture,
)


CORE_FIELDS = (
    "quarter_revenue_growth_pct",
    "year_revenue_growth_pct",
    "gross_margin_pct",
    "operating_cost_ratio_pct",
    "target_pe",
)


def _fresh_draft(client, db, ticker: str):
    case, snapshot, now = _research_fixture(db, ticker=ticker)
    response = client.post(
        f"/api/research-cases/{case.id}/valuation-runs",
        json=_queue_request(snapshot.id, now),
    )
    assert response.status_code == 201, response.text
    run = claim_agent_run(
        db,
        agent_run_id=response.json()["agent_run_id"],
        worker_id=f"drafter-{ticker.lower()}",
    )
    return case, snapshot, ValuationSnapshotDraftIn.model_validate(_draft_from_run(run))


def _gate_results(db, case, draft) -> dict[str, object]:
    return {
        result.gate: result
        for result in evaluate_structural_gates(db, case, draft)
    }


def _configured_house_default_mix() -> tuple[int, int, int]:
    """Discover a configured fingerprint without restating its numeric mix."""
    for mix in combinations_with_replacement(range(1, 99), 3):
        if sum(mix) != 100:
            continue
        encoded = json.dumps(
            mix,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() in KNOWN_DEFAULT_PROBABILITY_FINGERPRINTS:
            return mix
    pytest.fail("The configured house-default fingerprints contain no valid triad.")


def _persist_current_valuation(
    db,
    case,
    research_snapshot,
    draft,
    *,
    probability_mix: tuple[int, ...] | None = None,
    vector_scale: float = 1.0,
) -> ValuationSnapshot:
    assumptions = [row.model_dump(mode="json") for row in draft.assumptions]
    for scenario in assumptions:
        for field in CORE_FIELDS:
            scenario[field]["value"] *= vector_scale

    judgment = draft.codex_judgment.model_dump(mode="json")
    if probability_mix is not None:
        assert len(probability_mix) == len(judgment["scenarios"])
        for scenario, probability in zip(
            judgment["scenarios"], probability_mix, strict=True
        ):
            scenario["probability_pct"] = probability

    row = ValuationSnapshot(
        research_case_id=case.id,
        research_snapshot_id=research_snapshot.id,
        version=1,
        contract_version=draft.contract_version,
        status="verified",
        origin="codex",
        as_of=draft.as_of,
        template_id=draft.template_id,
        template_version=draft.template_version,
        calculation_engine_version=draft.engine_version,
        assumptions={"scenarios": assumptions},
        base_values=draft.base_values,
        deterministic_outputs=draft.deterministic_outputs,
        codex_judgment=judgment,
        input_manifest=draft.input_manifest,
        gaps=draft.gaps,
        input_fingerprint=draft.input_fingerprint,
        calculation_fingerprint=draft.calculation_fingerprint,
        artifact_fingerprint=f"{case.id:064x}",
        verifier_result={"verdict": "pass"},
    )
    db.add(row)
    db.commit()
    return row


def test_optional_event_with_degenerate_probability_is_rejected(client, db):
    case, _snapshot, draft = _fresh_draft(client, db, "EVENT-GATE")
    payload = draft.model_dump(mode="json")

    event_assumptions = deepcopy(payload["assumptions"][-1])
    event_assumptions["kind"] = "event"
    event_assumptions["label"] = "event"
    for offset, field in enumerate(CORE_FIELDS, start=1):
        event_assumptions[field]["value"] += offset
    event_assumptions["event_one_off_net_pln_thousands"] = {
        "value": 1.0,
        "provenance": "human_assumption",
        "rationale": "Jawny jednorazowy efekt zdarzenia.",
        "source_fact_ids": [],
    }
    payload["assumptions"].append(event_assumptions)
    payload["codex_judgment"]["scenarios"].append(
        {
            "kind": "event",
            "mechanism": (
                "A company-specific one-off event changes the reported result "
                "without recurring in the ordinary operating path."
            ),
            "probability_pct": 0,
            "probability_rationale": (
                "The frozen evidence does not support assigning a non-zero chance "
                "to this optional event scenario."
            ),
            "catalyst_or_counter_driver": "Named one-off event outcome.",
            "falsifier": "No qualifying event is reported by 2026Q4.",
            "gaps": [],
        }
    )
    event_draft = ValuationSnapshotDraftIn.model_validate(payload)

    result = _gate_results(db, case, event_draft)["probability_structure"]

    assert result.passed is False
    assert "event" in result.reason.lower()
    assert "degenerate" in result.reason.lower()


def test_configured_house_default_fingerprint_is_rejected_without_literal_mix(
    client, db
):
    case, _snapshot, draft = _fresh_draft(client, db, "DEFAULT-GATE")
    payload = draft.model_dump(mode="json")
    configured_mix = _configured_house_default_mix()
    for scenario, probability in zip(
        payload["codex_judgment"]["scenarios"], configured_mix, strict=True
    ):
        scenario["probability_pct"] = probability
    configured_default_draft = ValuationSnapshotDraftIn.model_validate(payload)

    result = _gate_results(db, case, configured_default_draft)[
        "probability_structure"
    ]

    assert result.passed is False
    assert "known house default" in result.reason.lower()


def test_probability_mix_repeated_by_two_current_companies_is_rejected(client, db):
    case, _snapshot, draft = _fresh_draft(client, db, "REPEAT-GATE")
    probability_mix = tuple(
        row.probability_pct for row in draft.codex_judgment.scenarios
    )
    for ticker, scale in (("REPEAT-PEER-A", 2.0), ("REPEAT-PEER-B", 3.0)):
        peer_case, peer_snapshot, _now = _research_fixture(db, ticker=ticker)
        _persist_current_valuation(
            db,
            peer_case,
            peer_snapshot,
            draft,
            probability_mix=probability_mix,
            vector_scale=scale,
        )

    result = _gate_results(db, case, draft)["probability_repetition"]

    assert result.passed is False
    assert "2 other current valuations" in result.reason


def test_near_duplicate_core_vectors_from_another_current_company_are_rejected(
    client, db
):
    case, _snapshot, draft = _fresh_draft(client, db, "VECTOR-GATE")
    peer_case, peer_snapshot, _now = _research_fixture(db, ticker="VECTOR-PEER")
    _persist_current_valuation(
        db,
        peer_case,
        peer_snapshot,
        draft,
        vector_scale=1.01,
    )

    result = _gate_results(db, case, draft)["cross_company_specificity"]

    assert result.passed is False
    assert str(peer_case.id) in result.reason
    assert "near-duplicate" in result.reason


def test_zero_evidence_bound_core_fields_are_rejected(client, db):
    case, _snapshot, draft = _fresh_draft(client, db, "EVIDENCE-GATE")
    payload = draft.model_dump(mode="json")
    for scenario in payload["assumptions"]:
        for field in CORE_FIELDS:
            scenario[field]["provenance"] = "human_assumption"
            scenario[field]["source_fact_ids"] = []
    unbound_draft = ValuationSnapshotDraftIn.model_validate(payload)

    result = _gate_results(db, case, unbound_draft)["evidence_binding"]

    assert result.passed is False
    assert "no core assumption" in result.reason.lower()


@pytest.mark.parametrize("defect", ("mechanism", "rationale", "vectors"))
def test_copied_scenario_content_is_rejected(client, db, defect):
    case, _snapshot, draft = _fresh_draft(client, db, f"DISTINCT-{defect}")
    payload = draft.model_dump(mode="json")

    if defect == "mechanism":
        copied = (
            "The same copied operating mechanism is reused across every scenario."
        )
        for scenario in payload["codex_judgment"]["scenarios"]:
            scenario["mechanism"] = copied
    elif defect == "rationale":
        copied = (
            "The same copied evidence rationale is reused across every scenario."
        )
        for scenario in payload["codex_judgment"]["scenarios"]:
            scenario["probability_rationale"] = copied
    else:
        reference = payload["assumptions"][1]
        for scenario in payload["assumptions"]:
            for field in CORE_FIELDS:
                scenario[field] = deepcopy(reference[field])

    copied_draft = ValuationSnapshotDraftIn.model_validate(payload)
    result = _gate_results(db, case, copied_draft)["scenario_distinctness"]

    assert result.passed is False
    assert result.reason
