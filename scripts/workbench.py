"""Local process manager and diagnostics for the Stock Analysis Workbench.

The command is intentionally stdlib-only so `./workbench doctor` still explains
what is missing before the Python or Node dependencies have been installed.
It never contacts external data/model providers: source status is read from the
local backend's stored diagnostics endpoint when that backend is running.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
STATE_DIR = ROOT / ".workbench"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:3000"
SESSION_HOOK_PID = STATE_DIR / "session-hook.pid"
SESSION_HOOK_LOG = STATE_DIR / "session-hook.log"


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # pass | warn | fail | info
    detail: str


def _run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    timeout: float = 8,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _command_version(command: list[str]) -> str | None:
    result = _run(command)
    if result is None or result.returncode != 0:
        return None
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else None


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _http_json(url: str, timeout: float = 1.5) -> tuple[int | None, Any]:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310 - local URL only
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = {"detail": str(exc)}
        return exc.code, body
    except (URLError, TimeoutError, ValueError):
        return None, None


def _dotenv_values(path: Path) -> dict[str, str]:
    """Read presence-only dotenv values without evaluating or exposing them."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _configured(key: str, dotenv: dict[str, str]) -> bool:
    return bool(os.environ.get(key) or dotenv.get(key))


def _database_endpoint() -> tuple[str, int]:
    """Read only the local DB host/port from configuration, never credentials.

    The main project maps Postgres to 5433 while older worktrees used 5432.
    Keeping this in one helper prevents the process manager from declaring a
    healthy Compose container dead just because its host port changed.
    """
    dotenv = _dotenv_values(BACKEND / ".env")
    raw_url = os.environ.get("DATABASE_URL") or dotenv.get("DATABASE_URL") or ""
    try:
        parsed = urlparse(raw_url)
        return parsed.hostname or "127.0.0.1", parsed.port or 5432
    except ValueError:
        return "127.0.0.1", 5432


def _pair_status(
    label: str, first: str, second: str, dotenv: dict[str, str]
) -> Check:
    states = (_configured(first, dotenv), _configured(second, dotenv))
    if states == (True, True):
        return Check(label, "pass", "configured (values hidden)")
    if any(states):
        return Check(label, "warn", "partially configured (values hidden)")
    return Check(label, "info", "not configured (optional)")


def _python_executable() -> Path:
    candidate = BACKEND / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


def _pid_path(name: str) -> Path:
    return STATE_DIR / f"{name}.pid"


