import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("workbench_operator", ROOT / "scripts" / "workbench.py")
assert SPEC and SPEC.loader
workbench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workbench
SPEC.loader.exec_module(workbench)


def test_session_hook_is_idempotent_while_previous_hook_is_alive(tmp_path, monkeypatch):
    pid_file = tmp_path / "session-hook.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    monkeypatch.setattr(workbench, "SESSION_HOOK_PID", pid_file)
    monkeypatch.setattr(workbench, "_pid_alive", lambda pid: pid == os.getpid())

    check = workbench._start_session_hook()

    assert check.status == "pass"
    assert "already running" in check.detail


def test_session_hook_starts_detached_backend_script(tmp_path, monkeypatch):
    pid_file = tmp_path / "session-hook.pid"
    log_file = tmp_path / "session-hook.log"
    monkeypatch.setattr(workbench, "SESSION_HOOK_PID", pid_file)
    monkeypatch.setattr(workbench, "SESSION_HOOK_LOG", log_file)
    monkeypatch.setattr(workbench, "_python_executable", lambda: Path("/venv/bin/python"))
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(pid=321))

    check = workbench._start_session_hook()

    assert check.status == "pass"
    assert pid_file.read_text(encoding="utf-8") == "321"
    assert log_file.exists()


def test_session_start_claims_only_the_new_pre_session_run(monkeypatch, capsys):
    from scripts import codex_session_start

    monkeypatch.setattr(
        codex_session_start.stock_tools,
        "prepare_pre_session_brief",
        lambda payload: {
            "ok": True,
            "espi_poll": {"complete": True},
            "agent_run": {"id": 44, "workflow": "stock-pre-session-brief"},
        },
    )
    monkeypatch.setattr(
        codex_session_start,
        "_claim_agent_run",
        lambda agent_run_id: {
            "ok": agent_run_id == 44,
            "agent_run_id": agent_run_id,
            "status": "running",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["codex_session_start.py", "--pretty"],
    )

    assert codex_session_start.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["queue_attempt"]["agent_run_id"] == 44
