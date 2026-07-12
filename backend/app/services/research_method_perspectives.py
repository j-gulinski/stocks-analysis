"""Strict persistence for immutable method lenses over Research snapshots.

This boundary never refreshes evidence or changes a canonical ResearchSnapshot.
It only accepts a claimed, snapshot-bound method perspective and an independent
verifier verdict for the exact submitted draft.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ResearchMethodPerspectiveDraftIn,
    ResearchMethodPerspectiveSaveIn,
    ResearchMethodPerspectiveVerificationIn,
    ResearchMethodPerspectiveVerifierResult,
)
from app.db.models import (
    AgentRun,
    CompanyProfile,
    ResearchCase,
    ResearchMethodPerspective,
    ResearchSnapshot,
    VerificationRun,
    utcnow,
)
from app.services.agent_queue import clear_agent_lease
from app.services.company_profiles import frozen_profile
from app.services.research_method_catalog import canonical_manifest_fingerprint


WORKFLOW = "stock-research-method-perspective"
SKILL = "research-method-perspective"
SKILL_VERSION = "research-method-perspective-v1"
CONTRACT_VERSION = "research-method-perspective-v1"


class ResearchMethodPerspectiveError(ValueError):
    """A perspective draft cannot cross its immutable persistence boundary."""

    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def research_method_perspective_draft_fingerprint(
    payload: ResearchMethodPerspectiveDraftIn,
) -> str:
    return _canonical_hash(payload.model_dump(mode="json"))


def frozen_research_snapshot_bundle(
    db: Session, snapshot: ResearchSnapshot
) -> dict:
    """Freeze every parent field a worker may interpret without duplicating truth."""
    profile = db.get(CompanyProfile, snapshot.company_profile_id)
    if profile is None:
        raise ResearchMethodPerspectiveError(
            "The parent Research snapshot profile is missing.", kind="conflict"
        )
    return {
        "snapshot": {
            "id": snapshot.id,
            "research_case_id": snapshot.research_case_id,
            "company_profile_id": snapshot.company_profile_id,
            "version": snapshot.version,
            "contract_version": snapshot.contract_version,
            "status": snapshot.status,
            "as_of": _aware(snapshot.as_of).isoformat(),
            "input_fingerprint": snapshot.input_fingerprint,
            "artifact_fingerprint": snapshot.artifact_fingerprint,
            "sections": snapshot.sections,
            "source_manifest": snapshot.source_manifest,
            "conflicts": snapshot.conflicts,
            "gaps": snapshot.gaps,
            "next_checks": snapshot.next_checks,
            "statement_provenance": snapshot.statement_provenance,
            "verifier_result": snapshot.verifier_result,
        },
        "company_profile": frozen_profile(profile),
    }


def _final_status(
    result: ResearchMethodPerspectiveVerifierResult, gaps: list
) -> str:
    checks_pass = all(result.checks.model_dump().values())
    if result.verdict == "pass":
        if not checks_pass:
            raise ResearchMethodPerspectiveError(
                "A passing verifier verdict requires every integrity check."
            )
        return "provisional" if gaps else "verified"
    if result.verdict == "fail":
        return "rejected"
    if result.verdict == "needs-human":
        return "needs-human"
    raise ResearchMethodPerspectiveError("Unsupported verifier verdict.")


def _context(agent: AgentRun) -> dict:
    value = (agent.inputs or {}).get("method_perspective")
    if not isinstance(value, dict):
        raise ResearchMethodPerspectiveError(
            "Agent run has no frozen method-perspective context.", kind="conflict"
        )
    return value


def _validate_run(
    db: Session,
    case: ResearchCase,
    payload: ResearchMethodPerspectiveDraftIn,
) -> tuple[AgentRun, ResearchSnapshot, dict]:
    agent = db.get(AgentRun, payload.agent_run_id)
    if agent is None:
        raise ResearchMethodPerspectiveError(
            f"Unknown agent run {payload.agent_run_id}.", kind="not-found"
        )
    if agent.status != "running" or agent.workflow != WORKFLOW:
        raise ResearchMethodPerspectiveError(
            "Method perspective requires its running workflow row.", kind="conflict"
        )
    if agent.company_id != case.company_id:
        raise ResearchMethodPerspectiveError(
            "Method perspective company does not match the Research case.", kind="conflict"
        )
    if not agent.lease_owner or agent.lease_expires_at is None:
        raise ResearchMethodPerspectiveError(
            "Method perspective requires an active claimed lease.", kind="conflict"
        )
    if payload.lease_owner != agent.lease_owner:
        raise ResearchMethodPerspectiveError(
            "Payload lease owner does not own the claimed run.", kind="conflict"
        )
    if _aware(agent.lease_expires_at) <= utcnow():
        raise ResearchMethodPerspectiveError(
            "The agent-run lease expired before perspective processing.", kind="conflict"
        )
    inputs = agent.inputs or {}
    task = inputs.get("task") if isinstance(inputs.get("task"), dict) else {}
    if (
        inputs.get("research_case_id") != case.id
        or task.get("skill") != SKILL
        or task.get("skill_version") != SKILL_VERSION
        or task.get("output_contract_version") != CONTRACT_VERSION
        or task.get("required_verification") != "verifier_strict"
    ):
        raise ResearchMethodPerspectiveError(
            "Frozen job skill/version/output contract does not authorize this perspective.",
            kind="conflict",
        )
    context = _context(agent)
    bundle = context.get("research_snapshot")
    manifest = context.get("method_manifest")
    manifest_fingerprint = context.get("method_manifest_fingerprint")
    if not isinstance(bundle, dict) or not isinstance(manifest, dict):
        raise ResearchMethodPerspectiveError(
            "Frozen parent snapshot or method manifest is invalid.", kind="conflict"
        )
    if not isinstance(manifest_fingerprint, str) or (
        canonical_manifest_fingerprint(manifest) != manifest_fingerprint
    ):
        raise ResearchMethodPerspectiveError(
            "Frozen method manifest fingerprint is invalid.", kind="conflict"
        )
    snapshot_data = bundle.get("snapshot")
    if not isinstance(snapshot_data, dict):
        raise ResearchMethodPerspectiveError(
            "Frozen parent snapshot payload is invalid.", kind="conflict"
        )
    snapshot_id = snapshot_data.get("id")
    snapshot = db.get(ResearchSnapshot, snapshot_id) if isinstance(snapshot_id, int) else None
    if snapshot is None or snapshot.research_case_id != case.id:
        raise ResearchMethodPerspectiveError(
            "Frozen parent Research snapshot is missing or belongs to another case.",
            kind="conflict",
        )
    if frozen_research_snapshot_bundle(db, snapshot) != bundle:
        raise ResearchMethodPerspectiveError(
            "Frozen parent Research snapshot drifted.", kind="conflict"
        )
    if snapshot.status not in {"provisional", "verified"}:
        raise ResearchMethodPerspectiveError(
            "A method perspective requires a provisional or verified Research snapshot.",
            kind="conflict",
        )
    if (
        payload.contract_version != CONTRACT_VERSION
        or payload.research_snapshot_id != snapshot.id
        or payload.method_pack_id != manifest.get("id")
        or payload.method_pack_version != manifest.get("version")
        or payload.method_manifest != manifest
        or payload.method_manifest_fingerprint != manifest_fingerprint
        or _aware(payload.as_of) != _aware(snapshot.as_of)
    ):
        raise ResearchMethodPerspectiveError(
            "Draft does not match its frozen snapshot or method manifest.", kind="conflict"
        )
    if manifest.get("research_stage", {}).get("status") != "supported":
        raise ResearchMethodPerspectiveError(
            "Only a supported Research method pack may persist a perspective.",
            kind="conflict",
        )
    return agent, snapshot, context


def _source_ids(payload: ResearchMethodPerspectiveDraftIn) -> set[int]:
    values = set(payload.applicability.reason.source_document_version_ids)
    if payload.conclusion is not None:
        values.update(payload.conclusion.source_document_version_ids)
    for finding in payload.findings:
        values.update(finding.claim.source_document_version_ids)
    for falsifier in payload.falsifiers:
        values.update(falsifier.source_document_version_ids)
    return values


def _validate_draft(
    snapshot: ResearchSnapshot, payload: ResearchMethodPerspectiveDraftIn
) -> None:
    manifest_checks = payload.method_manifest.get("required_checks")
    if not isinstance(manifest_checks, list) or not manifest_checks:
        raise ResearchMethodPerspectiveError("Method manifest has no required checks.")
    expected = [item.get("id") for item in manifest_checks if isinstance(item, dict)]
    supplied = [item.required_check_id for item in payload.findings]
    if len(expected) != len(manifest_checks) or not all(isinstance(item, str) for item in expected):
        raise ResearchMethodPerspectiveError("Method manifest required checks are invalid.")
    if len(supplied) != len(set(supplied)) or set(supplied) != set(expected):
        raise ResearchMethodPerspectiveError(
            "Findings must classify every frozen required method check exactly once."
        )
    if payload.applicability.status == "applicable":
        if any(item.status == "not-applicable" for item in payload.findings):
            raise ResearchMethodPerspectiveError(
                "Applicable methods cannot mark an individual required check not-applicable."
            )
    elif any(item.status != "not-applicable" for item in payload.findings):
        raise ResearchMethodPerspectiveError(
            "A not-applicable method must mark every required check not-applicable."
        )
    source_manifest_roles = {
        item.get("document_version_id"): item.get("role")
        for item in snapshot.source_manifest
        if isinstance(item, dict) and isinstance(item.get("document_version_id"), int)
    }
    if not source_manifest_roles:
        raise ResearchMethodPerspectiveError(
            "Parent Research snapshot has no frozen source manifest.", kind="conflict"
        )
    outside = _source_ids(payload) - set(source_manifest_roles)
    if outside:
        raise ResearchMethodPerspectiveError(
            "Perspective references document versions outside its parent snapshot: "
            f"{sorted(outside)}."
        )
    authoritative_roles = {"primary", "normalized", "context"}
    for item in payload.findings:
        if item.status == "unknown" and item.claim.kind != "unknown":
            raise ResearchMethodPerspectiveError(
                "Unknown findings require an explicit unknown claim."
            )
        if item.status == "not-applicable" and item.claim.kind not in {"unknown", "fact"}:
            raise ResearchMethodPerspectiveError(
                "Not-applicable findings require an unknown or sourced factual basis."
            )
        if item.status in {"supports", "contradicts"}:
            if item.claim.kind not in {"fact", "calculation"}:
                raise ResearchMethodPerspectiveError(
                    "Supports and contradicts findings require factual or calculation claims."
                )
            if not item.claim.source_document_version_ids or not any(
                source_manifest_roles.get(source_id) in authoritative_roles
                for source_id in item.claim.source_document_version_ids
            ):
                raise ResearchMethodPerspectiveError(
                    "Supports and contradicts findings require a non-lead parent source id."
                )
    if payload.conclusion is not None and payload.conclusion.kind in {"fact", "calculation"}:
        if not payload.conclusion.source_document_version_ids or not any(
            source_manifest_roles.get(source_id) in authoritative_roles
            for source_id in payload.conclusion.source_document_version_ids
        ):
            raise ResearchMethodPerspectiveError(
                "Method conclusions require a non-lead parent source id or an explicit unknown."
            )
    required_blind_spots = payload.method_manifest.get("blind_spots")
    if not isinstance(required_blind_spots, list) or not set(required_blind_spots).issubset(
        set(payload.blind_spots)
    ):
        raise ResearchMethodPerspectiveError(
            "Perspective must retain every frozen method blind spot."
        )


def _input_fingerprint(agent: AgentRun, payload: ResearchMethodPerspectiveDraftIn) -> str:
    return _canonical_hash(
        {
            "agent_run_id": agent.id,
            "company_id": agent.company_id,
            "workflow": agent.workflow,
            "trigger": agent.trigger,
            "inputs": agent.inputs or {},
            "research_snapshot_id": payload.research_snapshot_id,
            "method_manifest_fingerprint": payload.method_manifest_fingerprint,
        }
    )


def _artifact_fingerprint(
    payload: ResearchMethodPerspectiveDraftIn, verification: VerificationRun
) -> str:
    return _canonical_hash(
        {
            "draft_fingerprint": research_method_perspective_draft_fingerprint(payload),
            "verification_run_id": verification.id,
            "verifier_model": verification.verifier_model,
            "verdict": verification.verdict,
            "checks": verification.checks,
            "summary": verification.summary,
        }
    )


def verify_research_method_perspective(
    db: Session,
    *,
    case_id: int,
    payload: ResearchMethodPerspectiveVerificationIn,
) -> VerificationRun:
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ResearchMethodPerspectiveError(
            f"Unknown research case {case_id}.", kind="not-found"
        )
    agent, snapshot, _ = _validate_run(db, case, payload.draft)
    if payload.verifier_worker_id == agent.lease_owner:
        raise ResearchMethodPerspectiveError(
            "The drafting worker cannot verify its own method perspective.", kind="conflict"
        )
    _validate_draft(snapshot, payload.draft)
    final_status = _final_status(payload.verifier_result, payload.draft.gaps)
    checks = {
        **payload.verifier_result.checks.model_dump(mode="json"),
        "verifier_worker_id": payload.verifier_worker_id,
        "research_case_id": case.id,
        "perspective_draft_fingerprint": research_method_perspective_draft_fingerprint(
            payload.draft
        ),
        "input_fingerprint": _input_fingerprint(agent, payload.draft),
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


def _verification_result(
    verification: VerificationRun,
) -> ResearchMethodPerspectiveVerifierResult:
    checks = verification.checks or {}
    return ResearchMethodPerspectiveVerifierResult.model_validate(
        {
            "model_role": verification.model_role,
            "verifier_model": verification.verifier_model,
            "verdict": verification.verdict,
            "checks": {
                key: checks.get(key)
                for key in (
                    "schema_integrity",
                    "source_integrity",
                    "snapshot_binding",
                    "method_manifest_integrity",
                    "attribution",
                    "non_impersonation",
                    "applicability",
                    "unknown_handling",
                    "no_hidden_blend",
                    "look_ahead",
                )
            },
            "summary": verification.summary,
        }
    )


def _validated_verification(
    db: Session,
    agent: AgentRun,
    payload: ResearchMethodPerspectiveSaveIn,
    draft: ResearchMethodPerspectiveDraftIn,
) -> tuple[VerificationRun, ResearchMethodPerspectiveVerifierResult]:
    verification = db.get(VerificationRun, payload.verification_run_id)
    if verification is None:
        raise ResearchMethodPerspectiveError(
            f"Unknown verification run {payload.verification_run_id}.", kind="not-found"
        )
    checks = verification.checks or {}
    if (
        verification.agent_run_id != agent.id
        or verification.analysis_run_id is not None
        or verification.model_role != "verifier_strict"
        or checks.get("verifier_worker_id") in {None, agent.lease_owner}
        or checks.get("perspective_draft_fingerprint")
        != research_method_perspective_draft_fingerprint(draft)
        or checks.get("input_fingerprint") != _input_fingerprint(agent, draft)
    ):
        raise ResearchMethodPerspectiveError(
            "Verification row is not an independent verdict for this exact perspective draft.",
            kind="conflict",
        )
    result = _verification_result(verification)
    final_status = _final_status(result, payload.gaps)
    if checks.get("final_status") != final_status:
        raise ResearchMethodPerspectiveError(
            "Verification final status does not match its verdict and perspective gaps.",
            kind="conflict",
        )
    return verification, result


def save_research_method_perspective(
    db: Session,
    *,
    case_id: int,
    payload: ResearchMethodPerspectiveSaveIn,
) -> ResearchMethodPerspective:
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ResearchMethodPerspectiveError(
            f"Unknown research case {case_id}.", kind="not-found"
        )
    draft = ResearchMethodPerspectiveDraftIn.model_validate(
        payload.model_dump(exclude={"verification_run_id"})
    )
    verification = db.get(VerificationRun, payload.verification_run_id)
    if verification is None:
        raise ResearchMethodPerspectiveError(
            f"Unknown verification run {payload.verification_run_id}.", kind="not-found"
        )
    artifact_fingerprint = _artifact_fingerprint(draft, verification)
    existing = db.scalar(
        select(ResearchMethodPerspective).where(
            ResearchMethodPerspective.agent_run_id == payload.agent_run_id
        )
    )
    if existing is not None:
        if (
            existing.research_case_id == case_id
            and existing.artifact_fingerprint == artifact_fingerprint
        ):
            return existing
        raise ResearchMethodPerspectiveError(
            "This agent run already created a different immutable method perspective.",
            kind="conflict",
        )

    agent, snapshot, _ = _validate_run(db, case, draft)
    _validate_draft(snapshot, draft)
    verification, verifier_result = _validated_verification(db, agent, payload, draft)
    final_status = (verification.checks or {})["final_status"]
    perspective = ResearchMethodPerspective(
        research_case_id=case.id,
        research_snapshot_id=snapshot.id,
        agent_run_id=agent.id,
        verification_run_id=verification.id,
        method_pack_id=draft.method_pack_id,
        method_pack_version=draft.method_pack_version,
        contract_version=draft.contract_version,
        status=final_status,
        as_of=draft.as_of,
        method_manifest=draft.method_manifest,
        method_manifest_fingerprint=draft.method_manifest_fingerprint,
        applicability=draft.applicability.model_dump(mode="json"),
        conclusion=(draft.conclusion.model_dump(mode="json") if draft.conclusion else None),
        findings=[item.model_dump(mode="json") for item in draft.findings],
        blind_spots=draft.blind_spots,
        falsifiers=[item.model_dump(mode="json") for item in draft.falsifiers],
        next_checks=[item.model_dump(mode="json") for item in draft.next_checks],
        gaps=[item.model_dump(mode="json") for item in draft.gaps],
        input_fingerprint=_input_fingerprint(agent, draft),
        artifact_fingerprint=artifact_fingerprint,
        verifier_result=verifier_result.model_dump(mode="json"),
    )
    db.add(perspective)
    db.flush()
    now = utcnow()
    agent.status = final_status
    agent.outputs = {
        **(agent.outputs or {}),
        "research_case_id": case.id,
        "research_snapshot_id": snapshot.id,
        "research_method_perspective_id": perspective.id,
        "verification_run_id": verification.id,
        "output_contract_version": draft.contract_version,
        "input_fingerprint": perspective.input_fingerprint,
    }
    agent.error = verifier_result.summary if final_status in {"rejected", "needs-human"} else None
    agent.finished_at = now
    agent.updated_at = now
    clear_agent_lease(agent)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = db.scalar(
            select(ResearchMethodPerspective).where(
                ResearchMethodPerspective.agent_run_id == payload.agent_run_id
            )
        )
        if raced is not None and raced.artifact_fingerprint == artifact_fingerprint:
            return raced
        raise ResearchMethodPerspectiveError(
            "Method perspective already exists and is immutable.", kind="conflict"
        ) from exc
    db.refresh(perspective)
    return perspective
