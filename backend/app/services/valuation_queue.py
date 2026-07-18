"""Canonical valuation job producer shared by explicit and Portfolio paths."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentRun, ResearchCase
from app.services.model_policy import default_model_for_workflow
from app.services.valuation_artifacts import CONTRACT_VERSION, SKILL_VERSION
from app.services.valuation_engine import (
    ENGINE_VERSION,
    TEMPLATE_CONTRACT_VERSION,
    prepare_valuation_base,
)


WORKFLOW = "stock-company-valuation"


class ValuationQueueError(ValueError):
    pass


@dataclass(frozen=True)
class ValuationQueueResult:
    agent: AgentRun
    created: bool
    input_fingerprint: str


def enqueue_valuation(
    db: Session,
    *,
    case: ResearchCase,
    research_snapshot_id: int,
    as_of: datetime,
    trigger: str = "valuation-command",
    queue_priority: float = 0.0,
    portfolio_coverage: dict | None = None,
) -> ValuationQueueResult:
    """Freeze one valuation base and add/reuse its canonical durable job."""
    base = prepare_valuation_base(
        db,
        case=case,
        research_snapshot_id=research_snapshot_id,
        as_of=as_of,
    )
    key = f"valuation:{case.id}:{base['input_fingerprint']}"
    existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
    if existing is not None:
        if existing.status in {"failed", "rejected", "needs-human"}:
            raise ValuationQueueError(
                "The matching canonical valuation attempt ended in "
                f"'{existing.status}' and requires an explicit review before retry."
            )
        if portfolio_coverage is not None and existing.status == "queued":
            existing.queue_priority = queue_priority
            existing.inputs = {
                **(existing.inputs or {}),
                "portfolio_coverage": portfolio_coverage,
            }
        return ValuationQueueResult(
            agent=existing,
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
        active_valuation = (active_peer.inputs or {}).get("valuation") or {}
        if active_valuation.get("research_snapshot_id") == research_snapshot_id:
            return ValuationQueueResult(
                agent=active_peer,
                created=False,
                input_fingerprint=str(
                    active_valuation.get("input_fingerprint")
                    or base["input_fingerprint"]
                ),
            )
        raise ValuationQueueError(
            "Another valuation for this company is already queued or running; "
            "finish it before freezing different inputs."
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
    inputs = {
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
    }
    if portfolio_coverage is not None:
        inputs["portfolio_coverage"] = portfolio_coverage
    agent = AgentRun(
        workflow=WORKFLOW,
        trigger=trigger,
        status="queued",
        company_id=case.company_id,
        model_role="analyst_deep",
        model=model,
        orchestrator_model=model,
        idempotency_key=key,
        queue_priority=queue_priority,
        inputs=inputs,
        outputs={},
    )
    db.add(agent)
    db.flush()
    return ValuationQueueResult(
        agent=agent,
        created=True,
        input_fingerprint=base["input_fingerprint"],
    )
