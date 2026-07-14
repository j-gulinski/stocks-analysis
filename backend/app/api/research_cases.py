"""Research Lab entry point: one durable company case and one executable job."""

from __future__ import annotations

from datetime import timezone
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    CompanyProfileCorrectionIn,
    CompanyProfileOut,
    ResearchCaseWorkspaceOut,
    ResearchCaseSummaryOut,
    ResearchLabCreateIn,
    ResearchLabCreateOut,
    ResearchReviewQueueOut,
    ResearchSnapshotHistoryOut,
    ResearchSnapshotOut,
    ResearchSnapshotSaveIn,
    ResearchSnapshotVerificationIn,
)
from app.db.base import get_db
from app.db.models import (
    AgentRun,
    Company,
    CompanyProfile,
    DocumentVersion,
    ResearchCase,
    ResearchCaseStepHistory,
    ResearchSnapshot,
    SourceDocument,
    ValuationSnapshot,
    utcnow,
)
from app.services.archetype_packs import coverage_payload
from app.services.company_profiles import (
    CompanyProfileError,
    append_human_profile,
    frozen_profile,
)
from app.services.discovery import DiscoveryAdmission, admit_discovery_candidate
from app.services.model_policy import default_model_for_workflow
from app.services.research_artifacts import (
    ResearchArtifactError,
    save_research_snapshot,
    verify_research_snapshot,
)

router = APIRouter(prefix="/research-cases", tags=["research-cases"])

_PURPOSE = "investment-research"
_WORKFLOW = "stock-initial-research"
_REVIEW_WORKFLOW = "stock-company-review"
_SKILL_VERSION = "company-research-v3"
_OUTPUT_CONTRACT_VERSION = "research-snapshot-v3"
_PROFILE_SCHEMA_VERSION = "company-profile-v2"
_ARCHETYPE_CONTRACT_VERSION = "archetype-packs-v1"
def _initial_run_key(case_id: int) -> str:
    return f"research-case-initial-research:{case_id}"


def _review_source_state(db: Session, company_id: int) -> tuple[str, list[dict]]:
    rows = db.execute(
        select(
            SourceDocument.id,
            DocumentVersion.id,
            DocumentVersion.content_hash,
            DocumentVersion.fetched_at,
        )
        .join(DocumentVersion, DocumentVersion.source_document_id == SourceDocument.id)
        .where(SourceDocument.company_id == company_id)
        .order_by(SourceDocument.id, DocumentVersion.id.desc())
    ).all()
    latest_by_document: dict[int, dict] = {}
    for document_id, version_id, content_hash, fetched_at in rows:
        latest_by_document.setdefault(
            document_id,
            {
                "source_document_id": document_id,
                "document_version_id": version_id,
                "content_hash": content_hash,
                "fetched_at": (
                    fetched_at
                    if fetched_at.tzinfo is not None
                    else fetched_at.replace(tzinfo=timezone.utc)
                ).isoformat(),
            },
        )
    manifest = list(latest_by_document.values())
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), manifest


