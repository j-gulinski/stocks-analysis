"""RT4.3c industrial/consumer template-backed operating bridge."""

from app.services import operating_scenarios
from app.services.strategies import malik
from tests.test_scenarios import cz_inputs


def _income():
    rows = {}
    for index, period in enumerate(("2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1")):
        revenue = 90_000.0 + index * 4_000.0
        gross_profit = revenue * 0.32
        selling_costs = revenue * 0.08
        admin_costs = 6_000.0
        profit_on_sales = gross_profit - selling_costs - admin_costs
        operating_profit = profit_on_sales - 500.0
        pretax_profit = operating_profit - 300.0
        rows[period] = {
            "revenue": revenue,
            "gross_profit": gross_profit,
            "selling_costs": selling_costs,
            "admin_costs": admin_costs,
            "profit_on_sales": profit_on_sales,
            "operating_profit": operating_profit,
            "pretax_profit": pretax_profit,
            "net_profit": pretax_profit * 0.81,
            "depreciation": 1_000.0,
        }
    return rows


def test_industrial_bridge_projects_pnl_and_keeps_suggestions_inactive():
    result = operating_scenarios.build_operating_bridge(
        cz_inputs(),
        _income(),
        malik.MALIK,
        [
            {
                "scenario_kind": "base",
                "status": "approved",
                "label": "Bazowy P&L",
                "assumptions": [
                    {
                        "key": "revenue",
                        "value": 125_000,
                        "unit": "tys. PLN",
                        "provenance": "human_assumption",
                        "rationale": "Wariant bazowy.",
                    },
                    {
                        "key": "gross_margin_pct",
                        "value": 35.0,
                        "unit": "%",
                        "provenance": "evidence",
                        "rationale": "Marża z przyjętego źródła.",
                    },
                    {
                        "key": "selling_costs_pct",
                        "value": 7.0,
                        "unit": "%",
                        "provenance": "model_suggestion",
                        "rationale": "Wymaga akceptacji.",
                    },
                ],
            },
            {"scenario_kind": "negative", "status": "draft", "assumptions": []},
        ],
        cashflow_latest={
            "operating_cashflow": ("2025Q1", 1_500.0),
            "capex": ("2025Q1", -400.0),
        },
        balance_series={
            "2024Q4": {"receivables_current": 100.0, "inventory": 200.0},
            "2025Q1": {"receivables_current": 150.0, "inventory": 250.0},
        },
    )

    assert result["status"] == "applied"
    assert result["template"]["id"] == "industrial_consumer_pnl_v1"
    row = result["rows"][0]
    assert row["projected_revenue"] == 125_000.0
    assert row["projected_gross_margin_pct"] == 35.0
    assert row["operating_target_price"] is not None
    assert row["target_price_delta"] is not None
    assert {item["key"] for item in row["applied"]} == {"revenue", "gross_margin_pct"}
    assert row["ignored"][0]["key"] == "selling_costs_pct"
    assert row["ignored"][0]["applied"] is False
    assert row["projected_fcf"] == round(
        row["projected_net_profit"] + row["projected_depreciation"] - 100.0 - 400.0,
        1,
    )


def test_bridge_keeps_unsupported_archetype_explicit():
    inputs = cz_inputs()
    inputs.thesis_inputs.insights.sector_group = "biotech_med"
    result = operating_scenarios.build_operating_bridge(inputs, _income(), malik.MALIK, [])
    assert result["status"] == "unsupported_template"
    assert result["rows"] == []


def test_cash_conversion_snapshot_keeps_working_capital_gap_explicit():
    snapshot = operating_scenarios.build_cash_conversion_snapshot(
        {
            "operating_cashflow": ("2025Q1", 1_500.0),
            "capex": ("2025Q1", -400.0),
        },
        {"2025Q1": {"net_profit": 1_000.0, "revenue": 10_000.0}},
    )
    assert snapshot["status"] == "partial"
    assert snapshot["conversion_ratio"] == 1.5
    assert snapshot["capex_intensity_pct"] == 4.0
    assert snapshot["observed_fcf"] == 1_100.0
    assert any("należności" in gap for gap in snapshot["gaps"])

    complete = operating_scenarios.build_cash_conversion_snapshot(
        {"operating_cashflow": ("2025Q1", 1_500.0), "capex": ("2025Q1", -400.0)},
        {"2024Q4": {"net_profit": 900.0, "revenue": 9_500.0}, "2025Q1": {"net_profit": 1_000.0, "revenue": 10_000.0}},
        {
            "2024Q4": {"receivables_current": 100.0, "inventory": 200.0},
            "2025Q1": {"receivables_current": 150.0, "inventory": 250.0},
        },
    )
    assert complete["working_capital_change"] == 100.0
    assert complete["working_capital_cash_effect"] == -100.0
    assert not any("dwóch porównywalnych" in gap for gap in complete["gaps"])


