"""Valuation API: preview, queue (Codex-drafted), gates, verify, save, override.

VISION V4: queueing freezes only the deterministic base — the Codex drafter
owns company-specific assumptions and probabilities. The user can preview any
grid deterministically and save an explicit human override version.
"""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ValuationHistoryOut,
    ValuationOverrideIn,
    ValuationPreviewOut,
    ValuationQueueIn,
    ValuationQueueOut,
    ValuationRequestIn,
    ValuationSnapshotDraftIn,
    ValuationSnapshotOut,
    ValuationSnapshotSaveIn,
    ValuationSnapshotVerificationIn,
    ValuationWorkspaceOut,
)
from app.db.base import get_db
from app.db.models import (
    AgentRun,
    CompanyProfile,
    ResearchCase,
    ResearchSnapshot,
    ValuationSnapshot,
    utcnow,
)
from app.services.model_policy import default_model_for_workflow
from app.services.valuation_artifacts import (
    CONTRACT_VERSION,
    SKILL_VERSION,
    ValuationArtifactError,
    save_valuation_override,
    save_valuation_snapshot,
    structural_gate_report,
    verify_valuation_snapshot,
)
from app.services.valuation_engine import (
    ENGINE_VERSION,
    TEMPLATE_CONTRACT_VERSION,
    ValuationInputError,
    prepare_valuation,
    prepare_valuation_base,
)
from app.services.valuation_templates import get_template

router = APIRouter(tags=["valuations"])
WORKFLOW = "stock-company-valuation"


def _case(db: Session, case_id: int) -> ResearchCase:
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Research case not found.")
    return case


