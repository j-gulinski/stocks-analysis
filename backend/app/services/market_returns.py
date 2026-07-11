"""Eligibility rules for deterministic historical return calculations."""
from __future__ import annotations

from app.db.models import Price


RETURN_ELIGIBLE_ADJUSTMENTS = ("split_adjusted", "total_return")
UNVERIFIED_PRICE_BLOCKER = (
    "Stored price series has no verified corporate-action adjustment basis."
)


def is_return_eligible(price: Price | None) -> bool:
    return bool(
        price is not None
        and price.adjustment_status in RETURN_ELIGIBLE_ADJUSTMENTS
        and bool(price.source_name)
        and bool(price.series_key)
        and bool(price.basis_version)
    )


def series_identity(price: Price | None) -> tuple[str, str, str, str] | None:
    if not is_return_eligible(price):
        return None
    assert price is not None
    return (
        price.source_name or "",
        price.series_key or "",
        price.adjustment_status,
        price.basis_version or "",
    )
