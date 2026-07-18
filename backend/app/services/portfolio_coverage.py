"""Deterministic Portfolio-first Research and valuation coverage (VISION V7)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentRun,
    Company,
    CompanyProfile,
    InstrumentMapping,
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
    PortfolioSync,
    ResearchCase,
    ResearchSnapshot,
    ThesisFalsifier,
    ValuationSnapshot,
)
from app.services.artifact_contracts import (
    RESEARCH_PROFILE_SCHEMA,
    canonical_research_snapshot_predicate,
    canonical_valuation_snapshot_predicate,
)
from app.services.research_queue import (
    PURPOSE,
    ResearchQueueError,
    enqueue_research_review,
    ensure_research_case,
)
from app.services.valuation_engine import ValuationInputError
from app.services.valuation_queue import (
    WORKFLOW as VALUATION_WORKFLOW,
    ValuationQueueError,
    enqueue_valuation,
)


COVERAGE_VERSION = "portfolio-coverage-v1"
RESEARCH_STALE_DAYS = 30
UNCOVERED_STALENESS_DAYS = 31


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _latest_canonical_research(
    db: Session, case_id: int
) -> tuple[ResearchSnapshot | None, CompanyProfile | None]:
    row = db.execute(
        select(ResearchSnapshot, CompanyProfile)
        .join(CompanyProfile, ResearchSnapshot.company_profile_id == CompanyProfile.id)
        .where(
            ResearchSnapshot.research_case_id == case_id,
            *canonical_research_snapshot_predicate(),
            CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
        )
        .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        .limit(1)
    ).first()
    return row if row is not None else (None, None)


def _latest_profile(db: Session, case_id: int) -> CompanyProfile | None:
    return db.scalar(
        select(CompanyProfile)
        .where(
            CompanyProfile.research_case_id == case_id,
            CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
        )
        .order_by(CompanyProfile.version.desc(), CompanyProfile.id.desc())
        .limit(1)
    )


def _latest_valuation(
    db: Session, case_id: int, research_snapshot_id: int
) -> ValuationSnapshot | None:
    return db.scalar(
        select(ValuationSnapshot)
        .where(
            ValuationSnapshot.research_case_id == case_id,
            ValuationSnapshot.research_snapshot_id == research_snapshot_id,
            *canonical_valuation_snapshot_predicate(),
        )
        .order_by(ValuationSnapshot.version.desc(), ValuationSnapshot.id.desc())
        .limit(1)
    )


def _valuation_run_for_research(
    db: Session, company_id: int, research_snapshot_id: int
) -> AgentRun | None:
    rows = db.scalars(
        select(AgentRun)
        .where(
            AgentRun.company_id == company_id,
            AgentRun.workflow == VALUATION_WORKFLOW,
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).all()
    return next(
        (
            row
            for row in rows
            if ((row.inputs or {}).get("valuation") or {}).get("research_snapshot_id")
            == research_snapshot_id
        ),
        None,
    )


def _position_groups(
    db: Session, snapshot: PortfolioSnapshot
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    rows = list(
        db.scalars(
            select(PortfolioPositionSnapshot)
            .where(PortfolioPositionSnapshot.snapshot_id == snapshot.id)
            .order_by(PortfolioPositionSnapshot.id)
        )
    )
    mappings = (
        {
            row.id: row
            for row in db.scalars(
                select(InstrumentMapping).where(
                    InstrumentMapping.id.in_([item.mapping_id for item in rows])
                )
            )
        }
        if rows
        else {}
    )
    groups: dict[int, dict[str, Any]] = {}
    exclusions: list[dict[str, Any]] = []
    for row in rows:
        mapping = mappings[row.mapping_id]
        provider_type = " ".join(str(mapping.provider_type or "").split()).casefold()
        currency = str(mapping.currency or row.currency or "").strip().upper()
        reason = None
        if mapping.mapping_status == "ignored":
            reason = "mapping_ignored"
        elif mapping.mapping_kind != "company" or mapping.company_id is None:
            reason = "mapping_not_company"
        elif provider_type != "akcje gpw":
            reason = "not_gpw_equity"
        elif currency != "PLN":
            reason = "not_pln"
        if reason is not None:
            exclusions.append(
                {
                    "position_ids": [row.id],
                    "mapping_id": mapping.id,
                    "company_id": mapping.company_id,
                    "included": False,
                    "coverage_state": "excluded",
                    "reasons": [reason],
                }
            )
            continue
        group = groups.setdefault(
            mapping.company_id,
            {"position_ids": [], "mapping_ids": [], "value": 0.0},
        )
        group["position_ids"].append(row.id)
        group["mapping_ids"].append(mapping.id)
        group["value"] += float(row.value)
    return groups, exclusions


def produce_portfolio_coverage(
    db: Session,
    *,
    sync: PortfolioSync,
    snapshot: PortfolioSnapshot,
    evaluated_at: datetime,
) -> list[dict[str, Any]]:
    """Evaluate and enqueue coverage inside the successful-sync transaction."""
    groups, decisions = _position_groups(db, snapshot)
    total = float(snapshot.total_value)
    for company_id, group in groups.items():
        company = db.get(Company, company_id)
        if company is None:
            decisions.append(
                {
                    **group,
                    "company_id": company_id,
                    "included": False,
                    "coverage_state": "excluded",
                    "reasons": ["company_missing"],
                }
            )
            continue
        weight_pct = round(group["value"] / total * 100.0, 6) if total else 0.0
        case = db.scalar(
            select(ResearchCase).where(
                ResearchCase.company_id == company_id,
                ResearchCase.purpose == PURPOSE,
            ).with_for_update()
        )
        research, profile = (
            _latest_canonical_research(db, case.id) if case is not None else (None, None)
        )
        staleness_days = (
            max(0, (_aware(evaluated_at) - _aware(research.as_of)).days)
            if research is not None
            else UNCOVERED_STALENESS_DAYS
        )
        priority = round(weight_pct * staleness_days, 6)
        frozen = {
            "coverage_version": COVERAGE_VERSION,
            "portfolio_sync_id": sync.id,
            "portfolio_snapshot_id": snapshot.id,
            "evaluated_at": _aware(evaluated_at).isoformat(),
            "position_ids": list(group["position_ids"]),
            "weight_pct": weight_pct,
            "staleness_days": staleness_days,
            "priority_score": priority,
            "priority_formula": "position_weight_pct * research_staleness_days",
        }
        reasons: list[str] = []
        agent: AgentRun | None = None
        created_job = False
        if research is None:
            try:
                ensured = ensure_research_case(
                    db,
                    ticker=company.ticker,
                    origin="portfolio",
                    portfolio_coverage={**frozen, "reason": "missing_verified_research"},
                    queue_priority=priority,
                )
            except ResearchQueueError as exc:
                state = "research_blocked"
                reasons.extend(["missing_verified_research", f"queue_blocked:{exc}"])
            else:
                case = ensured.research_case
                agent = ensured.agent
                created_job = ensured.created_job
                if agent.status in {"queued", "running"}:
                    state = "research_queued" if created_job else "research_pending"
                    reasons.append("missing_verified_research")
                else:
                    current_profile = _latest_profile(db, case.id)
                    state = (
                        "research_profile_blocked"
                        if current_profile is not None
                        and current_profile.provenance == "codex-proposed"
                        else "research_blocked"
                    )
                    reasons.extend(
                        ["missing_verified_research", f"initial_job_{agent.status}"]
                    )
                    if state == "research_profile_blocked":
                        reasons.append("profile_not_human_confirmed")
        else:
            fired = db.scalar(
                select(ThesisFalsifier.id)
                .where(
                    ThesisFalsifier.company_id == company_id,
                    ThesisFalsifier.status == "fired",
                )
                .limit(1)
            )
            review_reason = None
            if research.status != "verified":
                review_reason = f"current_research_{research.status}"
                reasons.append(review_reason)
            if fired is not None:
                review_reason = review_reason or "current_falsifier_fired"
                reasons.append("current_falsifier_fired")
            if staleness_days > RESEARCH_STALE_DAYS:
                review_reason = review_reason or "research_older_than_30_days"
                reasons.append("research_older_than_30_days")
            if review_reason is not None:
                try:
                    queued_review = enqueue_research_review(
                        db,
                        case=case,
                        trigger="portfolio-sync-coverage",
                        queue_priority=priority,
                        portfolio_coverage={**frozen, "reason": review_reason},
                        changed_by="portfolio-sync-coverage",
                    )
                except ResearchQueueError as exc:
                    detail = str(exc)
                    state = (
                        "research_profile_blocked"
                        if "profile" in detail.casefold()
                        else "research_review_blocked"
                    )
                    reasons.append(f"review_blocked:{detail}")
                else:
                    agent = queued_review.agent
                    created_job = queued_review.created
                    if agent.status in {"queued", "running"}:
                        state = (
                            "research_review_queued"
                            if queued_review.created
                            else "research_review_pending"
                        )
                    else:
                        state = "research_review_blocked"
                        reasons.append(f"review_job_{agent.status}")
            else:
                valuation = _latest_valuation(db, case.id, research.id)
                if valuation is not None:
                    if valuation.status == "verified":
                        state = "covered"
                    else:
                        state = "valuation_needs_attention"
                        reasons.append(f"current_valuation_{valuation.status}")
                else:
                    existing = _valuation_run_for_research(db, company_id, research.id)
                    if existing is not None:
                        agent = existing
                        if existing.status == "queued":
                            existing.queue_priority = priority
                            existing.inputs = {
                                **(existing.inputs or {}),
                                "portfolio_coverage": {
                                    **frozen,
                                    "reason": "missing_current_valuation",
                                },
                            }
                        if existing.status in {"queued", "running"}:
                            state = "valuation_pending"
                            reasons.append("missing_current_valuation")
                        else:
                            state = "valuation_blocked"
                            reasons.append(f"valuation_job_{existing.status}")
                    else:
                        try:
                            queued = enqueue_valuation(
                                db,
                                case=case,
                                research_snapshot_id=research.id,
                                as_of=_aware(evaluated_at),
                                trigger="portfolio-sync-coverage",
                                queue_priority=priority,
                                portfolio_coverage={
                                    **frozen,
                                    "reason": "missing_current_valuation",
                                },
                            )
                        except (ValuationInputError, ValuationQueueError) as exc:
                            state = "valuation_blocked"
                            reasons.extend(
                                ["missing_current_valuation", f"input_blocked:{exc}"]
                            )
                        else:
                            agent = queued.agent
                            created_job = queued.created
                            state = "valuation_queued" if queued.created else "valuation_pending"
                            reasons.append("missing_current_valuation")
        decisions.append(
            {
                **frozen,
                "mapping_ids": list(group["mapping_ids"]),
                "company_id": company_id,
                "ticker": company.ticker,
                "research_case_id": case.id if case is not None else None,
                "research_origin": case.origin if case is not None else None,
                "research_snapshot_id": research.id if research is not None else None,
                "included": True,
                "coverage_state": state,
                "reasons": reasons,
                "agent_run_id": agent.id if agent is not None else None,
                "created_job": created_job,
            }
        )
    sync.coverage_version = COVERAGE_VERSION
    sync.coverage_evaluated_at = evaluated_at
    sync.coverage_decisions = decisions
    return decisions


def latest_portfolio_research_context(db: Session) -> dict[int, dict[str, Any]]:
    """Read frozen holding context from the latest successful sync log."""
    sync = db.scalar(
        select(PortfolioSync)
        .where(
            PortfolioSync.status == "succeeded",
            PortfolioSync.coverage_version == COVERAGE_VERSION,
        )
        .order_by(PortfolioSync.requested_at.desc(), PortfolioSync.id.desc())
        .limit(1)
    )
    if sync is None:
        return {}
    return {
        int(row["company_id"]): row
        for row in (sync.coverage_decisions or [])
        if isinstance(row, dict)
        and row.get("included") is True
        and row.get("company_id") is not None
    }
