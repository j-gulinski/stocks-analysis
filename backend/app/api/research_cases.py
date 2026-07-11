"""Research Lab entry point: one durable company case and one executable job."""

from __future__ import annotations

from dataclasses import dataclass

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
_SKILL_VERSION = "company-research-v2"
_OUTPUT_CONTRACT_VERSION = "research-snapshot-v2"
_PROFILE_SCHEMA_VERSION = "company-profile-v2"
_ARCHETYPE_CONTRACT_VERSION = "archetype-packs-v1"


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


def _summary(
    case: ResearchCase,
    company: Company,
    agent: AgentRun | None,
    latest_snapshot: ResearchSnapshot | None = None,
) -> ResearchCaseSummaryOut:
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
        if agent is not None and agent.status in {"completed", "provisional", "verified"}:
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
            _summary(research_case, company, agent, _latest_snapshot(db, research_case.id))
        )
    return result


@router.get("/by-ticker/{ticker}", response_model=ResearchCaseWorkspaceOut)
def get_research_workspace(
    ticker: str, db: Session = Depends(get_db)
) -> ResearchCaseWorkspaceOut:
    """Read the canonical stored Research workspace without side effects."""
    company = db.scalar(select(Company).where(Company.ticker == ticker.strip().upper()))
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown company.")
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
        select(AgentRun).where(AgentRun.idempotency_key == _initial_run_key(research_case.id))
    )
    snapshots = list(
        db.scalars(
            select(ResearchSnapshot)
            .where(ResearchSnapshot.research_case_id == research_case.id)
            .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        )
    )
    latest = snapshots[0] if snapshots else None
    profile = db.get(CompanyProfile, latest.company_profile_id) if latest else db.scalar(
        select(CompanyProfile)
        .where(CompanyProfile.research_case_id == research_case.id)
        .order_by(CompanyProfile.version.desc(), CompanyProfile.id.desc())
        .limit(1)
    )
    profile_out = CompanyProfileOut.model_validate(profile) if profile else None
    snapshot_out = ResearchSnapshotOut.model_validate(latest) if latest else None
    return ResearchCaseWorkspaceOut(
        research_case=_summary(research_case, company, agent, latest),
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
