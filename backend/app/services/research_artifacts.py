"""Strict verification and atomic persistence for versioned research snapshots."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ResearchSnapshotDraftIn,
    ResearchSnapshotSaveIn,
    ResearchSnapshotVerificationIn,
    ResearchVerifierResult,
)
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
from app.services.agent_queue import clear_agent_lease
from app.services.archetype_packs import (
    get_pack,
    known_marker_ids,
)
from app.services.company_profiles import profile_fingerprint, profile_values

ALLOWED_WORKFLOWS = {
    "stock-initial-research",
    "stock-company-review",
}
SKILL = "company-research"
WRITE_CONTRACTS = {
    "research-snapshot-v3": {
        "skill_version": "company-research-v3",
        "profile_schema_version": "company-profile-v2",
        "archetype_contract_version": "archetype-packs-v1",
    },
}

REQUIRED_SOURCE_CHANNELS = {
    "issuer-primary",
    "regulatory-primary",
    "biznesradar",
    "portalanaliz",
    "other-web",
}
REQUIRED_STANDING_RESOLUTIONS = {"catalyst", "visibility", "governance"}


def _source_host(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").casefold()
    return host.removeprefix("www.")


def _matches_host(hosts: set[str], domain: str) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for host in hosts)


def _stored_source_policy(
    *,
    source_name: str,
    source_type: str,
    canonical_url: str,
    effective_url: str,
) -> dict[str, set[str]]:
    """Derive v3 channel/role eligibility from server-owned source identity."""
    hosts = {
        host
        for host in (_source_host(canonical_url), _source_host(effective_url))
        if host
    }
    normalized_name = source_name.strip().casefold()
    normalized_type = source_type.strip().casefold()

    # Provider hosts win over draft-assigned roles, including when stored
    # metadata is internally inconsistent. This keeps aggregator/forum rows
    # from being promoted to primary evidence by a model-authored manifest.
    if _matches_host(hosts, "biznesradar.pl"):
        if not normalized_name.startswith("biznesradar"):
            return {}
        return {
            "biznesradar": {
                "context" if normalized_type == "market_rating" else "normalized"
            }
        }
    if _matches_host(hosts, "portalanaliz.pl"):
        return {"portalanaliz": {"lead"}}
    if _matches_host(hosts, "gpw.pl"):
        return (
            {"regulatory-primary": {"primary"}}
            if normalized_type == "espi_ebi"
            else {}
        )
    if normalized_type in {"issuer_ir", "issuer_ir_report"}:
        return {"issuer-primary": {"primary"}}
    if normalized_type == "espi_ebi":
        return {"regulatory-primary": {"primary"}}
    if normalized_type == "forum":
        return {"other-web": {"lead"}}
    if hosts:
        return {"other-web": {"primary", "context"}}
    return {}


class ResearchArtifactError(ValueError):
    """A draft cannot cross the research verification/save boundary."""

    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def research_draft_fingerprint(payload: ResearchSnapshotDraftIn) -> str:
    """Server-owned digest of the exact draft reviewed by verifier_strict."""
    return _canonical_hash(payload.model_dump(mode="json"))


def _input_fingerprint(agent: AgentRun, payload: ResearchSnapshotDraftIn) -> str:
    """Bind the artifact to frozen job inputs and the cited point-in-time set."""
    return _canonical_hash(
        {
            "agent_run_id": agent.id,
            "company_id": agent.company_id,
            "workflow": agent.workflow,
            "trigger": agent.trigger,
            "inputs": agent.inputs or {},
            "as_of": payload.as_of.isoformat(),
            "source_document_version_ids": sorted(
                item.document_version_id for item in payload.source_manifest
            ),
        }
    )


def _artifact_fingerprint(
    payload: ResearchSnapshotDraftIn, verification: VerificationRun
) -> str:
    return _canonical_hash(
        {
            "draft_fingerprint": research_draft_fingerprint(payload),
            "verification_run_id": verification.id,
            "verifier_model": verification.verifier_model,
            "verdict": verification.verdict,
            "checks": verification.checks,
            "summary": verification.summary,
        }
    )


def _profile_values(payload: ResearchSnapshotDraftIn) -> dict:
    profile = payload.profile
    return {
        "schema_version": profile.schema_version,
        "archetype": profile.archetype,
        "archetype_version": profile.archetype_version,
        "company_overlay": profile.company_overlay.model_dump(mode="json"),
        "drivers": [item.model_dump(mode="json") for item in profile.drivers],
        "kpis": [item.model_dump(mode="json") for item in profile.kpis],
    }


def _assert_profile_matches(profile: CompanyProfile, values: dict) -> None:
    for field, expected in values.items():
        if getattr(profile, field) != expected:
            raise ResearchArtifactError(
                "That company-profile version already exists with different content.",
                kind="conflict",
            )


def _validate_frozen_review_profile(
    db: Session,
    case: ResearchCase,
    review: dict,
    payload: ResearchSnapshotDraftIn,
) -> None:
    frozen = review.get("confirmed_company_profile")
    if not isinstance(frozen, dict):
        raise ResearchArtifactError(
            "Company review requires one frozen confirmed company profile.",
            kind="conflict",
        )
    profile_id = frozen.get("id")
    profile = db.get(CompanyProfile, profile_id) if isinstance(profile_id, int) else None
    if profile is None or profile.research_case_id != case.id:
        raise ResearchArtifactError(
            "Company review frozen profile is missing or belongs to another case.",
            kind="conflict",
        )
    expected_frozen = {
        "id": profile.id,
        "version": profile.version,
        "fingerprint": profile_fingerprint(profile),
        **profile_values(profile),
        "provenance": profile.provenance,
        "author": profile.author,
        "reason": profile.reason,
        "based_on_profile_id": profile.based_on_profile_id,
    }
    if frozen != expected_frozen:
        raise ResearchArtifactError(
            "Company review frozen profile fingerprint drifted.", kind="conflict"
        )
    actual = {"version": payload.profile.version, **_profile_values(payload)}
    expected = {"version": profile.version, **profile_values(profile)}
    if actual != expected:
        raise ResearchArtifactError(
            "Company review draft profile does not match its frozen confirmed profile.",
            kind="conflict",
        )


def _material_statements(payload: ResearchSnapshotDraftIn) -> dict[str, str]:
    statements = {
        "/profile/archetype": payload.profile.archetype,
        "/sections/brief/current_understanding": payload.sections.brief.current_understanding,
        "/sections/brief/freshness": payload.sections.brief.freshness,
        "/sections/brief/main_gap": payload.sections.brief.main_gap,
        "/sections/brief/next_action": payload.sections.brief.next_action,
        "/sections/business_and_drivers/business_model": payload.sections.business_and_drivers.business_model,
        "/sections/business_and_drivers/revenue_model": payload.sections.business_and_drivers.revenue_model,
        "/sections/performance/summary": payload.sections.performance.summary,
        "/sections/evidence/summary": payload.sections.evidence.summary,
        "/sections/thesis/why_now": payload.sections.thesis.why_now,
        "/sections/thesis/counter_thesis": payload.sections.thesis.counter_thesis,
        "/sections/thesis/governance": payload.sections.thesis.governance,
    }
    outlook = payload.sections.outlook
    if outlook is not None:
        statements["/sections/outlook/summary"] = outlook.summary
        for index, item in enumerate(outlook.driver_outlooks):
            statements[
                f"/sections/outlook/driver_outlooks/{index}/next_quarter/assessment"
            ] = item.next_quarter.assessment.text
            statements[
                f"/sections/outlook/driver_outlooks/{index}/next_12_months/assessment"
            ] = item.next_12_months.assessment.text
        for index, item in enumerate(outlook.question_resolutions):
            statements[
                f"/sections/outlook/question_resolutions/{index}/answer"
            ] = item.answer.text
    overlay = payload.profile.company_overlay
    for field in ("segments", "competitors", "unusual_risks"):
        statements.update(
            {
                f"/profile/company_overlay/{field}/{index}": value
                for index, value in enumerate(getattr(overlay, field))
            }
        )
    section_lists = (
        ("/sections/performance/result_bridge", payload.sections.performance.result_bridge),
        ("/sections/thesis/catalysts", payload.sections.thesis.catalysts),
        ("/sections/thesis/risks", payload.sections.thesis.risks),
        ("/sections/thesis/falsifiers", payload.sections.thesis.falsifiers),
        (
            "/sections/history/changes_since_previous",
            payload.sections.history.changes_since_previous,
        ),
    )
    for prefix, values in section_lists:
        statements.update({f"{prefix}/{index}": value for index, value in enumerate(values)})
    return statements


def _referenced_source_ids(payload: ResearchSnapshotDraftIn) -> tuple[set[int], set[int]]:
    manifest_ids = {item.document_version_id for item in payload.source_manifest}
    referenced = set(manifest_ids)
    for item in [*payload.profile.drivers, *payload.profile.kpis]:
        referenced.update(item.source_document_version_ids)
    referenced.update(payload.sections.evidence.primary_document_version_ids)
    for section in (
        payload.sections.business_and_drivers,
        payload.sections.performance,
        payload.sections.evidence,
        payload.sections.thesis,
        payload.sections.history,
    ):
        for claim in section.claims:
            referenced.update(claim.source_document_version_ids)
    outlook = payload.sections.outlook
    if outlook is not None:
        for item in outlook.source_searches:
            referenced.update(item.document_version_ids)
        for item in outlook.driver_outlooks:
            referenced.update(item.next_quarter.assessment.source_document_version_ids)
            referenced.update(item.next_12_months.assessment.source_document_version_ids)
        for item in outlook.question_resolutions:
            referenced.update(item.answer.source_document_version_ids)
        for claim in outlook.claims:
            referenced.update(claim.source_document_version_ids)
    for item in payload.statement_provenance:
        referenced.update(item.claim.source_document_version_ids)
    for conflict in payload.conflicts:
        referenced.update(conflict.document_version_ids)
    return manifest_ids, referenced


def _case_company(db: Session, case: ResearchCase) -> Company:
    company = db.get(Company, case.company_id)
    if company is None:
        raise ResearchArtifactError(
            "Research case company no longer exists.", kind="conflict"
        )
    return company


def _validate_run(
    db: Session, case: ResearchCase, payload: ResearchSnapshotDraftIn
) -> AgentRun:
    agent = db.get(AgentRun, payload.agent_run_id)
    if agent is None:
        raise ResearchArtifactError(
            f"Unknown agent run {payload.agent_run_id}.", kind="not-found"
        )
    if agent.status != "running":
        raise ResearchArtifactError(
            "Research artifact requires a running agent run.", kind="conflict"
        )
    if agent.workflow not in ALLOWED_WORKFLOWS:
        raise ResearchArtifactError("Agent run workflow cannot create a research snapshot.")
    if agent.company_id != case.company_id:
        raise ResearchArtifactError(
            "Agent run company does not match the research case.", kind="conflict"
        )
    inputs = agent.inputs or {}
    if inputs.get("research_case_id") != case.id:
        raise ResearchArtifactError(
            "Agent run inputs do not match the research case.", kind="conflict"
        )
    task = inputs.get("task") if isinstance(inputs.get("task"), dict) else {}
    contract = WRITE_CONTRACTS.get(payload.contract_version)
    if (
        contract is None
        or task.get("skill") != SKILL
        or task.get("skill_version") != contract["skill_version"]
        or task.get("output_contract_version") != payload.contract_version
        or task.get("company_profile_schema_version")
        != contract["profile_schema_version"]
        or task.get("archetype_contract_version")
        != contract["archetype_contract_version"]
    ):
        raise ResearchArtifactError(
            "Frozen job skill/version/output contract does not authorize this artifact.",
            kind="conflict",
        )
    expiry = agent.lease_expires_at
    if not agent.lease_owner or expiry is None:
        raise ResearchArtifactError(
            "Research artifact requires an active claimed lease.", kind="conflict"
        )
    if payload.lease_owner != agent.lease_owner:
        raise ResearchArtifactError(
            "Payload lease owner does not own the claimed run.", kind="conflict"
        )
    if _aware(expiry) <= utcnow():
        raise ResearchArtifactError(
            "The agent-run lease expired before artifact processing.", kind="conflict"
        )
    if agent.workflow == "stock-company-review":
        review = inputs.get("review") if isinstance(inputs.get("review"), dict) else None
        if review is None:
            raise ResearchArtifactError(
                "Company review requires frozen prior-snapshot inputs.", kind="conflict"
            )
        prior_id = review.get("prior_research_snapshot_id")
        prior = db.get(ResearchSnapshot, prior_id) if isinstance(prior_id, int) else None
        if prior is None or prior.research_case_id != case.id:
            raise ResearchArtifactError(
                "Company review frozen prior snapshot is missing or belongs to another case.",
                kind="conflict",
            )
        if review.get("prior_artifact_fingerprint") != prior.artifact_fingerprint:
            raise ResearchArtifactError(
                "Company review frozen prior artifact fingerprint drifted.",
                kind="conflict",
            )
        queued_manifest = review.get("queued_source_manifest")
        queued_fingerprint = review.get("queued_source_fingerprint")
        if (
            not isinstance(queued_manifest, list)
            or not isinstance(queued_fingerprint, str)
            or _canonical_hash(queued_manifest) != queued_fingerprint
        ):
            raise ResearchArtifactError(
                "Company review queued source fingerprint is invalid.", kind="conflict"
            )
        if payload.sections.history.prior_snapshot_id != prior.id:
            raise ResearchArtifactError(
                "Company review history does not bind its frozen prior snapshot.",
                kind="conflict",
            )
        _validate_frozen_review_profile(db, case, review, payload)
        latest_id = db.scalar(
            select(ResearchSnapshot.id)
            .where(ResearchSnapshot.research_case_id == case.id)
            .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
            .limit(1)
        )
        if latest_id != prior.id:
            raise ResearchArtifactError(
                "Company review frozen prior snapshot is no longer latest.",
                kind="conflict",
            )
    return agent


def _final_status(result: ResearchVerifierResult, gaps: list) -> str:
    if result.verdict == "pass":
        return "provisional" if gaps else "verified"
    if result.verdict == "fail":
        return "rejected"
    if result.verdict == "needs-human":
        return "needs-human"
    raise ResearchArtifactError("Unsupported verifier verdict.")


def _validate_self_resolving_outlook(payload: ResearchSnapshotDraftIn) -> None:
    outlook = payload.sections.outlook
    if outlook is None:
        raise ResearchArtifactError(
            "research-snapshot-v3 requires a future-oriented outlook section."
        )

    search_channels = [item.channel for item in outlook.source_searches]
    if len(search_channels) != len(set(search_channels)):
        raise ResearchArtifactError("Outlook source-search channels must be unique.")
    supplied_channels = set(search_channels)
    if supplied_channels != REQUIRED_SOURCE_CHANNELS:
        raise ResearchArtifactError(
            "Outlook must record one bounded attempt for every required source "
            f"channel; missing={sorted(REQUIRED_SOURCE_CHANNELS - supplied_channels)}, "
            f"extra={sorted(supplied_channels - REQUIRED_SOURCE_CHANNELS)}."
        )

    driver_keys = [item.key for item in payload.profile.drivers]
    outlook_driver_keys = [item.driver_key for item in outlook.driver_outlooks]
    if Counter(outlook_driver_keys) != Counter(driver_keys):
        raise ResearchArtifactError(
            "Outlook must assess next-quarter and next-12-month effects exactly once "
            "for every company-profile driver."
        )

    profile_questions = payload.profile.company_overlay.source_questions
    if not profile_questions:
        raise ResearchArtifactError(
            "A v3 company profile requires at least one company-specific source question."
        )
    if len(profile_questions) != len(set(profile_questions)):
        raise ResearchArtifactError("Company-profile source questions must be unique.")
    profile_resolutions = [
        item.question for item in outlook.question_resolutions if item.scope == "profile"
    ]
    if Counter(profile_resolutions) != Counter(profile_questions):
        raise ResearchArtifactError(
            "Outlook must resolve every frozen company-profile source question exactly once."
        )
    standing = Counter(
        item.scope for item in outlook.question_resolutions if item.scope != "profile"
    )
    if set(standing) != REQUIRED_STANDING_RESOLUTIONS or any(
        standing[scope] != 1 for scope in REQUIRED_STANDING_RESOLUTIONS
    ):
        raise ResearchArtifactError(
            "Outlook requires exactly one catalyst, visibility and governance resolution."
        )

    gap_topics = {item.topic for item in payload.gaps}
    linked_gap_topics: list[str] = []
    for item in outlook.question_resolutions:
        if not set(item.source_channels).issubset(supplied_channels):
            raise ResearchArtifactError(
                f"Question resolution cites an unsearched channel: {item.question}."
            )
        if item.gap_topic:
            linked_gap_topics.append(item.gap_topic)
    for item in outlook.driver_outlooks:
        for assessment in (item.next_quarter, item.next_12_months):
            if not set(assessment.source_channels).issubset(supplied_channels):
                raise ResearchArtifactError(
                    "Driver outlook cites an unsearched channel: "
                    f"{item.driver_key}."
                )
            if assessment.gap_topic:
                linked_gap_topics.append(assessment.gap_topic)
    missing_gaps = set(linked_gap_topics) - gap_topics
    if missing_gaps:
        raise ResearchArtifactError(
            "Unknown outlooks and unresolved answers must link to top-level named "
            f"gaps; missing={sorted(missing_gaps)}."
        )


def _validate_contract(
    db: Session, case: ResearchCase, payload: ResearchSnapshotDraftIn
) -> None:
    driver_keys = {item.key for item in payload.profile.drivers}
    kpi_keys = {item.key for item in payload.profile.kpis}
    if len(driver_keys) != len(payload.profile.drivers):
        raise ResearchArtifactError("Company-profile driver keys must be unique.")
    if len(kpi_keys) != len(payload.profile.kpis):
        raise ResearchArtifactError("Company-profile KPI keys must be unique.")
    if not set(payload.sections.business_and_drivers.driver_keys).issubset(driver_keys):
        raise ResearchArtifactError("Business section references an unknown driver key.")
    if not set(payload.sections.performance.kpi_keys).issubset(kpi_keys):
        raise ResearchArtifactError("Performance section references an unknown KPI key.")

    contract = WRITE_CONTRACTS[payload.contract_version]
    if payload.profile.schema_version != contract["profile_schema_version"]:
        raise ResearchArtifactError(
            f"{payload.contract_version} requires {contract['profile_schema_version']}."
        )
    _validate_self_resolving_outlook(payload)
    pack = get_pack(payload.profile.archetype)
    if pack is None:  # Pydantic currently makes this defensive only.
        raise ResearchArtifactError("Unknown company-profile archetype.")
    elif payload.profile.archetype_version != pack.version:
        raise ResearchArtifactError(
            f"Archetype {pack.id} requires canonical pack version {pack.version}."
        )
    assert pack is not None
    allowed_focus = known_marker_ids(pack)
    evidence_focus: list[str] = []
    for item in [*payload.profile.drivers, *payload.profile.kpis]:
        if len(item.focus_tags) > 1:
            raise ResearchArtifactError(
                f"Profile item {item.key} may address at most one archetype marker."
            )
        if item.focus_tags:
            marker = item.focus_tags[0]
            if marker != item.key:
                raise ResearchArtifactError(
                    f"Profile item {item.key} must use the same focus tag as its key."
                )
            evidence_focus.append(marker)
    if len(evidence_focus) != len(set(evidence_focus)):
        raise ResearchArtifactError(
            "Each archetype marker may map to only one driver or KPI."
        )

    gap_focus: list[str] = []
    for gap in payload.gaps:
        if len(gap.focus_tags) > 1:
            raise ResearchArtifactError(
                f"Research gap {gap.topic} may address at most one archetype marker."
            )
        if gap.focus_tags:
            marker = gap.focus_tags[0]
            if marker != gap.topic:
                raise ResearchArtifactError(
                    f"Research gap {gap.topic} must use the same focus tag as its topic."
                )
            gap_focus.append(marker)
    if len(gap_focus) != len(set(gap_focus)):
        raise ResearchArtifactError(
            "Each archetype marker may map to only one explicit gap."
        )

    evidence_set = set(evidence_focus)
    gap_set = set(gap_focus)
    overlap = evidence_set & gap_set
    if overlap:
        raise ResearchArtifactError(
            "An archetype marker cannot be both evidence-covered and an explicit gap; "
            f"overlap={sorted(overlap)}."
        )
    supplied_focus = evidence_set | gap_set
    unknown_focus = supplied_focus - allowed_focus
    if unknown_focus:
        raise ResearchArtifactError(
            f"Unknown focus tags for {pack.id}: {sorted(unknown_focus)}."
        )
    missing_focus = allowed_focus - supplied_focus
    if missing_focus:
        raise ResearchArtifactError(
            "Every required archetype marker must be covered by a driver/KPI "
            f"or an explicit gap; missing={sorted(missing_focus)}."
        )

    expected_statements = _material_statements(payload)
    expected_paths = set(expected_statements)
    supplied_paths = [item.path for item in payload.statement_provenance]
    if len(supplied_paths) != len(set(supplied_paths)):
        raise ResearchArtifactError("Statement provenance paths must be unique.")
    if set(supplied_paths) != expected_paths:
        missing = sorted(expected_paths - set(supplied_paths))
        extra = sorted(set(supplied_paths) - expected_paths)
        raise ResearchArtifactError(
            f"Statement provenance coverage mismatch; missing={missing}, extra={extra}."
        )
    for item in payload.statement_provenance:
        if item.claim.text != expected_statements[item.path]:
            raise ResearchArtifactError(
                f"Statement provenance text does not match {item.path}."
            )

    manifest_ids, referenced_ids = _referenced_source_ids(payload)
    if not manifest_ids:
        raise ResearchArtifactError("A research snapshot draft requires sources.")
    if len(manifest_ids) != len(payload.source_manifest):
        raise ResearchArtifactError(
            "Source-manifest document versions must be unique."
        )
    outside_manifest = referenced_ids - manifest_ids
    if outside_manifest:
        raise ResearchArtifactError(
            "Referenced document versions are absent from source_manifest: "
            f"{sorted(outside_manifest)}."
        )
    rows = (
        list(
            db.execute(
                select(
                    DocumentVersion.id,
                    DocumentVersion.fetched_at,
                    DocumentVersion.effective_url,
                    SourceDocument.company_id,
                    SourceDocument.company_ticker,
                    SourceDocument.source_name,
                    SourceDocument.source_type,
                    SourceDocument.canonical_url,
                )
                .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
                .where(DocumentVersion.id.in_(referenced_ids))
            )
        )
        if referenced_ids
        else []
    )
    found = {row.id for row in rows}
    missing = referenced_ids - found
    if missing:
        raise ResearchArtifactError(
            f"Unknown document version ids: {sorted(missing)}.", kind="not-found"
        )
    company = _case_company(db, case)
    manifest_roles = {item.document_version_id: item.role for item in payload.source_manifest}
    outlook = payload.sections.outlook
    if outlook is not None:
        source_policies = {
            row.id: _stored_source_policy(
                source_name=row.source_name,
                source_type=row.source_type,
                canonical_url=row.canonical_url,
                effective_url=row.effective_url,
            )
            for row in rows
        }
        for version_id, role in manifest_roles.items():
            policy = source_policies.get(version_id, {})
            allowed_manifest_roles = set().union(*policy.values()) if policy else set()
            if role not in allowed_manifest_roles:
                raise ResearchArtifactError(
                    "Source-manifest role conflicts with stored source identity; "
                    f"document_version_id={version_id}, role={role!r}."
                )
        for search in outlook.source_searches:
            mismatched = [
                version_id
                for version_id in search.document_version_ids
                if search.channel not in source_policies.get(version_id, {})
                or manifest_roles.get(version_id)
                not in source_policies[version_id][search.channel]
            ]
            if mismatched:
                raise ResearchArtifactError(
                    f"Source-search channel {search.channel} conflicts with stored "
                    "source identity or manifest role "
                    f"for document versions {sorted(mismatched)}."
                )
        searched_version_ids = {
            search.channel: set(search.document_version_ids)
            for search in outlook.source_searches
        }
        for resolution in outlook.question_resolutions:
            cited = set(resolution.answer.source_document_version_ids)
            allowed = set().union(
                *(searched_version_ids[channel] for channel in resolution.source_channels)
            )
            outside_declared_channels = cited - allowed
            if outside_declared_channels:
                raise ResearchArtifactError(
                    "Question-resolution evidence must come from its declared searched "
                    f"channels; question={resolution.question!r}, "
                    f"outside={sorted(outside_declared_channels)}."
                )
        for driver in outlook.driver_outlooks:
            for horizon, assessment in (
                ("next_quarter", driver.next_quarter),
                ("next_12_months", driver.next_12_months),
            ):
                cited = set(assessment.assessment.source_document_version_ids)
                allowed = set().union(
                    *(
                        searched_version_ids[channel]
                        for channel in assessment.source_channels
                    )
                )
                outside_declared_channels = cited - allowed
                if outside_declared_channels:
                    raise ResearchArtifactError(
                        "Driver-outlook evidence must come from its declared searched "
                        f"channels; driver={driver.driver_key!r}, horizon={horizon}, "
                        f"outside={sorted(outside_declared_channels)}."
                    )
        material_claims = [
            *(
                item.answer
                for item in outlook.question_resolutions
                if item.status in {"confirmed", "partial", "not_applicable"}
            ),
            *(
                assessment.assessment
                for item in outlook.driver_outlooks
                for assessment in (item.next_quarter, item.next_12_months)
                if assessment.direction != "unknown"
            ),
        ]
        for claim in material_claims:
            if not claim.source_document_version_ids:
                raise ResearchArtifactError(
                    "Supported outlook conclusions require at least one cited document version."
                )
            if claim.source_document_version_ids and all(
                manifest_roles.get(version_id) in {"lead", "context"}
                for version_id in claim.source_document_version_ids
            ):
                raise ResearchArtifactError(
                    "A lead/context-only source set cannot support an outlook conclusion."
                )
    for row in rows:
        if row.company_id is not None:
            identity_ok = row.company_id == case.company_id
        else:
            identity_ok = row.company_ticker.upper() == company.ticker.upper()
            if row.company_ticker == "__GPW__":
                identity_ok = manifest_roles.get(row.id) == "context"
        if not identity_ok:
            raise ResearchArtifactError(
                f"Document version {row.id} belongs to another company.",
                kind="conflict",
            )
        if _aware(row.fetched_at) > _aware(payload.as_of):
            raise ResearchArtifactError(
                f"Document version {row.id} was fetched after snapshot as_of.",
                kind="conflict",
            )
    if _aware(payload.as_of) > utcnow() + timedelta(minutes=1):
        raise ResearchArtifactError("Snapshot as_of cannot be in the future.")


def _validate_version_history(
    db: Session, case: ResearchCase, payload: ResearchSnapshotDraftIn
) -> ResearchSnapshot | None:
    latest = db.scalar(
        select(ResearchSnapshot)
        .where(ResearchSnapshot.research_case_id == case.id)
        .order_by(ResearchSnapshot.version.desc(), ResearchSnapshot.id.desc())
        .limit(1)
    )
    expected_version = (latest.version if latest else 0) + 1
    if payload.version != expected_version:
        raise ResearchArtifactError(
            f"Next research snapshot version must be {expected_version}.",
            kind="conflict",
        )
    prior_id = payload.sections.history.prior_snapshot_id
    if latest is None and prior_id is not None:
        raise ResearchArtifactError("The first snapshot cannot cite a prior snapshot.")
    if latest is not None:
        if prior_id != latest.id:
            raise ResearchArtifactError(
                "History must cite the immediately preceding snapshot.", kind="conflict"
            )
        if _aware(payload.as_of) <= _aware(latest.as_of):
            raise ResearchArtifactError(
                "Snapshot as_of must advance chronologically.", kind="conflict"
            )
    return latest


def verify_research_snapshot(
    db: Session, *, case_id: int, payload: ResearchSnapshotVerificationIn
) -> VerificationRun:
    """Persist an independent verdict bound to the exact immutable draft."""
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ResearchArtifactError(f"Unknown research case {case_id}.", kind="not-found")
    agent = _validate_run(db, case, payload.draft)
    if payload.verifier_worker_id == agent.lease_owner:
        raise ResearchArtifactError(
            "The drafting worker cannot verify its own research snapshot.",
            kind="conflict",
        )
    _validate_contract(db, case, payload.draft)
    _validate_version_history(db, case, payload.draft)
    final_status = _final_status(payload.verifier_result, payload.draft.gaps)
    checks = {
        "computed_evidence": {
            "source_manifest_count": len(payload.draft.source_manifest),
            "statement_provenance_count": len(payload.draft.statement_provenance),
            "conflict_count": len(payload.draft.conflicts),
            "gap_count": len(payload.draft.gaps),
            "next_check_count": len(payload.draft.next_checks),
        },
        "findings": [
            item.model_dump(mode="json")
            for item in payload.verifier_result.findings
        ],
        "justifications": payload.verifier_result.justifications.model_dump(
            mode="json"
        ),
        "verifier_worker_id": payload.verifier_worker_id,
        "research_case_id": case.id,
        "research_draft_fingerprint": research_draft_fingerprint(payload.draft),
        "input_fingerprint": _input_fingerprint(agent, payload.draft),
        "final_status": final_status,
    }
    verification = VerificationRun(
        agent_run_id=agent.id,
        model_role=payload.verifier_result.model_role,
        verifier_model=payload.verifier_result.verifier_model,
        verdict=payload.verifier_result.verdict,
        checks=checks,
        summary=payload.verifier_result.summary,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    return verification


def _verification_result(verification: VerificationRun) -> ResearchVerifierResult:
    checks = verification.checks or {}
    return ResearchVerifierResult.model_validate(
        {
            "model_role": verification.model_role,
            "verifier_model": verification.verifier_model,
            "verdict": verification.verdict,
            "findings": checks.get("findings") or [],
            "justifications": checks.get("justifications"),
            "summary": verification.summary,
        }
    )


def _validated_verification(
    db: Session,
    agent: AgentRun,
    payload: ResearchSnapshotSaveIn,
    draft: ResearchSnapshotDraftIn,
) -> tuple[VerificationRun, ResearchVerifierResult]:
    verification = db.get(VerificationRun, payload.verification_run_id)
    if verification is None:
        raise ResearchArtifactError(
            f"Unknown verification run {payload.verification_run_id}.", kind="not-found"
        )
    checks = verification.checks or {}
    if (
        verification.agent_run_id != agent.id
        or verification.analysis_run_id is not None
        or verification.model_role != "verifier_strict"
        or checks.get("verifier_worker_id") in {None, agent.lease_owner}
        or checks.get("research_draft_fingerprint") != research_draft_fingerprint(draft)
        or checks.get("input_fingerprint") != _input_fingerprint(agent, draft)
    ):
        raise ResearchArtifactError(
            "Verification row is not an independent verdict for this exact draft.",
            kind="conflict",
        )
    result = _verification_result(verification)
    final_status = _final_status(result, payload.gaps)
    if checks.get("final_status") != final_status:
        raise ResearchArtifactError(
            "Verification final status does not match its verdict and draft gaps.",
            kind="conflict",
        )
    return verification, result


def save_research_snapshot(
    db: Session, *, case_id: int, payload: ResearchSnapshotSaveIn
) -> ResearchSnapshot:
    """Save one canonical snapshot and terminalize only its owning leased run."""
    case = db.get(ResearchCase, case_id)
    if case is None:
        raise ResearchArtifactError(f"Unknown research case {case_id}.", kind="not-found")
    draft = ResearchSnapshotDraftIn.model_validate(
        payload.model_dump(exclude={"verification_run_id"})
    )
    agent = db.get(AgentRun, payload.agent_run_id)
    verification = db.get(VerificationRun, payload.verification_run_id)
    if agent is None:
        raise ResearchArtifactError(
            f"Unknown agent run {payload.agent_run_id}.", kind="not-found"
        )
    if verification is None:
        raise ResearchArtifactError(
            f"Unknown verification run {payload.verification_run_id}.", kind="not-found"
        )
    artifact_fingerprint = _artifact_fingerprint(draft, verification)
    existing = db.scalar(
        select(ResearchSnapshot).where(ResearchSnapshot.agent_run_id == payload.agent_run_id)
    )
    if existing is not None:
        if (
            existing.research_case_id == case_id
            and existing.artifact_fingerprint == artifact_fingerprint
        ):
            return existing
        raise ResearchArtifactError(
            "This agent run already created a different immutable snapshot.",
            kind="conflict",
        )

    agent = _validate_run(db, case, draft)
    _validate_contract(db, case, draft)
    _validate_version_history(db, case, draft)
    verification, verifier_result = _validated_verification(db, agent, payload, draft)
    final_status = (verification.checks or {})["final_status"]
    input_fingerprint = _input_fingerprint(agent, draft)

    values = _profile_values(draft)
    profile = db.scalar(
        select(CompanyProfile).where(
            CompanyProfile.research_case_id == case.id,
            CompanyProfile.version == payload.profile.version,
        )
    )
    if profile is None:
        latest_profile_version = db.scalar(
            select(func.max(CompanyProfile.version)).where(
                CompanyProfile.research_case_id == case.id
            )
        )
        expected_profile_version = (latest_profile_version or 0) + 1
        if payload.profile.version != expected_profile_version:
            raise ResearchArtifactError(
                f"Next company profile version must be {expected_profile_version}.",
                kind="conflict",
            )
        profile = CompanyProfile(
            research_case_id=case.id,
            version=payload.profile.version,
            **values,
            provenance="codex-proposed",
            author=f"{agent.workflow}:{agent.id}",
            reason=None,
            based_on_profile_id=None,
        )
        db.add(profile)
        db.flush()
    else:
        _assert_profile_matches(profile, values)

    snapshot = ResearchSnapshot(
        research_case_id=case.id,
        company_profile_id=profile.id,
        agent_run_id=agent.id,
        verification_run_id=verification.id,
        version=payload.version,
        contract_version=payload.contract_version,
        status=final_status,
        as_of=payload.as_of,
        input_fingerprint=input_fingerprint,
        artifact_fingerprint=artifact_fingerprint,
        sections=payload.sections.model_dump(mode="json"),
        source_manifest=[item.model_dump(mode="json") for item in payload.source_manifest],
        conflicts=[item.model_dump(mode="json") for item in payload.conflicts],
        gaps=[item.model_dump(mode="json") for item in payload.gaps],
        next_checks=[item.model_dump(mode="json") for item in payload.next_checks],
        statement_provenance=[
            item.model_dump(mode="json") for item in payload.statement_provenance
        ],
        verifier_result=verifier_result.model_dump(mode="json"),
    )
    db.add(snapshot)
    db.flush()

    now = utcnow()
    agent.status = final_status
    agent.outputs = {
        **(agent.outputs or {}),
        "research_case_id": case.id,
        "company_profile_id": profile.id,
        "research_snapshot_id": snapshot.id,
        "verification_run_id": verification.id,
        "output_contract_version": payload.contract_version,
        "input_fingerprint": input_fingerprint,
    }
    agent.error = verifier_result.summary if final_status in {"rejected", "needs-human"} else None
    agent.finished_at = now
    agent.updated_at = now
    clear_agent_lease(agent)

    previous_state, previous_step = case.state, case.current_step
    case.as_of = payload.as_of
    case.updated_at = now
    if final_status in {"verified", "provisional"}:
        case.state = "monitoring"
        case.current_step = "monitoring"
        case.blocked_reason = None
    else:
        case.state = "blocked"
        case.current_step = "data_review"
        case.blocked_reason = verifier_result.summary
    if (previous_state, previous_step) != (case.state, case.current_step):
        from app.db.models import ResearchCaseStepHistory

        db.add(
            ResearchCaseStepHistory(
                research_case_id=case.id,
                from_state=previous_state,
                from_step=previous_step,
                to_state=case.state,
                to_step=case.current_step,
                reason=f"Research snapshot v{payload.version}: {final_status}.",
                changed_by="codex-worker",
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = db.scalar(
            select(ResearchSnapshot).where(
                ResearchSnapshot.agent_run_id == payload.agent_run_id
            )
        )
        if raced is not None and raced.artifact_fingerprint == artifact_fingerprint:
            return raced
        raise ResearchArtifactError(
            "Snapshot or profile version already exists and is immutable.",
            kind="conflict",
        ) from exc
    db.refresh(snapshot)
    return snapshot
