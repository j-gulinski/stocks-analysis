"""Durable claim and lease operations for Codex-operated agent runs.

The web app owns queue state, while a Codex task owns the leased work.  Claims
use a compare-and-swap update so two scheduled workers cannot both receive the
same queued row, including when the database is PostgreSQL rather than the
single-connection SQLite test database.
"""
from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.db.models import AgentRun, utcnow
from app.services.model_policy import CANONICAL_WORKFLOWS

DEFAULT_LEASE_MINUTES = 45
DEFAULT_MAX_ATTEMPTS = 3


class AgentQueueError(ValueError):
    """A queue operation cannot be applied to the requested run."""


def default_worker_id() -> str:
    return f"codex:{socket.gethostname()}:{os.getpid()}"


def _lease_expiry(now: datetime, lease_minutes: int) -> datetime:
    bounded = min(max(int(lease_minutes), 5), 240)
    return now + timedelta(minutes=bounded)


def claim_agent_run(
    db: Session,
    *,
    agent_run_id: int | None = None,
    workflow: str | None = None,
    worker_id: str | None = None,
    model_role: str | None = None,
    model: str | None = None,
    orchestrator_model: str | None = None,
    lease_minutes: int = DEFAULT_LEASE_MINUTES,
) -> AgentRun | None:
    """Atomically claim one queued run, or return ``None`` for an empty queue."""
    worker_id = (worker_id or default_worker_id())[:160]

    for _ in range(3):
        now = utcnow()
        stmt = select(AgentRun.id).where(
            AgentRun.workflow.in_(CANONICAL_WORKFLOWS),
            AgentRun.status == "queued",
            or_(AgentRun.available_at.is_(None), AgentRun.available_at <= now),
        )
        if agent_run_id is not None:
            stmt = stmt.where(AgentRun.id == agent_run_id)
        elif workflow:
            stmt = stmt.where(AgentRun.workflow == workflow)
        stmt = stmt.order_by(AgentRun.created_at.asc(), AgentRun.id.asc()).limit(1)
        candidate_id = db.scalar(stmt)
        if candidate_id is None:
            if agent_run_id is not None and db.get(AgentRun, agent_run_id) is None:
                raise AgentQueueError(f"Unknown agent_run_id {agent_run_id}.")
            if agent_run_id is not None:
                current = db.get(AgentRun, agent_run_id)
                if current.workflow not in CANONICAL_WORKFLOWS:
                    raise AgentQueueError(
                        f"Agent run {agent_run_id} uses deleted workflow "
                        f"'{current.workflow}'."
                    )
                raise AgentQueueError(
                    f"Agent run {agent_run_id} has status '{current.status}', not 'queued'."
                )
            return None

        values: dict[str, object] = {
            "status": "running",
            "started_at": now,
            "heartbeat_at": now,
            "lease_expires_at": _lease_expiry(now, lease_minutes),
            "lease_owner": worker_id,
            "attempt_count": AgentRun.attempt_count + 1,
            "updated_at": now,
        }
        if model_role:
            values["model_role"] = model_role
        if model:
            values["model"] = model
        if orchestrator_model:
            values["orchestrator_model"] = orchestrator_model

        claimed = db.execute(
            update(AgentRun)
            .where(AgentRun.id == candidate_id, AgentRun.status == "queued")
            .values(**values)
        )
        if claimed.rowcount == 1:
            db.commit()
            agent = db.get(AgentRun, candidate_id)
            if agent is None:  # pragma: no cover - row cannot disappear normally
                raise AgentQueueError(f"Agent run {candidate_id} disappeared after claim.")
            db.refresh(agent)
            return agent
        db.rollback()

    raise AgentQueueError("Queue claim lost a race three times; retry later.")


def heartbeat_agent_run(
    db: Session,
    agent_run_id: int,
    *,
    worker_id: str | None = None,
    lease_minutes: int = DEFAULT_LEASE_MINUTES,
) -> AgentRun:
    """Extend a running worker lease without changing workflow output."""
    agent = db.get(AgentRun, agent_run_id)
    if agent is None:
        raise AgentQueueError(f"Unknown agent_run_id {agent_run_id}.")
    if agent.workflow not in CANONICAL_WORKFLOWS:
        raise AgentQueueError(
            f"Agent run {agent_run_id} uses deleted workflow '{agent.workflow}'."
        )
    if agent.status != "running":
        raise AgentQueueError(
            f"Agent run {agent_run_id} has status '{agent.status}', not 'running'."
        )
    if worker_id and agent.lease_owner and agent.lease_owner != worker_id:
        raise AgentQueueError(f"Agent run {agent_run_id} is leased by another worker.")
    now = utcnow()
    agent.heartbeat_at = now
    agent.lease_expires_at = _lease_expiry(now, lease_minutes)
    agent.updated_at = now
    db.commit()
    db.refresh(agent)
    return agent


def clear_agent_lease(agent: AgentRun) -> None:
    """Clear ownership after a terminal result is durably written."""
    agent.lease_owner = None
    agent.lease_expires_at = None
    agent.heartbeat_at = utcnow()


def recover_expired_agent_runs(
    db: Session,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    now: datetime | None = None,
) -> list[AgentRun]:
    """Requeue expired runs, or stop retrying after the configured attempt cap."""
    now = now or datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(AgentRun)
            .where(
                AgentRun.workflow.in_(CANONICAL_WORKFLOWS),
                AgentRun.status == "running",
                AgentRun.lease_expires_at.is_not(None),
                AgentRun.lease_expires_at < now,
            )
            .order_by(AgentRun.lease_expires_at.asc(), AgentRun.id.asc())
        )
    )
    for agent in rows:
        recovery = {
            "recovered_at": now.isoformat(),
            "previous_lease_owner": agent.lease_owner,
            "previous_lease_expires_at": agent.lease_expires_at.isoformat()
            if agent.lease_expires_at
            else None,
        }
        agent.outputs = {**(agent.outputs or {}), "queue_recovery": recovery}
        agent.error = "worker lease expired; run returned to the durable queue"
        if (agent.attempt_count or 0) >= max(1, max_attempts):
            agent.status = "needs-human"
            agent.finished_at = now
        else:
            agent.status = "queued"
            agent.started_at = None
            agent.finished_at = None
        agent.lease_owner = None
        agent.heartbeat_at = now
        agent.lease_expires_at = None
        agent.updated_at = now
    if rows:
        db.commit()
        for agent in rows:
            db.refresh(agent)
    return rows
