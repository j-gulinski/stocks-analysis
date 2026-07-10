"""Pure deterministic monitor snapshot and diff helpers.

The service consumes an already available dossier/event read. It never fetches
HTTP data and never calls a model, which keeps a change card auditable.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any


def build_snapshot(dossier: dict, event_reports: Iterable[dict]) -> dict:
    """Keep only decision-relevant, stable fields for comparison."""
    checks = {
        row.get("id"): row.get("verdict")
        for row in (dossier.get("prescore", {}).get("checks", []) or [])
        if row.get("id")
    }
    thesis = dossier.get("thesis") or {}
    result_quality = dossier.get("result_quality") or {}
    valuation = dossier.get("valuation") or {}
    pe_history = dossier.get("pe_history") or {}
    events = [
        {
            "external_id": row.get("external_id"),
            "title": row.get("title"),
            "published_at": row.get("published_at"),
        }
        for row in event_reports
        if row.get("external_id")
    ]
    events.sort(key=lambda row: row["external_id"])
    return {
        "checks": checks,
        "thesis": {
            "entry_quality": (thesis.get("entry_quality") or {}).get("code"),
            "thesis_read": thesis.get("thesis_read"),
            "verify_next": [
                row.get("id")
                for row in (thesis.get("verify_next", []) or [])
                if row.get("id")
            ],
        },
        "result_quality": {
            "cause_status": result_quality.get("cause_status"),
            "is_material": result_quality.get("is_material"),
            "valuation_basis": result_quality.get("valuation_basis"),
        },
        "valuation": {
            "value_pct": (valuation.get("potential") or {}).get("value_pct"),
            "range_pct": (valuation.get("potential") or {}).get("range_pct"),
            "confidence": (valuation.get("confidence") or {}).get("level"),
        },
        "pe_history": {
            "current": pe_history.get("current"),
            "median": pe_history.get("median"),
        },
        "events": events,
    }


def snapshot_hash(snapshot: dict) -> str:
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else key
            result.update(_flatten(value[key], child))
        return result
    return {prefix: value}


def _kind(path: str) -> str:
    if path.startswith("checks"):
        return "check"
    if path.startswith("thesis"):
        return "thesis"
    if path.startswith("valuation") or path.startswith("pe_history"):
        return "valuation"
    if path.startswith("events"):
        return "event"
    return "result_quality"


def diff_snapshots(before: dict, after: dict) -> list[dict]:
    """Return stable change cards; unchanged values never produce a card."""
    old = _flatten(before)
    new = _flatten(after)
    changes: list[dict] = []
    for path in sorted(set(old) | set(new)):
        if old.get(path) == new.get(path):
            continue
        changes.append(
            {
                "kind": _kind(path),
                "key": path,
                "before": old.get(path),
                "after": new.get(path),
                "summary": f"Zmieniono {path}.",
            }
        )
    return changes
