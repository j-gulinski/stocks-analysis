"""Source-linked report calendar and its idempotent Research producer."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentRun,
    Company,
    CompanyReportSchedule,
    DocumentVersion,
    ResearchCase,
    SourceDocument,
)
from app.services.research_queue import ResearchQueueError, enqueue_research_review


CALENDAR_VERSION = "report-calendar-v1"


class ReportCalendarError(ValueError):
    """The proposed calendar observation is not valid source lineage."""


def record_profile_schedule(
    db: Session,
    *,
    company: Company,
    source_version: DocumentVersion,
    report_date: date | None,
    report_label: str | None,
    parse_error: str | None = None,
) -> CompanyReportSchedule:
    """Persist one observation per immutable profile version, idempotently."""
    source = db.get(SourceDocument, source_version.source_document_id)
    if (
        source is None
        or source.company_id != company.id
        or source.company_ticker != company.ticker
        or source.source_name != "biznesradar"
        or source.source_type != "company_profile"
        or source.scope_key != "current"
        or source_version.parse_status != "parsed"
    ):
        raise ReportCalendarError(
            "Calendar evidence must be a parsed BiznesRadar company_profile/current "
            "version owned by the same company."
        )
    existing = db.scalar(
        select(CompanyReportSchedule).where(
            CompanyReportSchedule.company_id == company.id,
            CompanyReportSchedule.source_version_id == source_version.id,
        )
    )
    if existing is not None:
        return existing
    source_status = "scheduled" if report_date is not None and not parse_error else "unavailable"
    reason = parse_error
    if reason is None and report_date is None:
        reason = "Źródło profilu nie pokazuje obecnie daty następnego raportu."
    row = CompanyReportSchedule(
        company_id=company.id,
        source_version_id=source_version.id,
        report_date=report_date if source_status == "scheduled" else None,
        report_label=report_label if source_status == "scheduled" else None,
        source_status=source_status,
        automation_status="not-eligible",
        automation_reason=reason,
        observed_at=source_version.fetched_at,
    )
    db.add(row)
    db.flush()
    return row


def _review_available_at(report_date: date) -> datetime:
    # Run after the scheduled day, avoiding a pre-publication refresh when a
    # company releases after the market close. Queue workers remain explicit.
    return datetime.combine(report_date + timedelta(days=1), time(6), tzinfo=timezone.utc)


def ensure_report_review(
    db: Session, *, schedule: CompanyReportSchedule
) -> CompanyReportSchedule:
    """Create/reuse one future Research review for a source-backed date."""
    if schedule.source_status != "scheduled" or schedule.report_date is None:
        schedule.automation_status = "not-eligible"
        schedule.automation_reason = (
            schedule.automation_reason
            or "Brak źródłowej daty raportu; automatyzacja nie została utworzona."
        )
        return schedule
    if schedule.research_agent_run_id is not None:
        existing = db.get(AgentRun, schedule.research_agent_run_id)
        if existing is None:
            schedule.automation_status = "blocked"
            schedule.automation_reason = (
                "Zaplanowane odświeżenie Research nie istnieje; wymagany jest przegląd."
            )
            return schedule
        if existing.status in {"queued", "running"}:
            schedule.automation_status = "scheduled"
            schedule.automation_reason = (
                "Research odświeży źródła po planowanym dniu publikacji."
            )
            return schedule
        if existing.status in {"verified", "provisional", "completed"}:
            if schedule.automation_status != "blocked":
                schedule.automation_status = "already-covered"
                schedule.automation_reason = (
                    "Raport uruchomił już odświeżenie Research dla tej obserwacji."
                )
            return schedule
        schedule.automation_status = "blocked"
        schedule.automation_reason = (
            "Odświeżenie Research po raporcie wymaga decyzji przed ponowieniem."
        )
        return schedule
    case = db.scalar(
        select(ResearchCase).where(
            ResearchCase.company_id == schedule.company_id,
            ResearchCase.purpose == "investment-research",
        )
    )
    if case is None:
        schedule.automation_status = "not-eligible"
        schedule.automation_reason = "Spółka nie ma aktywnego przypadku Research."
        return schedule
    context = {
        "version": CALENDAR_VERSION,
        "schedule_id": schedule.id,
        "source_version_id": schedule.source_version_id,
        "report_date": schedule.report_date.isoformat(),
        "report_label": schedule.report_label,
        "policy": "refresh-after-scheduled-publication-day",
    }
    available_at = _review_available_at(schedule.report_date)
    if available_at <= datetime.now(timezone.utc):
        available_at = datetime.now(timezone.utc)
    try:
        queued = enqueue_research_review(
            db,
            case=case,
            trigger="report-calendar",
            changed_by="report-calendar",
            available_at=available_at,
            report_calendar=context,
        )
    except ResearchQueueError as exc:
        schedule.automation_status = "blocked"
        schedule.automation_reason = {
            "Confirm or correct the latest company profile before queuing a Research review.": (
                "Najpierw potwierdź lub skoryguj profil spółki."
            ),
            "Complete the initial Research snapshot before queuing a review.": (
                "Najpierw zakończ pierwszy Research spółki."
            ),
            "Add at least one company-specific source question to the confirmed profile before queuing a Research review.": (
                "Potwierdzony profil wymaga co najmniej jednego pytania właściwego dla spółki."
            ),
        }.get(str(exc), f"Kalendarz nie może zlecić Research: {exc}")
        schedule.research_agent_run_id = None
        return schedule
    agent = queued.agent
    schedule.research_agent_run_id = agent.id
    if agent.status in {"queued", "running"}:
        schedule.automation_status = "scheduled"
        schedule.automation_reason = (
            "Research odświeży źródła po planowanym dniu publikacji."
        )
    elif agent.status in {"verified", "provisional", "completed"}:
        schedule.automation_status = "already-covered"
        schedule.automation_reason = (
            "Ten sam zamrożony stan Research został już przetworzony."
        )
    else:
        schedule.automation_status = "blocked"
        schedule.automation_reason = (
            "Istniejące odświeżenie Research wymaga decyzji przed ponowieniem."
        )
    return schedule


def latest_schedule(
    db: Session, *, company_id: int
) -> CompanyReportSchedule | None:
    return db.scalar(
        select(CompanyReportSchedule)
        .where(CompanyReportSchedule.company_id == company_id)
        .order_by(
            CompanyReportSchedule.observed_at.desc(),
            CompanyReportSchedule.id.desc(),
        )
        .limit(1)
    )


def schedule_payload(db: Session, *, company_id: int) -> dict:
    row = latest_schedule(db, company_id=company_id)
    if row is None:
        return {
            "status": "missing",
            "version": CALENDAR_VERSION,
            "report_date": None,
            "report_label": None,
            "source_version_id": None,
            "observed_at": None,
            "automation_status": "not-eligible",
            "automation_reason": "Brak źródłowej obserwacji kalendarza raportów.",
            "review_available_at": None,
            "research_agent_run_id": None,
            "research_status": None,
            "valuation_agent_run_id": None,
            "valuation_status": None,
        }
    research_agent = (
        db.get(AgentRun, row.research_agent_run_id)
        if row.research_agent_run_id is not None
        else None
    )
    valuation_agent = (
        db.get(AgentRun, row.valuation_agent_run_id)
        if row.valuation_agent_run_id is not None
        else None
    )
    status = row.source_status
    if row.report_date is not None and row.report_date < date.today():
        status = "overdue"
    return {
        "status": status,
        "version": CALENDAR_VERSION,
        "report_date": row.report_date,
        "report_label": row.report_label,
        "source_version_id": row.source_version_id,
        "observed_at": row.observed_at,
        "automation_status": row.automation_status,
        "automation_reason": row.automation_reason,
        "review_available_at": (
            research_agent.available_at if research_agent is not None else None
        ),
        "research_agent_run_id": row.research_agent_run_id,
        "research_status": research_agent.status if research_agent is not None else None,
        "valuation_agent_run_id": row.valuation_agent_run_id,
        "valuation_status": valuation_agent.status if valuation_agent is not None else None,
    }


def reconcile_latest_schedule(db: Session, *, company_id: int) -> CompanyReportSchedule | None:
    row = latest_schedule(db, company_id=company_id)
    return ensure_report_review(db, schedule=row) if row is not None else None


def reconcile_schedule(
    db: Session, *, schedule_id: int, company_id: int
) -> CompanyReportSchedule:
    """Reconcile exactly the observation produced by the completed refresh."""
    row = db.scalar(
        select(CompanyReportSchedule).where(
            CompanyReportSchedule.id == schedule_id,
            CompanyReportSchedule.company_id == company_id,
        )
    )
    if row is None:
        raise ReportCalendarError(
            "The report-calendar observation disappeared before reconciliation."
        )
    return ensure_report_review(db, schedule=row)
