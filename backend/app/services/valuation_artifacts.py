"""Verification and immutable save boundary for valuation snapshots.

VISION V4/V5: the drafter owns company-specific assumptions and
probabilities; the backend computes structural gates; the strict verifier is
adversarial and never rewrites the draft. Any computable check lives here or
in `valuation_gates`, never in agent self-reporting.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ValuationOverrideIn,
    ValuationSnapshotDraftIn,
    ValuationSnapshotSaveIn,
    ValuationSnapshotVerificationIn,
    ValuationVerifierResult,
)
from app.db.models import (
    AgentRun,
    ResearchCase,
    ResearchSnapshot,
    ValuationSnapshot,
    VerificationRun,
    utcnow,
)
from app.services.agent_queue import clear_agent_lease
from app.services.valuation_engine import (
    ValuationInputError,
    calculate_valuation,
    canonical_hash,
    prepare_valuation,
    probability_weighted,
    validate_assumption_bindings,
)
from app.services.valuation_gates import (
    evaluate_structural_gates,
    gate_report,
    gates_passed,
)
from app.services.valuation_templates import get_template

WORKFLOW = "stock-company-valuation"
SKILL_VERSION = "company-valuation-v2"
CONTRACT_VERSION = "valuation-snapshot-v2"
ENGINE_VERSION = "valuation-engine-v2"
TEMPLATE_CONTRACT_VERSION = "valuation-templates-v1"

# Frozen at queue time; the drafter may not change these.
FROZEN_BASE_FIELDS = (
    "research_snapshot_id",
    "template_id",
    "template_version",
    "base_values",
    "input_manifest",
    "input_fingerprint",
)


class ValuationArtifactError(ValueError):
    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def valuation_draft_fingerprint(draft: ValuationSnapshotDraftIn) -> str:
    return canonical_hash(draft.model_dump(mode="json"))


def _expected_input(agent: AgentRun) -> dict:
    value = (agent.inputs or {}).get("valuation")
    if not isinstance(value, dict):
        raise ValuationArtifactError("Valuation run has no frozen input bundle.", kind="conflict")
    return value


def _validate_run(
    db: Session, case: ResearchCase, draft: ValuationSnapshotDraftIn
) -> AgentRun:
    agent = db.get(AgentRun, draft.agent_run_id)
    if agent is None:
        raise ValuationArtifactError("Unknown agent run.", kind="not-found")
    task = (agent.inputs or {}).get("task") or {}
    if (
        agent.company_id != case.company_id
        or agent.workflow != WORKFLOW
        or agent.status != "running"
        or task.get("skill_version") != SKILL_VERSION
        or task.get("output_contract_version") != CONTRACT_VERSION
        or task.get("engine_version") != ENGINE_VERSION
        or task.get("template_contract_version") != TEMPLATE_CONTRACT_VERSION
    ):
        raise ValuationArtifactError(
            "Frozen job versions/status do not authorize this valuation.", kind="conflict"
        )
    if not agent.lease_owner or agent.lease_expires_at is None:
        raise ValuationArtifactError("Valuation requires an active claimed lease.", kind="conflict")
    if draft.lease_owner != agent.lease_owner:
        raise ValuationArtifactError("Draft lease owner does not own the run.", kind="conflict")
    if _aware(agent.lease_expires_at) <= utcnow():
        raise ValuationArtifactError("Valuation lease expired.", kind="conflict")
    return agent


def _validate_draft(
    db: Session, case: ResearchCase, draft: ValuationSnapshotDraftIn
) -> AgentRun:
    """Frozen-base equality + deterministic recomputation of drafter output."""
    agent = _validate_run(db, case, draft)
    frozen = _expected_input(agent)
    for key in FROZEN_BASE_FIELDS:
        if frozen.get(key) != getattr(draft, key):
            raise ValuationArtifactError(
                f"Draft field {key} differs from frozen job input.", kind="conflict"
            )
    if frozen.get("as_of") != draft.as_of.isoformat():
        raise ValuationArtifactError(
            "Draft field as_of differs from frozen job input.", kind="conflict"
        )
    snapshot = db.get(ResearchSnapshot, draft.research_snapshot_id)
    if snapshot is None or snapshot.research_case_id != case.id:
        raise ValuationArtifactError("Bound research snapshot is invalid.", kind="conflict")
    if draft.input_manifest.get("research_artifact_fingerprint") != snapshot.artifact_fingerprint:
        raise ValuationArtifactError("Research snapshot fingerprint is stale.", kind="conflict")
    profile_archetype = frozen.get("profile_archetype")
    template = get_template(profile_archetype)
    if (
        template is None
        or template.id != draft.template_id
        or template.version != draft.template_version
    ):
        raise ValuationArtifactError("Template is not bound to the research archetype.")
    try:
        validate_assumption_bindings(draft.assumptions, draft.input_manifest)
    except ValuationInputError as exc:
        raise ValuationArtifactError(str(exc), kind=exc.kind) from exc
    recomputed = calculate_valuation(draft.base_values, draft.assumptions)
    if recomputed != draft.deterministic_outputs:
        raise ValuationArtifactError("Deterministic valuation does not reconcile.", kind="conflict")
    if canonical_hash(recomputed) != draft.calculation_fingerprint:
        raise ValuationArtifactError("Calculation fingerprint does not reconcile.", kind="conflict")
    calculation_gaps = [
        f"{row['kind']}: {row['valuation_gap']}"
        for row in recomputed["scenarios"]
        if row.get("valuation_gap")
    ]
    expected_gaps = sorted(set(list(frozen.get("gaps") or []) + calculation_gaps))
    if sorted(set(draft.gaps)) != expected_gaps:
        raise ValuationArtifactError(
            "Draft gaps must equal frozen base gaps plus calculation gaps.", kind="conflict"
        )
    assumption_kinds = {row.kind for row in draft.assumptions}
    output_kinds = {row["kind"] for row in draft.deterministic_outputs.get("scenarios", [])}
    judgment_kinds = {row.kind for row in draft.codex_judgment.scenarios}
    if assumption_kinds != output_kinds or output_kinds != judgment_kinds:
        raise ValuationArtifactError(
            "Assumptions, deterministic outputs and Codex judgment must cover identical scenario kinds."
        )
    return agent


def _validate_version(db: Session, case: ResearchCase, draft) -> None:
    latest = db.scalar(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.research_case_id == case.id)
        .order_by(ValuationSnapshot.version.desc(), ValuationSnapshot.id.desc())
        .limit(1)
    )
    expected = (latest.version if latest else 0) + 1
    if draft.version != expected:
        raise ValuationArtifactError(
            f"Next valuation snapshot version must be {expected}.", kind="conflict"
        )
    if latest is not None and _aware(draft.as_of) < _aware(latest.as_of):
        raise ValuationArtifactError("Valuation history cannot move backwards.", kind="conflict")


def _final_status(result: ValuationVerifierResult, gaps: list[str]) -> str:
    if result.verdict == "pass":
        return "provisional" if gaps else "verified"
    if result.verdict == "fail":
        return "rejected"
    return "needs-human"


def structural_gate_report(db: Session, *, case_id: int, draft: ValuationSnapshotDraftIn) -> dict:
    """Zero-write dry run: the drafter's self-check before verification."""
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ValuationArtifactError("Unknown research case.", kind="not-found")
    _validate_draft(db, case, draft)
    return gate_report(evaluate_structural_gates(db, case, draft))