def _summary(
    case: ResearchCase,
    company: Company,
    agent: AgentRun | None,
    latest_snapshot: ResearchSnapshot | None = None,
    latest_agent: AgentRun | None = None,
    latest_valuation: ValuationSnapshot | None = None,
) -> ResearchCaseSummaryOut:
    current_agent = latest_agent or agent
    brief = (latest_snapshot.sections or {}).get("brief", {}) if latest_snapshot else {}
    phase_summary = str(brief.get("current_understanding") or "").strip()
    main_gap = str(brief.get("main_gap") or "").strip() or case.blocked_reason
    collection_progress = None
    valuation_strip = None
    if latest_snapshot is None:
        phase = "collecting"
        phase_label = "Zbieranie"
        state = "waiting"
        phase_summary = "Research czeka na rozpoczęcie zbierania źródeł."
        if current_agent is not None and current_agent.status == "running":
            state = "collecting"
            phase_summary = "Trwa zbieranie i porządkowanie źródeł spółki."
        elif current_agent is not None and current_agent.status in {
            "rejected",
            "needs-human",
            "failed",
        }:
            state = "attention"
            phase_summary = (
                case.blocked_reason
                or current_agent.error
                or "Zbieranie wymaga interwencji."
            )
        raw_progress = (
            (current_agent.outputs or {}).get("collection_progress")
            if current_agent is not None
            else None
        )
        raw_progress = raw_progress if isinstance(raw_progress, dict) else {}
        percent = raw_progress.get("percent")
        collection_progress = {
            "state": state,
            "summary": phase_summary,
            "completed_sources": list(raw_progress.get("completed_sources") or []),
            "remaining_sources": list(raw_progress.get("remaining_sources") or []),
            "percent": percent if isinstance(percent, int) else None,
        }
    elif latest_valuation is None:
        phase = "researched"
        phase_label = "Zbadana"
    else:
        phase = "valued"
        phase_label = "Wyceniona"
        outputs = latest_valuation.deterministic_outputs or {}
        scenario_rows = [
            row for row in outputs.get("scenarios", []) if isinstance(row, dict)
        ]
        prices = {
            str(row.get("kind")): (
                float(row["target_price_pln"])
                if row.get("target_price_pln") is not None
                else None
            )
            for row in scenario_rows
            if row.get("kind")
        }
        probability_rows = outputs.get("final_probabilities") or []
        probabilities = {
            str(row.get("kind")): float(row.get("probability_pct"))
            for row in probability_rows
            if isinstance(row, dict)
            and row.get("kind")
            and row.get("probability_pct") is not None
        }
        priced = [value for value in prices.values() if value is not None]
        weighted = outputs.get("probability_weighted") or {}
        judgment = latest_valuation.codex_judgment or {}
        catalysts = judgment.get("catalysts") or []
        valuation_strip = {
            "scenario_prices_pln": prices,
            "scenario_probabilities_pct": probabilities,
            "price_range_pln": [min(priced), max(priced)] if priced else None,
            "weighted_value_pln": (
                float(weighted["price_pln"])
                if weighted.get("price_pln") is not None
                else None
            ),
            "current_price_pln": (
                float(outputs["current_price_pln"])
                if outputs.get("current_price_pln") is not None
                else None
            ),
            "upside_pct": (
                float(weighted["return_pct"])
                if weighted.get("return_pct") is not None
                else None
            ),
            "catalyst": str(catalysts[0]) if catalysts else None,
            "verification_status": latest_valuation.status,
            "as_of": latest_valuation.as_of,
        }
    return ResearchCaseSummaryOut(
        id=case.id,
        company_id=company.id,
        ticker=company.ticker,
        name=company.name,
        purpose=case.purpose,
        state=case.state,
        current_step=case.current_step,
        as_of=case.as_of,
        blocked_reason=case.blocked_reason,
        created_at=case.created_at,
        updated_at=case.updated_at,
        phase=phase,
        phase_label=phase_label,
        phase_summary=phase_summary,
        main_gap=main_gap,
        collection_progress=collection_progress,
        valuation_strip=valuation_strip,
        latest_snapshot_status=latest_snapshot.status if latest_snapshot else None,
        latest_snapshot_as_of=latest_snapshot.as_of if latest_snapshot else None,
    )


def _latest_snapshot(db: Session, case_id: int) -> ResearchSnapshot | None:
    return db.scalar(
        select(ResearchSnapshot)
        .where(ResearchSnapshot.research_case_id == case_id)
        .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        .limit(1)
    )


def _latest_valuation(
    db: Session,
    case_id: int,
    latest_snapshot: ResearchSnapshot | None,
) -> ValuationSnapshot | None:
    if latest_snapshot is None:
        return None
    return db.scalar(
        select(ValuationSnapshot)
        .where(
            ValuationSnapshot.research_case_id == case_id,
            ValuationSnapshot.research_snapshot_id == latest_snapshot.id,
        )
        .order_by(ValuationSnapshot.version.desc(), ValuationSnapshot.id.desc())
        .limit(1)
    )


