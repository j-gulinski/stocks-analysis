import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("workbench_operator", ROOT / "scripts" / "workbench.py")
assert SPEC and SPEC.loader
workbench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workbench
SPEC.loader.exec_module(workbench)


def test_session_hook_is_disabled_and_never_starts_a_process(tmp_path, monkeypatch):
    pid_file = tmp_path / "session-hook.pid"
    log_file = tmp_path / "session-hook.log"
    monkeypatch.setattr(workbench, "SESSION_HOOK_PID", pid_file)
    monkeypatch.setattr(workbench, "SESSION_HOOK_LOG", log_file)
    monkeypatch.setattr(
        workbench.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not start")),
    )

    check = workbench._start_session_hook()

    assert check.status == "info"
    assert "disabled" in check.detail
    assert not pid_file.exists()
    assert not log_file.exists()


def test_session_start_prepares_but_never_claims_the_new_run(monkeypatch, capsys):
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
        sys,
        "argv",
        ["codex_session_start.py", "--pretty"],
    )

    assert codex_session_start.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["agent_run"]["id"] == 44
    assert payload["queue_attempt"] is None
    assert "no lease" in payload["message"]