def verify_valuation_snapshot(
    db: Session, *, case_id: int, payload: ValuationSnapshotVerificationIn
) -> VerificationRun:
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ValuationArtifactError("Unknown research case.", kind="not-found")
    agent = _validate_draft(db, case, payload.draft)
    _validate_version(db, case, payload.draft)
    if payload.verifier_worker_id == agent.lease_owner:
        raise ValuationArtifactError("Drafting worker cannot verify its own valuation.", kind="conflict")
    gates = evaluate_structural_gates(db, case, payload.draft)
    report = gate_report(gates)
    failed_gates = [result for result in gates if not result.passed]
    effective_result = payload.verifier_result
    automatic_rejection_reasons: list[str] = []
    if failed_gates:
        automatic_rejection_reasons = [
            result.reason or result.gate for result in failed_gates
        ]
        generated_findings = [
            {
                "severity": "blocking",
                "area": f"structural_gate:{result.gate}",
                "detail": (
                    f"Backend structural gate rejected the valuation: "
                    f"{result.reason or result.gate}"
                ),
            }
            for result in failed_gates
        ]
        summary = (
            "Backend structural gates automatically rejected the draft: "
            + "; ".join(automatic_rejection_reasons)
            + f" Original verifier summary: {payload.verifier_result.summary}"
        )
        effective_result = ValuationVerifierResult.model_validate(
            {
                **payload.verifier_result.model_dump(mode="json"),
                "verdict": "fail",
                "findings": [
                    *[row.model_dump(mode="json") for row in payload.verifier_result.findings],
                    *generated_findings,
                ],
                "summary": summary[:4000],
            }
        )
    checks = {
        "structural_gates": report,
        "automatic_rejection_reasons": automatic_rejection_reasons,
        "requested_verdict": payload.verifier_result.verdict,
        "findings": [row.model_dump(mode="json") for row in effective_result.findings],
        "judgment_review": effective_result.judgment_review.model_dump(mode="json"),
        "verifier_worker_id": payload.verifier_worker_id,
        "valuation_draft_fingerprint": valuation_draft_fingerprint(payload.draft),
        "input_fingerprint": payload.draft.input_fingerprint,
        "calculation_fingerprint": payload.draft.calculation_fingerprint,
        "final_status": _final_status(effective_result, payload.draft.gaps),
    }
    verification = VerificationRun(
        agent_run_id=agent.id,
        model_role=effective_result.model_role,
        verifier_model=effective_result.verifier_model,
        verdict=effective_result.verdict,
        checks=checks,
        summary=effective_result.summary,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    return verification


def _verification_result(verification: VerificationRun) -> ValuationVerifierResult:
    checks = verification.checks or {}
    return ValuationVerifierResult.model_validate(
        {
            "model_role": verification.model_role,
            "verifier_model": verification.verifier_model,
            "verdict": verification.verdict,
            "findings": checks.get("findings") or [],
            "judgment_review": checks.get("judgment_review"),
            "summary": verification.summary,
        }
    )


def _draft_probabilities(draft: ValuationSnapshotDraftIn) -> list[dict]:
    return [
        {
            "kind": row.kind,
            "probability_pct": row.probability_pct,
            "rationale": row.probability_rationale,
        }
        for row in draft.codex_judgment.scenarios
    ]


def save_valuation_snapshot(
    db: Session, *, case_id: int, payload: ValuationSnapshotSaveIn
) -> ValuationSnapshot:
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ValuationArtifactError("Unknown research case.", kind="not-found")
    draft = ValuationSnapshotDraftIn.model_validate(
        payload.model_dump(exclude={"verification_run_id"})
    )
    agent = db.get(AgentRun, draft.agent_run_id)
    if agent is None:
        raise ValuationArtifactError("Unknown agent run.", kind="not-found")
    verification = db.get(VerificationRun, payload.verification_run_id)
    if verification is None:
        raise ValuationArtifactError("Unknown verification run.", kind="not-found")
    result = _verification_result(verification)
    checks = verification.checks or {}
    if (
        verification.agent_run_id != agent.id
        or verification.analysis_run_id is not None
        or verification.model_role != "verifier_strict"
        or checks.get("verifier_worker_id") in {None, agent.lease_owner}
        or checks.get("valuation_draft_fingerprint") != valuation_draft_fingerprint(draft)
        or checks.get("input_fingerprint") != draft.input_fingerprint
        or checks.get("calculation_fingerprint") != draft.calculation_fingerprint
    ):
        raise ValuationArtifactError(
            "Verification is not an independent verdict for this exact valuation.",
            kind="conflict",
        )
    existing = db.scalar(
        select(ValuationSnapshot).where(ValuationSnapshot.agent_run_id == agent.id)
    )
    probabilities = _draft_probabilities(draft)
    weighted = probability_weighted(draft.deterministic_outputs, probabilities)
    final_outputs = {
        **draft.deterministic_outputs,
        "probability_weighted": weighted,
        "final_probabilities": probabilities,
    }
    final_status = _final_status(result, draft.gaps)
    artifact_fingerprint = canonical_hash(
        {
            "draft": draft.model_dump(mode="json"),
            "verification_run_id": verification.id,
            "final_outputs": final_outputs,
        }
    )
    if existing is not None:
        if existing.artifact_fingerprint == artifact_fingerprint:
            return existing
        raise ValuationArtifactError("Agent run already saved another valuation.", kind="conflict")
    _validate_draft(db, case, draft)
    _validate_version(db, case, draft)
    if checks.get("final_status") != final_status:
        raise ValuationArtifactError("Verifier final status is inconsistent.", kind="conflict")
    gate_state = checks.get("structural_gates") or {}
    if final_status in {"verified", "provisional"} and not gate_state.get("passed"):
        raise ValuationArtifactError(
            "A passing valuation cannot save with failing structural gates.", kind="conflict"
        )
    snapshot = ValuationSnapshot(
        research_case_id=case.id,
        research_snapshot_id=draft.research_snapshot_id,
        agent_run_id=agent.id,
        verification_run_id=verification.id,
        version=draft.version,
        contract_version=draft.contract_version,
        status=final_status,
        origin="codex",
        as_of=draft.as_of,
        template_id=draft.template_id,
        template_version=draft.template_version,
        calculation_engine_version=draft.engine_version,
        assumptions={"scenarios": [row.model_dump(mode="json") for row in draft.assumptions]},
        base_values=draft.base_values,
        deterministic_outputs=final_outputs,
        codex_judgment=draft.codex_judgment.model_dump(mode="json"),
        input_manifest=draft.input_manifest,
        gaps=draft.gaps,
        input_fingerprint=draft.input_fingerprint,
        calculation_fingerprint=draft.calculation_fingerprint,
        artifact_fingerprint=artifact_fingerprint,
        verifier_result={
            **result.model_dump(mode="json"),
            "structural_gates": gate_state,
        },
    )
    db.add(snapshot)
    db.flush()
    now = utcnow()
    agent.status = final_status
    agent.outputs = {
        "valuation_snapshot_id": snapshot.id,
        "verification_run_id": verification.id,
        "input_fingerprint": draft.input_fingerprint,
        "calculation_fingerprint": draft.calculation_fingerprint,
    }
    agent.finished_at = now
    agent.updated_at = now
    agent.error = result.summary if final_status in {"rejected", "needs-human"} else None
    clear_agent_lease(agent)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = db.scalar(
            select(ValuationSnapshot).where(ValuationSnapshot.agent_run_id == agent.id)
        )
        if raced is not None and raced.artifact_fingerprint == artifact_fingerprint:
            return raced
        raise ValuationArtifactError("Valuation version already exists.", kind="conflict") from exc
    db.refresh(snapshot)
    return snapshot


def save_valuation_override(
    db: Session, *, case_id: int, payload: ValuationOverrideIn
) -> ValuationSnapshot:
    """Explicit human correction: deterministic recompute, provisional version.

    The user owns assumptions here; no verifier or agent run is involved and
    the snapshot is labelled `human-override` so it never masquerades as a
    verified Codex artifact. Draft lineage of prior versions is untouched.
    """
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ValuationArtifactError("Unknown research case.", kind="not-found")
    try:
        prepared = prepare_valuation(db, case=case, request=payload)
    except ValuationInputError as exc:
        raise ValuationArtifactError(str(exc), kind=exc.kind) from exc
    latest = db.scalar(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.research_case_id == case.id)
        .order_by(ValuationSnapshot.version.desc(), ValuationSnapshot.id.desc())
        .limit(1)
    )
    version = (latest.version if latest else 0) + 1
    if latest is not None and _aware(payload.as_of) < _aware(latest.as_of):
        raise ValuationArtifactError("Valuation history cannot move backwards.", kind="conflict")
    judgment = {
        "strategy_read": f"Korekta użytkownika: {payload.note}",
        "scenarios": [],
        "catalysts": [],
        "falsifiers": [],
    }
    outputs = {
        **prepared["deterministic_outputs"],
        "probability_weighted": None,
        "final_probabilities": [],
    }
    snapshot = ValuationSnapshot(
        research_case_id=case.id,
        research_snapshot_id=payload.research_snapshot_id,
        agent_run_id=None,
        verification_run_id=None,
        version=version,
        contract_version=CONTRACT_VERSION,
        status="provisional",
        origin="human-override",
        as_of=payload.as_of,
        template_id=prepared["template"].id,
        template_version=prepared["template"].version,
        calculation_engine_version=ENGINE_VERSION,
        assumptions={
            "scenarios": [row.model_dump(mode="json") for row in payload.assumptions]
        },
        base_values=prepared["base_values"],
        deterministic_outputs=outputs,
        codex_judgment=judgment,
        input_manifest=prepared["input_manifest"],
        gaps=sorted(set(prepared["gaps"] + ["Korekta użytkownika bez probabilistyki i weryfikacji."])),
        input_fingerprint=prepared["input_fingerprint"],
        calculation_fingerprint=prepared["calculation_fingerprint"],
        artifact_fingerprint=canonical_hash(
            {
                "origin": "human-override",
                "assumptions": [row.model_dump(mode="json") for row in payload.assumptions],
                "outputs": outputs,
                "note": payload.note,
                "version": version,
            }
        ),
        verifier_result={"origin": "human-override", "note": payload.note},
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