def _latest_research_run(db: Session, case: ResearchCase) -> AgentRun | None:
    return db.scalar(
        select(AgentRun)
        .where(
            AgentRun.company_id == case.company_id,
            AgentRun.workflow.in_((_WORKFLOW, _REVIEW_WORKFLOW)),
            AgentRun.inputs["research_case_id"].as_integer() == case.id,
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(1)
    )


def _initial_research_run(db: Session, case: ResearchCase) -> AgentRun | None:
    """Return the stable initial run, including runs saved before keys existed."""
    keyed = db.scalar(
        select(AgentRun).where(
            AgentRun.idempotency_key == _initial_run_key(case.id)
        )
    )
    if keyed is not None:
        return keyed
    return db.scalar(
        select(AgentRun)
        .where(
            AgentRun.workflow == _WORKFLOW,
            AgentRun.company_id == case.company_id,
            AgentRun.inputs["research_case_id"].as_integer() == case.id,
        )
        .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
        .limit(1)
    )


def _frozen_discovery_origin(admission: DiscoveryAdmission) -> dict:
    """Freeze server-recomputed Discover membership into the initial job."""
    return {
        "batch_id": admission.batch.id,
        "sieve_id": "workbench_sieve_v1",
        "sieve_version": "workbench-sieve-v1",
        "page_document_versions": admission.page_document_versions,
        "batch_fingerprint": admission.fingerprint,
        "candidate": admission.candidate.frozen_evidence(),
    }


def _ensure_research_case(
    db: Session,
    *,
    ticker: str,
    discovery_origin: dict | None = None,
) -> tuple[Company, ResearchCase, AgentRun, bool, bool, bool, bool]:
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    created_company = company is None
    if company is None:
        company = Company(
            ticker=ticker,
            name=(discovery_origin or {}).get("candidate", {}).get("name"),
        )
        db.add(company)
        db.flush()

    research_case = db.scalar(
        select(ResearchCase).where(
            ResearchCase.company_id == company.id,
            ResearchCase.purpose == _PURPOSE,
        )
    )
    created_case = research_case is None
    if research_case is None:
        research_case = ResearchCase(
            company_id=company.id,
            purpose=_PURPOSE,
            state="ingesting",
            current_step="ingest",
            as_of=utcnow(),
        )
        db.add(research_case)
        db.flush()
        db.add(
            ResearchCaseStepHistory(
                research_case_id=research_case.id,
                from_state=None,
                from_step=None,
                to_state="ingesting",
                to_step="ingest",
                reason="Research Lab: utworzono sprawę i zlecono pierwszy research.",
            )
        )

    run_key = _initial_run_key(research_case.id)
    agent = _initial_research_run(db, research_case)
    if agent is not None and (
        agent.workflow != _WORKFLOW or agent.company_id != company.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initial-research idempotency key points to an inconsistent job.",
        )
    reactivated_case = not created_case and research_case.state == "closed"
    if reactivated_case:
        previous_step = research_case.current_step
        if agent is not None and agent.status in {
            "completed",
            "provisional",
            "verified",
        }:
            research_case.state = "monitoring"
            research_case.current_step = "monitoring"
        elif agent is not None and agent.status in {
            "failed",
            "rejected",
            "needs-human",
        }:
            research_case.state = "blocked"
            research_case.current_step = "data_review"
            research_case.blocked_reason = (
                "Pierwszy research wymaga jawnego przeglądu lub ponowienia."
            )
        else:
            research_case.state = "ingesting"
            research_case.current_step = "ingest"
            research_case.blocked_reason = None
        research_case.as_of = utcnow()
        research_case.updated_at = utcnow()
        db.add(
            ResearchCaseStepHistory(
                research_case_id=research_case.id,
                from_state="closed",
                from_step=previous_step,
                to_state=research_case.state,
                to_step=research_case.current_step,
                reason="Research Lab: ponownie aktywowano istniejący przypadek.",
            )
        )

    created_job = agent is None
    if agent is None:
        model = default_model_for_workflow(_WORKFLOW)
        inputs = {
            "ticker": company.ticker,
            "research_case_id": research_case.id,
            "task": {
                "skill": "company-research",
                "skill_version": _SKILL_VERSION,
                "output_contract_version": _OUTPUT_CONTRACT_VERSION,
                "company_profile_schema_version": _PROFILE_SCHEMA_VERSION,
                "archetype_contract_version": _ARCHETYPE_CONTRACT_VERSION,
                "objective": (
                    "Refresh one company, resolve its source questions and save a "
                    "tailored forward-looking first snapshot."
                ),
                "refresh_scope": "all",
                "required_verification": "verifier_strict",
                "watchlist_policy": "do not add automatically",
            },
        }
        if discovery_origin is not None:
            inputs["discovery_origin"] = discovery_origin
        agent = AgentRun(
            workflow=_WORKFLOW,
            trigger="research-lab",
            status="queued",
            company_id=company.id,
            model_role="worker_standard",
            model=model,
            orchestrator_model=model,
            idempotency_key=run_key,
            inputs=inputs,
            outputs={},
        )
        db.add(agent)
        db.flush()
    return (
        company,
        research_case,
        agent,
        created_company,
        created_case,
        reactivated_case,
        created_job,
    )


@router.get("", response_model=list[ResearchCaseSummaryOut])
def list_research_cases(db: Session = Depends(get_db)) -> list[ResearchCaseSummaryOut]:
    rows = db.execute(
        select(ResearchCase, Company)
        .join(Company, ResearchCase.company_id == Company.id)
        .order_by(ResearchCase.updated_at.desc(), ResearchCase.id.desc())
    ).all()
    result: list[ResearchCaseSummaryOut] = []
    for research_case, company in rows:
        agent = _initial_research_run(db, research_case)
        latest_snapshot = _latest_snapshot(db, research_case.id)
        result.append(
            _summary(
                research_case,
                company,
                agent,
                latest_snapshot,
                _latest_research_run(db, research_case),
                _latest_valuation(db, research_case.id, latest_snapshot),
            )
        )
    return result


@router.get("/by-ticker/{ticker}", response_model=ResearchCaseWorkspaceOut)
def get_research_workspace(
    ticker: str, db: Session = Depends(get_db)
) -> ResearchCaseWorkspaceOut:
    """Read the canonical stored Research workspace without side effects."""
    company = db.scalar(select(Company).where(Company.ticker == ticker.strip().upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown company."
        )
    research_case = db.scalar(
        select(ResearchCase).where(
            ResearchCase.company_id == company.id,
            ResearchCase.purpose == _PURPOSE,
        )
    )
    if research_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Research case not found."
        )
    agent = _initial_research_run(db, research_case)
    snapshots = list(
        db.scalars(
            select(ResearchSnapshot)
            .where(ResearchSnapshot.research_case_id == research_case.id)
            .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        )
    )
    latest = snapshots[0] if snapshots else None
    profiles = list(
        db.scalars(
            select(CompanyProfile)
            .where(CompanyProfile.research_case_id == research_case.id)
            .order_by(CompanyProfile.version.desc(), CompanyProfile.id.desc())
        )
    )
    current_profile = profiles[0] if profiles else None
    snapshot_profile = (
        db.get(CompanyProfile, latest.company_profile_id) if latest else None
    )
    profile = snapshot_profile or current_profile
    profile_out = CompanyProfileOut.model_validate(profile) if profile else None
    snapshot_out = ResearchSnapshotOut.model_validate(latest) if latest else None
    return ResearchCaseWorkspaceOut(
        research_case=_summary(
            research_case,
            company,
            agent,
            latest,
            _latest_research_run(db, research_case),
            _latest_valuation(db, research_case.id, latest),
        ),
        profile=profile_out,
        current_profile=(
            CompanyProfileOut.model_validate(current_profile) if current_profile else None
        ),
        profile_history=[CompanyProfileOut.model_validate(item) for item in profiles],
        latest_snapshot=snapshot_out,
        history=[
            ResearchSnapshotHistoryOut(
                id=item.id,
                version=item.version,
                status=item.status,
                as_of=item.as_of,
                profile_version=db.get(CompanyProfile, item.company_profile_id).version,
                created_at=item.created_at,
            )
            for item in snapshots
        ],
        archetype_pack=(
            coverage_payload(profile_out, snapshot_out.gaps if snapshot_out else [])
            if profile_out
            else None
        ),
    )


@router.post("/{case_id}/profiles", response_model=CompanyProfileOut)
def confirm_company_profile(
    case_id: int,
    payload: CompanyProfileCorrectionIn,
    db: Session = Depends(get_db),
) -> CompanyProfile:
    """Append a user-owned profile version; no evidence or snapshot is rewritten."""
    case = db.scalar(
        select(ResearchCase).where(ResearchCase.id == case_id).with_for_update()
    )
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Research case not found."
        )
    try:
        profile = append_human_profile(db, case=case, payload=payload)
        db.commit()
    except CompanyProfileError as exc:
        db.rollback()
        code = {
            "conflict": status.HTTP_409_CONFLICT,
            "not-found": status.HTTP_404_NOT_FOUND,
        }.get(exc.kind, status.HTTP_422_UNPROCESSABLE_CONTENT)
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The company profile changed concurrently; reopen it before confirming.",
        ) from exc
    db.refresh(profile)
    return profile


