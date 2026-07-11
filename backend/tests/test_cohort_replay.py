"""CX.16 frozen-cohort identity and no-fabrication cards."""
from datetime import date, datetime, timezone


def _adjusted_price(**kwargs):
    from app.db.models import Price

    return Price(
        source_name="test_verified_prices",
        series_key="test:verified:split:v1",
        adjustment_status="split_adjusted",
        basis_version="v1",
        **kwargs,
    )


def test_frozen_cohort_resolves_identities_without_inventing_returns(db):
    from app.services.cohort_replay import build_frozen_cohort_review

    result = build_frozen_cohort_review(db)
    cards = {card["case_id"]: card for card in result["outcomes"]}

    assert cards["DGN"]["market_identity"] == {
        "ticker": "DIG",
        "isin": "PL4FNMD00013",
        "market": "GPW",
        "source": cards["DGN"]["market_identity"]["source"],
    }
    assert cards["SUNTECH"]["market_identity"]["ticker"] == "SUN"
    assert cards["SUNTECH"]["market_identity"]["isin"] == "PLSNTCH00012"
    assert cards["OPTEX"]["market_identity"]["ticker"] == "OPXS"
    assert cards["SNT"]["admission_status"] == "excluded"
    assert result["verification_status"] == "needs-human"
    assert all(
        horizon["return_pct"] is None
        for card in cards.values()
        for horizon in card["horizons"]
    )


def test_frozen_cohort_measures_only_admissible_exact_anchor_price(db):
    from app.db.models import Company, Price
    from app.services.cohort_replay import build_frozen_cohort_review

    company = Company(ticker="SUN", name="SUNTECH")
    db.add(company)
    db.flush()
    db.add_all(
        [
            _adjusted_price(
                company_id=company.id,
                date=date(2023, 3, 31),
                close=6.0,
                scraped_at=datetime(2023, 3, 31, 12, 0, tzinfo=timezone.utc),
            ),
            _adjusted_price(company_id=company.id, date=date(2024, 4, 1), close=3.0),
        ]
    )
    db.commit()

    result = build_frozen_cohort_review(db)
    sun = next(card for card in result["outcomes"] if card["case_id"] == "SUNTECH")
    one_year = next(item for item in sun["horizons"] if item["days"] == 365)

    assert sun["admission_status"] == "measurable"
    assert one_year["return_pct"] == -50.0
    assert one_year["status"] == "measured"
    assert one_year["source_name"] == "test_verified_prices"
    assert one_year["series_key"] == "test:verified:split:v1"
    assert one_year["basis_version"] == "v1"
    two_year = next(item for item in sun["horizons"] if item["days"] == 730)
    assert two_year["reason"] == "no_matching_series_endpoint"
