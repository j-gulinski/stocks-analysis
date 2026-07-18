"""Research Lab entry point: one durable company case and one executable job."""

from __future__ import annotations

from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
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
    ThesisFalsifier,
    ValuationSnapshot,
    utcnow,
)
from app.services.archetype_packs import coverage_payload
from app.services.company_profiles import (
    CompanyProfileError,
    append_human_profile,
)
from app.services.discovery import DiscoveryAdmission, admit_discovery_candidate
from app.services.artifact_contracts import (
    RESEARCH_PROFILE_SCHEMA,
    canonical_research_snapshot_predicate,
    canonical_valuation_snapshot_predicate,
)
from app.services.research_artifacts import (
    ResearchArtifactError,
    save_research_snapshot,
    verify_research_snapshot,
)
from app.services.research_queue import (
    ResearchQueueError,
    enqueue_research_review,
    ensure_research_case,
    initial_research_run,
)
from app.services.portfolio_coverage import latest_portfolio_research_context
from app.services import report_calendar

router = APIRouter(prefix="/research-cases", tags=["research-cases"])

_PURPOSE = "investment-research"
_WORKFLOW = "stock-initial-research"
_REVIEW_WORKFLOW = "stock-company-review"
_RESEARCH_STALE_AFTER = timedelta(days=30)


def _agenda_reasons(
    db: Session,
    *,
    company: Company,
    latest_snapshot: ResearchSnapshot | None,
    latest_agent: AgentRun | None,
    latest_valuation: ValuationSnapshot | None,
    portfolio_context: dict | None = None,
) -> list[str]:
    reasons: list[str] = []
    if latest_snapshot is None:
        if latest_agent is not None and latest_agent.status in {
            "rejected",
            "needs-human",
            "failed",
        }:
            reasons.append("Zbieranie źródeł wymaga interwencji.")
        if portfolio_context is not None:
            reasons.append(
                "Pozycja portfelowa nie ma jeszcze bieżącego zweryfikowanego Research."
            )
        return reasons

    if latest_snapshot.status in {"rejected", "needs-human"}:
        reasons.append("Snapshot Research wymaga decyzji lub ponownej weryfikacji.")

    snapshot_as_of = latest_snapshot.as_of
    if snapshot_as_of.tzinfo is None:
        snapshot_as_of = snapshot_as_of.replace(tzinfo=timezone.utc)
    if snapshot_as_of <= utcnow() - _RESEARCH_STALE_AFTER:
        reasons.append("Research ma ponad 30 dni i wymaga sprawdzenia aktualności.")

    new_evidence_id = db.scalar(
        select(DocumentVersion.id)
        .join(
            SourceDocument,
            DocumentVersion.source_document_id == SourceDocument.id,
        )
        .where(
            or_(
                SourceDocument.company_id == company.id,
                SourceDocument.company_ticker == company.ticker,
            ),
            DocumentVersion.parse_status == "parsed",
            DocumentVersion.fetched_at > snapshot_as_of,
        )
        .limit(1)
    )
    if new_evidence_id is not None:
        reasons.append("Od ostatniego snapshotu pojawiły się nowe sparsowane dowody.")

    fired_falsifier_id = db.scalar(
        select(ThesisFalsifier.id)
        .where(
            ThesisFalsifier.company_id == company.id,
            ThesisFalsifier.status == "fired",
        )
        .limit(1)
    )
    if fired_falsifier_id is not None:
        reasons.append("Co najmniej jeden zapisany falsyfikator został uruchomiony.")

    if (
        latest_valuation is None
        and latest_snapshot.status in {"provisional", "verified"}
    ):
        reasons.append("Brak bieżącej wyceny — założenia scenariuszy czekają na uzupełnienie.")
    elif latest_valuation is not None and latest_valuation.status in {
        "rejected",
        "needs-human",
    }:
        reasons.append("Wycena wymaga decyzji lub ponownej weryfikacji.")
    if portfolio_context is not None:
        coverage_state = portfolio_context.get("coverage_state")
        if coverage_state in {
            "research_queued",
            "research_pending",
            "research_blocked",
            "research_profile_blocked",
            "research_review_blocked",
        }:
            reasons.append(
                "Pozycja portfelowa nie ma jeszcze bieżącego zweryfikowanego Research."
            )
        elif coverage_state in {
            "research_stale",
            "falsifier_fired",
            "research_review_queued",
            "research_review_pending",
        }:
            reasons.append(
                "Pokrycie pozycji portfelowej wymaga odświeżenia Research."
            )
        elif coverage_state in {
            "valuation_queued",
            "valuation_pending",
            "valuation_blocked",
            "valuation_needs_attention",
        }:
            reasons.append("Pozycja portfelowa nie ma jeszcze bieżącej wyceny.")
    return reasons


