"""Shared helpers for Codex-facing JSON scripts.

These scripts are the stable local contract that repo skills and the later MCP
server will call. Keep them boring: JSON in, JSON out, non-zero exit on failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class ScriptError(Exception):
    def __init__(self, message: str, *, code: int = 1):
        super().__init__(message)
        self.code = code


def add_json_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def write_json(value: Any, *, pretty: bool = False) -> None:
    kwargs = {"ensure_ascii": False}
    if pretty:
        kwargs["indent"] = 2
        kwargs["sort_keys"] = True
    print(json.dumps(json_safe(value), **kwargs))


def read_payload(path: str | None) -> dict:
    if path in (None, "-"):
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    if not raw.strip():
        raise ScriptError("JSON input is empty.", code=2)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScriptError(f"Invalid JSON input: {exc}", code=2) from exc
    if not isinstance(payload, dict):
        raise ScriptError("JSON input must be an object.", code=2)
    return payload


def require_dict(payload: dict, key: str) -> dict:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ScriptError(f"Required JSON field '{key}' must be an object.", code=2)
    return value


def require_nonempty(value: str | None, name: str) -> str:
    if value is None or not str(value).strip():
        raise ScriptError(f"Missing required argument: {name}", code=2)
    return str(value).strip()


def get_company(db, ticker: str):
    from sqlalchemy import select

    from app.db.models import Company

    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise ScriptError(f"Unknown company '{ticker.upper()}'. Refresh/add it first.", code=1)
    return company


def run_main(fn) -> None:
    try:
        raise SystemExit(fn())
    except ScriptError as exc:
        write_json({"ok": False, "error": str(exc)}, pretty=False)
        raise SystemExit(exc.code)
