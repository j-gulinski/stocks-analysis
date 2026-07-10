"""Keyless Codex CLI fallback contracts."""
from __future__ import annotations

import json
import sys

import pytest


def test_codex_mark_verification_completes_agent_without_provider_key(db, monkeypatch, capsys):
    from app.db.models import AgentRun, VerificationRun
    from scripts import codex_mark_verification

    agent = AgentRun(
        workflow="stock-verifier",
        trigger="manual",
        status="running",
        model_role="verifier_strict",
        model="codex-host",
        inputs={"target": "fixture"},
        outputs={},
    )
    db.add(agent)
    db.commit()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "codex_mark_verification.py",
            "--agent-run-id",
            str(agent.id),
            "--verifier-model",
            "codex-host",
            "--verdict",
            "needs-human",
        ],
    )
    monkeypatch.setattr(sys, "stdin", type("Input", (), {"read": lambda _self: '{"checks": {}}'})())

    assert codex_mark_verification.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["agent_run_id"] == agent.id
    db.refresh(agent)
    assert agent.status == "needs-human"
    assert db.query(VerificationRun).one().verdict == "needs-human"


def test_codex_pick_contract_includes_keyless_model_policy(db, monkeypatch, capsys):
    from app.db.models import AgentRun
    from scripts import codex_pick_agent_run

    agent = AgentRun(
        workflow="stock-deep-analysis",
        trigger="manual",
        status="queued",
        model_role="analyst_deep",
        inputs={"ticker": "DEC"},
        outputs={},
    )
    db.add(agent)
    db.commit()
    monkeypatch.setattr(
        sys,
        "argv",
        ["codex_pick_agent_run.py", "--agent-run-id", str(agent.id), "--pretty"],
    )

    assert codex_pick_agent_run.main() == 0
    payload = json.loads(capsys.readouterr().out)
    policy = payload["execution_contract"]["model_policy"]
    assert policy["draft_role"] == "analyst_deep"
    assert policy["api_key_required"] is False


def test_codex_save_analysis_applies_scenario_contract_before_database_write(
    db, monkeypatch
):
    from scripts import codex_save_analysis
    from tests.test_mcp_stock_workbench import (
        _strict_scenario_verification,
        _verified_scenario_simulation_payload,
    )

    output = _verified_scenario_simulation_payload()
    payload = {
        "input_snapshot": {"operating_bridge_fingerprint": "bridge:fixture"},
        "output": output,
        "verification": _strict_scenario_verification(),
    }
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "codex_save_analysis.py",
            "DEC",
            "--workflow",
            "scenario-simulation",
            "--model-role",
            "analyst_deep",
            "--model",
            "codex-host",
            "--verification-status",
            "pass",
        ],
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        type("Input", (), {"read": lambda _self: json.dumps(payload)})(),
    )

    from scripts.codex_common import ScriptError

    with pytest.raises(ScriptError) as exc:
        codex_save_analysis.main()

    assert exc.value.code == 2
    assert "input_snapshot.scenario_set" in str(exc.value)
