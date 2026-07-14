"""Structural valuation gates — computed company-specificity enforcement.

VISION V4/V5: a valuation must be specific to its company. These gates are
deterministic backend checks that run before any verifier opinion. They can
only be tightened, never delegated to agent self-reporting.

Think of this as a guard clause layer (C# analogy: FluentValidation rules
that run server-side regardless of what the client asserts).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResearchCase, ValuationSnapshot

# Opaque fingerprints let the gate reject known default mixes and deleted
# template fossils without retaining reusable scenario numbers in the codebase.
KNOWN_DEFAULT_PROBABILITY_FINGERPRINTS = frozenset(
    {
        "2453f999dd60a9a11361ab292f1104838666de77a92b3cbdda63e01471e87ed3",
        "383aa55f75d76f16980f8e05302219ad8c26de5b2582781e5d7a865ec8182106",
        "9d28ca7db1fae5fc94239ab02f31172b0293ebe898bddd3493190afc6064395f",
        "7b497fd82eb27471f31ff7c299c024b8cf1c77ad153136ef0e6cc945a8494ce1",
        "a35c841327e90b47617809e5b26acf7f2884a9989e243cfe42f98e1ea53e07bf",
        "e8ae6100df3763697f01c722c95ad07792255faeae72a7ebe276492b276b2a47",
        "9de9fcb8bf2d3fe8591c2542b20ccc307d1e4b7e9cb75c4fdb6614221955acb0",
        "9489f5938bb4d05bf5cce7e8c863a74a615c9bf76514e313d79e9063b26f433a",
        "61eef6fa6c1891520f70e1a6ad8e308c9650a03d1eb8f582ab4eaae5bf89a82e",
        "49b972ab36c94626d544e448c2b2f280b40d312644141e84b8cfbe19960dec20",
        "7a3b7f1ed4271bad6c989badd1dc99b8fa3aca04a20a671734d566137d9e061e",
        "efea4b891347276db323017bae4256a0410b68e9d7a83963b77ee8b55e2cbe33",
        "63ef77b53108a147aa3da55aef6b882ea44332b85222cba64cea71b588d93670",
    }
)
FORBIDDEN_SEED_FINGERPRINTS = frozenset(
    {
        "65e7a2a7f420969530ef07a90b79158320a84b1876382a787a31f22442780738",
        "cec15b099ae2e5007731a8e0e45f6ff736e396e680661765abac9fd7b0097877",
    }
)

# Two live valuations of different companies closer than this on every core
# element are near-duplicates (relative tolerance).
NEAR_DUPLICATE_REL_TOL = 0.02
GATE_CONTRACT_VERSION = "valuation-gates-v1"

_CORE_FIELDS = (
    "quarter_revenue_growth_pct",
    "year_revenue_growth_pct",
    "gross_margin_pct",
    "operating_cost_ratio_pct",
    "target_pe",
)


@dataclass
class GateResult:
    gate: str
    passed: bool
    reason: str | None = None

    def to_dict(self) -> dict:
        return {"gate": self.gate, "passed": self.passed, "reason": self.reason}


def _scenario_vector(scenario) -> tuple[float, ...]:
    return tuple(round(float(getattr(scenario, field).value), 4) for field in _CORE_FIELDS)


def _draft_vectors(draft) -> dict[str, tuple[float, ...]]:
    return {row.kind: _scenario_vector(row) for row in draft.assumptions}


def _probability_tuple(draft) -> tuple[int, ...]:
    return tuple(
        sorted(int(row.probability_pct) for row in draft.codex_judgment.scenarios)
    )


def _fingerprint(value) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rel_close(a: float, b: float, tol: float) -> bool:
    scale = max(1.0, abs(a), abs(b))
    return abs(a - b) / scale < tol


def _vectors_near_duplicate(
    ours: dict[str, tuple[float, ...]],
    theirs: dict[str, tuple[float, ...]],
    tol: float = NEAR_DUPLICATE_REL_TOL,
) -> bool:
    shared = set(ours) & set(theirs) & {"negative", "base", "positive"}
    if len(shared) < 3:
        return False
    return all(
        _rel_close(ours[kind][i], theirs[kind][i], tol)
        for kind in shared
        for i in range(len(_CORE_FIELDS))
    )


def _snapshot_vectors(snapshot: ValuationSnapshot) -> dict[str, tuple[float, ...]]:
    vectors: dict[str, tuple[float, ...]] = {}
    for row in (snapshot.assumptions or {}).get("scenarios", []):
        try:
            vectors[row["kind"]] = tuple(
                round(float(row[field]["value"]), 4) for field in _CORE_FIELDS
            )
        except (KeyError, TypeError, ValueError):
            continue
    return vectors


def _gate_probability_structure(draft) -> GateResult:
    gate = "probability_structure"
    rows = draft.codex_judgment.scenarios
    total = sum(int(row.probability_pct) for row in rows)
    if not 99 <= total <= 101:
        return GateResult(gate, False, f"Scenario probabilities sum to {total}, not 100.")
    for row in rows:
        if not 1 <= int(row.probability_pct) <= 98:
            return GateResult(
                gate, False,
                f"Scenario '{row.kind}' probability {row.probability_pct}% is degenerate.",
            )
    mix = _probability_tuple(draft)
    if _fingerprint(mix) in KNOWN_DEFAULT_PROBABILITY_FINGERPRINTS:
        return GateResult(
            gate, False,
            f"Probability mix {mix} is a known house default; probabilities must "
            "come from this company's evidence.",
        )
    return GateResult(gate, True)


def _gate_probability_repetition(db: Session, case: ResearchCase, draft) -> GateResult:
    """A mix legitimately repeats sometimes; three concurrent copies is a pattern."""
    gate = "probability_repetition"
    mix = _probability_tuple(draft)
    others = _latest_other_valuations(db, case)
    same = 0
    for snapshot in others:
        their_rows = (snapshot.codex_judgment or {}).get("scenarios", [])
        their_mix = tuple(sorted(int(row.get("probability_pct", -1)) for row in their_rows))
        if their_mix == mix:
            same += 1
    if same >= 2:
        return GateResult(
            gate, False,
            f"Probability mix {mix} already used by {same} other current "
            "valuations; distribution looks generic, justify a different read "
            "or cite why this company genuinely shares it.",
        )
    return GateResult(gate, True)


def _gate_seed_fossils(draft) -> GateResult:
    gate = "seed_fossils"
    vectors = _draft_vectors(draft)
    if _fingerprint(vectors) in FORBIDDEN_SEED_FINGERPRINTS:
        return GateResult(
            gate, False,
            "Assumption vector reproduces a deleted template seed; draft "
            "assumptions from this company's evidence instead.",
        )
    return GateResult(gate, True)


def _latest_other_valuations(db: Session, case: ResearchCase) -> list[ValuationSnapshot]:
    rows = db.scalars(
        select(ValuationSnapshot)
        .where(
            ValuationSnapshot.research_case_id != case.id,
            ValuationSnapshot.status.in_(("verified", "provisional")),
        )
        .order_by(
            ValuationSnapshot.research_case_id,
            ValuationSnapshot.version.desc(),
            ValuationSnapshot.id.desc(),
        )
    ).all()
    latest: dict[int, ValuationSnapshot] = {}
    for row in rows:
        latest.setdefault(row.research_case_id, row)
    return list(latest.values())


def _gate_cross_company(db: Session, case: ResearchCase, draft) -> GateResult:
    gate = "cross_company_specificity"
    ours = _draft_vectors(draft)
    for snapshot in _latest_other_valuations(db, case):
        theirs = _snapshot_vectors(snapshot)
        if _vectors_near_duplicate(ours, theirs):
            return GateResult(
                gate, False,
                "Core assumption vector is a near-duplicate of the current "
                f"valuation for research case {snapshot.research_case_id}; a "
                "different company cannot share effectively identical "
                "scenario numbers.",
            )
    return GateResult(gate, True)


def _gate_scenario_distinctness(draft) -> GateResult:
    gate = "scenario_distinctness"
    mechanisms = [row.mechanism.strip().lower() for row in draft.codex_judgment.scenarios]
    if len(set(mechanisms)) != len(mechanisms):
        return GateResult(gate, False, "Scenario mechanisms must be distinct per scenario.")
    rationales = [
        row.probability_rationale.strip().lower() for row in draft.codex_judgment.scenarios
    ]
    if len(set(rationales)) != len(rationales):
        return GateResult(
            gate, False, "Probability rationales must be scenario-specific, not copies."
        )
    vectors = list(_draft_vectors(draft).values())
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            if vectors[i] == vectors[j]:
                return GateResult(
                    gate, False, "Two scenarios share an identical core assumption vector."
                )
    return GateResult(gate, True)


def _gate_scenario_completeness(draft) -> GateResult:
    gate = "scenario_completeness"
    for row in draft.codex_judgment.scenarios:
        if not any(ch.isdigit() for ch in row.falsifier):
            return GateResult(
                gate, False,
                f"Scenario '{row.kind}' falsifier has no dated/quantified element; "
                "a falsifier must be checkable (date, quarter, or threshold).",
            )
    return GateResult(gate, True)


def _gate_evidence_binding(draft) -> GateResult:
    gate = "evidence_binding"
    evidence_bound = 0
    total = 0
    for scenario in draft.assumptions:
        for field in _CORE_FIELDS:
            value = getattr(scenario, field)
            total += 1
            if value.provenance == "evidence" and value.source_fact_ids:
                evidence_bound += 1
    if total and evidence_bound == 0:
        return GateResult(
            gate, False,
            "No core assumption is bound to a research fact; a valuation must "
            "anchor at least part of its scenario grid in this company's evidence.",
        )
    return GateResult(gate, True)


def evaluate_structural_gates(db: Session, case: ResearchCase, draft) -> list[GateResult]:
    """All computed gates for one draft. Order is stable for reporting."""
    return [
        _gate_probability_structure(draft),
        _gate_probability_repetition(db, case, draft),
        _gate_seed_fossils(draft),
        _gate_cross_company(db, case, draft),
        _gate_scenario_distinctness(draft),
        _gate_scenario_completeness(draft),
        _gate_evidence_binding(draft),
    ]


def gates_passed(results: list[GateResult]) -> bool:
    return all(result.passed for result in results)


def gate_report(results: list[GateResult]) -> dict:
    return {
        "contract_version": GATE_CONTRACT_VERSION,
        "passed": gates_passed(results),
        "results": [result.to_dict() for result in results],
    }
