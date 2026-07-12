"""Frozen queue, independent verification and immutable save for portfolio review."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    PortfolioReviewDraftIn,
    PortfolioReviewSaveIn,
    PortfolioReviewVerificationIn,
    PortfolioReviewVerifierResult,
)
from app.db.models import (
    AgentRun,
    InstrumentMapping,
    Portfolio,
    PortfolioPositionSnapshot,
    PortfolioReviewSnapshot,
    PortfolioSnapshot,
    ResearchCase,
    ResearchSnapshot,
    CompanyProfile,
    ValuationSnapshot,
    VerificationRun,
    utcnow,
)
from app.services.agent_queue import clear_agent_lease
from app.services.model_policy import default_model_for_workflow, get_model_policy
from app.services.portfolio import portfolio_workspace
from app.services.valuation_engine import canonical_hash

WORKFLOW = "stock-portfolio-review"
SKILL_VERSION = "portfolio-review-v1"
CONTRACT_VERSION = "portfolio-review-v1"
ANALYTICS_VERSION = "portfolio-analytics-v1"
_TRANSACTION_OBJECT = (
    r"(?:pozycj(?:ę|i)|akcj(?:e|i)|walor(?:y|ów)|udział(?:y|u)?|papiery|papierów|"
    r"spółk(?:ę|i)|ekspozycj(?:ę|i)|koncentracj(?:ę|i)|gotówk(?:ę|i))"
)
_UNAMBIGUOUS_TRANSACTION_ACTION = (
    r"(?:sprzedaż|sprzedaży|sprzedać|sprzedawanie|sprzedawać|kupno|kupna|kupić|"
    r"kupować|dokupienie|dokupowania|dokupić|dokupować)"
)
_AMBIGUOUS_ACTION = (
    r"(?:zwiększenie|zwiększyć|zmniejszenie|zmniejszyć|redukcję|redukować|zredukować|"
    r"zamknięcie|zamknąć|utrzymanie|utrzymywać|trzymanie|trzymać|zachowanie|"
    r"zachować|wyjście|wyjść)"
)
_ADVICE_INTENT = (
    r"(?:zalecam|rekomenduję|proponuję|sugeruję|rozważ|warto|najlepiej|"
    r"powinieneś|powinno\s+się|należy|nie\s+należy|trzeba|unikaj)"
)
_TRANSACTION_TARGET_OR_END = (
    rf"(?:\s+(?:z\s+)?(?:(?:tej|tę|swojej|swoją)\s+)?{_TRANSACTION_OBJECT}"
    rf"|(?=\s*(?:[,.;:!?]|$)))"
)
_ADVICE = re.compile(
    rf"(?:"
    # Direct imperatives need a portfolio object or a deliberate clause boundary.
    rf"\b(?:kup|kupuj|sprzedaj|sprzedawaj|dokup|dokupuj)"
    rf"{_TRANSACTION_TARGET_OR_END}|"
    # Ambiguous imperatives are blocked only with an investment/portfolio object.
    rf"\b(?:zwiększ|zmniejsz|redukuj|zredukuj|zachowaj|trzymaj|utrzymaj|zamknij)\s+"
    rf"(?:(?:tę|tej|swoją|swojej)\s+)?{_TRANSACTION_OBJECT}\b|"
    rf"\bwyjdź\s+z\s+(?:(?:tej|swojej)\s+)?pozycji\b|"
    rf"\bpozbądź\s+się\s+(?:(?:tej|swojej)\s+)?{_TRANSACTION_OBJECT}\b|"
    # Intent-led actions need a portfolio object or must end the clause.
    rf"\b{_ADVICE_INTENT}\s*,?\s*(?:(?:aby|żeby|rozważyć)\s+)?"
    rf"(?:{_UNAMBIGUOUS_TRANSACTION_ACTION}|{_AMBIGUOUS_ACTION})"
    rf"{_TRANSACTION_TARGET_OR_END}|"
    rf"\bnie\s+(?:kupuj|dokupuj|sprzedawaj|sprzedaj)"
    rf"(?:{_TRANSACTION_TARGET_OR_END}|\s+(?:teraz|dziś|obecnie|jeszcze)\b)|"
    rf"\bnie\s+(?:redukuj|zamykaj|wychodź){_TRANSACTION_TARGET_OR_END}|"
    rf"\bwstrzymaj\s+się\s+od\s+(?:kupna|sprzedaży|dokupienia)\b"
    rf")",
    re.IGNORECASE,
)


def _json_safe(value: Any) -> Any:
    def encode(item: Any) -> str:
        if hasattr(item, "isoformat"):
            return item.isoformat()
        return str(item)

    return json.loads(json.dumps(value, ensure_ascii=False, default=encode))


class PortfolioReviewArtifactError(ValueError):
    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _aware(value)
    return _aware(datetime.fromisoformat(str(value)))


def portfolio_review_draft_fingerprint(draft: PortfolioReviewDraftIn) -> str:
    return canonical_hash(draft.model_dump(mode="json"))


def _review_gaps(workspace: dict[str, Any]) -> list[str]:
    gaps = list(workspace["snapshot"].get("gaps") or [])
    coverage = workspace.get("coverage") or {}
    if coverage.get("unmapped_positions"):
        gaps.append("Portfel zawiera niezmapowane instrumenty.")
    liquidity = workspace.get("liquidity") or []
    if any(row.get("status") == "unavailable" for row in liquidity):
        gaps.append("Dla części pozycji nie ma pełnej podstawy płynności z 20 sesji.")
    sensitivity = workspace.get("scenario_sensitivity") or {}
    if sensitivity.get("exclusions"):
        gaps.append(
            "Nie wszystkie pozycje mają kwalifikującą się zweryfikowaną wycenę."
        )
    methods = workspace.get("performance_methods") or {}
    if methods.get("twr") == "unavailable" or methods.get("xirr") == "unavailable":
        gaps.append("Brak przepływów wymaganych do niezależnego TWR/XIRR.")
    risk_companies = (workspace.get("risk_context") or {}).get("companies") or []
    if any((row.get("research") or {}).get("stale") for row in risk_companies):
        gaps.append("Co najmniej jedna pozycja ma brakujące lub nieaktualne Research.")
    if any(row.get("snapshot_known_fired_count", 0) for row in risk_companies):
        gaps.append(
            "Co najmniej jedna pozycja miała znany w dacie snapshotu falsyfikator fired."
        )
    if any(row.get("current_only_fired_count", 0) for row in risk_companies):
        gaps.append(
            "Co najmniej jedna pozycja ma bieżący falsyfikator fired nieznany w dacie snapshotu."
        )
    if any(row.get("falsifiers") for row in risk_companies):
        gaps.append("Statusy falsyfikatorów są bieżące; brak historii punkt-w-czasie.")
    return list(dict.fromkeys(str(gap) for gap in gaps if str(gap).strip()))


def freeze_portfolio_review_inputs(
    db: Session, portfolio: Portfolio, snapshot: PortfolioSnapshot
) -> dict[str, Any]:
    """Freeze only stored state; this function never fetches or repairs mappings."""
    workspace = portfolio_workspace(db, snapshot)
    reconciliation = workspace.get("reconciliation") or {}
    if reconciliation.get("status") != "reconciled":
        raise PortfolioReviewArtifactError(
            "Portfolio positions do not reconcile to the provider total.",
            kind="conflict",
        )
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
                    InstrumentMapping.id.in_([position.mapping_id for position in rows])
                )
            )
        }
        if rows
        else {}
    )
    if not rows:
        raise PortfolioReviewArtifactError(
            "A stored portfolio snapshot with retained positions is required.",
            kind="conflict",
        )
    positions = [
        {
            "position_snapshot_id": row.id,
            "provider_row_key": row.provider_row_key,
            "mapping_id": row.mapping_id,
            "snapshot_mapping_kind": row.mapping_kind,
            "snapshot_mapping_status": row.mapping_status,
            "current_mapping_kind": mappings[row.mapping_id].mapping_kind,
            "current_mapping_status": mappings[row.mapping_id].mapping_status,
            "current_company_id": mappings[row.mapping_id].company_id,
            "ticker": row.ticker,
            "sector": row.sector,
            "asset_type": row.asset_type,
            "currency": row.currency,
            "quantity": float(row.quantity) if row.quantity is not None else None,
            "value": float(row.value),
        }
        for row in rows
    ]
    analytics = _json_safe(
        {
            "snapshot": workspace["snapshot"],
            "reconciliation": reconciliation,
            "concentration": workspace["concentration"],
            "history": workspace["history"],
            "history_quality": workspace["history_quality"],
            "liquidity": workspace["liquidity"],
            "scenario_sensitivity": workspace["scenario_sensitivity"],
            "risk_context": workspace["risk_context"],
            "performance_methods": workspace["performance_methods"],
            "coverage": workspace["coverage"],
        }
    )
    analytics_fingerprint = canonical_hash(analytics)
    risk_context_fingerprint = canonical_hash(analytics["risk_context"])
    eligible = [
        {
            "position_snapshot_id": row["position_id"],
            "valuation_snapshot_id": row["valuation_snapshot_id"],
            "valuation_fingerprint": row["valuation_fingerprint"],
        }
        for row in (workspace["scenario_sensitivity"] or {}).get("covered", [])
    ]
    manifest = {
        "portfolio": {
            "id": portfolio.id,
            "provider": portfolio.provider,
            "provider_ref": portfolio.provider_ref,
            "name": portfolio.name,
        },
        "snapshot": {
            "id": snapshot.id,
            "version": snapshot.version,
            "as_of": _aware(snapshot.as_of).isoformat(),
            "input_fingerprint": snapshot.input_fingerprint,
        },
        "positions": positions,
        "analytics": analytics,
        "analytics_version": ANALYTICS_VERSION,
        "analytics_fingerprint": analytics_fingerprint,
        "risk_context_version": analytics["risk_context"]["version"],
        "risk_context_fingerprint": risk_context_fingerprint,
        "history_method": workspace["performance_methods"],
        "eligible_valuations": eligible,
        "scenario_exclusions": (workspace["scenario_sensitivity"] or {}).get(
            "exclusions", []
        ),
        "gaps": _review_gaps(workspace),
        "skill_version": SKILL_VERSION,
        "contract_version": CONTRACT_VERSION,
    }
    return {**manifest, "input_fingerprint": canonical_hash(manifest)}


def queue_portfolio_review(
    db: Session, portfolio: Portfolio, snapshot: PortfolioSnapshot
) -> tuple[AgentRun, bool]:
    frozen = freeze_portfolio_review_inputs(db, portfolio, snapshot)
    key = f"portfolio-review:{frozen['input_fingerprint']}"
    existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
    if existing is not None:
        return existing, False
    model = default_model_for_workflow(WORKFLOW)
    policy = get_model_policy(WORKFLOW)
    agent = AgentRun(
        workflow=WORKFLOW,
        trigger="manual",
        status="queued",
        model_role=policy["draft_role"],
        model=model,
        orchestrator_model=model,
        idempotency_key=key,
        inputs={
            "task": {
                "skill_version": SKILL_VERSION,
                "output_contract_version": CONTRACT_VERSION,
                "analytics_version": ANALYTICS_VERSION,
                "draft_model_role": policy["draft_role"],
                "draft_model": policy["draft_model"],
                "draft_reasoning_effort": policy["draft_reasoning_effort"],
                "verifier_model_role": policy["required_verifier_role"],
                "verifier_model": policy["verifier_model"],
                "verifier_reasoning_effort": policy["verifier_reasoning_effort"],
            },
            "portfolio_review": frozen,
        },
        outputs={},
    )
    db.add(agent)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == key))
        if raced is None:
            raise
        return raced, False
    db.refresh(agent)
    return agent, True


def _frozen(agent: AgentRun) -> dict[str, Any]:
    frozen = (agent.inputs or {}).get("portfolio_review")
    if not isinstance(frozen, dict):
        raise PortfolioReviewArtifactError(
            "Run has no frozen portfolio review.", kind="conflict"
        )
    return frozen


def _validate_run(
    db: Session, draft: PortfolioReviewDraftIn
) -> tuple[AgentRun, dict[str, Any]]:
    agent = db.get(AgentRun, draft.agent_run_id)
    if agent is None:
        raise PortfolioReviewArtifactError("Unknown agent run.", kind="not-found")
    task = (agent.inputs or {}).get("task") or {}
    policy = get_model_policy(WORKFLOW)
    if (
        agent.workflow != WORKFLOW
        or agent.status != "running"
        or task.get("skill_version") != SKILL_VERSION
        or task.get("output_contract_version") != CONTRACT_VERSION
        or task.get("analytics_version") != ANALYTICS_VERSION
        or task.get("draft_model_role") != agent.model_role
        or task.get("draft_model") != agent.model
        or draft.requested_model_role != task.get("draft_model_role")
        or draft.requested_model != task.get("draft_model")
        or draft.reasoning_effort != task.get("draft_reasoning_effort")
        or task.get("verifier_model_role") != "verifier_strict"
        or task.get("draft_model_role") != policy.get("draft_role")
        or task.get("draft_model") != policy.get("draft_model")
        or task.get("draft_reasoning_effort") != policy.get("draft_reasoning_effort")
        or task.get("verifier_model") != policy.get("verifier_model")
        or task.get("verifier_reasoning_effort")
        != policy.get("verifier_reasoning_effort")
    ):
        raise PortfolioReviewArtifactError(
            "Run status/version does not authorize review.", kind="conflict"
        )
    if (
        not agent.lease_owner
        or not agent.lease_expires_at
        or _aware(agent.lease_expires_at) <= utcnow()
    ):
        raise PortfolioReviewArtifactError(
            "Portfolio review requires a live claimed lease.", kind="conflict"
        )
    if draft.lease_owner != agent.lease_owner:
        raise PortfolioReviewArtifactError(
            "Drafting worker does not own this lease.", kind="conflict"
        )
    return agent, _frozen(agent)


def _validate_version(db: Session, draft: PortfolioReviewDraftIn) -> None:
    latest = db.scalar(
        select(PortfolioReviewSnapshot)
        .where(PortfolioReviewSnapshot.portfolio_id == draft.portfolio_id)
        .order_by(PortfolioReviewSnapshot.version.desc())
        .limit(1)
    )
    if draft.version != (latest.version if latest else 0) + 1:
        raise PortfolioReviewArtifactError(
            "Portfolio review version is not sequential.", kind="conflict"
        )


def _validate_frozen_integrity(
    db: Session, draft: PortfolioReviewDraftIn, *, allow_mapping_drift: bool = False
) -> tuple[AgentRun, bool]:
    agent, frozen = _validate_run(db, draft)
    expected = {
        "portfolio_id": frozen["portfolio"]["id"],
        "portfolio_snapshot_id": frozen["snapshot"]["id"],
        "as_of": frozen["snapshot"]["as_of"],
        "input_manifest": {
            key: value for key, value in frozen.items() if key != "input_fingerprint"
        },
        "gaps": frozen["gaps"],
        "input_fingerprint": frozen["input_fingerprint"],
        "analytics_fingerprint": frozen["analytics_fingerprint"],
    }
    actual = {
        "portfolio_id": draft.portfolio_id,
        "portfolio_snapshot_id": draft.portfolio_snapshot_id,
        "as_of": draft.as_of.isoformat(),
        "input_manifest": draft.input_manifest,
        "gaps": draft.gaps,
        "input_fingerprint": draft.input_fingerprint,
        "analytics_fingerprint": draft.analytics_fingerprint,
    }
    if actual != expected:
        raise PortfolioReviewArtifactError(
            "Draft differs from its frozen portfolio inputs.", kind="conflict"
        )
    snapshot = db.get(PortfolioSnapshot, draft.portfolio_snapshot_id)
    if (
        snapshot is None
        or snapshot.portfolio_id != draft.portfolio_id
        or snapshot.input_fingerprint != frozen["snapshot"]["input_fingerprint"]
        or _aware(snapshot.as_of).isoformat() != frozen["snapshot"]["as_of"]
    ):
        raise PortfolioReviewArtifactError(
            "Portfolio snapshot identity changed.", kind="conflict"
        )
    if canonical_hash(frozen["analytics"]) != draft.analytics_fingerprint:
        raise PortfolioReviewArtifactError(
            "Frozen portfolio analytics fingerprint is invalid.", kind="conflict"
        )
    if canonical_hash(frozen["analytics"].get("risk_context")) != frozen.get(
        "risk_context_fingerprint"
    ) or (frozen["analytics"].get("risk_context") or {}).get("version") != frozen.get(
        "risk_context_version"
    ):
        raise PortfolioReviewArtifactError(
            "Frozen portfolio risk context fingerprint is invalid.", kind="conflict"
        )
    reconciliation = frozen["analytics"].get("reconciliation") or {}
    if reconciliation.get("status") != "reconciled":
        raise PortfolioReviewArtifactError(
            "Frozen portfolio reconciliation is not valid.", kind="conflict"
        )
    _validate_risk_context(db, frozen, snapshot)
    retained_total = sum(row["value"] for row in frozen["positions"])
    total = float(frozen["analytics"]["snapshot"]["total_value"])
    if abs(retained_total - total) > max(0.02, total * 0.001):
        raise PortfolioReviewArtifactError(
            "Frozen retained positions do not reconcile.", kind="conflict"
        )
    mapping_drift = False
    for row in frozen["positions"]:
        position = db.get(PortfolioPositionSnapshot, row["position_snapshot_id"])
        mapping = db.get(InstrumentMapping, row["mapping_id"])
        if (
            position is None
            or position.snapshot_id != snapshot.id
            or position.provider_row_key != row["provider_row_key"]
            or float(position.value) != row["value"]
        ):
            raise PortfolioReviewArtifactError(
                "Frozen retained position set changed.", kind="conflict"
            )
        if (
            mapping is None
            or mapping.mapping_kind != row["current_mapping_kind"]
            or mapping.mapping_status != row["current_mapping_status"]
            or mapping.company_id != row["current_company_id"]
        ):
            mapping_drift = True
    if mapping_drift and not allow_mapping_drift:
        raise PortfolioReviewArtifactError(
            "Mapping state changed after queueing.", kind="conflict"
        )
    for eligible in frozen["eligible_valuations"]:
        valuation = db.get(ValuationSnapshot, eligible["valuation_snapshot_id"])
        if (
            valuation is None
            or valuation.status != "verified"
            or valuation.artifact_fingerprint != eligible["valuation_fingerprint"]
            or _aware(valuation.as_of) > _aware(snapshot.as_of)
        ):
            raise PortfolioReviewArtifactError(
                "Eligible valuation identity/look-ahead failed.", kind="conflict"
            )
    methods = frozen["history_method"]
    if methods != frozen["analytics"]["performance_methods"]:
        raise PortfolioReviewArtifactError(
            "History/benchmark method labels changed.", kind="conflict"
        )
    if (
        methods.get("provider_return") != "provider-reported"
        or methods.get("benchmark")
        != "provider-reported; total-return basis unverified"
        or methods.get("twr") != "unavailable"
        or methods.get("xirr") != "unavailable"
    ):
        raise PortfolioReviewArtifactError(
            "Unsupported performance method label.", kind="conflict"
        )
    _validate_scenario_arithmetic(db, frozen, total)
    text = " ".join(
        [draft.sections.summary]
        + draft.sections.concentration
        + draft.sections.liquidity
        + draft.sections.history
        + draft.sections.scenario_exposure
        + draft.sections.risks
        + draft.sections.next_checks
    )
    if _ADVICE.search(text):
        raise PortfolioReviewArtifactError(
            "Portfolio review must not recommend a transaction."
        )
    return agent, mapping_drift


def _validate_risk_context(
    db: Session, frozen: dict[str, Any], snapshot: PortfolioSnapshot
) -> None:
    context = frozen["analytics"].get("risk_context") or {}
    if _as_datetime(context.get("snapshot_as_of")) != _aware(snapshot.as_of):
        raise PortfolioReviewArtifactError(
            "Risk context snapshot time is invalid.", kind="conflict"
        )
    positions = {row["position_snapshot_id"]: row for row in frozen["positions"]}
    companies = context.get("companies") or []
    by_company: dict[int, dict[str, Any]] = {}
    for row in companies:
        position = positions.get(row.get("position_id"))
        if position is None or position.get("current_company_id") != row.get(
            "company_id"
        ):
            raise PortfolioReviewArtifactError(
                "Risk context company identity is invalid.", kind="conflict"
            )
        research_data = row.get("research") or {}
        research_id = research_data.get("id")
        if research_id is not None:
            research = db.get(ResearchSnapshot, research_id)
            case = db.get(ResearchCase, research.research_case_id) if research else None
            profile = (
                db.get(CompanyProfile, research.company_profile_id)
                if research
                else None
            )
            if (
                research is None
                or case is None
                or case.company_id != row.get("company_id")
                or _aware(research.as_of) > _aware(snapshot.as_of)
                or profile is None
                or profile.id != (row.get("profile") or {}).get("id")
            ):
                raise PortfolioReviewArtifactError(
                    "Risk context Research/Profile look-ahead failed.", kind="conflict"
                )
        for falsifier in row.get("falsifiers") or []:
            created_at = _as_datetime(falsifier["created_at"])
            updated_at = _as_datetime(falsifier["updated_at"])
            known = created_at <= _aware(snapshot.as_of) and updated_at <= _aware(
                snapshot.as_of
            )
            expected_basis = (
                "snapshot-known-current-row-no-history"
                if known
                else "current-only-no-history"
            )
            if (
                falsifier.get("status_basis") != expected_basis
                or falsifier.get("known_by_snapshot") is not known
                or falsifier.get("changed_after_snapshot")
                is not (updated_at > _aware(snapshot.as_of))
            ):
                raise PortfolioReviewArtifactError(
                    "Falsifier availability markers are invalid.", kind="conflict"
                )
        snapshot_known = [
            item for item in row.get("falsifiers") or [] if item["known_by_snapshot"]
        ]
        current_only = [
            item
            for item in row.get("falsifiers") or []
            if not item["known_by_snapshot"]
        ]
        snapshot_fired = [item for item in snapshot_known if item["status"] == "fired"]
        current_fired = [item for item in current_only if item["status"] == "fired"]
        if (
            row.get("snapshot_known_falsifiers") != snapshot_known
            or row.get("current_only_falsifiers") != current_only
            or row.get("snapshot_known_fired_falsifiers") != snapshot_fired
            or row.get("current_only_fired_falsifiers") != current_fired
            or row.get("snapshot_known_fired_count") != len(snapshot_fired)
            or row.get("current_only_fired_count") != len(current_fired)
        ):
            raise PortfolioReviewArtifactError(
                "Falsifier time-basis partitions are invalid.", kind="conflict"
            )
        by_company[row["company_id"]] = row
    for group in context.get("shared_groups") or []:
        members = [
            by_company.get(company_id) for company_id in group.get("company_ids") or []
        ]
        if len({member["company_id"] for member in members if member}) < 2:
            raise PortfolioReviewArtifactError(
                "Risk co-exposure group lacks two companies.", kind="conflict"
            )
        if group.get("group_type") == "sector":
            labels = {member.get("sector") for member in members if member}
        elif group.get("group_type") == "archetype":
            labels = {
                (member.get("profile") or {}).get("archetype")
                for member in members
                if member
            }
        else:
            raise PortfolioReviewArtifactError(
                "Unsupported risk co-exposure group.", kind="conflict"
            )
        if labels != {group.get("label")}:
            raise PortfolioReviewArtifactError(
                "Risk co-exposure evidence does not reconcile.", kind="conflict"
            )
        expected_time_basis = (
            "snapshot-known"
            if group.get("group_type") == "archetype"
            or all(member.get("sector_known_by_snapshot") for member in members)
            else "includes-current-only"
        )
        if group.get("time_basis") != expected_time_basis:
            raise PortfolioReviewArtifactError(
                "Risk co-exposure time basis is invalid.", kind="conflict"
            )


def _validate_scenario_arithmetic(
    db: Session, frozen: dict[str, Any], total: float
) -> None:
    sensitivity = frozen["analytics"].get("scenario_sensitivity") or {}
    covered = sensitivity.get("covered") or []
    eligible = frozen.get("eligible_valuations") or []
    expected_pairs = {
        (
            row["position_snapshot_id"],
            row["valuation_snapshot_id"],
            row["valuation_fingerprint"],
        )
        for row in eligible
    }
    covered_pairs = {
        (row["position_id"], row["valuation_snapshot_id"], row["valuation_fingerprint"])
        for row in covered
    }
    if expected_pairs != covered_pairs:
        raise PortfolioReviewArtifactError(
            "Eligible valuation set does not match scenario coverage.", kind="conflict"
        )
    positions = {row["position_snapshot_id"]: row for row in frozen["positions"]}
    totals = {"negative": 0.0, "base": 0.0, "positive": 0.0, "weighted": 0.0}
    unchanged = total
    for row in covered:
        position = positions.get(row["position_id"])
        valuation = db.get(ValuationSnapshot, row["valuation_snapshot_id"])
        if position is None or valuation is None or position["quantity"] is None:
            raise PortfolioReviewArtifactError(
                "Covered scenario lacks a frozen quantity.", kind="conflict"
            )
        outputs = valuation.deterministic_outputs or {}
        by_kind = {
            item.get("kind"): item
            for item in outputs.get("scenarios", [])
            if isinstance(item, dict)
        }
        quantity = float(position["quantity"])
        unchanged -= float(position["value"])
        for kind in ("negative", "base", "positive"):
            target = (by_kind.get(kind) or {}).get("target_price_pln")
            expected = quantity * float(target) if target is not None else None
            if expected is None or abs(float(row[f"{kind}_value"]) - expected) > 0.02:
                raise PortfolioReviewArtifactError(
                    "Aligned scenario arithmetic does not reconcile.", kind="conflict"
                )
            totals[kind] += expected
        weighted_price = (outputs.get("probability_weighted") or {}).get("price_pln")
        expected_weighted = (
            quantity * float(weighted_price) if weighted_price is not None else None
        )
        if (
            expected_weighted is None
            or abs(float(row["weighted_value"]) - expected_weighted) > 0.02
        ):
            raise PortfolioReviewArtifactError(
                "Weighted scenario arithmetic does not reconcile.", kind="conflict"
            )
        totals["weighted"] += expected_weighted
    actual_totals = sensitivity.get("portfolio_values") or {}
    for kind, covered_total in totals.items():
        expected = covered_total + unchanged
        if (
            kind not in actual_totals
            or abs(float(actual_totals[kind]) - expected) > 0.02
        ):
            raise PortfolioReviewArtifactError(
                "Portfolio scenario total does not reconcile.", kind="conflict"
            )


def _final_status(result: PortfolioReviewVerifierResult, gaps: list[str]) -> str:
    if result.verdict == "pass":
        if not all(result.checks.model_dump().values()):
            raise PortfolioReviewArtifactError(
                "A passing verdict requires every strict check."
            )
        return "provisional" if gaps else "verified"
    return "rejected" if result.verdict == "fail" else "needs-human"


def verify_portfolio_review(
    db: Session, payload: PortfolioReviewVerificationIn
) -> VerificationRun:
    agent, mapping_drift = _validate_frozen_integrity(
        db, payload.draft, allow_mapping_drift=True
    )
    _validate_version(db, payload.draft)
    if payload.verifier_worker_id == agent.lease_owner:
        raise PortfolioReviewArtifactError(
            "Drafting worker cannot verify its own review.", kind="conflict"
        )
    task = (agent.inputs or {}).get("task") or {}
    if payload.verifier_result.requested_model_role != task.get(
        "verifier_model_role"
    ) or payload.verifier_result.requested_model != task.get("verifier_model"):
        raise PortfolioReviewArtifactError(
            "Verifier model/role differs from the queued strict policy.",
            kind="conflict",
        )
    if payload.verifier_result.reasoning_effort != task.get(
        "verifier_reasoning_effort"
    ):
        raise PortfolioReviewArtifactError(
            "Verifier reasoning differs from the queued strict policy.", kind="conflict"
        )
    if mapping_drift and not (
        payload.verifier_result.verdict == "needs-human"
        and payload.verifier_result.checks.mapping_set is False
    ):
        raise PortfolioReviewArtifactError(
            "Mapping drift requires a needs-human verdict with mapping_set=false.",
            kind="conflict",
        )
    final_status = _final_status(payload.verifier_result, payload.draft.gaps)
    checks = {
        **payload.verifier_result.checks.model_dump(mode="json"),
        "verifier_worker_id": payload.verifier_worker_id,
        "portfolio_review_draft_fingerprint": portfolio_review_draft_fingerprint(
            payload.draft
        ),
        "input_fingerprint": payload.draft.input_fingerprint,
        "analytics_fingerprint": payload.draft.analytics_fingerprint,
        "requested_model": payload.verifier_result.requested_model,
        "reasoning_effort": payload.verifier_result.reasoning_effort,
        "actual_host_model": payload.verifier_result.actual_host_model,
        "substitution_or_escalation": payload.verifier_result.substitution_or_escalation,
        "final_status": final_status,
    }
    row = VerificationRun(
        agent_run_id=agent.id,
        model_role=payload.verifier_result.requested_model_role,
        verifier_model=payload.verifier_result.actual_host_model,
        verdict=payload.verifier_result.verdict,
        checks=checks,
        summary=payload.verifier_result.summary,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _result(row: VerificationRun) -> PortfolioReviewVerifierResult:
    names = PortfolioReviewVerifierResult.model_fields["checks"].annotation.model_fields
    return PortfolioReviewVerifierResult.model_validate(
        {
            "requested_model_role": row.model_role,
            "requested_model": (row.checks or {}).get("requested_model"),
            "reasoning_effort": (row.checks or {}).get("reasoning_effort"),
            "actual_host_model": row.verifier_model,
            "substitution_or_escalation": (row.checks or {}).get(
                "substitution_or_escalation"
            ),
            "verdict": row.verdict,
            "checks": {name: (row.checks or {}).get(name) for name in names},
            "summary": row.summary,
        }
    )


def save_portfolio_review(
    db: Session, payload: PortfolioReviewSaveIn
) -> PortfolioReviewSnapshot:
    draft = PortfolioReviewDraftIn.model_validate(
        payload.model_dump(exclude={"verification_run_id"})
    )
    verification = db.get(VerificationRun, payload.verification_run_id)
    if verification is None:
        raise PortfolioReviewArtifactError(
            "Unknown verification run.", kind="not-found"
        )
    result = _result(verification)
    draft_fingerprint = portfolio_review_draft_fingerprint(draft)
    artifact_fingerprint = canonical_hash(
        {
            "draft": draft.model_dump(mode="json"),
            "verification_run_id": verification.id,
            "verifier_result": result.model_dump(mode="json"),
        }
    )
    existing = db.scalar(
        select(PortfolioReviewSnapshot).where(
            PortfolioReviewSnapshot.agent_run_id == draft.agent_run_id
        )
    )
    if existing is not None:
        if existing.artifact_fingerprint == artifact_fingerprint:
            return existing
        raise PortfolioReviewArtifactError(
            "Run already saved a different review.", kind="conflict"
        )
    agent, mapping_drift = _validate_frozen_integrity(
        db, draft, allow_mapping_drift=result.verdict == "needs-human"
    )
    _validate_version(db, draft)
    if mapping_drift and result.checks.mapping_set:
        raise PortfolioReviewArtifactError(
            "Verifier did not report the mapping drift.", kind="conflict"
        )
    checks = verification.checks or {}
    if (
        verification.agent_run_id != agent.id
        or verification.analysis_run_id is not None
        or verification.model_role != "verifier_strict"
        or checks.get("verifier_worker_id") in {None, agent.lease_owner}
        or checks.get("portfolio_review_draft_fingerprint") != draft_fingerprint
        or checks.get("input_fingerprint") != draft.input_fingerprint
        or checks.get("analytics_fingerprint") != draft.analytics_fingerprint
    ):
        raise PortfolioReviewArtifactError(
            "Verification is not for this exact independent draft.", kind="conflict"
        )
    final_status = _final_status(result, draft.gaps)
    if checks.get("final_status") != final_status:
        raise PortfolioReviewArtifactError(
            "Verifier final status is inconsistent.", kind="conflict"
        )
    row = PortfolioReviewSnapshot(
        portfolio_id=draft.portfolio_id,
        portfolio_snapshot_id=draft.portfolio_snapshot_id,
        agent_run_id=agent.id,
        verification_run_id=verification.id,
        version=draft.version,
        contract_version=draft.contract_version,
        status=final_status,
        draft_requested_model_role=draft.requested_model_role,
        draft_requested_model=draft.requested_model,
        draft_reasoning_effort=draft.reasoning_effort,
        draft_actual_host_model=draft.actual_host_model,
        draft_substitution_or_escalation=draft.substitution_or_escalation,
        as_of=draft.as_of,
        sections=draft.sections.model_dump(mode="json"),
        input_manifest=draft.input_manifest,
        gaps=draft.gaps,
        input_fingerprint=draft.input_fingerprint,
        analytics_fingerprint=draft.analytics_fingerprint,
        draft_fingerprint=draft_fingerprint,
        artifact_fingerprint=artifact_fingerprint,
        verifier_result=result.model_dump(mode="json"),
    )
    db.add(row)
    db.flush()
    agent.status = final_status
    agent.outputs = {
        "portfolio_review_snapshot_id": row.id,
        "verification_run_id": verification.id,
        "input_fingerprint": draft.input_fingerprint,
        "analytics_fingerprint": draft.analytics_fingerprint,
    }
    agent.finished_at = utcnow()
    agent.updated_at = agent.finished_at
    agent.error = (
        result.summary if final_status in {"rejected", "needs-human"} else None
    )
    clear_agent_lease(agent)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = db.scalar(
            select(PortfolioReviewSnapshot).where(
                PortfolioReviewSnapshot.agent_run_id == agent.id
            )
        )
        if raced is not None and raced.artifact_fingerprint == artifact_fingerprint:
            return raced
        raise PortfolioReviewArtifactError(
            "Portfolio review version already exists.", kind="conflict"
        ) from exc
    db.refresh(row)
    return row
