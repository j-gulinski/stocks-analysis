"""Single explicit workflow for a full-company investment verdict."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.executor import ModelExecutionError, execute_verdict
from app.analysis.providers import AnthropicProvider, ModelProvider
from app.analysis.recovery import reconcile_stale_runs
from app.analysis import usage
from app.db.models import Analysis, Company, ForumPost, ForumTopic
from app.services import analysis_scoring
from app.services import dossier as dossier_service
from app.services import prompts as prompts_service

PURPOSE = "investment_verdict"
SKILL_VERSION = "malik-obs-analyst@1"
FORUM_POST_LIMIT = 40


class AnalysisRunError(Exception):
    def __init__(self, code: str, public_detail: str, *, http_status: int = 503):
        super().__init__(public_detail)
        self.code = code
        self.public_detail = public_detail
        self.http_status = http_status


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _idempotency_hash(
    key: str | None, *, ticker: str, user_email: str | None
) -> str | None:
    if not key:
        return None
    scoped = f"{user_email or 'anonymous'}\0{ticker}\0{PURPOSE}\0{key}"
    return hashlib.sha256(scoped.encode("utf-8")).hexdigest()


def _recent_forum_posts(db: Session, company_id: int) -> list[dict]:
    rows = db.scalars(
        select(ForumPost)
        .join(ForumTopic, ForumPost.topic_id == ForumTopic.id)
        .where(ForumTopic.company_id == company_id)
        .order_by(ForumPost.posted_at.desc())
        .limit(FORUM_POST_LIMIT)
    ).all()
    return [
        {
            "post_id": row.phpbb_post_id,
            "author": row.author,
            "posted_at": row.posted_at,
            "upvotes": row.upvotes,
            "content_text": row.content_text,
        }
        for row in rows
    ]


def _existing_idempotent_run(
    db: Session, key_hash: str | None
) -> Analysis | None:
    if key_hash is None:
        return None
    return db.scalar(
        select(Analysis).where(Analysis.idempotency_key_hash == key_hash)
    )


def _resolve_existing(record: Analysis) -> Analysis:
    if record.status == "succeeded":
        return record
    if record.status == "running":
        raise AnalysisRunError(
            "run_in_progress",
            "Analiza z tym kluczem jest już wykonywana.",
            http_status=409,
        )
    raise AnalysisRunError(
        "previous_run_failed",
        "Poprzednia analiza z tym kluczem zakończyła się błędem.",
    )


def _failure_public_detail(code: str) -> str:
    return {
        "missing_configuration": (
            "Analiza AI wymaga skonfigurowania dostawcy modelu."
        ),
        "invalid_output": (
            "Dostawca zwrócił odpowiedź niezgodną z kontraktem analizy."
        ),
        "transport_error": (
            "Dostawca modelu jest chwilowo niedostępny; próba została zapisana."
        ),
        "refused": "Dostawca odmówił wykonania analizy; odmowa została zapisana.",
        "truncated": (
            "Odpowiedź dostawcy została obcięta przed ukończeniem analizy."
        ),
        "call_limit": (
            "Osiągnięto dzienny limit wywołań lub tokenów modeli."
        ),
    }.get(code, "Analiza AI nie mogła zostać ukończona.")


def run_analysis(
    db: Session,
    company: Company,
    settings,
    *,
    user_email: str | None,
    idempotency_key: str | None = None,
    provider: ModelProvider | None = None,
) -> Analysis:
    """Create/reuse one run and drive it synchronously to a terminal state."""
    reconcile_stale_runs(db)
    key_hash = _idempotency_hash(
        idempotency_key, ticker=company.ticker, user_email=user_email
    )
    existing = _existing_idempotent_run(db, key_hash)
    if existing is not None:
        return _resolve_existing(existing)

    provider = provider or AnthropicProvider(settings)
    dossier = dossier_service.build_dossier(db, company)
    forum_posts = _recent_forum_posts(db, company.id)
    # Until forum distillation is migrated through the same executor, use the
    # deterministic, token-capped raw-opinion path. This prevents up to 40
    # invisible provider calls while retaining labelled forum context.
    prompt_bundle = prompts_service.build_analysis_prompt(dossier, forum_posts)
    as_of = datetime.now(timezone.utc)
    forum_ids = sorted(
        {
            post["post_id"]
            for post in prompt_bundle["snapshot"]["forum_posts"]
            if isinstance(post.get("post_id"), int)
        }
    )

    configured_run_limit = getattr(settings, "ai_daily_limit", 20)
    limit = 20 if configured_run_limit is None else int(configured_run_limit)
    if not usage.reserve_run(db, "_all", limit):
        raise AnalysisRunError(
            "daily_limit",
            f"Osiągnięto dzienny limit analiz AI ({limit}). Spróbuj ponownie jutro.",
            http_status=429,
        )

    record = Analysis(
        company_id=company.id,
        provider=provider.name,
        model=provider.model,
        purpose=PURPOSE,
        status="running",
        as_of=as_of,
        heartbeat_at=as_of,
        prescore=dossier["prescore"],
        input_snapshot={
            "ticker": company.ticker,
            "as_of": as_of.isoformat(),
            "prompt": prompt_bundle,
        },
        evidence_ids={"forum_post_ids": forum_ids},
        skill_version=SKILL_VERSION,
        skill_hash=_sha256(prompt_bundle["system"]),
        model_configuration={
            "structured_output": "forced_tool",
            "score_owner": "server",
            "forum_context": "raw_opinions_token_capped",
        },
        idempotency_key_hash=key_hash,
        created_by=user_email,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        usage.release_run(db, "_all")
        concurrent = _existing_idempotent_run(db, key_hash)
        if concurrent is not None:
            return _resolve_existing(concurrent)
        raise exc

    started = datetime.now(timezone.utc)
    try:
        result = execute_verdict(
            db,
            record,
            provider,
            prompt_bundle,
            ticker=company.ticker,
            call_limit=int(getattr(settings, "ai_daily_call_limit", 60)),
            token_limit=int(getattr(settings, "ai_daily_token_limit", 500_000)),
        )
    except ModelExecutionError as exc:
        completed = datetime.now(timezone.utc)
        record.status = "failed"
        record.error = exc.detail[:4000]
        record.validation = {
            "status": "failed",
            "error_code": exc.code,
            "forum_context": "raw_opinions_token_capped",
        }
        record.completed_at = completed
        record.heartbeat_at = completed
        record.latency_ms = round((completed - started).total_seconds() * 1000)
        db.commit()
        public_detail = _failure_public_detail(exc.code)
        if exc.code == "transport_error":
            public_detail = (
                "Analiza AI nie powiodła się: błąd wywołania API Claude. "
                f"Szczegóły: {exc.detail[:200]}"
            )
        raise AnalysisRunError(
            exc.code,
            public_detail,
            http_status=(
                429
                if exc.code == "call_limit"
                else 502
                if exc.code == "transport_error"
                else 503
            ),
        ) from exc

    completed = datetime.now(timezone.utc)
    verdict = dict(result.verdict)
    score = analysis_scoring.compute_alignment_score(verdict, dossier)
    verdict["alignment_score"] = score
    record.model = result.model
    record.status = "succeeded"
    record.output = verdict
    record.validation = {
        "status": "passed",
        "contract": "AnalysisVerdict",
        "strict": True,
        "authoritative_score": "analysis_scoring@1",
        "forum_context": "raw_opinions_token_capped",
        "warnings": [
            "Forum distillation is deferred until child calls use the audited executor."
        ],
    }
    record.alignment_score = score
    record.input_tokens = result.input_tokens
    record.output_tokens = result.output_tokens
    record.completed_at = completed
    record.heartbeat_at = completed
    record.latency_ms = round((completed - started).total_seconds() * 1000)
    db.commit()
    return record
