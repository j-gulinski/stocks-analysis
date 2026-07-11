"""Pure tests for authoritative strategy-score arithmetic and vetoes."""

from app.services.analysis_scoring import build_codex_score_base, compute_alignment_score, compute_conviction_score


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
    # (10 + 15 + 7.5) / (10 + 10 + 15 + 7.5) = 76.47% -> 76.
    assert compute_alignment_score(verdict, _dossier()) == 76


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
    # Unique weights: (10 + 7.5) / (10 + 10 + 7.5) = 63.64 -> 64.
    assert compute_alignment_score(verdict, _dossier()) == 64


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


def test_codex_score_base_prioritizes_growth_but_is_not_a_final_rating():
    dossier = _dossier()
    dossier["prescore"] = {
        "checks": [
            {"id": "revenue_growth", "verdict": "pass"},
            {"id": "gross_margin_trend", "verdict": "pass"},
            {"id": "operating_leverage", "verdict": "pass"},
            {"id": "profit_quality", "verdict": "fail"},
            {"id": "net_cash", "verdict": "pass"},
            {"id": "pe_vs_history", "verdict": "pass"},
        ]
    }

    base = build_codex_score_base(dossier)

    assert base["factors"][0]["weight"] == 30
    assert base["deterministic_signal"] <= 50
    assert base["caps"] == [{"id": "one_off_profit", "maximum_score": 50}]
    assert "not a standalone" in base["purpose"]


def test_conviction_score_is_reproducible_and_respects_base_caps():
    score = compute_conviction_score(
        {"deterministic_signal": 90, "evidence_coverage_pct": 100, "caps": [{"maximum_score": 50}]},
        [
            {"probability_pct": 25, "deterministic_impact": {"price_impact": {"return_pct": -20}}},
            {"probability_pct": 50, "deterministic_impact": {"price_impact": {"return_pct": 0}}},
            {"probability_pct": 25, "deterministic_impact": {"price_impact": {"return_pct": 20}}},
        ],
    )
    assert score["value"] == 50
    assert score["basis"]["weighted_return_pct"] == 0
