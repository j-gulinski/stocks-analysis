"""Canonical durable queue lease/recovery mechanics (VISION V6)."""

from datetime import datetime, timedelta, timezone

import pytest


def test_agent_run_lease_heartbeat_and_bounded_recovery(db):
    from app.db.models import AgentRun
    from app.services.agent_queue import (
        AgentQueueError,
        claim_agent_run,
        heartbeat_agent_run,
        recover_expired_agent_runs,
    )

    first = AgentRun(
        workflow="stock-initial-research",
        trigger="test",
        status="queued",
        inputs={"ticker": "SNT"},
        outputs={},
    )
    exhausted = AgentRun(
        workflow="stock-company-valuation",
        trigger="test",
        status="running",
        attempt_count=3,
        lease_owner="dead-worker",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        inputs={"ticker": "OPM"},
        outputs={},
    )
    db.add_all([first, exhausted])
    db.commit()

    claimed = claim_agent_run(db, agent_run_id=first.id, worker_id="worker-a")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempt_count == 1
    old_expiry = claimed.lease_expires_at

    with pytest.raises(AgentQueueError, match="another worker"):
        heartbeat_agent_run(db, claimed.id, worker_id="worker-b")
    refreshed = heartbeat_agent_run(db, claimed.id, worker_id="worker-a")
    assert refreshed.lease_expires_at > old_expiry

    refreshed.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    refreshed.updated_at = refreshed.lease_expires_at
    db.commit()
    recovered = recover_expired_agent_runs(db)

    assert {row.id for row in recovered} == {claimed.id, exhausted.id}
    db.refresh(claimed)
    db.refresh(exhausted)
    assert claimed.status == "queued"
    assert claimed.lease_owner is None
    assert exhausted.status == "needs-human"
    assert exhausted.finished_at is not None


def test_queue_claim_skips_scheduled_work_until_it_is_due(db):
    from app.db.models import AgentRun
    from app.services.agent_queue import claim_agent_run

    future = AgentRun(
        workflow="stock-company-valuation",
        trigger="test",
        status="queued",
        available_at=datetime.now(timezone.utc) + timedelta(days=1),
        inputs={},
        outputs={},
    )
    due = AgentRun(
        workflow="stock-initial-research",
        trigger="test",
        status="queued",
        available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        inputs={},
        outputs={},
    )
    db.add_all([future, due])
    db.commit()

    claimed = claim_agent_run(db, worker_id="worker-a")

    assert claimed is not None
    assert claimed.id == due.id
    db.refresh(future)
    assert future.status == "queued"
