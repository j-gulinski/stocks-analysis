"""Atomic quota accounting and interrupted-worker recovery."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analysis import usage
from app.analysis.recovery import reconcile_stale_runs
from app.db.base import Base
from app.db.models import AiUsageDaily, Analysis, Company, ModelCall


def test_atomic_run_reservation_stops_at_limit(db):
    day = datetime.now(timezone.utc).date()
    assert usage.reserve_run(db, "_all", 2, day=day) is True
    assert usage.reserve_run(db, "_all", 2, day=day) is True
    assert usage.reserve_run(db, "_all", 2, day=day) is False

    row = db.get(AiUsageDaily, (day, "_all"))
    assert row.run_count == 2


def test_file_sqlite_concurrent_run_reservation_has_one_winner(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'quota.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    barrier = Barrier(2)

    def reserve_once() -> bool:
        with sessions() as session:
            barrier.wait()
            return usage.reserve_run(session, "_all", 1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: reserve_once(), range(2)))

    assert sorted(results) == [False, True]
    with sessions() as session:
        row = session.get(
            AiUsageDaily, (datetime.now(timezone.utc).date(), "_all")
        )
        assert row.run_count == 1
    engine.dispose()


def test_zero_limits_disable_runs_and_provider_attempts(db):
    day = datetime.now(timezone.utc).date()
    assert usage.reserve_run(db, "_all", 0, day=day) is False
    assert usage.reserve_provider_attempt(db, 0, 500_000, day=day) is False
    assert usage.reserve_provider_attempt(db, 60, 0, day=day) is False
    assert db.get(AiUsageDaily, (day, "_all")) is None


def test_atomic_provider_attempt_reservation_checks_call_and_token_caps(db):
    day = datetime.now(timezone.utc).date()
    assert usage.reserve_run(db, "_all", 10, day=day) is True
    assert usage.reserve_provider_attempt(db, 2, 100, day=day) is True
    assert usage.reserve_provider_attempt(db, 2, 100, day=day) is True
    assert usage.reserve_provider_attempt(db, 2, 100, day=day) is False

    usage.record_attempt_outcome(
        db, "anthropic", billed=True, input_tokens=80, output_tokens=20
    )
    row = db.get(AiUsageDaily, (day, "_all"))
    assert row.provider_attempts == 2
    assert row.input_tokens + row.output_tokens == 100


def test_usage_counters_upsert_provider_row(db):
    day = datetime.now(timezone.utc).date()
    usage.record_logical_operation(db, "anthropic")
    usage.record_provider_attempt(db, "anthropic")
    usage.record_attempt_outcome(
        db,
        "anthropic",
        billed=True,
        input_tokens=120,
        output_tokens=30,
    )
    usage.record_cache_hit(db, "anthropic")

    row = db.get(AiUsageDaily, (day, "anthropic"))
    assert row.run_count == 0
    assert row.logical_operations == 1
    assert row.provider_attempts == 1
    assert row.cache_hits == 1
    assert row.billable_calls == 1
    assert row.input_tokens == 120
    assert row.output_tokens == 30


def test_ai_usage_diagnostics_exposes_limits_without_pricing_guess(client, db):
    assert usage.reserve_run(db, "_all", 20) is True
    assert usage.reserve_provider_attempt(db, 60, 500_000) is True
    usage.record_provider_attempt(db, "anthropic")
    usage.record_attempt_outcome(
        db, "anthropic", billed=True, input_tokens=90, output_tokens=10
    )

    response = client.get("/api/health/ai-usage")
    assert response.status_code == 200
    body = response.json()
    assert body["usage"]["runs"] == 1
    assert body["usage"]["provider_attempts"] == 1
    assert body["usage"]["input_tokens"] == 90
    assert body["usage"]["output_tokens"] == 10
    assert body["pricing_status"] == "not_configured"


def test_reconcile_stale_rows_leaves_recent_work_running(db):
    now = datetime.now(timezone.utc)
    company = Company(ticker="SNT", name="SYNEKTIK")
    db.add(company)
    db.flush()
    stale = Analysis(
        company_id=company.id,
        model="test",
        status="running",
        heartbeat_at=now - timedelta(minutes=30),
        created_at=now - timedelta(minutes=30),
    )
    recent = Analysis(
        company_id=company.id,
        model="test",
        status="running",
        heartbeat_at=now - timedelta(minutes=2),
        created_at=now - timedelta(minutes=2),
    )
    db.add_all([stale, recent])
    db.flush()
    stale_call = ModelCall(
        analysis_id=stale.id,
        role="investment_verdict",
        provider="anthropic",
        model="test",
        status="running",
        created_at=now - timedelta(minutes=30),
    )
    recent_call = ModelCall(
        analysis_id=recent.id,
        role="investment_verdict",
        provider="anthropic",
        model="test",
        status="running",
        created_at=now - timedelta(minutes=2),
    )
    db.add_all([stale_call, recent_call])
    db.commit()

    result = reconcile_stale_runs(db, now=now)
    second_result = reconcile_stale_runs(db, now=now)

    assert result == {"analysis_runs": 1, "model_calls": 1}
    assert second_result == {"analysis_runs": 0, "model_calls": 0}
    assert stale.status == "failed"
    assert stale.validation["error_code"] == "stale_interrupted"
    assert stale_call.status == "failed"
    assert stale_call.error_code == "stale_interrupted"
    assert recent.status == "running"
    assert recent_call.status == "running"
    provider_usage = db.get(AiUsageDaily, (now.date(), "anthropic"))
    global_usage = db.get(AiUsageDaily, (now.date(), "_all"))
    assert provider_usage.unknown_billing_calls == 1
    assert global_usage.unknown_billing_calls == 1