@router.post(
    "/{case_id}/review-runs",
    response_model=ResearchReviewQueueOut,
    status_code=status.HTTP_201_CREATED,
)
def queue_research_review(
    case_id: int, db: Session = Depends(get_db)
) -> ResearchReviewQueueOut:
    case = db.scalar(
        select(ResearchCase).where(ResearchCase.id == case_id).with_for_update()
    )
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Research case not found."
        )
    company = db.get(Company, case.company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Research company is missing."
        )
    latest_snapshot = _latest_snapshot(db, case.id)
    if latest_snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the initial Research snapshot before queuing a review.",
        )

    profile = db.scalar(
        select(CompanyProfile)
        .where(CompanyProfile.research_case_id == case.id)
        .order_by(CompanyProfile.version.desc(), CompanyProfile.id.desc())
        .limit(1)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The latest Research snapshot has no company profile.",
        )
    if profile.provenance == "codex-proposed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Confirm or correct the latest company profile before queuing "
                "a Research review."
            ),
        )
    source_questions = (profile.company_overlay or {}).get("source_questions") or []
    if not source_questions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Add at least one company-specific source question to the confirmed "
                "profile before queuing a Research review."
            ),
        )
    frozen = frozen_profile(profile)

    source_fingerprint, source_manifest = _review_source_state(db, company.id)
    key = f"research-case-review:{case.id}:{source_fingerprint}:{frozen['fingerprint']}"
    existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
    if existing is not None:
        existing_review = (
            (existing.inputs or {}).get("review")
            if isinstance((existing.inputs or {}).get("review"), dict)
            else {}
        )
        return ResearchReviewQueueOut(
            agent_run_id=existing.id,
            status=existing.status,
            created=False,
            prior_snapshot_id=existing_review.get(
                "prior_research_snapshot_id", latest_snapshot.id
            ),
            source_fingerprint=source_fingerprint,
            profile_id=existing_review.get("confirmed_company_profile", {}).get(
                "id", profile.id
            ),
            profile_version=existing_review.get("confirmed_company_profile", {}).get(
                "version", profile.version
            ),
            profile_fingerprint=existing_review.get("confirmed_company_profile", {}).get(
                "fingerprint", frozen["fingerprint"]
            ),
        )

    active_peer = db.scalar(
        select(AgentRun).where(
            AgentRun.company_id == company.id,
            AgentRun.workflow.in_((_WORKFLOW, _REVIEW_WORKFLOW)),
            AgentRun.status.in_(("queued", "running")),
        )
    )
    if active_peer is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another Research collection for this company is already queued or running.",
        )

    model = default_model_for_workflow(_REVIEW_WORKFLOW)
    agent = AgentRun(
        workflow=_REVIEW_WORKFLOW,
        trigger="research-review-command",
        status="queued",
        company_id=company.id,
        model_role="worker_standard",
        model=model,
        orchestrator_model=model,
        idempotency_key=key,
        inputs={
            "ticker": company.ticker,
            "research_case_id": case.id,
            "task": {
                "skill": "company-research",
                "skill_version": _SKILL_VERSION,
                "output_contract_version": _OUTPUT_CONTRACT_VERSION,
                "company_profile_schema_version": _PROFILE_SCHEMA_VERSION,
                "archetype_contract_version": _ARCHETYPE_CONTRACT_VERSION,
                "objective": (
                    "Refresh one existing company case, resolve its source questions, "
                    "compare forward drivers with the prior immutable snapshot and save "
                    "the next verified snapshot."
                ),
                "refresh_scope": "all",
                "required_verification": "verifier_strict",
                "watchlist_policy": "do not add automatically",
            },
            "review": {
                "prior_research_snapshot_id": latest_snapshot.id,
                "prior_artifact_fingerprint": latest_snapshot.artifact_fingerprint,
                "queued_source_fingerprint": source_fingerprint,
                "queued_source_manifest": source_manifest,
                "confirmed_company_profile": frozen,
            },
        },
        outputs={},
    )
    db.add(agent)
    previous_state, previous_step = case.state, case.current_step
    case.state = "ingesting"
    case.current_step = "ingest"
    case.blocked_reason = None
    case.updated_at = utcnow()
    db.add(
        ResearchCaseStepHistory(
            research_case_id=case.id,
            from_state=previous_state,
            from_step=previous_step,
            to_state="ingesting",
            to_step="ingest",
            reason="Research: jawnie zlecono odświeżenie istniejącego snapshotu.",
            changed_by="user-command",
        )
    )
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
    return ResearchReviewQueueOut(
        agent_run_id=agent.id,
        status=agent.status,
        created=created,
        prior_snapshot_id=latest_snapshot.id,
        source_fingerprint=source_fingerprint,
        profile_id=profile.id,
        profile_version=profile.version,
        profile_fingerprint=frozen["fingerprint"],
    )


