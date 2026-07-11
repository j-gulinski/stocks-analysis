"""Exact verification and immutable save boundary for valuation snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
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
    calculate_valuation,
    canonical_hash,
    probability_weighted,
)
from app.services.valuation_method_packs import get_method_pack
from app.services.valuation_templates import get_template

WORKFLOW = "stock-company-valuation"
SKILL_VERSION = "company-valuation-v1"
CONTRACT_VERSION = "valuation-snapshot-v1"
ENGINE_VERSION = "valuation-engine-v2"
TEMPLATE_CONTRACT_VERSION = "valuation-templates-v1"


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


def _validate_exact_draft(
    db: Session, case: ResearchCase, draft: ValuationSnapshotDraftIn
) -> AgentRun:
    agent = _validate_run(db, case, draft)
    frozen = _expected_input(agent)
    exact_fields = {
        "research_snapshot_id": draft.research_snapshot_id,
        "as_of": draft.as_of.isoformat(),
        "method_pack_id": draft.method_pack_id,
        "method_pack_version": draft.method_pack_version,
        "template_id": draft.template_id,
        "template_version": draft.template_version,
        "assumptions": [row.model_dump(mode="json") for row in draft.assumptions],
        "base_values": draft.base_values,
        "deterministic_outputs": draft.deterministic_outputs,
        "input_manifest": draft.input_manifest,
        "gaps": draft.gaps,
        "input_fingerprint": draft.input_fingerprint,
        "calculation_fingerprint": draft.calculation_fingerprint,
    }
    for key, value in exact_fields.items():
        if frozen.get(key) != value:
            raise ValuationArtifactError(
                f"Draft field {key} differs from frozen job input.", kind="conflict"
            )
    snapshot = db.get(ResearchSnapshot, draft.research_snapshot_id)
    if snapshot is None or snapshot.research_case_id != case.id:
        raise ValuationArtifactError("Bound research snapshot is invalid.", kind="conflict")
    if draft.input_manifest.get("research_artifact_fingerprint") != snapshot.artifact_fingerprint:
        raise ValuationArtifactError("Research snapshot fingerprint is stale.", kind="conflict")
    method = get_method_pack(draft.method_pack_id)
    if method is None or method.status != "ready" or method.version != draft.method_pack_version:
        raise ValuationArtifactError("Method pack is unavailable or version-mismatched.")
    profile_archetype = frozen.get("profile_archetype")
    template = get_template(profile_archetype)
    if (
        template is None
        or template.id != draft.template_id
        or template.version != draft.template_version
    ):
        raise ValuationArtifactError("Template is not bound to the research archetype.")
    recomputed = calculate_valuation(draft.base_values, draft.assumptions)
    if recomputed != draft.deterministic_outputs:
        raise ValuationArtifactError("Deterministic valuation does not reconcile.", kind="conflict")
    if canonical_hash(recomputed) != draft.calculation_fingerprint:
        raise ValuationArtifactError("Calculation fingerprint does not reconcile.", kind="conflict")
    assumption_kinds = {row.kind for row in draft.assumptions}
    output_kinds = {row["kind"] for row in draft.deterministic_outputs.get("scenarios", [])}
    judgment_kinds = {row.kind for row in draft.codex_judgment.scenarios}
    if assumption_kinds != output_kinds or output_kinds != judgment_kinds:
        raise ValuationArtifactError(
            "Assumptions, deterministic outputs and Codex judgment must cover identical scenario kinds."
        )
    return agent


def _validate_version(db: Session, case: ResearchCase, draft: ValuationSnapshotDraftIn) -> None:
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
    checks_pass = all(result.checks.model_dump().values())
    if result.verdict == "pass":
        if not checks_pass:
            raise ValuationArtifactError("A passing verdict requires every strict check.")
        return "provisional" if gaps else "verified"
    if result.verdict == "fail":
        return "rejected"
    return "needs-human"


def verify_valuation_snapshot(
    db: Session, *, case_id: int, payload: ValuationSnapshotVerificationIn
) -> VerificationRun:
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ValuationArtifactError("Unknown research case.", kind="not-found")
    agent = _validate_exact_draft(db, case, payload.draft)
    _validate_version(db, case, payload.draft)
    if payload.verifier_worker_id == agent.lease_owner:
        raise ValuationArtifactError("Drafting worker cannot verify its own valuation.", kind="conflict")
    deterministic_kinds = {
        row["kind"] for row in payload.draft.deterministic_outputs.get("scenarios", [])
    }
    probability_kinds = {row.kind for row in payload.verifier_result.final_probabilities}
    judgment_kinds = {row.kind for row in payload.draft.codex_judgment.scenarios}
    if deterministic_kinds != judgment_kinds:
        raise ValuationArtifactError("Codex judgment must cover exactly the calculated scenarios.")
    if payload.verifier_result.verdict == "pass" and deterministic_kinds != probability_kinds:
        raise ValuationArtifactError("Final probabilities must cover exactly the calculated scenarios.")
    final_status = _final_status(payload.verifier_result, payload.draft.gaps)
    checks = {
        **payload.verifier_result.checks.model_dump(mode="json"),
        "verifier_worker_id": payload.verifier_worker_id,
        "valuation_draft_fingerprint": valuation_draft_fingerprint(payload.draft),
        "input_fingerprint": payload.draft.input_fingerprint,
        "calculation_fingerprint": payload.draft.calculation_fingerprint,
        "final_probabilities": [
            row.model_dump(mode="json")
            for row in payload.verifier_result.final_probabilities
        ],
        "final_status": final_status,
    }
    verification = VerificationRun(
        agent_run_id=agent.id,
        model_role=payload.verifier_result.model_role,
        verifier_model=payload.verifier_result.verifier_model,
        verdict=payload.verifier_result.verdict,
        checks=checks,
        summary=payload.verifier_result.summary,
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
            "checks": {
                key: checks.get(key)
                for key in (
                    "schema_integrity", "source_integrity", "company_identity",
                    "look_ahead", "math_integrity", "probability_coherence",
                    "method_integrity",
                )
            },
            "final_probabilities": checks.get("final_probabilities"),
            "summary": verification.summary,
        }
    )


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
    probabilities = [row.model_dump(mode="json") for row in result.final_probabilities]
    weighted = (
        probability_weighted(draft.deterministic_outputs, probabilities)
        if probabilities
        else None
    )
    final_outputs = {
        **draft.deterministic_outputs,
        "probability_weighted": weighted,
        "final_probabilities": probabilities,
    }
    final_status = _final_status(result, draft.gaps)
    codex_judgment = {
        **draft.codex_judgment.model_dump(mode="json"),
        "final_probabilities": probabilities,
    }
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
    _validate_exact_draft(db, case, draft)
    _validate_version(db, case, draft)
    if checks.get("final_status") != final_status:
        raise ValuationArtifactError("Verifier final status is inconsistent.", kind="conflict")
    snapshot = ValuationSnapshot(
        research_case_id=case.id,
        research_snapshot_id=draft.research_snapshot_id,
        agent_run_id=agent.id,
        verification_run_id=verification.id,
        version=draft.version,
        contract_version=draft.contract_version,
        status=final_status,
        as_of=draft.as_of,
        method_pack_id=draft.method_pack_id,
        method_pack_version=draft.method_pack_version,
        template_id=draft.template_id,
        template_version=draft.template_version,
        calculation_engine_version=draft.engine_version,
        assumptions={"scenarios": [row.model_dump(mode="json") for row in draft.assumptions]},
        base_values=draft.base_values,
        deterministic_outputs=final_outputs,
        codex_judgment=codex_judgment,
        input_manifest=draft.input_manifest,
        gaps=draft.gaps,
        input_fingerprint=draft.input_fingerprint,
        calculation_fingerprint=draft.calculation_fingerprint,
        artifact_fingerprint=artifact_fingerprint,
        verifier_result=result.model_dump(mode="json"),
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