def _read_pid(name: str) -> int | None:
    try:
        return int(_pid_path(name).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _start_session_hook() -> Check:
    """Start one detached pre-session/queue attempt after app startup.

    The hook is deliberately detached: source polling can take several polite
    requests and must never make the local health gate look broken. A PID file
    makes repeated ``workbench start`` calls idempotent while the same hook is
    still running; a later invocation can retry once the process has exited.
    """
    existing_pid = _read_pid_file(SESSION_HOOK_PID)
    if _pid_alive(existing_pid):
        return Check("session hook", "pass", f"already running (pid {existing_pid})")
    SESSION_HOOK_PID.unlink(missing_ok=True)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        log_handle = SESSION_HOOK_LOG.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [
                str(_python_executable()),
                str(BACKEND / "scripts" / "codex_session_start.py"),
                "--trigger",
                "session-start",
                "--pretty",
            ],
            cwd=BACKEND,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
    except OSError as exc:
        return Check("session hook", "warn", f"could not start: {exc}")
    finally:
        if "log_handle" in locals():
            log_handle.close()
    SESSION_HOOK_PID.write_text(str(process.pid), encoding="utf-8")
    return Check(
        "session hook",
        "pass",
        f"started in background pid {process.pid}; log: {SESSION_HOOK_LOG}",
    )


def _read_pid_file(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _owned_status(name: str, port: int) -> dict[str, Any]:
    pid = _read_pid(name)
    alive = _pid_alive(pid)
    listening = _port_open(port)
    if pid is not None and not alive:
        _pid_path(name).unlink(missing_ok=True)
        pid = None
    return {
        "name": name,
        "pid": pid,
        "owned_process_alive": alive,
        "port": port,
        "listening": listening,
        "ownership": "workbench" if alive else ("external" if listening else "none"),
    }


def status_payload() -> dict[str, Any]:
    database_host, database_port = _database_endpoint()
    backend = _owned_status("backend", 8000)
    frontend = _owned_status("frontend", 3000)
    health_status, health = _http_json(f"{BACKEND_URL}/api/health")
    backend["health_status"] = health_status
    backend["health"] = health
    frontend["url"] = FRONTEND_URL
    return {
        "postgres": {
            "host": database_host,
            "port": database_port,
            "listening": _port_open(database_port, database_host),
        },
        "backend": backend,
        "frontend": frontend,
        "state_dir": str(STATE_DIR),
    }


def doctor_checks() -> list[Check]:
    checks: list[Check] = []

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(
        Check(
            "Python",
            "pass" if sys.version_info >= (3, 11) else "fail",
            f"{py_version} ({_python_executable()})",
        )
    )

    backend_import = _run(
        [
            str(_python_executable()),
            "-c",
            "import fastapi, sqlalchemy, bs4, requests, pydantic_settings",
        ],
        cwd=BACKEND,
    )
    checks.append(
        Check(
            "Backend dependencies",
            "pass" if backend_import and backend_import.returncode == 0 else "fail",
            "importable" if backend_import and backend_import.returncode == 0 else "run: cd backend && pip install -r requirements.txt",
        )
    )

    node_version = _command_version(["node", "--version"])
    node_ok = False
    if node_version:
        try:
            node_ok = int(node_version.lstrip("v").split(".", 1)[0]) >= 20
        except ValueError:
            node_ok = False
    checks.append(
        Check("Node.js", "pass" if node_ok else "fail", node_version or "not found (need >=20)")
    )
    npm_version = _command_version(["npm", "--version"])
    checks.append(Check("npm", "pass" if npm_version else "fail", npm_version or "not found"))

    next_binary = FRONTEND / "node_modules" / ".bin" / "next"
    checks.append(
        Check(
            "Frontend dependencies",
            "pass" if next_binary.exists() else "fail",
            "installed from lockfile" if next_binary.exists() else "run: cd frontend && npm ci",
        )
    )

    dotenv = _dotenv_values(BACKEND / ".env")
    checks.append(
        Check(
            "backend/.env",
            "pass" if (BACKEND / ".env").exists() else "info",
            "present (values hidden)" if (BACKEND / ".env").exists() else "absent; defaults/OS environment will be used",
        )
    )
    checks.append(_pair_status("PortalAnaliz credentials", "PA_USERNAME", "PA_PASSWORD", dotenv))
    checks.append(_pair_status("BiznesRadar credentials", "BR_USERNAME", "BR_PASSWORD", dotenv))

    openai = _configured("OPENAI_API_KEY", dotenv)
    anthropic = _configured("ANTHROPIC_API_KEY", dotenv)
    providers = [name for name, present in (("OpenAI", openai), ("Anthropic", anthropic)) if present]
    checks.append(
        Check(
            "AI providers",
            "pass" if providers else "info",
            f"configured: {', '.join(providers)} (values hidden)" if providers else "none configured (optional for deterministic workflow)",
        )
    )

    services = status_payload()
    checks.append(
        Check(
            "PostgreSQL",
            "pass" if services["postgres"]["listening"] else "warn",
            (
                f"listening on {services['postgres']['host']}:"
                f"{services['postgres']['port']}"
                if services["postgres"]["listening"]
                else "not running; ./workbench start will start docker compose postgres"
            ),
        )
    )
    backend_status = services["backend"]
    checks.append(
        Check(
            "Backend API",
            "pass" if backend_status["health_status"] == 200 else "warn",
            f"healthy at {BACKEND_URL}" if backend_status["health_status"] == 200 else f"not healthy at {BACKEND_URL}",
        )
    )
    checks.append(
        Check(
            "Frontend",
            "pass" if services["frontend"]["listening"] else "warn",
            f"listening at {FRONTEND_URL}" if services["frontend"]["listening"] else f"not running at {FRONTEND_URL}",
        )
    )

    if backend_status["health_status"] == 200:
        source_status, sources = _http_json(f"{BACKEND_URL}/api/health/scrapers")
        if source_status == 200 and isinstance(sources, dict):
            for name, info in sources.items():
                errors = info.get("errors_24h", 0)
                last_ok = info.get("last_ok_at")
                source_state = info.get("status", "unknown")
                check_state = {
                    "healthy": "pass",
                    "recovered": "pass",
                    "degraded": "warn",
                    "unknown": "info",
                }.get(source_state, "warn")
                checks.append(
                    Check(
                        f"Stored source health: {name}",
                        check_state,
                        (
                            f"state: {source_state}; last success: "
                            f"{last_ok or 'none'}; historical errors 24h: {errors}"
                        ),
                    )
                )
        else:
            checks.append(Check("Stored source health", "warn", "diagnostics endpoint unavailable"))
    else:
        checks.append(
            Check(
                "Stored source health",
                "info",
                "not checked because backend is offline; no external requests were made",
            )
        )

    return checks


def _spawn(name: str, command: list[str], cwd: Path, port: int, env: dict[str, str] | None = None) -> Check:
    status = _owned_status(name, port)
    if status["owned_process_alive"]:
        return Check(name, "pass", f"already running (pid {status['pid']})")
    if status["listening"]:
        return Check(name, "pass", f"port {port} already served by an external process; left untouched")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = STATE_DIR / f"{name}.log"
    try:
        log_handle = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
    except OSError as exc:
        return Check(name, "fail", f"could not start: {exc}")
    finally:
        if "log_handle" in locals():
            log_handle.close()
    _pid_path(name).write_text(str(process.pid), encoding="utf-8")
    return Check(name, "pass", f"started pid {process.pid}; log: {log_path}")


def _start_postgres() -> Check:
    """Start Docker/Postgres and apply migrations, with a Mac Docker Desktop assist."""
    docker = _run(["docker", "compose", "up", "-d", "postgres"], timeout=40)
    if (docker is None or docker.returncode != 0) and sys.platform == "darwin":
        docker_installed = _run(["open", "-Ra", "Docker"])
        if docker_installed and docker_installed.returncode == 0:
            _run(["open", "-a", "Docker"])
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                info = _run(["docker", "info"], timeout=3)
                if info and info.returncode == 0:
                    break
                time.sleep(1)
            docker = _run(["docker", "compose", "up", "-d", "postgres"], timeout=40)

    if docker is None or docker.returncode != 0:
        detail = "docker compose failed or is unavailable"
        if docker and docker.stderr.strip():
            detail += f": {docker.stderr.strip().splitlines()[-1]}"
        return Check("postgres", "fail", detail)

    database_host, database_port = _database_endpoint()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not _port_open(database_port, database_host):
        time.sleep(0.5)
    if not _port_open(database_port, database_host):
        return Check(
            "postgres",
            "fail",
            f"container started but {database_host}:{database_port} did not become ready",
        )

    migration = _run(
        [str(_python_executable()), "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        timeout=40,
    )
    if migration is None or migration.returncode != 0:
        detail = "Postgres is ready but Alembic migration failed"
        if migration and migration.stderr.strip():
            detail += f": {migration.stderr.strip().splitlines()[-1]}"
        return Check("postgres", "fail", detail)
    return Check(
        "postgres",
        "pass",
        f"Docker Postgres ready at {database_host}:{database_port}; migrations at head",
    )


def start_services(open_browser: bool = False) -> list[Check]:
    checks: list[Check] = []
    backend_before = _owned_status("backend", 8000)
    frontend_before = _owned_status("frontend", 3000)
    postgres = _start_postgres()
    checks.append(postgres)
    if postgres.status == "fail":
        return checks

    if not (FRONTEND / "node_modules" / ".bin" / "next").exists():
        checks.append(Check("frontend", "fail", "dependencies missing; run: cd frontend && npm ci"))
        return checks

    checks.append(
        _spawn(
            "backend",
            [str(_python_executable()), "-m", "uvicorn", "app.main:app", "--port", "8000"],
            BACKEND,
            8000,
        )
    )
    frontend_env = os.environ.copy()
    frontend_env.setdefault("BACKEND_URL", BACKEND_URL)
    checks.append(
        _spawn("frontend", ["npm", "run", "dev"], FRONTEND, 3000, env=frontend_env)
    )

    deadline = time.monotonic() + 35
    backend_ok = frontend_ok = False
    while time.monotonic() < deadline:
        backend_ok = _http_json(f"{BACKEND_URL}/api/health", timeout=0.8)[0] == 200
        frontend_ok = _port_open(3000)
        if backend_ok and frontend_ok:
            break
        time.sleep(0.5)
    checks.append(
        Check(
            "startup health",
            "pass" if backend_ok and frontend_ok else "fail",
            f"backend={'ok' if backend_ok else 'not ready'}, frontend={'ok' if frontend_ok else 'not ready'}; logs: {STATE_DIR}",
        )
    )

    if backend_ok and frontend_ok:
        app_was_already_ready = backend_before["listening"] and frontend_before["listening"]
        if app_was_already_ready:
            checks.append(Check("session hook", "info", "skipped; workbench already ready"))
        else:
            checks.append(_start_session_hook())

    if open_browser and frontend_ok:
        opener = _run(["open", FRONTEND_URL])
        checks.append(
            Check("open browser", "pass" if opener and opener.returncode == 0 else "warn", FRONTEND_URL)
        )
    return checks


def stop_services() -> list[Check]:
    checks: list[Check] = []
    session_pid = _read_pid_file(SESSION_HOOK_PID)
    if not _pid_alive(session_pid):
        SESSION_HOOK_PID.unlink(missing_ok=True)
        checks.append(Check("session hook", "info", "no active workbench-owned hook"))
    else:
        try:
            if os.name == "posix":
                os.killpg(session_pid, signal.SIGTERM)
            else:  # pragma: no cover - Windows fallback
                os.kill(session_pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and _pid_alive(session_pid):
                time.sleep(0.1)
            if _pid_alive(session_pid):
                if os.name == "posix":
                    os.killpg(session_pid, signal.SIGKILL)
                else:  # pragma: no cover
                    os.kill(session_pid, signal.SIGKILL)
            SESSION_HOOK_PID.unlink(missing_ok=True)
            checks.append(Check("session hook", "pass", f"stopped workbench-owned pid {session_pid}"))
        except OSError as exc:
            checks.append(Check("session hook", "warn", f"could not stop pid {session_pid}: {exc}"))
    for name in ("frontend", "backend"):
        pid = _read_pid(name)
        if not _pid_alive(pid):
            _pid_path(name).unlink(missing_ok=True)
            checks.append(Check(name, "info", "no workbench-owned process"))
            continue
        try:
            if os.name == "posix":
                os.killpg(pid, signal.SIGTERM)
            else:  # pragma: no cover - Windows fallback
                os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and _pid_alive(pid):
                time.sleep(0.1)
            if _pid_alive(pid):
                if os.name == "posix":
                    os.killpg(pid, signal.SIGKILL)
                else:  # pragma: no cover
                    os.kill(pid, signal.SIGKILL)
            _pid_path(name).unlink(missing_ok=True)
            checks.append(Check(name, "pass", f"stopped workbench-owned pid {pid}"))
        except OSError as exc:
            checks.append(Check(name, "warn", f"could not stop pid {pid}: {exc}"))
    checks.append(Check("postgres", "info", "left running; use `docker compose stop postgres` if desired"))
    return checks


def _print_checks(checks: list[Check], as_json: bool) -> None:
    if as_json:
        print(json.dumps([asdict(check) for check in checks], indent=2, ensure_ascii=False))
        return
    marks = {"pass": "OK", "warn": "WARN", "fail": "FAIL", "info": "INFO"}
    for check in checks:
        print(f"[{marks.get(check.status, check.status.upper()):4}] {check.name}: {check.detail}")


def _print_status(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    postgres = "listening" if payload["postgres"]["listening"] else "stopped"
    print(
        f"PostgreSQL: {postgres} on {payload['postgres']['host']}:"
        f"{payload['postgres']['port']}"
    )
    for name in ("backend", "frontend"):
        item = payload[name]
        print(
            f"{name.capitalize()}: {item['ownership']} (port {item['port']} "
            f"{'listening' if item['listening'] else 'stopped'}, pid {item['pid'] or '—'})"
        )
    print(f"Logs/state: {payload['state_dir']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workbench", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    for name in ("doctor", "status", "stop"):
        command = sub.add_parser(name)
        command.add_argument("--json", action="store_true", dest="as_json")
    start = sub.add_parser("start")
    start.add_argument("--json", action="store_true", dest="as_json")
    start.add_argument("--open", action="store_true", dest="open_browser")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "doctor"
    as_json = getattr(args, "as_json", False)
    if command == "doctor":
        checks = doctor_checks()
        _print_checks(checks, as_json)
        return 1 if any(check.status == "fail" for check in checks) else 0
    if command == "status":
        _print_status(status_payload(), as_json)
        return 0
    if command == "start":
        checks = start_services(getattr(args, "open_browser", False))
        _print_checks(checks, as_json)
        return 1 if any(check.status == "fail" for check in checks) else 0
    if command == "stop":
        checks = stop_services()
        _print_checks(checks, as_json)
        return 1 if any(check.status == "fail" for check in checks) else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
