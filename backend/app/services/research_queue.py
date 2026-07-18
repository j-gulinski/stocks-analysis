"""Canonical ResearchCase and initial-job producer shared by every entry path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.services.artifact_contracts import (
    RESEARCH_PROFILE_SCHEMA,
    canonical_research_snapshot_predicate,
)
from app.services.company_profiles import frozen_profile
from app.services.model_policy import default_model_for_workflow


PURPOSE = "investment-research"
INITIAL_WORKFLOW = "stock-initial-research"
REVIEW_WORKFLOW = "stock-company-review"
SKILL_VERSION = "company-research-v3"
OUTPUT_CONTRACT_VERSION = "research-snapshot-v3"
PROFILE_SCHEMA_VERSION = "company-profile-v2"
ARCHETYPE_CONTRACT_VERSION = "archetype-packs-v1"
RESEARCH_ORIGINS = {"manual", "discover", "portfolio"}


class ResearchQueueError(ValueError):
    pass


@dataclass(frozen=True)
class ResearchEnsureResult:
    company: Company
    research_case: ResearchCase
    agent: AgentRun
    created_company: bool
    created_case: bool
    reactivated_case: bool
    created_job: bool


@dataclass(frozen=True)
class ResearchReviewQueueResult:
    agent: AgentRun
    created: bool
    prior_snapshot: ResearchSnapshot
    source_fingerprint: str
    profile: CompanyProfile
    profile_fingerprint: str


def initial_run_key(case_id: int) -> str:
    return f"research-case-initial-research:{case_id}"


def initial_research_run(db: Session, case: ResearchCase) -> AgentRun | None:
    """Return the stable initial run, including pre-key canonical rows."""
    keyed = db.scalar(
        select(AgentRun).where(AgentRun.idempotency_key == initial_run_key(case.id))
    )
    if keyed is not None:
        return keyed
    return db.scalar(
        select(AgentRun)
        .where(
            AgentRun.workflow == INITIAL_WORKFLOW,
            AgentRun.company_id == case.company_id,
            AgentRun.inputs["research_case_id"].as_integer() == case.id,
        )
        .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
        .limit(1)
    )


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


def enqueue_research_review(
    db: Session,
    *,
    case: ResearchCase,
    trigger: str = "research-review-command",
    queue_priority: float = 0.0,
    portfolio_coverage: dict | None = None,
    changed_by: str = "user-command",
    available_at: datetime | None = None,
    report_calendar: dict | None = None,
) -> ResearchReviewQueueResult:
    """Freeze and enqueue the sole canonical Research refresh workflow."""
    company = db.get(Company, case.company_id)
    if company is None:
        raise ResearchQueueError("Research company is missing.")
    latest_snapshot = db.scalar(
        select(ResearchSnapshot)
        .join(
            CompanyProfile,
            ResearchSnapshot.company_profile_id == CompanyProfile.id,
        )
        .where(
            ResearchSnapshot.research_case_id == case.id,
            *canonical_research_snapshot_predicate(),
            CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
        )
        .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        .limit(1)
    )
    if latest_snapshot is None:
        raise ResearchQueueError(
            "Complete the initial Research snapshot before queuing a review."
        )
    profile = db.scalar(
        select(CompanyProfile)
        .where(
            CompanyProfile.research_case_id == case.id,
            CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
        )
        .order_by(CompanyProfile.version.desc(), CompanyProfile.id.desc())
        .limit(1)
    )
    if profile is None:
        raise ResearchQueueError("The latest Research snapshot has no company profile.")
    if profile.provenance == "codex-proposed":
        raise ResearchQueueError(
            "Confirm or correct the latest company profile before queuing a Research review."
        )
    source_questions = (profile.company_overlay or {}).get("source_questions") or []
    if not source_questions:
        raise ResearchQueueError(
            "Add at least one company-specific source question to the confirmed profile "
            "before queuing a Research review."
        )
    frozen = frozen_profile(profile)
    source_fingerprint, source_manifest = _review_source_state(db, company.id)
    review_identity = ":".join(
        (
            str(latest_snapshot.id),
            latest_snapshot.artifact_fingerprint,
            source_fingerprint,
            frozen["fingerprint"],
        )
    )
    review_fingerprint = hashlib.sha256(review_identity.encode("utf-8")).hexdigest()
    key = f"research-case-review:{case.id}:{review_fingerprint}"
    existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
    if existing is not None:
        accelerated = False
        if existing.status == "queued":
            if trigger == "report-calendar":
                if existing.available_at is not None and available_at is not None:
                    existing.available_at = available_at
            elif existing.available_at is not None:
                # An explicit/portfolio refresh accelerates the same frozen
                # review instead of creating a competing implementation path.
                existing.available_at = None
                existing.trigger = trigger
                accelerated = True
            if report_calendar is not None:
                existing.inputs = {
                    **(existing.inputs or {}),
                    "report_calendar": report_calendar,
                }
        if portfolio_coverage is not None and existing.status == "queued":
            existing.queue_priority = queue_priority
            existing.inputs = {
                **(existing.inputs or {}),
                "portfolio_coverage": portfolio_coverage,
            }
        if accelerated:
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
                    reason="Research: przyspieszono zaplanowane odświeżenie.",
                    changed_by=changed_by,
                )
            )
        return ResearchReviewQueueResult(
            agent=existing,
            created=False,
            prior_snapshot=latest_snapshot,
            source_fingerprint=source_fingerprint,
            profile=profile,
            profile_fingerprint=frozen["fingerprint"],
        )
    active_peer = db.scalar(
        select(AgentRun).where(
            AgentRun.company_id == company.id,
            AgentRun.workflow.in_((INITIAL_WORKFLOW, REVIEW_WORKFLOW)),
            AgentRun.status.in_(("queued", "running")),
        )
    )
    if active_peer is not None:
        raise ResearchQueueError(
            "Another Research collection for this company is already queued or running."
        )
    model = default_model_for_workflow(REVIEW_WORKFLOW)
    inputs = {
        "ticker": company.ticker,
        "research_case_id": case.id,
        "task": {
            "skill": "company-research",
            "skill_version": SKILL_VERSION,
            "output_contract_version": OUTPUT_CONTRACT_VERSION,
            "company_profile_schema_version": PROFILE_SCHEMA_VERSION,
            "archetype_contract_version": ARCHETYPE_CONTRACT_VERSION,
            "objective": (
                "Refresh one existing company case, resolve its source questions, "
                "compare forward drivers with the prior immutable snapshot and save "
                "the next verified snapshot."
            ),
            "refresh_scope": "all",
            "required_verification": "verifier_strict",
            "research_list_policy": "do not add automatically",
        },
        "review": {
            "prior_research_snapshot_id": latest_snapshot.id,
            "prior_artifact_fingerprint": latest_snapshot.artifact_fingerprint,
            "queued_source_fingerprint": source_fingerprint,
            "queued_source_manifest": source_manifest,
            "confirmed_company_profile": frozen,
        },
    }
    if portfolio_coverage is not None:
        inputs["portfolio_coverage"] = portfolio_coverage
    if report_calendar is not None:
        inputs["report_calendar"] = report_calendar
    agent = AgentRun(
        workflow=REVIEW_WORKFLOW,
        trigger=trigger,
        status="queued",
        company_id=company.id,
        model_role="worker_standard",
        model=model,
        orchestrator_model=model,
        idempotency_key=key,
        queue_priority=queue_priority,
        available_at=available_at,
        inputs=inputs,
        outputs={},
    )
    db.add(agent)
    db.flush()
    now = utcnow()
    if available_at is None or available_at <= now:
        previous_state, previous_step = case.state, case.current_step
        case.state = "ingesting"
        case.current_step = "ingest"
        case.blocked_reason = None
        case.updated_at = now
        db.add(
            ResearchCaseStepHistory(
                research_case_id=case.id,
                from_state=previous_state,
                from_step=previous_step,
                to_state="ingesting",
                to_step="ingest",
                reason=(
                    "Portfolio: automatycznie zlecono odświeżenie pokrycia Research."
                    if trigger == "portfolio-sync-coverage"
                    else "Research: jawnie zlecono odświeżenie istniejącego snapshotu."
                ),
                changed_by=changed_by,
            )
        )
    return ResearchReviewQueueResult(
        agent=agent,
        created=True,
        prior_snapshot=latest_snapshot,
        source_fingerprint=source_fingerprint,
        profile=profile,
        profile_fingerprint=frozen["fingerprint"],
    )


def ensure_research_case(
    db: Session,
    *,
    ticker: str,
    origin: str,
    discovery_origin: dict | None = None,
    portfolio_coverage: dict | None = None,
    queue_priority: float = 0.0,
) -> ResearchEnsureResult:
    """Ensure one durable case and one canonical initial Research job.

    Origin is immutable once the case exists. Portfolio sync may add scheduling
    context to an unclaimed initial job without changing a manual/Discover case's
    origin.
    """
    if origin not in RESEARCH_ORIGINS:
        raise ResearchQueueError(f"Unsupported Research origin: {origin}.")
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
            ResearchCase.purpose == PURPOSE,
        )
    )
    created_case = research_case is None
    if research_case is None:
        research_case = ResearchCase(
            company_id=company.id,
            purpose=PURPOSE,
            origin=origin,
            state="ingesting",
            current_step="ingest",
            as_of=utcnow(),
        )
        db.add(research_case)
        db.flush()
        reason = (
            "Portfolio: utworzono sprawę dla pozycji i zlecono pierwszy research."
            if origin == "portfolio"
            else "Research Lab: utworzono sprawę i zlecono pierwszy research."
        )
        db.add(
            ResearchCaseStepHistory(
                research_case_id=research_case.id,
                from_state=None,
                from_step=None,
                to_state="ingesting",
                to_step="ingest",
                reason=reason,
            )
        )

    agent = initial_research_run(db, research_case)
    if agent is not None and (
        agent.workflow != INITIAL_WORKFLOW or agent.company_id != company.id
    ):
        raise ResearchQueueError(
            "Initial-research idempotency key points to an inconsistent job."
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
        model = default_model_for_workflow(INITIAL_WORKFLOW)
        inputs = {
            "ticker": company.ticker,
            "research_case_id": research_case.id,
            "task": {
                "skill": "company-research",
                "skill_version": SKILL_VERSION,
                "output_contract_version": OUTPUT_CONTRACT_VERSION,
                "company_profile_schema_version": PROFILE_SCHEMA_VERSION,
                "archetype_contract_version": ARCHETYPE_CONTRACT_VERSION,
                "objective": (
                    "Refresh one company, resolve its source questions and save a "
                    "tailored forward-looking first snapshot."
                ),
                "refresh_scope": "all",
                "required_verification": "verifier_strict",
                "research_list_policy": "do not add automatically",
            },
        }
        if discovery_origin is not None:
            inputs["discovery_origin"] = discovery_origin
        if portfolio_coverage is not None:
            inputs["portfolio_coverage"] = portfolio_coverage
        agent = AgentRun(
            workflow=INITIAL_WORKFLOW,
            trigger=(
                "portfolio-sync-coverage" if origin == "portfolio" else "research-lab"
            ),
            status="queued",
            company_id=company.id,
            model_role="worker_standard",
            model=model,
            orchestrator_model=model,
            idempotency_key=initial_run_key(research_case.id),
            queue_priority=queue_priority,
            inputs=inputs,
            outputs={},
        )
        db.add(agent)
        db.flush()
    elif portfolio_coverage is not None and agent.status == "queued":
        # The job has not been claimed, so its current portfolio scheduling basis
        # can be frozen before a worker consumes it.
        agent.queue_priority = queue_priority
        agent.inputs = {**(agent.inputs or {}), "portfolio_coverage": portfolio_coverage}

    return ResearchEnsureResult(
        company=company,
        research_case=research_case,
        agent=agent,
        created_company=created_company,
        created_case=created_case,
        reactivated_case=reactivated_case,
        created_job=created_job,
    )
