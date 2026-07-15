"""The sole current artifact identities exposed by the Workbench.

Read paths import these values instead of guessing from a row version.  Older
rows are not compatibility artifacts: the clean-baseline gate removes them.
Until that reset, they cannot become the current product state.
"""

RESEARCH_PROFILE_SCHEMA = "company-profile-v2"
RESEARCH_SNAPSHOT_CONTRACT = "research-snapshot-v3"
VALUATION_SNAPSHOT_CONTRACT = "valuation-snapshot-v3"
VALUATION_CALCULATION_ENGINE = "valuation-engine-v4"


def canonical_research_snapshot_predicate():
    """SQL predicate for a snapshot that may enter the current product flow."""
    from app.db.models import ResearchSnapshot

    return (
        ResearchSnapshot.contract_version == RESEARCH_SNAPSHOT_CONTRACT,
        ResearchSnapshot.verifier_result["justifications"].as_string().is_not(None),
    )


def canonical_valuation_snapshot_predicate():
    """SQL identity predicate for the sole current valuation implementation."""
    from app.db.models import ValuationSnapshot

    return (
        ValuationSnapshot.contract_version == VALUATION_SNAPSHOT_CONTRACT,
        ValuationSnapshot.calculation_engine_version == VALUATION_CALCULATION_ENGINE,
    )