def _case_for_update(db: Session, case_id: int) -> ResearchCase:
    case = db.scalar(
        select(ResearchCase).where(ResearchCase.id == case_id).with_for_update()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Research case not found.")
    return case


def _raise_input(exc: ValuationInputError | ValuationArtifactError) -> None:
    code = {
        "not-found": status.HTTP_404_NOT_FOUND,
        "conflict": status.HTTP_409_CONFLICT,
        "gates": status.HTTP_422_UNPROCESSABLE_CONTENT,
    }.get(exc.kind, status.HTTP_422_UNPROCESSABLE_CONTENT)
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _latest_research(db: Session, case_id: int) -> ResearchSnapshot | None:
    return db.scalar(
        select(ResearchSnapshot)
        .where(ResearchSnapshot.research_case_id == case_id)
        .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        .limit(1)
    )


@router.get(
    "/research-cases/{case_id}/valuation-workspace",
    response_model=ValuationWorkspaceOut,
)
def valuation_workspace(case_id: int, db: Session = Depends(get_db)) -> dict:
    case = _case(db, case_id)
    research = _latest_research(db, case.id)
    profile = db.get(CompanyProfile, research.company_profile_id) if research else None
    template = get_template(profile.archetype) if profile else None
    rows = list(
        db.scalars(
            select(ValuationSnapshot)
            .where(ValuationSnapshot.research_case_id == case.id)
            .order_by(ValuationSnapshot.version.desc(), ValuationSnapshot.id.desc())
        ).all()
    )
    return {
        "research_case_id": case.id,
        "latest_research_snapshot_id": research.id if research else None,
        "template": template.to_dict() if template else None,
        "latest_valuation": rows[0] if rows else None,
        "history": [
            {
                "id": row.id,
                "version": row.version,
                "status": row.status,
                "origin": row.origin,
                "as_of": row.as_of,
                "template_id": row.template_id,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.get(
    "/research-cases/{case_id}/valuations",
    response_model=list[ValuationHistoryOut],
)
def valuation_history(case_id: int, db: Session = Depends(get_db)) -> list[dict]:
    case = _case(db, case_id)
    rows = db.scalars(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.research_case_id == case.id)
        .order_by(ValuationSnapshot.version.desc(), ValuationSnapshot.id.desc())
    ).all()
    return [
        {
            "id": row.id, "version": row.version, "status": row.status,
            "origin": row.origin, "as_of": row.as_of,
            "template_id": row.template_id, "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get(
    "/research-cases/{case_id}/valuations/{valuation_id}",
    response_model=ValuationSnapshotOut,
)
def get_valuation(
    case_id: int, valuation_id: int, db: Session = Depends(get_db)
) -> ValuationSnapshot:
    case = _case(db, case_id)
    row = db.scalar(
        select(ValuationSnapshot).where(
            ValuationSnapshot.id == valuation_id,
            ValuationSnapshot.research_case_id == case.id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Valuation snapshot not found.")
    return row


@router.post(
    "/research-cases/{case_id}/valuation-preview",
    response_model=ValuationPreviewOut,
)
def preview_valuation(
    case_id: int, payload: ValuationRequestIn, db: Session = Depends(get_db)
) -> dict:
    """Deterministic zero-write compute for an explicit assumption grid."""
    case = _case(db, case_id)
    try:
        prepared = prepare_valuation(db, case=case, request=payload)
    except ValuationInputError as exc:
        _raise_input(exc)
    return {
        "research_snapshot_id": payload.research_snapshot_id,
        "template": prepared["template"].to_dict(),
        "base_values": prepared["base_values"],
        "deterministic_outputs": prepared["deterministic_outputs"],
        "input_manifest": prepared["input_manifest"],
        "gaps": prepared["gaps"],
        "input_fingerprint": prepared["input_fingerprint"],
        "calculation_fingerprint": prepared["calculation_fingerprint"],
    }


@router.post(
    "/research-cases/{case_id}/valuation-runs",
    response_model=ValuationQueueOut,
    status_code=status.HTTP_201_CREATED,
)
def queue_valuation(
    case_id: int,
    payload: ValuationQueueIn | None = None,
    db: Session = Depends(get_db),
) -> ValuationQueueOut:
    """Freeze the deterministic base and queue a Codex-drafted valuation."""
    case = _case_for_update(db, case_id)
    payload = payload or ValuationQueueIn()
    research_snapshot_id = payload.research_snapshot_id
    if research_snapshot_id is None:
        research = _latest_research(db, case.id)
        if research is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No research snapshot exists; valuation starts from research.",
            )
        research_snapshot_id = research.id
    as_of = payload.as_of or utcnow().replace(tzinfo=timezone.utc)
    try:
        base = prepare_valuation_base(
            db, case=case, research_snapshot_id=research_snapshot_id, as_of=as_of
        )
    except ValuationInputError as exc:
        _raise_input(exc)
    key = f"valuation:{case.id}:{base['input_fingerprint']}"
    existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
    if existing is not None:
        return ValuationQueueOut(
            agent_run_id=existing.id,
            status=existing.status,
            created=False,
            input_fingerprint=base["input_fingerprint"],
        )
    active_peer = db.scalar(
        select(AgentRun).where(
            AgentRun.company_id == case.company_id,
            AgentRun.workflow == WORKFLOW,
            AgentRun.status.in_(("queued", "running")),
        )
    )
    if active_peer is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Another valuation for this company is already queued or running; "
                "finish it before freezing different inputs."
            ),
        )
    frozen = {
        "research_snapshot_id": research_snapshot_id,
        "as_of": as_of.isoformat(),
        "template_id": base["template"].id,
        "template_version": base["template"].version,
        "profile_archetype": base["template"].archetype,
        "base_values": base["base_values"],
        "input_manifest": base["input_manifest"],
        "gaps": base["gaps"],
        "input_fingerprint": base["input_fingerprint"],
    }
    model = default_model_for_workflow(WORKFLOW)
    agent = AgentRun(
        workflow=WORKFLOW,
        trigger="valuation-command",
        status="queued",
        company_id=case.company_id,
        model_role="analyst_deep",
        model=model,
        orchestrator_model=model,
        idempotency_key=key,
        inputs={
            "research_case_id": case.id,
            "ticker": frozen["base_values"]["company"]["ticker"],
            "task": {
                "skill": "company-valuation",
                "skill_version": SKILL_VERSION,
                "output_contract_version": CONTRACT_VERSION,
                "engine_version": ENGINE_VERSION,
                "template_contract_version": TEMPLATE_CONTRACT_VERSION,
                "required_verification": "verifier_strict",
            },
            "valuation": frozen,
        },
    )
    db.add(agent)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
        if existing is None:
            raise
        agent = existing
        created = False
    else:
        db.refresh(agent)
        created = True
    return ValuationQueueOut(
        agent_run_id=agent.id,
        status=agent.status,
        created=created,
        input_fingerprint=base["input_fingerprint"],
    )


@router.post("/research-cases/{case_id}/valuation-gates")
def valuation_gates(
    case_id: int, payload: ValuationSnapshotDraftIn, db: Session = Depends(get_db)
) -> dict:
    """Zero-write structural-gate dry run for the drafting worker."""
    try:
        return structural_gate_report(db, case_id=case_id, draft=payload)
    except ValuationArtifactError as exc:
        _raise_input(exc)


@router.post("/research-cases/{case_id}/valuation-verifications")
def verify_valuation(
    case_id: int,
    payload: ValuationSnapshotVerificationIn,
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = verify_valuation_snapshot(db, case_id=case_id, payload=payload)
    except ValuationArtifactError as exc:
        _raise_input(exc)
    return {
        "id": row.id, "agent_run_id": row.agent_run_id,
        "model_role": row.model_role, "verifier_model": row.verifier_model,
        "verdict": row.verdict, "checks": row.checks,
        "summary": row.summary, "created_at": row.created_at,
    }


@router.post(
    "/research-cases/{case_id}/valuation-snapshots",
    response_model=ValuationSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
def save_valuation(
    case_id: int, payload: ValuationSnapshotSaveIn, db: Session = Depends(get_db)
) -> ValuationSnapshot:
    try:
        return save_valuation_snapshot(db, case_id=case_id, payload=payload)
    except ValuationArtifactError as exc:
        _raise_input(exc)


@router.post(
    "/research-cases/{case_id}/valuation-override",
    response_model=ValuationSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
def override_valuation(
    case_id: int, payload: ValuationOverrideIn, db: Session = Depends(get_db)
) -> ValuationSnapshot:
    """Explicit user correction saved as a provisional `human-override` version."""
    try:
        return save_valuation_override(db, case_id=case_id, payload=payload)
    except ValuationArtifactError as exc:
        _raise_input(exc)
