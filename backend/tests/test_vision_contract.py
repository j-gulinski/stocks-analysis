"""Executable anti-drift gate for the binding Workbench VISION.

These tests intentionally cross backend, frontend and skill boundaries.  They
are architecture tests: a green unit test beside a second legacy path is not a
valid reset (VISION V10).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend" / "src"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _files(root: Path, *suffixes: str) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in suffixes
    )


def _matches(paths: list[Path], pattern: re.Pattern[str]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    return findings


def test_v1_discover_exposes_one_versioned_workbench_sieve() -> None:
    """V1: the wire contract is singular and the UI cannot select another sieve."""
    from app.api.schemas import DiscoveryOut

    fields = set(DiscoveryOut.model_fields)
    assert "sieve" in fields
    assert "sieves" not in fields

    api_source = _read("backend/app/api/discovery.py")
    assert "workbench_sieve_v1" in api_source
    assert not re.search(r"\b(?:obs|malik|areczeks|elendix)\b", api_source, re.I)

    ui_source = _read("frontend/src/app/discover/page.tsx")
    forbidden_selector_fragments = (
        "result.sieves",
        "selectedSieve",
        "setSelectedSieve",
        "sieve selector",
    )
    assert not [item for item in forbidden_selector_fragments if item in ui_source]


def test_v2_product_surfaces_have_no_author_or_method_branding() -> None:
    """V2: authors remain audit provenance, never a product abstraction."""
    product_paths = (
        _files(BACKEND / "app" / "api", ".py")
        + _files(BACKEND / "app" / "mcp", ".py")
        + _files(FRONTEND, ".ts", ".tsx")
        + sorted((BACKEND / "app" / "services").glob("*artifacts.py"))
        + sorted((BACKEND / "scripts").glob("codex_*.py"))
    )
    author_pattern = re.compile(r"\b(?:malik|obs|areczeks|elendix)\b", re.I)
    abstraction_pattern = re.compile(
        r"method[_\s-]?(?:pack|perspective)|\bpersona(?:s)?\b", re.I
    )

    findings = _matches(product_paths, author_pattern)
    findings += _matches(product_paths, abstraction_pattern)
    assert findings == [], "VISION V2 product branding:\n" + "\n".join(findings)


def test_v3_research_list_contract_is_phase_aware_and_not_job_led() -> None:
    """V3: list rows carry phase substance; process metadata stays out."""
    from app.api.schemas import ResearchCaseSummaryOut

    fields = set(ResearchCaseSummaryOut.model_fields)
    assert {
        "phase",
        "phase_label",
        "phase_summary",
        "main_gap",
        "agenda_reasons",
        "collection_progress",
        "valuation_strip",
    } <= fields
    assert {
        "initial_research_run_id",
        "initial_research_status",
        "latest_research_run_id",
        "latest_research_run_status",
    }.isdisjoint(fields)

    ui_source = _read("frontend/src/app/page.tsx")
    assert "phase_summary" in ui_source
    assert "collection_progress" in ui_source
    assert "valuation_strip" in ui_source
    assert "agenda_reasons" in ui_source
    assert "latest_research_run_status" not in ui_source


def test_v4_scenario_inputs_and_probabilities_have_no_defaults() -> None:
    """V4: every scenario value is supplied for this company, never seeded."""
    from app.api.schemas import (
        ValuationScenarioAssumptions,
        ValuationScenarioJudgment,
    )

    required_assumptions = {
        name
        for name in ValuationScenarioAssumptions.model_fields
        if name != "event_one_off_net_pln_thousands"
    }
    assert required_assumptions
    assert all(
        ValuationScenarioAssumptions.model_fields[name].is_required()
        for name in required_assumptions
    )
    assert ValuationScenarioJudgment.model_fields["probability_pct"].is_required()

    with pytest.raises(ValidationError):
        ValuationScenarioJudgment.model_validate(
            {
                "kind": "base",
                "mechanism": "Company-specific mechanism grounded in frozen evidence.",
                "probability_rationale": (
                    "The frozen evidence supports this company-specific probability."
                ),
                "catalyst_or_counter_driver": "reported backlog conversion",
                "falsifier": "backlog fails to convert by the next report",
            }
        )

    seed_pattern = re.compile(r"INDUSTRIAL_SEED|SOFTWARE_SEED")
    seed_surfaces = _files(FRONTEND, ".ts", ".tsx") + [
        BACKEND / "app" / "api" / "schemas.py",
        BACKEND / "app" / "services" / "valuation_templates.py",
    ]
    findings = _matches(seed_surfaces, seed_pattern)
    assert findings == [], "VISION V4 scenario seeds:\n" + "\n".join(findings)


def test_v4_backend_has_structural_company_specificity_gates() -> None:
    """V4: duplicate vectors/probabilities are computed backend defects."""
    from app.services import valuation_gates

    assert callable(valuation_gates.evaluate_structural_gates)
    source = Path(valuation_gates.__file__).read_text(encoding="utf-8")
    for computed_gate in (
        "probability_structure",
        "probability_repetition",
        "cross_company_specificity",
        "scenario_distinctness",
        "evidence_binding",
    ):
        assert computed_gate in source

    queue_skill = _read("skills/workbench-run-queue/SKILL.md").lower()
    valuation_skill = _read("skills/company-valuation/SKILL.md").lower()
    picker = _read("backend/scripts/codex_pick_agent_run.py").lower()
    compute_helper = _read("backend/scripts/codex_compute_valuation_draft.py").lower()
    assert "codex context itself must perform the company-specific causal analysis" in queue_skill
    assert "queued codex worker is an analyst, not a schema filler" in valuation_skill
    assert "whole frozen valuation dossier" in picker
    assert "build a causal company case" in picker
    assert "drafted grid" not in compute_helper


def test_v5_verifier_contract_is_adversarial_and_backend_recomputes() -> None:
    """V5: booleans cannot replace evidence, findings or deterministic checks."""
    from app.api.schemas import (
        PortfolioReviewVerifierResult,
        ResearchSnapshotOut,
        ResearchVerifierResult,
        ValuationVerifierResult,
    )
    from app.services import valuation_artifacts

    for model in (ResearchVerifierResult, PortfolioReviewVerifierResult):
        assert "checks" not in model.model_fields
        assert {"findings", "justifications"} <= set(model.model_fields)
        justification_model = model.model_fields["justifications"].annotation
        assert justification_model.model_fields
        assert all(
            field.annotation is str
            for field in justification_model.model_fields.values()
        )
    research_read_verifier = ResearchSnapshotOut.model_fields["verifier_result"].annotation
    assert "checks" not in research_read_verifier.model_fields
    assert {"findings", "justifications", "verification_standard"} <= set(
        research_read_verifier.model_fields
    )

    justification = (
        "Examined the frozen facts, assumption bindings, scenario mechanism, "
        "and recomputed backend evidence; no contradiction was found."
    )
    accepted = ValuationVerifierResult.model_validate(
        {
            "verifier_model": "strict-test-model",
            "verdict": "pass",
            "findings": [],
            "judgment_review": {
                "evidence_fit": justification,
                "mechanism_plausibility": justification,
                "potential_underwrite": justification,
                "probability_reasonableness": justification,
            },
            "summary": "Adversarial review found no judgment-only defect.",
        }
    )
    assert accepted.model_role == "verifier_strict"

    with pytest.raises(ValidationError):
        ValuationVerifierResult.model_validate(
            {
                "verifier_model": "strict-test-model",
                "verdict": "pass",
                "checks": {"math_correct": True},
                "summary": "Self-attested pass.",
            }
        )
    with pytest.raises(ValidationError):
        ValuationVerifierResult.model_validate(
            {
                "verifier_model": "strict-test-model",
                "verdict": "fail",
                "findings": [],
                "judgment_review": {
                    "evidence_fit": justification,
                    "mechanism_plausibility": justification,
                    "potential_underwrite": justification,
                    "probability_reasonableness": justification,
                },
                "summary": "Rejected without a finding.",
            }
        )

    source = Path(valuation_artifacts.__file__).read_text(encoding="utf-8")
    assert "calculate_valuation(" in source
    assert "canonical_hash(recomputed)" in source
    assert "evaluate_structural_gates(" in source
    assert '"structural_gates"' in source


def test_v6_run_queue_skill_drains_with_recovery_and_failure_caps() -> None:
    """V6: the operator loops to empty and bounds poison-job retries."""
    source = _read("skills/workbench-run-queue/SKILL.md").lower()

    assert re.search(r"until (?:the )?queue is empty", source)
    assert "recover" in source and "expired lease" in source
    assert "failure cap" in source
    forbidden = (
        "stop after this one row",
        "stop after this one job",
        "at most one row",
        "process exactly one claimed job",
        "never poll",
    )
    assert not [phrase for phrase in forbidden if phrase in source]


def test_v10_deleted_legacy_modules_and_routes_stay_deleted(client) -> None:
    """V10: the reset has no compatibility restoration."""
    deleted_paths = (
        "backend/app/analysis",
        "backend/app/api/analyses.py",
        "backend/app/api/backtests.py",
        "backend/app/api/forum.py",
        "backend/app/api/journal.py",
        "backend/app/api/monitor.py",
        "backend/app/api/watchlist.py",
        "backend/app/services/scenarios.py",
        "backend/app/services/thesis.py",
        "backend/app/services/valuation_ai.py",
        "backend/app/services/research_method_perspectives.py",
        "backend/app/services/dossier.py",
        "backend/scripts/codex_get_dossier.py",
        "frontend/src/lib/dossier.ts",
    )
    assert [path for path in deleted_paths if (ROOT / path).exists()] == []

    for route in (
        "/api/watchlist",
        "/api/backtests",
        "/api/forum",
        "/api/journal",
        "/api/monitor",
    ):
        assert client.get(route).status_code == 404, route


def test_v10_clean_baseline_has_no_legacy_artifact_schema() -> None:
    """V10: stale tables/fields cannot re-enter through a migration or model."""
    from app.api.schemas import CompanyProfileIn, ResearchSnapshotOut, ValuationSnapshotOut
    from app.db.base import Base
    from app.db.models import CompanyProfile, ResearchCase, VerificationRun

    migrations = sorted(
        path
        for path in (BACKEND / "alembic" / "versions").glob("*.py")
        if path.name != "__init__.py"
    )
    assert migrations[0].name == "0001_canonical_clean_baseline.py"
    baseline_source = migrations[0].read_text(encoding="utf-8")
    assert "down_revision = None" in baseline_source

    retired_tables = {
        "assumption_sets",
        "discovery_triage_reviews",
        "forecasts",
        "analyses",
        "model_calls",
        "forum_topics",
        "forum_posts",
        "watchlist_items",
        "monitor_snapshots",
        "monitor_changes",
        "analysis_runs",
        "candidate_runs",
        "backtest_runs",
        "backtest_observations",
        "agent_evaluation_runs",
        "agent_evaluation_observations",
    }
    migration_source = "\n".join(
        path.read_text(encoding="utf-8") for path in migrations
    )
    assert not any(
        f"'{table}'" in migration_source or f'"{table}"' in migration_source
        for table in retired_tables
    )
    assert retired_tables.isdisjoint(Base.metadata.tables)
    assert not hasattr(CompanyProfile, "author")
    assert not {
        "promotion_triage_review_id",
        "promotion_review_price_pln",
        "promotion_note",
        "promotion_evidence_reason",
        "quarterly_review_due_on",
        "material_event_review_policy",
    } & set(ResearchCase.__table__.columns)
    assert "analysis_run_id" not in VerificationRun.__table__.columns
    assert CompanyProfileIn.model_fields["schema_version"].annotation == Literal[
        "company-profile-v2"
    ]
    assert ResearchSnapshotOut.model_fields["contract_version"].annotation == Literal[
        "research-snapshot-v3"
    ]
    assert ValuationSnapshotOut.model_fields["contract_version"].annotation == Literal[
        "valuation-snapshot-v3"
    ]


def test_v10_only_canonical_workflows_and_artifact_gates_are_exposed() -> None:
    """V10: generic completion/verifier adapters cannot bypass stage artifacts."""
    from app.api.agent_runs import ALLOWED_WORKFLOWS
    from app.mcp import stock_tools
    from app.mcp.stock_workbench_server import TOOLS
    from app.services.model_policy import _POLICIES

    canonical = {
        "stock-initial-research",
        "stock-company-review",
        "stock-company-valuation",
        "stock-portfolio-review",
    }
    assert ALLOWED_WORKFLOWS == canonical
    assert set(_POLICIES) == canonical

    generic_bypasses = {
        "save_analysis_run",
        "complete_agent_run",
        "mark_verification_result",
        "get_company_dossier",
    }
    assert generic_bypasses.isdisjoint(TOOLS)
    assert not hasattr(stock_tools, "get_company_dossier")
    assert "getDossier" not in _read("frontend/src/lib/api.ts")
    assert "interface Dossier" not in _read("frontend/src/lib/types.ts")

    agent_api = _read("backend/app/api/agent_runs.py")
    assert "/companies/{ticker}/analysis-runs" not in agent_api
    assert "AnalysisRunOut" not in agent_api
    assert "/agent-runs/pre-session" not in agent_api

    picker = _read("backend/scripts/codex_pick_agent_run.py")
    legacy_workflows = {
        "stock-pre-session-brief",
        "stock-quick-analysis",
        "stock-deep-analysis",
        "stock-candidate-scout",
        "stock-backtest-review",
        "stock-verifier",
        "stock-thesis-review",
        "scenario-simulation",
    }
    assert [workflow for workflow in legacy_workflows if workflow in picker] == []
    assert "save_analysis_run" not in picker
    assert "complete_agent_run" not in picker
    assert "mark_verification_result" not in picker
