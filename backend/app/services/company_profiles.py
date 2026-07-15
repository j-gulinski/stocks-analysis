"""Immutable, human-owned CompanyProfile corrections and frozen identities."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import CompanyProfileCorrectionIn
from app.db.models import Company, CompanyProfile, DocumentVersion, ResearchCase, SourceDocument
from app.services.archetype_packs import get_pack, known_marker_ids
from app.services.artifact_contracts import RESEARCH_PROFILE_SCHEMA


class CompanyProfileError(ValueError):
    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


def profile_values(profile: CompanyProfile) -> dict:
    return {
        "schema_version": profile.schema_version,
        "archetype": profile.archetype,
        "archetype_version": profile.archetype_version,
        "company_overlay": profile.company_overlay,
        "drivers": profile.drivers,
        "kpis": profile.kpis,
    }


def profile_fingerprint(profile: CompanyProfile) -> str:
    value = {
        "id": profile.id,
        "research_case_id": profile.research_case_id,
        "version": profile.version,
        "values": profile_values(profile),
        "provenance": profile.provenance,
        "reason": profile.reason,
        "based_on_profile_id": profile.based_on_profile_id,
    }
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def frozen_profile(profile: CompanyProfile) -> dict:
    return {
        "id": profile.id,
        "version": profile.version,
        "fingerprint": profile_fingerprint(profile),
        **profile_values(profile),
        "provenance": profile.provenance,
        "reason": profile.reason,
        "based_on_profile_id": profile.based_on_profile_id,
    }


def _validate_profile_focus(payload: CompanyProfileCorrectionIn, *, archetype_version: str) -> None:
    pack = get_pack(payload.archetype)
    if pack is None:  # Defensive: ResearchArchetype should already guarantee this.
        raise CompanyProfileError("Unsupported company profile archetype.")
    if not archetype_version:
        raise CompanyProfileError("Company profile archetype version is required.")

    driver_keys = [item.key for item in payload.drivers]
    kpi_keys = [item.key for item in payload.kpis]
    if len(driver_keys) != len(set(driver_keys)) or len(kpi_keys) != len(set(kpi_keys)):
        raise CompanyProfileError("Company-profile driver and KPI keys must be unique.")

    used_focus: set[str] = set()
    allowed_focus = known_marker_ids(pack)
    for item in [*payload.drivers, *payload.kpis]:
        if len(item.focus_tags) > 1:
            raise CompanyProfileError(
                f"Profile item {item.key} may address at most one archetype marker."
            )
        if not item.focus_tags:
            continue
        marker = item.focus_tags[0]
        if marker != item.key or marker not in allowed_focus:
            raise CompanyProfileError(
                f"Profile item {item.key} has an invalid archetype focus tag."
            )
        if marker in used_focus:
            raise CompanyProfileError(
                f"Archetype marker {marker} is repeated in the profile."
            )
        used_focus.add(marker)


def _validate_profile_sources(
    db: Session, *, case: ResearchCase, payload: CompanyProfileCorrectionIn
) -> None:
    source_ids = {
        source_id
        for item in [*payload.drivers, *payload.kpis]
        for source_id in item.source_document_version_ids
    }
    if not source_ids:
        return
    company = db.get(Company, case.company_id)
    if company is None:
        raise CompanyProfileError("Research case company is missing.", kind="conflict")
    rows = list(
        db.execute(
            select(
                DocumentVersion.id,
                SourceDocument.company_id,
                SourceDocument.company_ticker,
            )
            .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
            .where(DocumentVersion.id.in_(source_ids))
        )
    )
    found = {row.id for row in rows}
    missing = source_ids - found
    if missing:
        raise CompanyProfileError(
            f"Unknown document version ids: {sorted(missing)}.", kind="not-found"
        )
    for version_id, source_company_id, source_ticker in rows:
        own_company = source_company_id == company.id
        own_ticker = source_company_id is None and source_ticker.upper() == company.ticker.upper()
        permitted_context = source_company_id is None and source_ticker == "__GPW__"
        if not (own_company or own_ticker or permitted_context):
            raise CompanyProfileError(
                f"Document version {version_id} belongs to another company.",
                kind="conflict",
            )


def append_human_profile(
    db: Session, *, case: ResearchCase, payload: CompanyProfileCorrectionIn
) -> CompanyProfile:
    """Append one user-confirmed/corrected profile without touching history."""
    current = db.scalar(
        select(CompanyProfile)
        .where(
            CompanyProfile.research_case_id == case.id,
            CompanyProfile.schema_version == RESEARCH_PROFILE_SCHEMA,
        )
        .order_by(CompanyProfile.version.desc(), CompanyProfile.id.desc())
        .limit(1)
    )
    if current is None:
        raise CompanyProfileError(
            "Complete the initial Research snapshot before confirming its profile.",
            kind="conflict",
        )
    if payload.base_profile_id != current.id:
        raise CompanyProfileError(
            "The current company profile changed; reopen it before confirming your edit.",
            kind="conflict",
        )

    pack = get_pack(payload.archetype)
    assert pack is not None
    _validate_profile_focus(payload, archetype_version=pack.version)
    _validate_profile_sources(db, case=case, payload=payload)
    values = {
        "schema_version": RESEARCH_PROFILE_SCHEMA,
        "archetype": payload.archetype,
        "archetype_version": pack.version,
        "company_overlay": payload.company_overlay.model_dump(mode="json"),
        "drivers": [item.model_dump(mode="json") for item in payload.drivers],
        "kpis": [item.model_dump(mode="json") for item in payload.kpis],
    }
    changed = values != profile_values(current)
    latest_version = db.scalar(
        select(func.max(CompanyProfile.version)).where(
            CompanyProfile.research_case_id == case.id
        )
    )
    assert latest_version == current.version
    profile = CompanyProfile(
        research_case_id=case.id,
        version=current.version + 1,
        **values,
        provenance="human-corrected" if changed else "human-confirmed",
        reason=payload.reason.strip(),
        based_on_profile_id=current.id,
    )
    db.add(profile)
    db.flush()
    return profile