@router.post("/{case_id}/snapshots", response_model=ResearchSnapshotOut)
def create_research_snapshot(
    case_id: int,
    payload: ResearchSnapshotSaveIn,
    db: Session = Depends(get_db),
) -> ResearchSnapshot:
    """Worker save adapter; validation/persistence is shared with CLI and MCP."""
    try:
        return save_research_snapshot(db, case_id=case_id, payload=payload)
    except ResearchArtifactError as exc:
        code = {
            "not-found": status.HTTP_404_NOT_FOUND,
            "conflict": status.HTTP_409_CONFLICT,
        }.get(exc.kind, status.HTTP_422_UNPROCESSABLE_CONTENT)
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/{case_id}/snapshot-verifications", response_model=dict)
def create_research_snapshot_verification(
    case_id: int,
    payload: ResearchSnapshotVerificationIn,
    db: Session = Depends(get_db),
) -> dict:
    """Independent verifier adapter; records a verdict but does not finish the job."""
    try:
        verification = verify_research_snapshot(db, case_id=case_id, payload=payload)
    except ResearchArtifactError as exc:
        code = {
            "not-found": status.HTTP_404_NOT_FOUND,
            "conflict": status.HTTP_409_CONFLICT,
        }.get(exc.kind, status.HTTP_422_UNPROCESSABLE_CONTENT)
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return {
        "id": verification.id,
        "agent_run_id": verification.agent_run_id,
        "model_role": verification.model_role,
        "verifier_model": verification.verifier_model,
        "verdict": verification.verdict,
        "checks": verification.checks,
        "summary": verification.summary,
        "created_at": verification.created_at,
    }