def _summary(
    db: Session,
    case: ResearchCase,
    company: Company,
    agent: AgentRun | None,
    latest_snapshot: ResearchSnapshot | None = None,
    latest_agent: AgentRun | None = None,
    latest_valuation: ValuationSnapshot | None = None,
    portfolio_context: dict | None = None,
) -> ResearchCaseSummaryOut:
    if portfolio_context is None:
        portfolio_context = latest_portfolio_research_context(db).get(company.id)
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
        agenda_reasons=_agenda_reasons(
            db,
            company=company,
            latest_snapshot=latest_snapshot,
            latest_agent=current_agent,
            latest_valuation=latest_valuation,
            portfolio_context=portfolio_context,
        ),
        collection_progress=collection_progress,
        valuation_strip=valuation_strip,
        report_calendar=report_calendar.schedule_payload(
            db, company_id=company.id
        ),
        latest_snapshot_status=latest_snapshot.status if latest_snapshot else None,
        latest_snapshot_as_of=latest_snapshot.as_of if latest_snapshot else None,
        origin=case.origin,
        is_portfolio_holding=portfolio_context is not None,
        portfolio_weight_pct=(
            float(portfolio_context["weight_pct"])
            if portfolio_context is not None
            and portfolio_context.get("weight_pct") is not None
            else None
        ),
        portfolio_priority_score=(
            float(portfolio_context["priority_score"])
            if portfolio_context is not None
            and portfolio_context.get("priority_score") is not None
            else None
        ),
        portfolio_staleness_days=(
            int(portfolio_context["staleness_days"])
            if portfolio_context is not None
            and portfolio_context.get("staleness_days") is not None
            else None
        ),
        portfolio_coverage_state=(
            str(portfolio_context.get("coverage_state"))
            if portfolio_context is not None
            and portfolio_context.get("coverage_state") is not None
            else None
        ),
    )


def _latest_snapshot(db: Session, case_id: int) -> ResearchSnapshot | None:
    return db.scalar(
        select(ResearchSnapshot)
        .join(
            CompanyProfile,
            ResearchSnapshot.company_profile_id == CompanyProfile.id,
        )
        .where(
            ResearchSnapshot.research_case_id == case_id,
            *canonical_research_snapshot_predicate(),
            CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
        )
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
            ValuationSnapshot.status.in_(("verified", "provisional")),
            *canonical_valuation_snapshot_predicate(),
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
    return initial_research_run(db, case)


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
    ensured = ensure_research_case(
        db,
        ticker=ticker,
        origin="discover" if discovery_origin is not None else "manual",
        discovery_origin=discovery_origin,
    )
    return (
        ensured.company,
        ensured.research_case,
        ensured.agent,
        ensured.created_company,
        ensured.created_case,
        ensured.reactivated_case,
        ensured.created_job,
    )


@router.get("", response_model=list[ResearchCaseSummaryOut])
def list_research_cases(db: Session = Depends(get_db)) -> list[ResearchCaseSummaryOut]:
    rows = db.execute(
        select(ResearchCase, Company)
        .join(Company, ResearchCase.company_id == Company.id)
        .order_by(ResearchCase.updated_at.desc(), ResearchCase.id.desc())
    ).all()
    result: list[ResearchCaseSummaryOut] = []
    portfolio_contexts = latest_portfolio_research_context(db)
    for research_case, company in rows:
        agent = _initial_research_run(db, research_case)
        latest_snapshot = _latest_snapshot(db, research_case.id)
        result.append(
            _summary(
                db,
                research_case,
                company,
                agent,
                latest_snapshot,
                _latest_research_run(db, research_case),
                _latest_valuation(db, research_case.id, latest_snapshot),
                portfolio_contexts.get(company.id),
            )
        )
    result.sort(
        key=lambda item: (
            0 if item.is_portfolio_holding else (1 if item.origin == "discover" else 2),
            -(item.portfolio_priority_score or 0.0)
            if item.is_portfolio_holding
            else 0.0,
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
                .join(
                    CompanyProfile,
                    ResearchSnapshot.company_profile_id == CompanyProfile.id,
                )
                .where(
                    ResearchSnapshot.research_case_id == research_case.id,
                    *canonical_research_snapshot_predicate(),
                    CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
            )
            .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        )
    )
    latest = snapshots[0] if snapshots else None
    profiles = list(
        db.scalars(
            select(CompanyProfile)
            .where(
                CompanyProfile.research_case_id == research_case.id,
                CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
            )
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
            db,
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
        report_calendar.reconcile_latest_schedule(
            db, company_id=case.company_id
        )
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
    try:
        queued = enqueue_research_review(db, case=case)
        db.commit()
    except ResearchQueueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.refresh(queued.agent)
    return ResearchReviewQueueOut(
        agent_run_id=queued.agent.id,
        status=queued.agent.status,
        created=queued.created,
        prior_snapshot_id=queued.prior_snapshot.id,
        source_fingerprint=queued.source_fingerprint,
        profile_id=queued.profile.id,
        profile_version=queued.profile.version,
        profile_fingerprint=queued.profile_fingerprint,
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
                research_case=_summary(db, research_case, company, agent),
                agent_run=agent,
                created_company=created_company,
                created_case=created_case,
                reactivated_case=reactivated_case,
                created_job=created_job,
            )
        except ResearchQueueError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
    raise AssertionError("unreachable")
