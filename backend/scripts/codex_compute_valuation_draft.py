"""Compute deterministic outputs and structural gates for one Codex-authored case.

The drafting worker owns company-specific assumptions and probabilities
(VISION V4). This script turns its submitted causal case into the exact draft payload:
frozen base fields from the claimed run + deterministic outputs + gaps +
fingerprints + expected next version — and, when judgment is included, the
structural gate report so the drafter can fix defects BEFORE the verifier
context runs (VISION V5).

Input JSON: {"agent_run_id": int, "lease_owner": str,
             "assumptions": [...], "codex_judgment": {...}}
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import BaseModel, Field, ValidationError

from app.api.schemas import (
    ValuationDraftJudgment,
    ValuationMethodology,
    ValuationScenarioAssumptions,
    ValuationSnapshotDraftIn,
)
from app.db.base import SessionLocal
from app.db.models import AgentRun, ResearchCase, ValuationSnapshot
from app.services.valuation_artifacts import (
    CONTRACT_VERSION,
    TEMPLATE_CONTRACT_VERSION,
    ValuationArtifactError,
)
from app.services.valuation_engine import (
    ENGINE_VERSION,
    ValuationInputError,
    compute_scenarios,
)
from app.services.valuation_gates import evaluate_structural_gates, gate_report
from scripts.codex_common import ScriptError, add_json_flags, read_payload, run_main, write_json
from sqlalchemy import select


class ComputeDraftIn(BaseModel):
    agent_run_id: int = Field(ge=1)
    lease_owner: str = Field(min_length=1, max_length=200)
    assumptions: list[ValuationScenarioAssumptions] = Field(min_length=3, max_length=4)
    methodology: ValuationMethodology
    codex_judgment: ValuationDraftJudgment | None = None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute one Codex-authored valuation case against its frozen base."
    )
    parser.add_argument("--input", default="-")
    add_json_flags(parser)
    args = parser.parse_args()
    try:
        payload = ComputeDraftIn.model_validate(read_payload(args.input))
    except ValidationError as exc:
        raise ScriptError(str(exc), code=2) from exc
    with SessionLocal() as db:
        agent = db.get(AgentRun, payload.agent_run_id)
        if agent is None:
            raise ScriptError("Unknown agent run.")
        if agent.lease_owner != payload.lease_owner:
            raise ScriptError("Lease owner does not own this run.")
        frozen = (agent.inputs or {}).get("valuation") or {}
        case_id = (agent.inputs or {}).get("research_case_id")
        case = db.get(ResearchCase, case_id) if case_id else None
        if not frozen or case is None:
            raise ScriptError("Run has no frozen valuation base bundle.")
        base = {
            "base_values": frozen["base_values"],
            "input_manifest": frozen["input_manifest"],
            "gaps": frozen.get("gaps") or [],
        }
        try:
            computed = compute_scenarios(
                base, payload.assumptions, payload.methodology
            )
        except ValuationInputError as exc:
            raise ScriptError(str(exc)) from exc
        latest = db.scalar(
            select(ValuationSnapshot)
            .where(ValuationSnapshot.research_case_id == case.id)
            .order_by(ValuationSnapshot.version.desc(), ValuationSnapshot.id.desc())
            .limit(1)
        )
        draft_fields = {
            "contract_version": CONTRACT_VERSION,
            "engine_version": ENGINE_VERSION,
            "template_contract_version": TEMPLATE_CONTRACT_VERSION,
            "agent_run_id": agent.id,
            "lease_owner": payload.lease_owner,
            "version": (latest.version if latest else 0) + 1,
            "research_snapshot_id": frozen["research_snapshot_id"],
            "as_of": frozen["as_of"],
            "template_id": frozen["template_id"],
            "template_version": frozen["template_version"],
            "assumptions": [row.model_dump(mode="json") for row in payload.assumptions],
            "methodology": payload.methodology.model_dump(mode="json"),
            "base_values": frozen["base_values"],
            "deterministic_outputs": computed["deterministic_outputs"],
            "input_manifest": frozen["input_manifest"],
            "gaps": computed["gaps"],
            "input_fingerprint": frozen["input_fingerprint"],
            "calculation_fingerprint": computed["calculation_fingerprint"],
        }
        result: dict = {"ok": True, "draft": draft_fields}
        if payload.codex_judgment is not None:
            try:
                draft = ValuationSnapshotDraftIn.model_validate(
                    {**draft_fields, "codex_judgment": payload.codex_judgment.model_dump(mode="json")}
                )
            except ValidationError as exc:
                raise ScriptError(str(exc), code=2) from exc
            try:
                gates = evaluate_structural_gates(db, case, draft)
            except ValuationArtifactError as exc:
                raise ScriptError(str(exc)) from exc
            result["structural_gates"] = gate_report(gates)
            result["draft"] = draft.model_dump(mode="json")
        write_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    run_main(main)
