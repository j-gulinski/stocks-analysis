"""Audited execution of one structured model operation."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.providers import ModelProvider, ModelRequest
from app.analysis import usage
from app.db.models import Analysis, ModelCall
from app.services import claude_client

MAX_ATTEMPTS = 3


class ModelExecutionError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _fingerprint(provider: ModelProvider, request: ModelRequest) -> str:
    payload = {
        "provider": provider.name,
        "model": request.model,
        "role": request.role,
        "messages": request.messages,
        "tools": request.tools,
        "tool_choice": request.tool_choice,
        "contract": [request.contract_name, request.contract_version],
        "generation_config": request.generation_config,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _record_non_invocation(
    db: Session,
    analysis: Analysis,
    provider: ModelProvider,
    request: ModelRequest,
    request_hash: str,
    *,
    status: str,
    error_code: str | None = None,
    error: str | None = None,
    cache_source: ModelCall | None = None,
    output: dict | None = None,
) -> ModelCall:
    now = datetime.now(timezone.utc)
    call = ModelCall(
        analysis_id=analysis.id,
        role=request.role,
        provider=provider.name,
        model=request.model,
        status=status,
        attempt=0 if cache_source else 1,
        operation_key=request.operation_key,
        contract_name=request.contract_name,
        contract_version=request.contract_version,
        request_hash=request_hash,
        output=output,
        error_code=error_code,
        error=error,
        cache_source_call_id=cache_source.id if cache_source else None,
        cache_hit=cache_source is not None,
        billed=False,
        completed_at=now,
    )
    db.add(call)
    db.commit()
    return call


def execute_verdict(
    db: Session,
    analysis: Analysis,
    provider: ModelProvider,
    prompt_bundle: dict,
    *,
    ticker: str,
    call_limit: int = 60,
    token_limit: int = 500_000,
) -> claude_client.AnalysisResult:
    """Execute or durably reuse the strict investment-verdict operation."""
    messages, tools, tool_choice = claude_client.analysis_request_parts(prompt_bundle)
    request = ModelRequest(
        role="investment_verdict",
        model=provider.model,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        contract_name=claude_client.ANALYSIS_CONTRACT_NAME,
        contract_version=claude_client.ANALYSIS_CONTRACT_VERSION,
        operation_key=f"company:{ticker}:investment_verdict",
        generation_config={"structured_output": "forced_tool"},
    )
    request_hash = _fingerprint(provider, request)
    usage.record_logical_operation(db, provider.name)

    cached = db.scalar(
        select(ModelCall)
        .where(
            ModelCall.provider == provider.name,
            ModelCall.model == provider.model,
            ModelCall.role == request.role,
            ModelCall.request_hash == request_hash,
            ModelCall.contract_version == request.contract_version,
            ModelCall.status == "succeeded",
            ModelCall.output.is_not(None),
        )
        .order_by(ModelCall.completed_at.desc(), ModelCall.id.desc())
        .limit(1)
    )
    if cached is not None:
        # Revalidate durable data against today's contract before reuse.
        verdict = claude_client.validate_analysis_verdict(cached.output)
        _record_non_invocation(
            db,
            analysis,
            provider,
            request,
            request_hash,
            status="cached",
            cache_source=cached,
            output=verdict,
        )
        usage.record_cache_hit(db, provider.name)
        return claude_client.AnalysisResult(
            verdict=verdict,
            input_tokens=0,
            output_tokens=0,
            model=provider.model,
        )

    if not provider.is_configured():
        detail = f"{provider.name} provider is not configured"
        _record_non_invocation(
            db,
            analysis,
            provider,
            request,
            request_hash,
            status="failed",
            error_code="missing_configuration",
            error=detail,
        )
        raise ModelExecutionError("missing_configuration", detail)

    last_error = "provider transport failed"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not usage.reserve_provider_attempt(db, call_limit, token_limit):
            detail = "Global daily provider call/token limit reached."
            _record_non_invocation(
                db,
                analysis,
                provider,
                request,
                request_hash,
                status="rejected",
                error_code="call_limit",
                error=detail,
            )
            raise ModelExecutionError("call_limit", detail)
        started_at = datetime.now(timezone.utc)
        call = ModelCall(
            analysis_id=analysis.id,
            role=request.role,
            provider=provider.name,
            model=provider.model,
            status="running",
            attempt=attempt,
            operation_key=request.operation_key,
            contract_name=request.contract_name,
            contract_version=request.contract_version,
            request_hash=request_hash,
            cache_hit=False,
            billed=None,
            created_at=started_at,
        )
        db.add(call)
        analysis.heartbeat_at = started_at
        db.commit()
        usage.record_provider_attempt(db, provider.name)

        started = time.perf_counter()
        try:
            response = provider.invoke(request)
        except Exception as exc:  # noqa: BLE001 - adapter errors are classified here
            last_error = str(exc)[:4000]
            call.status = "failed"
            call.error_code = "transport_error"
            call.error = last_error
            call.latency_ms = round((time.perf_counter() - started) * 1000)
            call.completed_at = datetime.now(timezone.utc)
            # Unknown: a timeout may occur after the provider accepted work.
            call.billed = None
            db.commit()
            usage.record_attempt_outcome(db, provider.name, billed=None)
            continue

        input_tokens, output_tokens = claude_client.extract_usage(response.raw)
        if response.outcome != "completed":
            call.status = "failed"
            call.error_code = response.outcome
            call.error = f"Provider outcome: {response.outcome}."
            call.provider_request_id = response.provider_request_id
            call.finish_reason = response.finish_reason
            call.input_tokens = input_tokens
            call.output_tokens = output_tokens
            call.latency_ms = round((time.perf_counter() - started) * 1000)
            call.completed_at = datetime.now(timezone.utc)
            call.billed = True
            db.commit()
            usage.record_attempt_outcome(
                db,
                provider.name,
                billed=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            raise ModelExecutionError(response.outcome, call.error)

        try:
            result = claude_client.parse_analysis_response(
                response.raw, model=provider.model
            )
        except claude_client.AnalysisUnavailable as exc:
            call.status = "failed"
            call.error_code = "invalid_output"
            call.error = str(exc)[:4000]
            call.provider_request_id = response.provider_request_id
            call.finish_reason = response.finish_reason
            call.input_tokens = input_tokens
            call.output_tokens = output_tokens
            call.latency_ms = round((time.perf_counter() - started) * 1000)
            call.completed_at = datetime.now(timezone.utc)
            call.billed = True
            db.commit()
            usage.record_attempt_outcome(
                db,
                provider.name,
                billed=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            raise ModelExecutionError("invalid_output", str(exc)) from exc

        call.status = "succeeded"
        call.output = result.verdict
        call.provider_request_id = response.provider_request_id
        call.finish_reason = response.finish_reason
        call.input_tokens = result.input_tokens
        call.output_tokens = result.output_tokens
        call.latency_ms = round((time.perf_counter() - started) * 1000)
        call.completed_at = datetime.now(timezone.utc)
        call.billed = True
        db.commit()
        usage.record_attempt_outcome(
            db,
            provider.name,
            billed=True,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        return result

    raise ModelExecutionError("transport_error", last_error)
