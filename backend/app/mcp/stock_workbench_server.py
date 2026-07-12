"""Minimal stdio MCP server for the Stock Analysis Workbench.

Codex starts this process from `.codex/config.toml`. The transport is
newline-delimited JSON-RPC over stdin/stdout, which keeps the server dependency
free and easy to regression-test.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.mcp import stock_tools
from scripts.codex_common import json_safe

JsonDict = dict[str, Any]
ToolHandler = Callable[[JsonDict], JsonDict]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: JsonDict
    handler: ToolHandler

    def as_mcp_tool(self) -> JsonDict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


TOOLS: dict[str, ToolSpec] = {
    "get_watchlist": ToolSpec(
        "get_watchlist",
        "Return watched companies from the local Stock Analysis Workbench.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        lambda args: stock_tools.get_watchlist(args),
    ),
    "get_model_policy": ToolSpec(
        "get_model_policy",
        "Return provider-free Codex role and verification guidance for a workflow.",
        {
            "type": "object",
            "properties": {"workflow": {"type": "string"}},
            "required": ["workflow"],
            "additionalProperties": False,
        },
        stock_tools.get_model_policy,
    ),
    "get_archetype_pack": ToolSpec(
        "get_archetype_pack",
        "Return the canonical version and required Polish focus markers for one research archetype.",
        {
            "type": "object",
            "properties": {"archetype": {"type": "string"}},
            "required": ["archetype"],
            "additionalProperties": False,
        },
        stock_tools.get_archetype_pack,
    ),
    "get_valuation_method_packs": ToolSpec(
        "get_valuation_method_packs",
        "Return versioned valuation methods and honest readiness/block reasons.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        stock_tools.get_valuation_method_packs,
    ),
    "get_company_dossier": ToolSpec(
        "get_company_dossier",
        "Return the deterministic company dossier used by the UI and Codex skills.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "use_ai_refiners": {"type": "boolean", "default": False},
            },
            "required": ["ticker"],
            "additionalProperties": False,
        },
        stock_tools.get_company_dossier,
    ),
    "list_queued_agent_runs": ToolSpec(
        "list_queued_agent_runs",
        "List queued or filtered Codex workflow runs.",
        {
            "type": "object",
            "properties": {
                "status": {"type": "string", "default": "queued"},
                "workflow": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
        lambda args: stock_tools.list_queued_agent_runs(args),
    ),
    "get_recent_source_deltas": ToolSpec(
        "get_recent_source_deltas",
        "Read recently stored source events for a ticker or watchlist.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "since": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
        lambda args: stock_tools.get_recent_source_deltas(args),
    ),
    "queue_agent_run": ToolSpec(
        "queue_agent_run",
        "Create a queued Codex workflow run for later pickup.",
        {
            "type": "object",
            "properties": {
                "workflow": {"type": "string"},
                "ticker": {"type": "string"},
                "model_role": {"type": "string"},
                "model": {"type": "string"},
                "orchestrator_model": {"type": "string"},
                "trigger": {"type": "string", "default": "ui-request"},
                "inputs": {"type": "object"},
            },
            "required": ["workflow"],
            "additionalProperties": False,
        },
        stock_tools.queue_agent_run,
    ),
    "claim_agent_run": ToolSpec(
        "claim_agent_run",
        "Mark a queued Codex workflow run as running.",
        {
            "type": "object",
            "properties": {
                "agent_run_id": {"type": "integer"},
                "model_role": {"type": "string"},
                "model": {"type": "string"},
                "orchestrator_model": {"type": "string"},
                "worker_id": {"type": "string"},
                "lease_minutes": {"type": "integer", "minimum": 5, "maximum": 240},
            },
            "required": ["agent_run_id"],
            "additionalProperties": False,
        },
        stock_tools.claim_agent_run,
    ),
    "save_analysis_run": ToolSpec(
        "save_analysis_run",
        "Persist a draft, verified, or rejected Codex analysis for UI display.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "workflow": {"type": "string"},
                "model_role": {"type": "string"},
                "model": {"type": "string"},
                "verification_status": {"type": "string"},
                "status": {"type": "string"},
                "source": {"type": "string"},
                "created_by": {"type": "string"},
                "agent_run_id": {"type": "integer"},
                "trigger": {"type": "string"},
                "input_snapshot": {"type": "object"},
                "output": {"type": "object"},
                "verification": {"type": "object"},
                "alignment_score": {"type": "integer"},
            },
            "required": [
                "ticker",
                "workflow",
                "model_role",
                "model",
                "verification_status",
                "output",
            ],
            "additionalProperties": False,
        },
        stock_tools.save_analysis_run,
    ),
    "complete_agent_run": ToolSpec(
        "complete_agent_run",
        "Complete a queued workflow that stores output directly on agent_runs.",
        {
            "type": "object",
            "properties": {
                "agent_run_id": {"type": "integer"},
                "verification_status": {"type": "string"},
                "status": {"type": "string"},
                "model_role": {"type": "string"},
                "model": {"type": "string"},
                "orchestrator_model": {"type": "string"},
                "output": {"type": "object"},
                "verification": {"type": "object"},
                "error": {"type": "string"},
            },
            "required": ["agent_run_id", "verification_status", "output"],
            "additionalProperties": False,
        },
        stock_tools.complete_agent_run,
    ),
    "save_research_snapshot": ToolSpec(
        "save_research_snapshot",
        "Validate and persist one immutable versioned research snapshot for a claimed run.",
        {
            "type": "object",
            "properties": {
                "case_id": {"type": "integer", "minimum": 1},
                "payload": {"type": "object"},
            },
            "required": ["case_id", "payload"],
            "additionalProperties": False,
        },
        stock_tools.save_research_snapshot,
    ),
    "verify_research_snapshot": ToolSpec(
        "verify_research_snapshot",
        "Persist an independent verdict bound to one exact versioned research snapshot draft.",
        {
            "type": "object",
            "properties": {
                "case_id": {"type": "integer", "minimum": 1},
                "payload": {"type": "object"},
            },
            "required": ["case_id", "payload"],
            "additionalProperties": False,
        },
        stock_tools.verify_research_snapshot,
    ),
    "save_valuation_snapshot": ToolSpec(
        "save_valuation_snapshot",
        "Save an immutable valuation after exact independent verification.",
        {
            "type": "object",
            "properties": {"case_id": {"type": "integer"}, "payload": {"type": "object"}},
            "required": ["case_id", "payload"],
            "additionalProperties": False,
        },
        stock_tools.save_valuation_snapshot,
    ),
    "verify_valuation_snapshot": ToolSpec(
        "verify_valuation_snapshot",
        "Record verifier_strict probabilities and verdict for one exact valuation draft.",
        {
            "type": "object",
            "properties": {"case_id": {"type": "integer"}, "payload": {"type": "object"}},
            "required": ["case_id", "payload"],
            "additionalProperties": False,
        },
        stock_tools.verify_valuation_snapshot,
    ),
    "mark_verification_result": ToolSpec(
        "mark_verification_result",
        "Attach verifier output to an agent or analysis run.",
        {
            "type": "object",
            "properties": {
                "agent_run_id": {"type": "integer"},
                "analysis_run_id": {"type": "integer"},
                "model_role": {"type": "string", "default": "verifier_strict"},
                "verifier_model": {"type": "string"},
                "verdict": {"type": "string"},
                "checks": {"type": "object"},
                "summary": {"type": "string"},
            },
            "required": ["verifier_model", "verdict"],
            "additionalProperties": False,
        },
        stock_tools.mark_verification_result,
    ),
    "poll_espi_watchlist": ToolSpec(
        "poll_espi_watchlist",
        "Fetch and store GPW ESPI/EBI reports for watched companies.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "fetch_details": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
        lambda args: stock_tools.poll_espi_watchlist(args),
    ),
    "prepare_pre_session_brief": ToolSpec(
        "prepare_pre_session_brief",
        "Fetch ESPI/EBI and queue a Codex pre-session brief workflow.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "trigger": {"type": "string", "default": "scheduled"},
                "orchestrator_model": {"type": "string"},
                "fetch_details": {"type": "boolean", "default": True},
                "queue": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
        lambda args: stock_tools.prepare_pre_session_brief(args),
    ),
    "assess_data_readiness": ToolSpec(
        "assess_data_readiness",
        "Assess stored-company research-data readiness; this is not an investment rank.",
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "ticker": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
            },
            "additionalProperties": False,
        },
        lambda args: stock_tools.assess_data_readiness(args),
    ),
    "run_backtest": ToolSpec(
        "run_backtest",
        "Run deterministic point-in-time backtest replay and persist observations.",
        {
            "type": "object",
            "properties": {
                "strategy": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "ticker": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
                "outcome_windows": {"type": "array", "items": {"type": "integer"}},
                "financial_availability_policy": {
                    "type": "string",
                    "enum": ["scraped_at", "estimated_period_lag"],
                    "default": "scraped_at",
                },
                "report_lag_days": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 730,
                    "default": 120,
                },
            },
            "required": ["strategy", "from_date", "to_date"],
            "additionalProperties": False,
        },
        stock_tools.run_backtest,
    ),
    "evaluate_agent_runs": ToolSpec(
        "evaluate_agent_runs",
        "Replay saved agent analyses against future price outcomes.",
        {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "string",
                    "default": "valuation_direction_v1",
                },
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "ticker": {"type": "string"},
                "workflow": {"type": "string"},
                "outcome_windows": {"type": "array", "items": {"type": "integer"}},
            },
            "additionalProperties": False,
        },
        lambda args: stock_tools.evaluate_agent_runs(args),
    ),
}

INSTRUCTIONS = (
    "Use these tools as the Stock Analysis Workbench system of record. "
    "Read tools are safe. Mutating tools save rows for the UI and must be used "
    "only with explicit structured inputs, model role, model, workflow, and "
    "verification status where required. Never invent missing facts."
)


def _success(message_id: Any, result: JsonDict) -> JsonDict:
    return {"jsonrpc": "2.0", "id": message_id, "result": json_safe(result)}


def _error(message_id: Any, code: int, message: str, data: Any | None = None) -> JsonDict:
    error: JsonDict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": message_id, "error": error}


def _tool_result(payload: JsonDict, *, is_error: bool = False) -> JsonDict:
    safe = json_safe(payload)
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(safe, ensure_ascii=False, sort_keys=True),
            }
        ],
        "structuredContent": safe,
        "isError": is_error,
    }


def handle_message(message: JsonDict) -> JsonDict | None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _success(
            message_id,
            {
                "protocolVersion": "2025-03-26",
                "serverInfo": {
                    "name": "stock-analysis-workbench",
                    "version": "0.1.0",
                },
                "capabilities": {"tools": {}},
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _success(
            message_id,
            {"tools": [tool.as_mcp_tool() for tool in TOOLS.values()]},
        )
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _success(
                message_id,
                _tool_result(
                    {"ok": False, "error": "Tool arguments must be an object."},
                    is_error=True,
                ),
            )
        tool = TOOLS.get(str(name))
        if tool is None:
            return _error(message_id, -32602, f"Unknown tool: {name}")
        try:
            return _success(message_id, _tool_result(tool.handler(arguments)))
        except stock_tools.ToolInputError as exc:
            return _success(
                message_id,
                _tool_result({"ok": False, "error": str(exc)}, is_error=True),
            )
        except Exception as exc:  # pragma: no cover - defensive RPC boundary
            return _success(
                message_id,
                _tool_result(
                    {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                    is_error=True,
                ),
            )
    if message_id is None:
        return None
    return _error(message_id, -32601, f"Method not found: {method}")


def serve_stdio() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"Parse error: {exc}")
        else:
            response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_stdio())
