"""Immutable document/version/fact persistence for point-in-time research."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    DataConflict,
    DocumentVersion,
    Fact,
    SourceDocument,
)

BR_PARSER_VERSION = "biznesradar-html@1"
BR_EXTRACTOR_VERSION = "biznesradar-fields@1"


@dataclass(frozen=True)
class RecordedDocument:
    document: SourceDocument
    version: DocumentVersion
    version_created: bool


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _insert_for(db: Session, model):
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


def record_document_version(
    db: Session,
    company: Company,
    *,
    source_name: str,
    source_type: str,
    scope_key: str,
    requested_url: str,
    effective_url: str,
    content: bytes,
    text: str,
    response_status: int,
    mime_type: str,
    parser_version: str = BR_PARSER_VERSION,
    fetched_at: datetime | None = None,
) -> RecordedDocument:
    """Append one immutable raw version, reusing identical content."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    content_hash = _sha256_bytes(content)
    document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.company_ticker == company.ticker,
            SourceDocument.source_name == source_name,
            SourceDocument.source_type == source_type,
            SourceDocument.scope_key == scope_key,
        )
    )
    if document is None:
        statement = _insert_for(db, SourceDocument).values(
            company_id=company.id,
            company_ticker=company.ticker,
            source_name=source_name,
            source_type=source_type,
            scope_key=scope_key,
            canonical_url=requested_url,
            first_seen_at=fetched_at,
            last_fetched_at=fetched_at,
            latest_content_hash=content_hash,
            mime_type=mime_type,
            parser_version=parser_version,
            last_fetch_status=response_status,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=["company_ticker", "source_name", "source_type", "scope_key"]
        )
        db.execute(statement)
        document = db.scalar(
            select(SourceDocument).where(
                SourceDocument.company_ticker == company.ticker,
                SourceDocument.source_name == source_name,
                SourceDocument.source_type == source_type,
                SourceDocument.scope_key == scope_key,
            )
        )
    assert document is not None
    # Mutable retrieval metadata belongs on the logical document; raw versions
    # and facts below remain immutable.
    if document.company_id is None:
        document.company_id = company.id
    document.canonical_url = requested_url
    document.last_fetched_at = fetched_at
    document.latest_content_hash = content_hash
    document.mime_type = mime_type
    document.last_fetch_status = response_status

    version = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.source_document_id == document.id,
            DocumentVersion.content_hash == content_hash,
        )
    )
    created = False
    if version is None:
        statement = _insert_for(db, DocumentVersion).values(
            source_document_id=document.id,
            content_hash=content_hash,
            fetched_at=fetched_at,
            requested_url=requested_url,
            effective_url=effective_url,
            response_status=response_status,
            mime_type=mime_type,
            parser_version=parser_version,
            parse_status="pending",
            byte_size=len(content),
            raw_content=text,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=["source_document_id", "content_hash"]
        )
        created = db.execute(statement.returning(DocumentVersion.id)).scalar_one_or_none() is not None
        version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.source_document_id == document.id,
                DocumentVersion.content_hash == content_hash,
            )
        )
    assert version is not None
    # Re-fetching identical bytes must not claim they were parsed by a newer
    # parser or mutate the immutable version's extraction state.
    document.parser_version = parser_version if created else version.parser_version
    return RecordedDocument(document=document, version=version, version_created=created)


