"""Source-linked, idempotent report-calendar scheduling contracts."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select


def _verifier_result() -> dict:
    return {
        "model_role": "verifier_strict",
        "verifier_model": "test",
        "verdict": "pass",
        "findings": [],
        "justifications": {
            "evidence_and_claim_fit": "The fixture is bound to its immutable source version.",
            "company_specificity": "The fixture concerns only the seeded company.",
            "outlook_and_thesis_plausibility": "The bounded fixture is sufficient for queue eligibility.",
        },
        "summary": "Canonical Research verification fixture.",
    }


def _eligible_case(db, *, profile_provenance: str = "human-confirmed"):
    from app.db.models import (
        AgentRun,
        Company,
        CompanyProfile,
        DocumentVersion,
        ResearchCase,
        ResearchSnapshot,
        SourceDocument,
        VerificationRun,
        utcnow,
    )

    now = utcnow()
    company = Company(
        ticker="ABS",
        name="Asseco Business Solutions",
        shares_outstanding=10_000_000,
        market_cap=1_000_000_000,
        enterprise_value=900_000_000,
    )
    db.add(company)
    db.flush()
    case = ResearchCase(
        company_id=company.id,
        purpose="investment-research",
        origin="manual",
        state="monitoring",
        current_step="monitoring",
        as_of=now,
    )
    db.add(case)
    db.flush()
    profile = CompanyProfile(
        research_case_id=case.id,
        version=1,
        schema_version="company-profile-v2",
        archetype="industrial-consumer",
        archetype_version="industrial-consumer-v1",
        company_overlay={
            "segments": ["ERP"],
            "competitors": [],
            "source_questions": ["Jak zmienia się udział przychodów abonamentowych?"],
            "unusual_risks": [],
        },
        drivers=[],
        kpis=[],
        provenance=profile_provenance,
    )
    db.add(profile)
    db.flush()
    research_run = AgentRun(
        workflow="stock-initial-research",
        trigger="research-command",
        status="verified",
        company_id=company.id,
        inputs={"research_case_id": case.id},
        outputs={},
    )
    db.add(research_run)
    db.flush()
    verification = VerificationRun(
        agent_run_id=research_run.id,
        model_role="verifier_strict",
        verifier_model="test",
        verdict="pass",
        checks={},
    )
    db.add(verification)
    db.flush()
    snapshot = ResearchSnapshot(
        research_case_id=case.id,
        company_profile_id=profile.id,
        agent_run_id=research_run.id,
        verification_run_id=verification.id,
        version=1,
        contract_version="research-snapshot-v3",
        status="verified",
        as_of=now,
        input_fingerprint="input",
        artifact_fingerprint="a" * 64,
        sections={"brief": {"current_understanding": "Stan bazowy.", "main_gap": ""}},
        source_manifest=[],
        conflicts=[],
        gaps=[],
        next_checks=[],
        statement_provenance=[],
        verifier_result=_verifier_result(),
    )
    db.add(snapshot)
    document = SourceDocument(
        company_id=company.id,
        company_ticker=company.ticker,
        source_name="biznesradar",
        source_type="company_profile",
        scope_key="current",
        canonical_url="https://www.biznesradar.pl/notowania/ABS",
        first_seen_at=now,
        last_fetched_at=now,
        latest_content_hash="b" * 64,
        mime_type="text/html",
        parser_version="fixture-v1",
        last_fetch_status=200,
    )
    db.add(document)
    db.flush()
    version = DocumentVersion(
        source_document_id=document.id,
        content_hash="b" * 64,
        fetched_at=now,
        requested_url=document.canonical_url,
        effective_url=document.canonical_url,
        response_status=200,
        mime_type="text/html",
        parser_version="fixture-v1",
        parse_status="parsed",
        byte_size=8,
        raw_content="calendar",
    )
    db.add(version)
    db.commit()
    return company, case, profile, version


def test_future_report_creates_one_unclaimable_review_and_manual_review_accelerates_it(
    client, db
):
    from app.db.models import AgentRun, CompanyReportSchedule
    from app.services.agent_queue import claim_agent_run
    from app.services.report_calendar import ensure_report_review, record_profile_schedule
    from app.services.research_queue import enqueue_research_review

    company, case, _profile, version = _eligible_case(db)
    report_day = date.today() + timedelta(days=30)
    schedule = record_profile_schedule(
        db,
        company=company,
        source_version=version,
        report_date=report_day,
        report_label="raport półroczny",
    )
    ensure_report_review(db, schedule=schedule)
    db.commit()

    scheduled = db.get(AgentRun, schedule.research_agent_run_id)
    assert schedule.automation_status == "scheduled"
    assert scheduled is not None
    assert scheduled.trigger == "report-calendar"
    assert scheduled.available_at == datetime.combine(
        report_day + timedelta(days=1),
        datetime.min.time().replace(hour=6),
        tzinfo=timezone.utc,
    ).replace(tzinfo=None)
    assert case.state == "monitoring"
    assert claim_agent_run(
        db, workflow="stock-company-review", worker_id="too-early"
    ) is None

    ensure_report_review(db, schedule=schedule)
    db.commit()
    assert db.scalar(select(func.count()).select_from(CompanyReportSchedule)) == 1
    assert db.scalar(
        select(func.count()).select_from(AgentRun).where(
            AgentRun.workflow == "stock-company-review"
        )
    ) == 1

    accelerated = enqueue_research_review(
        db,
        case=case,
        trigger="research-review-command",
        changed_by="user-command",
    )
    db.commit()
    assert accelerated.created is False
    assert accelerated.agent.id == scheduled.id
    assert accelerated.agent.available_at is None
    assert accelerated.agent.trigger == "research-review-command"
    assert case.state == "ingesting"

    listed = client.get("/api/research-cases")
    assert listed.status_code == 200, listed.text
    calendar = listed.json()[0]["report_calendar"]
    assert calendar["report_date"] == report_day.isoformat()
    assert calendar["source_version_id"] == version.id
    assert calendar["research_agent_run_id"] == scheduled.id
    assert calendar["research_status"] == "queued"


def test_calendar_records_source_date_but_blocks_unconfirmed_profile(db):
    from app.services.report_calendar import ensure_report_review, record_profile_schedule

    company, _case, _profile, version = _eligible_case(
        db, profile_provenance="codex-proposed"
    )
    schedule = record_profile_schedule(
        db,
        company=company,
        source_version=version,
        report_date=date.today() + timedelta(days=14),
        report_label="raport kwartalny",
    )

    ensure_report_review(db, schedule=schedule)

    assert schedule.source_status == "scheduled"
    assert schedule.automation_status == "blocked"
    assert schedule.research_agent_run_id is None
    assert schedule.automation_reason == "Najpierw potwierdź lub skoryguj profil spółki."


def test_calendar_rejects_cross_company_and_wrong_source_lineage(db):
    from app.db.models import Company, SourceDocument
    from app.services.report_calendar import ReportCalendarError, record_profile_schedule

    company, _case, _profile, version = _eligible_case(db)
    other = Company(ticker="DEC", name="Decora")
    db.add(other)
    db.flush()

    with pytest.raises(ReportCalendarError, match="same company"):
        record_profile_schedule(
            db,
            company=other,
            source_version=version,
            report_date=date.today() + timedelta(days=7),
            report_label="raport kwartalny",
        )

    source = db.get(SourceDocument, version.source_document_id)
    source.source_name = "issuer-ir"
    db.flush()
    with pytest.raises(ReportCalendarError, match="company_profile/current"):
        record_profile_schedule(
            db,
            company=company,
            source_version=version,
            report_date=date.today() + timedelta(days=7),
            report_label="raport kwartalny",
        )


def test_refresh_reconciles_calendar_after_later_source_versions(
    db, monkeypatch
):
    from app.db.models import AgentRun, DocumentVersion, SourceDocument, utcnow
    from app.services import refresh, report_calendar
    from app.services.research_queue import enqueue_research_review

    company, case, _profile, profile_version = _eligible_case(db)
    report_day = date.today() + timedelta(days=21)
    captured: dict[str, int] = {}

    def fake_profile(_db, _company, _force, _summary, session=None):
        schedule = report_calendar.record_profile_schedule(
            _db,
            company=_company,
            source_version=profile_version,
            report_date=report_day,
            report_label="raport kwartalny",
        )
        return refresh.ProfileRefreshResult(report_schedule_id=schedule.id)

    def later_reports(_db, _company, _force, summary, session=None):
        now = utcnow()
        document = SourceDocument(
            company_id=_company.id,
            company_ticker=_company.ticker,
            source_name="issuer-ir",
            source_type="issuer_ir_report",
            scope_key="later-in-refresh",
            canonical_url="https://investor.example.test/later",
            first_seen_at=now,
            last_fetched_at=now,
            latest_content_hash="c" * 64,
            mime_type="text/html",
            parser_version="fixture-v1",
            last_fetch_status=200,
        )
        _db.add(document)
        _db.flush()
        version = DocumentVersion(
            source_document_id=document.id,
            content_hash="c" * 64,
            fetched_at=now,
            requested_url=document.canonical_url,
            effective_url=document.canonical_url,
            response_status=200,
            mime_type="text/html",
            parser_version="fixture-v1",
            parse_status="parsed",
            byte_size=5,
            raw_content="later",
        )
        _db.add(version)
        _db.flush()
        captured["later_version_id"] = version.id
        summary["reports"] = "ok"

    monkeypatch.setattr(refresh, "_build_br_session", lambda _summary: None)
    monkeypatch.setattr(refresh, "_refresh_profile", fake_profile)
    monkeypatch.setattr(refresh, "_refresh_reports", later_reports)
    monkeypatch.setattr(refresh, "_refresh_indicators", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(refresh, "_refresh_dividends", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(refresh, "_refresh_forecasts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        refresh.market_data, "upsert_company_market_data", lambda *_args: None
    )

    summary = refresh.refresh_company(db, company.ticker, scope="financials")
    assert summary["report_calendar"].endswith("scheduled)")
    scheduled = db.scalar(
        select(AgentRun).where(AgentRun.trigger == "report-calendar")
    )
    assert scheduled is not None
    source_ids = {
        row["document_version_id"]
        for row in scheduled.inputs["review"]["queued_source_manifest"]
    }
    assert captured["later_version_id"] in source_ids

    accelerated = enqueue_research_review(
        db,
        case=case,
        trigger="research-review-command",
        changed_by="user-command",
    )
    assert accelerated.created is False
    assert accelerated.agent.id == scheduled.id
    assert accelerated.agent.available_at is None


def test_rejected_canonical_valuation_is_a_blocker_not_coverage(db, monkeypatch):
    from app.db.models import AgentRun
    from app.services import valuation_queue

    company, case, _profile, _version = _eligible_case(db)
    fingerprint = "d" * 64
    rejected = AgentRun(
        workflow=valuation_queue.WORKFLOW,
        trigger="report-calendar",
        status="rejected",
        company_id=company.id,
        idempotency_key=f"valuation:{case.id}:{fingerprint}",
        inputs={},
        outputs={},
    )
    db.add(rejected)
    db.flush()
    monkeypatch.setattr(
        valuation_queue,
        "prepare_valuation_base",
        lambda *_args, **_kwargs: {"input_fingerprint": fingerprint},
    )

    with pytest.raises(valuation_queue.ValuationQueueError, match="explicit review"):
        valuation_queue.enqueue_valuation(
            db,
            case=case,
            research_snapshot_id=1,
            as_of=datetime.now(timezone.utc),
            trigger="report-calendar",
        )