@router.post("", response_model=ResearchLabCreateOut)
def create_research_case(
    payload: ResearchLabCreateIn,
    db: Session = Depends(get_db),
) -> ResearchLabCreateOut:
    """Atomically create/reuse a company, case and its sole initial job."""
    ticker = payload.ticker.strip().upper()
    if not ticker:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ticker cannot be blank.",
        )
    discovery_origin = None
    if payload.discovery is not None:
        try:
            admission = admit_discovery_candidate(
                db,
                batch_id=payload.discovery.batch_id,
                ticker=ticker,
                sieve_id=payload.discovery.sieve_id,
                sieve_version=payload.discovery.sieve_version,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
        except (LookupError, PermissionError) as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        discovery_origin = _frozen_discovery_origin(admission)
    # Company, case and job each have a database uniqueness boundary. A
    # concurrent identical request can win one of them; retrying after rollback
    # then returns that complete committed unit rather than duplicating work.
    for attempt in range(2):
        try:
            ensured = _ensure_research_case(
                db, ticker=ticker, discovery_origin=discovery_origin
            )
            db.commit()
            (
                company,
                research_case,
                agent,
                created_company,
                created_case,
                reactivated_case,
                created_job,
            ) = ensured
            return ResearchLabCreateOut(
                research_case=_summary(research_case, company, agent),
                agent_run=agent,
                created_company=created_company,
                created_case=created_case,
                reactivated_case=reactivated_case,
                created_job=created_job,
            )
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
    raise AssertionError("unreachable")
