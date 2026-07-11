"""Canonical P3 valuation preview, queue, verification and history API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ValuationHistoryOut,
    ValuationMethodPackOut,
    ValuationPreviewOut,
    ValuationQueueOut,
    ValuationRequestIn,
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
)
from app.services.model_policy import default_model_for_workflow
from app.services.valuation_artifacts import (
    ValuationArtifactError,
    save_valuation_snapshot,
    verify_valuation_snapshot,
)
from app.services.valuation_engine import (
    ENGINE_VERSION,
    TEMPLATE_CONTRACT_VERSION,
    ValuationInputError,
    prepare_valuation,
)
from app.services.valuation_method_packs import list_method_packs
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
    }.get(exc.kind, status.HTTP_422_UNPROCESSABLE_CONTENT)
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _latest_research(db: Session, case_id: int) -> ResearchSnapshot | None:
    return db.scalar(
        select(ResearchSnapshot)
        .where(ResearchSnapshot.research_case_id == case_id)
        .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        .limit(1)
    )


def _latest_valuation(db: Session, case_id: int) -> ValuationSnapshot | None:
    return db.scalar(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.research_case_id == case_id)
        .order_by(ValuationSnapshot.version.desc(), ValuationSnapshot.id.desc())
        .limit(1)
    )


@router.get("/valuation-method-packs", response_model=list[ValuationMethodPackOut])
def method_packs() -> list[dict]:
    return list_method_packs()


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
        "method_packs": list_method_packs(),
        "template": template.to_dict() if template else None,
        "latest_valuation": rows[0] if rows else None,
        "history": [
            {
                "id": row.id,
                "version": row.version,
                "status": row.status,
                "as_of": row.as_of,
                "method_pack_id": row.method_pack_id,
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
            "as_of": row.as_of, "method_pack_id": row.method_pack_id,
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


def _preview(db: Session, case: ResearchCase, payload: ValuationRequestIn) -> dict:
    try:
        prepared = prepare_valuation(db, case=case, request=payload)
    except ValuationInputError as exc:
        _raise_input(exc)
    return {
        "research_snapshot_id": payload.research_snapshot_id,
        "method_pack": prepared["method"].to_dict(),
        "template": prepared["template"].to_dict(),
        "base_values": prepared["base_values"],
        "deterministic_outputs": prepared["deterministic_outputs"],
        "input_manifest": prepared["input_manifest"],
        "gaps": prepared["gaps"],
        "input_fingerprint": prepared["input_fingerprint"],
        "calculation_fingerprint": prepared["calculation_fingerprint"],
        "_profile_archetype": prepared["template"].archetype,
    }


@router.post(
    "/research-cases/{case_id}/valuation-preview",
    response_model=ValuationPreviewOut,
)
def preview_valuation(
    case_id: int, payload: ValuationRequestIn, db: Session = Depends(get_db)
) -> dict:
    return _preview(db, _case(db, case_id), payload)


@router.post(
    "/research-cases/{case_id}/valuation-runs",
    response_model=ValuationQueueOut,
    status_code=status.HTTP_201_CREATED,
)
def queue_valuation(
    case_id: int, payload: ValuationRequestIn, db: Session = Depends(get_db)
) -> ValuationQueueOut:
    case = _case_for_update(db, case_id)
    preview = _preview(db, case, payload)
    key = f"valuation:{case.id}:{preview['input_fingerprint']}"
    existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
    if existing is not None:
        return ValuationQueueOut(
            agent_run_id=existing.id,
            status=existing.status,
            created=False,
            input_fingerprint=preview["input_fingerprint"],
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
        "research_snapshot_id": payload.research_snapshot_id,
        "as_of": payload.as_of.isoformat(),
        "method_pack_id": preview["method_pack"]["id"],
        "method_pack_version": preview["method_pack"]["version"],
        "template_id": preview["template"]["id"],
        "template_version": preview["template"]["version"],
        "profile_archetype": preview["_profile_archetype"],
        "assumptions": payload.model_dump(mode="json")["assumptions"],
        "base_values": preview["base_values"],
        "deterministic_outputs": preview["deterministic_outputs"],
        "input_manifest": preview["input_manifest"],
        "gaps": preview["gaps"],
        "input_fingerprint": preview["input_fingerprint"],
        "calculation_fingerprint": preview["calculation_fingerprint"],
    }
    model = default_model_for_workflow(WORKFLOW)
    agent = AgentRun(
        workflow=WORKFLOW,
        trigger="valuation-command",
        status="queued",
        company_id=case.company_id,
        model_role="worker_standard",
        model=model,
        orchestrator_model=model,
        idempotency_key=key,
        inputs={
            "research_case_id": case.id,
            "ticker": frozen["base_values"]["company"]["ticker"],
            "task": {
                "skill": "company-valuation",
                "skill_version": "company-valuation-v1",
                "output_contract_version": "valuation-snapshot-v1",
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
        input_fingerprint=preview["input_fingerprint"],
    )


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