def record_market_document_version(
    db: Session,
    *,
    market_key: str,
    source_name: str,
    source_type: str,
    scope_key: str,
    requested_url: str,
    effective_url: str,
    content: bytes,
    text: str,
    response_status: int,
    mime_type: str,
    parser_version: str,
    fetched_at: datetime | None = None,
) -> RecordedDocument:
    """Append evidence for a market-wide document with no company FK."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    content_hash = _sha256_bytes(content)
    document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.company_ticker == market_key,
            SourceDocument.source_name == source_name,
            SourceDocument.source_type == source_type,
            SourceDocument.scope_key == scope_key,
        )
    )
    if document is None:
        statement = _insert_for(db, SourceDocument).values(
            company_id=None,
            company_ticker=market_key,
            source_name=source_name,
            source_type=source_type,
            scope_key=scope_key,
            canonical_url=requested_url,
            first_seen_at=fetched_at,
            last_fetched_at=fetched_at,
            latest_content_hash=content_hash,
            mime_type=mime_type,
            parser_version=parser_version,
            last_fetch_status=response_status,
        )
        db.execute(
            statement.on_conflict_do_nothing(
                index_elements=[
                    "company_ticker",
                    "source_name",
                    "source_type",
                    "scope_key",
                ]
            )
        )
        document = db.scalar(
            select(SourceDocument).where(
                SourceDocument.company_ticker == market_key,
                SourceDocument.source_name == source_name,
                SourceDocument.source_type == source_type,
                SourceDocument.scope_key == scope_key,
            )
        )
    assert document is not None
    document.canonical_url = requested_url
    document.last_fetched_at = fetched_at
    document.latest_content_hash = content_hash
    document.mime_type = mime_type
    document.parser_version = parser_version
    document.last_fetch_status = response_status

    version = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.source_document_id == document.id,
            DocumentVersion.content_hash == content_hash,
        )
    )
    created = False
    if version is None:
        statement = _insert_for(db, DocumentVersion).values(
            source_document_id=document.id,
            content_hash=content_hash,
            fetched_at=fetched_at,
            requested_url=requested_url,
            effective_url=effective_url,
            response_status=response_status,
            mime_type=mime_type,
            parser_version=parser_version,
            parse_status="pending",
            byte_size=len(content),
            raw_content=text,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=["source_document_id", "content_hash"]
        )
        created = db.execute(statement.returning(DocumentVersion.id)).scalar_one_or_none() is not None
        version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.source_document_id == document.id,
                DocumentVersion.content_hash == content_hash,
            )
        )
    assert version is not None
    return RecordedDocument(document=document, version=version, version_created=created)


def mark_parse_result(
    version: DocumentVersion, *, success: bool, error: str | None = None
) -> None:
    if version.parse_status == "parsed" and not success:
        # A later parser regression must not rewrite the historical successful
        # parse state for identical raw bytes. Bump parser_version when the
        # extraction contract changes.
        return
    version.parse_status = "parsed" if success else "failed"
    version.parse_error = None if success else (error or "unknown parse error")[:4000]


def record_numeric_fact(
    db: Session,
    company: Company,
    version: DocumentVersion,
    *,
    fact_type: str,
    fact_key: str,
    value: float | None,
    unit: str,
    period: str,
    locator: dict,
    extractor_version: str = BR_EXTRACTOR_VERSION,
) -> Fact:
    """Create one immutable parsed fact, including explicit missing values."""
    fingerprint = json.dumps(
        {
            "fact_type": fact_type,
            "fact_key": fact_key,
            "value": value,
            "unit": unit,
            "period": period,
            "locator": locator,
            "extractor_version": extractor_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fact_hash = hashlib.sha256(fingerprint).hexdigest()
    fact = db.scalar(
        select(Fact).where(
            Fact.source_version_id == version.id,
            Fact.fact_hash == fact_hash,
        )
    )
    if fact is None:
        statement = _insert_for(db, Fact).values(
            company_id=company.id,
            company_ticker=company.ticker,
            source_version_id=version.id,
            fact_type=fact_type,
            fact_key=fact_key,
            fact_hash=fact_hash,
            numeric_value=value,
            unit=unit,
            period=period,
            # Mutable aggregator: first observation, never backdated to a
            # historical publication label displayed on today's page.
            known_at=version.fetched_at,
            locator=locator,
            extractor_version=extractor_version,
            confidence=1.0,
            verification_state=("parsed" if value is not None else "not_reported"),
            created_at=datetime.now(timezone.utc),
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=["source_version_id", "fact_hash"]
        )
        db.execute(statement)
        fact = db.scalar(
            select(Fact).where(
                Fact.source_version_id == version.id,
                Fact.fact_hash == fact_hash,
            )
        )
    assert fact is not None
    return fact


def record_date_fact(
    db: Session,
    company: Company,
    version: DocumentVersion,
    *,
    fact_type: str,
    fact_key: str,
    value: date | None,
    period: str,
    locator: dict,
    extractor_version: str = BR_EXTRACTOR_VERSION,
) -> Fact:
    """Create one immutable parsed date fact, including explicit missing dates."""
    fingerprint = json.dumps(
        {
            "fact_type": fact_type,
            "fact_key": fact_key,
            "value": value.isoformat() if value is not None else None,
            "period": period,
            "locator": locator,
            "extractor_version": extractor_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fact_hash = hashlib.sha256(fingerprint).hexdigest()
    fact = db.scalar(
        select(Fact).where(
            Fact.source_version_id == version.id,
            Fact.fact_hash == fact_hash,
        )
    )
    if fact is None:
        statement = _insert_for(db, Fact).values(
            company_id=company.id,
            company_ticker=company.ticker,
            source_version_id=version.id,
            fact_type=fact_type,
            fact_key=fact_key,
            fact_hash=fact_hash,
            period=period,
            effective_date=value,
            known_at=version.fetched_at,
            locator=locator,
            extractor_version=extractor_version,
            confidence=1.0,
            verification_state=("parsed" if value is not None else "not_reported"),
            created_at=datetime.now(timezone.utc),
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=["source_version_id", "fact_hash"]
        )
        db.execute(statement)
        fact = db.scalar(
            select(Fact).where(
                Fact.source_version_id == version.id,
                Fact.fact_hash == fact_hash,
            )
        )
    assert fact is not None
    return fact


def record_text_fact(
    db: Session,
    company: Company,
    version: DocumentVersion,
    *,
    fact_type: str,
    fact_key: str,
    text: str,
    locator: dict,
    period: str | None = None,
    effective_date=None,
    verification_state: str = "unverified",
    extractor_version: str,
) -> Fact:
    """Create one immutable sourced text claim without implying verification."""
    normalized_text = " ".join(text.split())
    fingerprint = json.dumps(
        {
            "fact_type": fact_type,
            "fact_key": fact_key,
            "text": normalized_text,
            "period": period,
            "effective_date": effective_date.isoformat() if effective_date else None,
            "locator": locator,
            "verification_state": verification_state,
            "extractor_version": extractor_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fact_hash = hashlib.sha256(fingerprint).hexdigest()
    fact = db.scalar(
        select(Fact).where(
            Fact.source_version_id == version.id,
            Fact.fact_hash == fact_hash,
        )
    )
    if fact is None:
        statement = _insert_for(db, Fact).values(
            company_id=company.id,
            company_ticker=company.ticker,
            source_version_id=version.id,
            fact_type=fact_type,
            fact_key=fact_key,
            fact_hash=fact_hash,
            text_value=normalized_text,
            period=period,
            effective_date=effective_date,
            known_at=version.fetched_at,
            locator=locator,
            extractor_version=extractor_version,
            confidence=1.0,
            verification_state=verification_state,
            created_at=datetime.now(timezone.utc),
        )
        db.execute(
            statement.on_conflict_do_nothing(
                index_elements=["source_version_id", "fact_hash"]
            )
        )
        fact = db.scalar(
            select(Fact).where(
                Fact.source_version_id == version.id,
                Fact.fact_hash == fact_hash,
            )
        )
    assert fact is not None
    return fact


def latest_versions_as_of(
    db: Session, company_ticker: str, as_of: datetime
) -> list[tuple[SourceDocument, DocumentVersion]]:
    """One applicable full document version per logical source at ``as_of``."""
    documents = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.company_ticker == company_ticker.upper())
        .order_by(SourceDocument.source_type, SourceDocument.scope_key)
    ).all()
    selected: list[tuple[SourceDocument, DocumentVersion]] = []
    for document in documents:
        version = db.scalar(
            select(DocumentVersion)
            .where(
                DocumentVersion.source_document_id == document.id,
                DocumentVersion.fetched_at <= as_of,
                DocumentVersion.parse_status.in_(("parsed", "partial")),
            )
            .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
            .limit(1)
        )
        if version is not None:
            selected.append((document, version))
    return selected


def facts_as_of(
    db: Session,
    company_ticker: str,
    as_of: datetime,
    *,
    fact_type: str | None = None,
) -> list[tuple[Fact, DocumentVersion, SourceDocument]]:
    """Facts from each source's complete latest version known by ``as_of``."""
    versions = latest_versions_as_of(db, company_ticker, as_of)
    if not versions:
        return []
    version_to_document = {version.id: document for document, version in versions}
    statement = select(Fact, DocumentVersion).join(
        DocumentVersion, Fact.source_version_id == DocumentVersion.id
    ).where(Fact.source_version_id.in_(list(version_to_document)))
    if fact_type:
        statement = statement.where(Fact.fact_type == fact_type)
    rows = db.execute(statement.order_by(Fact.fact_key, Fact.period, Fact.id)).all()
    return [
        (fact, version, version_to_document[version.id]) for fact, version in rows
    ]


