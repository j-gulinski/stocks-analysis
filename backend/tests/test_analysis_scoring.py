"""Pure tests for authoritative strategy-score arithmetic and vetoes."""

from app.services.analysis_scoring import compute_alignment_score


def _item(item_id: str, verdict: str) -> dict:
    return {"id": item_id, "item": item_id, "verdict": verdict, "evidence": "x"}


def _dossier(profit=100.0, net_cash=50.0) -> dict:
    return {"ttm": {"net_profit": profit}, "net_cash": {"value": net_cash}}


def test_unknown_drops_out_and_catalyst_cap_applies():
    verdict = {
        "checklist": [
            _item("revenue_growth", "spełnia"),
            _item("gross_margin_trend", "spełnia"),
            _item("valuation_vs_history", "spełnia"),
            _item("catalyst", "nieznane"),
            _item("dividend", "nieznane"),
        ]
    }
    assert compute_alignment_score(verdict, _dossier()) == 75


def test_weighted_fail_is_server_computed():
    verdict = {
        "checklist": [
            _item("revenue_growth", "spełnia"),
            _item("gross_margin_trend", "nie spełnia"),
            _item("valuation_vs_history", "spełnia"),
            _item("catalyst", "spełnia"),
        ]
    }
    # (12 + 15 + 10) / (12 + 15 + 15 + 10) = 71.15% -> 71
    assert compute_alignment_score(verdict, _dossier()) == 71


def test_profit_quality_veto_caps_at_50():
    verdict = {
        "checklist": [
            _item("revenue_growth", "spełnia"),
            _item("valuation_vs_history", "spełnia"),
            _item("catalyst", "spełnia"),
            _item("profit_quality", "nie spełnia"),
        ]
    }
    assert compute_alignment_score(verdict, _dossier()) == 50


def test_deterministic_prescore_profit_quality_overrides_model_pass():
    verdict = {
        "checklist": [
            _item("revenue_growth", "spełnia"),
            _item("valuation_vs_history", "spełnia"),
            _item("catalyst", "spełnia"),
            _item("profit_quality", "spełnia"),
        ]
    }
    dossier = _dossier()
    dossier["prescore"] = {
        "checks": [{"id": "profit_quality", "verdict": "fail"}]
    }
    assert compute_alignment_score(verdict, dossier) == 50


def test_duplicate_ids_do_not_double_weight():
    verdict = {
        "checklist": [
            _item("revenue_growth", "spełnia"),
            _item("revenue_growth", "spełnia"),
            _item("gross_margin_trend", "nie spełnia"),
            _item("catalyst", "spełnia"),
        ]
    }
    # Unique weights: (12 + 10) / (12 + 15 + 10) = 59.46 -> 59.
    assert compute_alignment_score(verdict, _dossier()) == 59


def test_loss_and_net_debt_veto_caps_at_40():
    verdict = {
        "checklist": [
            _item("revenue_growth", "spełnia"),
            _item("valuation_vs_history", "spełnia"),
            _item("catalyst", "spełnia"),
        ]
    }
    assert compute_alignment_score(verdict, _dossier(profit=-10, net_cash=-20)) == 40


def test_fewer_than_three_known_items_returns_none():
    verdict = {
        "checklist": [
            _item("revenue_growth", "spełnia"),
            _item("catalyst", "nieznane"),
        ]
    }
    assert compute_alignment_score(verdict, _dossier()) is None
