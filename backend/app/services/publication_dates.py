"""Persist and backfill point-in-time financial-statement publication dates."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, DocumentVersion, Fact, SourceDocument
from app.scrapers import biznesradar
from app.services import evidence

PUBLICATION_FACT_TYPE = "financial_statement_publication"

# BiznesRadar logical document scope -> canonical statement and frequency.
STATEMENT_REPORT_SCOPES: dict[str, tuple[str, str]] = {
    "income_q": ("income", "Q"),
    "income_y": ("income", "Y"),
    "balance_q": ("balance", "Q"),
    "cashflow_q": ("cashflow", "Q"),
}


def record_statement_publication_facts(
    db: Session,
    company: Company,
    statement: str,
    table: biznesradar.ReportTable,
    source_version: DocumentVersion,
) -> list[Fact]:
    """Record one canonical availability fact for every selected period."""
    if len(table.publication_dates) != len(table.periods):
        raise LookupError(
            "Publication-date metadata is not aligned with statement periods."
        )

    return [
        evidence.record_date_fact(
            db,
            company,
            source_version,
            fact_type=PUBLICATION_FACT_TYPE,
            fact_key=f"{statement}.publication_date",
            value=publication_date,
            period=period,
            locator={
                "table": statement,
                "frequency": table.freq,
                "metadata_label": "Data publikacji",
                "period_position": period_position,
                "period": period,
            },
        )
        for period_position, (period, publication_date) in enumerate(
            zip(table.periods, table.publication_dates)
        )
    ]


def backfill_statement_publication_facts(
    db: Session, *, ticker: str | None = None
) -> dict:
    """Replay stored immutable report HTML; never fetch or mutate source versions.

    Bounded per-version failures cover parse and company-identity errors
    (``ParseError``/``LookupError``); any other exception aborts the run before
    the caller commits, so no partial state is persisted.
    """
    normalized_ticker = ticker.strip().upper() if ticker is not None else None
    if normalized_ticker == "":
        return {
            "ok": False,
            "ticker": normalized_ticker,
            "versions_scanned": 0,
            "versions_succeeded": 0,
            "versions_failed": 0,
            "facts_created": 0,
            "facts_reused": 0,
            "failures": [
                {
                    "company_ticker": normalized_ticker,
                    "scope_key": None,
                    "document_version_id": None,
                    "error": "Ticker filter must not be empty.",
                }
            ],
        }
    statement = (
        select(SourceDocument, DocumentVersion)
        .join(
            DocumentVersion,
            DocumentVersion.source_document_id == SourceDocument.id,
        )
        .where(
            SourceDocument.source_type == "financial_report",
            SourceDocument.scope_key.in_(STATEMENT_REPORT_SCOPES),
            DocumentVersion.parse_status.in_(("parsed", "partial")),
        )
        .order_by(
            SourceDocument.company_ticker,
            SourceDocument.scope_key,
            DocumentVersion.fetched_at,
            DocumentVersion.id,
        )
    )
    if normalized_ticker is not None:
        statement = statement.where(SourceDocument.company_ticker == normalized_ticker)

    versions = list(db.execute(statement).all())
    facts_created = 0
    facts_reused = 0
    failures: list[dict] = []

    for document, version in versions:
        statement_name, frequency = STATEMENT_REPORT_SCOPES[document.scope_key]
        company = (
            db.get(Company, document.company_id)
            if document.company_id is not None
            else db.scalar(
                select(Company).where(Company.ticker == document.company_ticker)
            )
        )
        if company is None or company.ticker != document.company_ticker:
            failures.append(
                {
                    "company_ticker": document.company_ticker,
                    "scope_key": document.scope_key,
                    "document_version_id": version.id,
                    "error": "Stored financial report has no matching company identity.",
                }
            )
            continue

        existing_fact_ids = set(
            db.scalars(
                select(Fact.id).where(
                    Fact.source_version_id == version.id,
                    Fact.fact_type == PUBLICATION_FACT_TYPE,
                )
            )
        )
        try:
            table = biznesradar.parse_report_table(version.raw_content, frequency)
            if not table.periods:
                raise biznesradar.ParseError("No statement periods found.")
            facts = record_statement_publication_facts(
                db,
                company,
                statement_name,
                table,
                version,
            )
        except (biznesradar.ParseError, LookupError) as exc:
            failures.append(
                {
                    "company_ticker": document.company_ticker,
                    "scope_key": document.scope_key,
                    "document_version_id": version.id,
                    "error": str(exc)[:500],
                }
            )
            continue

        created_for_version = sum(fact.id not in existing_fact_ids for fact in facts)
        facts_created += created_for_version
        facts_reused += len(facts) - created_for_version

    return {
        "ok": not failures,
        "ticker": normalized_ticker,
        "versions_scanned": len(versions),
        "versions_succeeded": len(versions) - len(failures),
        "versions_failed": len(failures),
        "facts_created": facts_created,
        "facts_reused": facts_reused,
        "failures": failures,
    }