def record_conflict_if_needed(
    db: Session,
    company: Company,
    *,
    previous_fact_id: int | None,
    new_fact: Fact,
) -> DataConflict | None:
    """Record a cross-document disagreement; same-document versions supersede."""
    if previous_fact_id is None or previous_fact_id == new_fact.id:
        return None
    previous = db.get(Fact, previous_fact_id)
    if previous is None or previous.fact_key != new_fact.fact_key:
        return None
    if previous.period != new_fact.period:
        return None
    if previous.numeric_value == new_fact.numeric_value and previous.text_value == new_fact.text_value:
        return None
    previous_version = db.get(DocumentVersion, previous.source_version_id)
    new_version = db.get(DocumentVersion, new_fact.source_version_id)
    if previous_version.source_document_id == new_version.source_document_id:
        return None

    left_id, right_id = sorted((previous.id, new_fact.id))
    existing = db.scalar(
        select(DataConflict).where(
            DataConflict.left_fact_id == left_id,
            DataConflict.right_fact_id == right_id,
        )
    )
    if existing is not None:
        return existing
    statement = _insert_for(db, DataConflict).values(
        company_id=company.id,
        company_ticker=company.ticker,
        fact_key=new_fact.fact_key,
        period=new_fact.period,
        left_fact_id=left_id,
        right_fact_id=right_id,
        status="open",
        created_at=datetime.now(timezone.utc),
    )
    statement = statement.on_conflict_do_nothing(
        index_elements=["left_fact_id", "right_fact_id"]
    )
    db.execute(statement)
    return db.scalar(
        select(DataConflict).where(
            DataConflict.left_fact_id == left_id,
            DataConflict.right_fact_id == right_id,
        )
    )
