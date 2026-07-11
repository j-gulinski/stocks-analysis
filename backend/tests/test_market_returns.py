"""RT2.5 price-basis constraints and eligibility."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError


def test_eligible_price_requires_registered_series_provenance(db):
    from app.db.models import Company, Price

    company = Company(ticker="BAS", name="BASIS TEST")
    db.add(company)
    db.flush()
    db.add(
        Price(
            company_id=company.id,
            date=date(2024, 1, 2),
            close=10,
            adjustment_status="split_adjusted",
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_eligible_price_rejects_empty_series_provenance(db):
    from app.db.models import Company, Price

    company = Company(ticker="EMP", name="EMPTY BASIS")
    db.add(company)
    db.flush()
    db.add(
        Price(
            company_id=company.id,
            date=date(2024, 1, 2),
            close=10,
            source_name=" ",
            series_key=" ",
            adjustment_status="split_adjusted",
            basis_version=" ",
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_series_identity_requires_complete_eligible_basis():
    from app.db.models import Price
    from app.services.market_returns import series_identity

    raw = Price(close=10, adjustment_status="raw_unverified")
    adjusted = Price(
        close=10,
        source_name="licensed_source",
        series_key="licensed:ABC:split:v1",
        adjustment_status="split_adjusted",
        basis_version="v1",
    )

    assert series_identity(raw) is None
    assert series_identity(adjusted) == (
        "licensed_source",
        "licensed:ABC:split:v1",
        "split_adjusted",
        "v1",
    )