def test_fcf_lens_requires_explicit_cash_inputs_and_prices_separately():
    result = operating_scenarios.build_operating_bridge(
        cz_inputs(),
        _income(),
        malik.MALIK,
        [
            {
                "scenario_kind": "base",
                "status": "approved",
                "label": "Bazowy FCF",
                "assumptions": [
                    {"key": "revenue", "value": 125_000, "provenance": "human_assumption", "rationale": "Przychód."},
                    {"key": "gross_margin_pct", "value": 35.0, "provenance": "evidence", "rationale": "Marża."},
                    {"key": "capex", "value": -400.0, "unit": "tys. PLN", "provenance": "evidence", "rationale": "Capex."},
                    {"key": "working_capital_change", "value": 100.0, "unit": "tys. PLN", "provenance": "human_assumption", "rationale": "Zmiana WC."},
                    {"key": "fcf_multiple", "value": 12.0, "unit": "x", "provenance": "human_assumption", "rationale": "Jawny mnożnik."},
                ],
            }
        ],
        cashflow_latest={"operating_cashflow": ("2025Q1", 1_500.0), "capex": ("2025Q1", -400.0)},
        balance_series={
            "2024Q4": {"receivables_current": 100.0, "inventory": 200.0},
            "2025Q1": {"receivables_current": 150.0, "inventory": 250.0},
        },
    )
    lens = result["fcf_lens"]
    assert lens["status"] == "applied"
    row = lens["rows"][0]
    assert row["projected_fcf"] is not None
    assert row["fcf_target_price"] == round(row["projected_fcf"] / 10_000_000 * 1_000 * 12.0, 2)
    assert row["target_price_delta"] is not None

    incomplete = operating_scenarios.build_operating_bridge(
        cz_inputs(),
        _income(),
        malik.MALIK,
        [{"scenario_kind": "base", "status": "approved", "assumptions": [
            {"key": "capex", "value": -400.0, "provenance": "evidence", "rationale": "Capex."},
            {"key": "working_capital_change", "value": 100.0, "provenance": "evidence", "rationale": "WC."},
        ]}],
    )
    assert incomplete["fcf_lens"]["status"] == "needs_human"
    assert "fcf_multiple" in incomplete["fcf_lens"]["rows"][0]["missing"]


def test_priced_outcome_gate_requires_strict_archetype_and_lookahead_checks():
    bridge = {
        "template": {"id": "industrial_consumer_pnl_v1"},
        "fcf_lens": {
            "status": "applied",
            "rows": [{
                "scenario_kind": "base",
                "baseline_target_price": 100.0,
                "fcf_target_price": 120.0,
                "target_price_delta": 20.0,
            }],
        },
    }
    blocked = operating_scenarios.evaluate_priced_outcome_gate(bridge, None)
    assert blocked["status"] == "blocked"
    assert "verifier_strict" in blocked["reason"]
    fingerprint = operating_scenarios.operating_bridge_fingerprint(bridge)

    verification = {
        "model_role": "verifier_strict",
        "verdict": "pass",
        "checks": {
            "representative_archetypes": {"archetypes": ["industrial", "financial", "event-driven"]},
            "no_lookahead": {"verdict": "pass"},
            "math_reconciliation": {"verdict": "pass"},
            "source_lineage": {"verdict": "pass"},
            "scenario_input_match": {"verdict": "pass", "fingerprint": fingerprint},
        },
    }
    approved = operating_scenarios.evaluate_priced_outcome_gate(
        bridge, verification, fingerprint
    )
    assert approved["status"] == "approved"
    rows = operating_scenarios.attach_priced_company_outcomes(
        [{
            "kind": "base",
            "company_outcome": {
                "direction": "neutral",
                "label": "Stabilny wynik spółki",
                "description": "fallback",
            },
        }],
        bridge["fcf_lens"],
    )
    assert rows[0]["company_outcome"]["mode"] == "priced"
    assert rows[0]["company_outcome"]["direction"] == "positive"

    mismatched = operating_scenarios.evaluate_priced_outcome_gate(
        bridge, verification, "different-bridge"
    )
    assert mismatched["status"] == "blocked"
    assert "aktualnym mostem" in mismatched["reason"]
