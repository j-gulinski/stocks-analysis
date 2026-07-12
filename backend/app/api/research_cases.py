"""Research Lab entry point: one durable company case and one executable job."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
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
    utcnow,
)
from app.scrapers.biznesradar import MarketCandidate, ParseError, parse_market_rating
from app.services.archetype_packs import coverage_payload
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
_SKILL_VERSION = "company-research-v2"
_OUTPUT_CONTRACT_VERSION = "research-snapshot-v2"
_PROFILE_SCHEMA_VERSION = "company-profile-v2"
_ARCHETYPE_CONTRACT_VERSION = "archetype-packs-v1"
_DISCOVERY_SIEVE_ID = "financial_health_br_v1"
_DISCOVERY_SIEVE_VERSION = "financial-health-br-v1"


@dataclass(frozen=True)
class _ResolvedSource:
    version: DocumentVersion | None
    candidate: MarketCandidate | None


def _source_for_request(db: Session, payload: ResearchLabCreateIn) -> _ResolvedSource:
    if payload.source_document_version_id is None:
        return _ResolvedSource(version=None, candidate=None)

    version = db.scalar(
        select(DocumentVersion)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(
            DocumentVersion.id == payload.source_document_version_id,
            SourceDocument.company_ticker == "__GPW__",
            SourceDocument.source_type == "market_rating",
            DocumentVersion.parse_status == "parsed",
        )
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown parsed discovery source version.",
        )
    try:
        candidate = next(
            (
                row
                for row in parse_market_rating(version.raw_content)
                if row.ticker == payload.ticker.strip().upper()
            ),
            None,
        )
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The frozen discovery source can no longer be parsed.",
        ) from exc
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ticker is not present in this immutable discovery version.",
        )
    return _ResolvedSource(version=version, candidate=candidate)


def _initial_run_key(case_id: int) -> str:
    return f"research-case-initial-research:{case_id}"


def _discovery_origin(source: _ResolvedSource) -> dict | None:
    """Freeze why a Discover click admitted this company to Research."""
    if source.version is None or source.candidate is None:
        return None
    candidate = source.candidate
    as_of = source.version.fetched_at
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return {
        "sieve_id": _DISCOVERY_SIEVE_ID,
        "sieve_version": _DISCOVERY_SIEVE_VERSION,
        "source_document_version_id": source.version.id,
        "parser_version": source.version.parser_version,
        "as_of": as_of.isoformat(),
        "report_period": candidate.report_period,
        "membership_factors": [
            {
                "id": "altman_em_score",
                "label": "Wartość Altman EM-Score",
                "value": candidate.rating_value,
                "report_period": candidate.report_period,
                "source_document_version_id": source.version.id,
            },
            {
                "id": "piotroski_f_score",
                "label": "Piotroski F-Score",
                "value": candidate.piotroski_f_score,
                "report_period": candidate.report_period,
                "source_document_version_id": source.version.id,
            },
        ],
        "factor_gaps": (
            ["Brak F-Score Piotroskiego w zapisanym źródle."]
            if candidate.piotroski_f_score is None
            else []
        ),
        "strategy_questions": [
            "Jaki mechanizm może poprawić wyniki w kolejnym kwartale lub roku?",
            "Czy wynik bazowy i przepływy pieniężne potwierdzają jakość poprawy?",
            "Jaki katalizator i falsyfikator uzasadniają dalszy Research?",
        ],
        "neutral_context": [
            {"id": "wig_bucket", "value": None, "basis": "Brak w zapisanym źródle rynkowego ratingu."},
            {"id": "sector", "value": None, "basis": "Brak w zapisanym źródle rynkowego ratingu."},
            {"id": "size", "value": None, "basis": "Brak raportowanej kapitalizacji w zapisanym źródle rynkowego ratingu."},
        ],
    }


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
) -> ResearchCaseSummaryOut:
    current_agent = latest_agent or agent
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
        initial_research_run_id=agent.id if agent else None,
        initial_research_status=agent.status if agent else None,
        latest_research_run_id=current_agent.id if current_agent else None,
        latest_research_run_status=current_agent.status if current_agent else None,
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


def _ensure_research_case(
    db: Session,
    *,
    ticker: str,
    source: _ResolvedSource,
) -> tuple[Company, ResearchCase, AgentRun, bool, bool, bool, bool]:
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    created_company = company is None
    if company is None:
        company = Company(
            ticker=ticker,
            name=source.candidate.name if source.candidate else None,
            br_slug=source.candidate.br_slug if source.candidate else None,
            market="GPW" if source.candidate else None,
        )
        db.add(company)
        db.flush()
    elif source.candidate is not None:
        # Frozen discovery identity may safely fill missing metadata, but it
        # never overwrites values learned from a company-specific source.
        company.name = company.name or source.candidate.name
        company.br_slug = company.br_slug or source.candidate.br_slug
        company.market = company.market or "GPW"

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
            as_of=source.version.fetched_at if source.version else utcnow(),
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
    agent = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == run_key))
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
        research_case.as_of = source.version.fetched_at if source.version else utcnow()
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
        agent = AgentRun(
            workflow=_WORKFLOW,
            trigger="research-lab",
            status="queued",
            company_id=company.id,
            model_role="worker_standard",
            model=model,
            orchestrator_model=model,
            idempotency_key=run_key,
            inputs={
                "ticker": company.ticker,
                "research_case_id": research_case.id,
                "source_document_version_id": (
                    source.version.id if source.version is not None else None
                ),
                "discovery_origin": _discovery_origin(source),
                "task": {
                    "skill": "company-research",
                    "skill_version": _SKILL_VERSION,
                    "output_contract_version": _OUTPUT_CONTRACT_VERSION,
                    "company_profile_schema_version": _PROFILE_SCHEMA_VERSION,
                    "archetype_contract_version": _ARCHETYPE_CONTRACT_VERSION,
                    "objective": (
                        "Refresh one company, organize its evidence into a tailored "
                        "research profile and save a structured first snapshot."
                    ),
                    "refresh_scope": "all",
                    "required_verification": "verifier_strict",
                    "watchlist_policy": "do not add automatically",
                },
            },
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
        agent = db.scalar(
            select(AgentRun).where(
                AgentRun.idempotency_key == _initial_run_key(research_case.id)
            )
        )
        result.append(
            _summary(
                research_case,
                company,
                agent,
                _latest_snapshot(db, research_case.id),
                _latest_research_run(db, research_case),
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
    agent = db.scalar(
        select(AgentRun).where(
            AgentRun.idempotency_key == _initial_run_key(research_case.id)
        )
    )
    snapshots = list(
        db.scalars(
            select(ResearchSnapshot)
            .where(ResearchSnapshot.research_case_id == research_case.id)
            .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        )
    )
    latest = snapshots[0] if snapshots else None
    profile = (
        db.get(CompanyProfile, latest.company_profile_id)
        if latest
        else db.scalar(
            select(CompanyProfile)
            .where(CompanyProfile.research_case_id == research_case.id)
            .order_by(CompanyProfile.version.desc(), CompanyProfile.id.desc())
            .limit(1)
        )
    )
    profile_out = CompanyProfileOut.model_validate(profile) if profile else None
    snapshot_out = ResearchSnapshotOut.model_validate(latest) if latest else None
    return ResearchCaseWorkspaceOut(
        research_case=_summary(
            research_case,
            company,
            agent,
            latest,
            _latest_research_run(db, research_case),
        ),
        profile=profile_out,
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

    source_fingerprint, source_manifest = _review_source_state(db, company.id)
    key = f"research-case-review:{case.id}:{source_fingerprint}"
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
                    "Refresh one existing company case, compare new evidence with the "
                    "prior immutable snapshot and save the next verified snapshot."
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
    source = _source_for_request(db, payload)

    # Company, case and job each have a database uniqueness boundary. A
    # concurrent identical request can win one of them; retrying after rollback
    # then returns that complete committed unit rather than duplicating work.
    for attempt in range(2):
        try:
            ensured = _ensure_research_case(db, ticker=ticker, source=source)
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
