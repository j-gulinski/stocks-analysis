"""Narrow model-provider interface.

Adapters perform exactly one HTTP invocation and return the provider envelope.
Retries, caching, validation, quotas and persistence belong to the executor and
orchestrator so a future OpenAI adapter cannot silently implement different
business policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.services import claude_client


@dataclass(frozen=True)
class ModelRequest:
    role: str
    model: str
    messages: list[dict]
    tools: list[dict]
    tool_choice: dict
    contract_name: str
    contract_version: str
    operation_key: str
    generation_config: dict


@dataclass(frozen=True)
class ProviderResponse:
    raw: dict
    outcome: Literal["completed", "refused", "truncated"] = "completed"
    provider_request_id: str | None = None
    finish_reason: str | None = None


class ModelProvider(Protocol):
    name: str
    model: str

    def is_configured(self) -> bool: ...

    def invoke(self, request: ModelRequest) -> ProviderResponse: ...


class AnthropicProvider:
    """Temporary Anthropic adapter; one attempt and no policy."""

    name = "anthropic"

    def __init__(self, settings):
        self.settings = settings
        self.model = str(
            getattr(settings, "anthropic_model", None) or "claude-sonnet-5"
        )

    def is_configured(self) -> bool:
        return bool(getattr(self.settings, "anthropic_api_key", None))

    def invoke(self, request: ModelRequest) -> ProviderResponse:
        transport = claude_client.default_transport(self.settings)
        raw = transport(
            request.messages,
            request.model,
            request.tools,
            request.tool_choice,
        )
        finish_reason = raw.get("stop_reason") if isinstance(raw, dict) else None
        outcome: Literal["completed", "refused", "truncated"] = "completed"
        if finish_reason == "max_tokens":
            outcome = "truncated"
        elif finish_reason in {"refusal", "refused"}:
            outcome = "refused"
        return ProviderResponse(
            raw=raw,
            outcome=outcome,
            provider_request_id=raw.get("id") if isinstance(raw, dict) else None,
            finish_reason=finish_reason,
        )
