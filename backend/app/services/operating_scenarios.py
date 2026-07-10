"""Small template-backed operating bridge for RT4.3c.

This module composes the existing pure next-quarter forecast with approved
case assumptions. It intentionally starts with the industrial/consumer P&L
template because DEC is the real pilot for this workflow; unsupported sectors
stay explicit instead of receiving a generic-looking equation.
"""
from __future__ import annotations

from dataclasses import replace
from math import isfinite

from app.services import forecast, scenarios
from app.services.strategies import base

_SUPPORTED_SECTORS = {"industrial", "consumer"}
_DRIVER_KEYS = {
    "revenue": "revenue",
    "gross_margin_pct": "gross_margin_pct",
    "selling_costs_pct": "selling_costs_pct",
    "admin_costs": "admin_costs",
    "other_operating": "other_operating",
    "financial_net": "financial_net",
    "tax_rate": "tax_rate",
    "depreciation": "depreciation",
}
_REQUIRED_KEYS = {"revenue", "gross_margin_pct"}


def _detail(item: dict, *, applied: bool, note: str) -> dict:
    return {
        "key": item.get("key", ""),
        "value": item.get("value"),
        "unit": item.get("unit"),
        "provenance": item.get("provenance", "human_assumption"),
        "source_ref": item.get("source_ref"),
        "rationale": item.get("rationale", ""),
        "applied": applied,
        "note": note,
    }


def _apply_items(defaults: forecast.ForecastAssumptions, items: list[dict]):
    projected = replace(defaults)
    applied: list[dict] = []
    ignored: list[dict] = []
    applied_keys: set[str] = set()
    for raw in items:
        item = raw if isinstance(raw, dict) else {}
        key = item.get("key")
        provenance = item.get("provenance")
        if provenance == "model_suggestion":
            ignored.append(
                _detail(item, applied=False, note="Sugestia modelu wymaga jawnego przyjęcia.")
            )
            continue
        target = _DRIVER_KEYS.get(key)
        value = item.get("value")
        if target is None:
            ignored.append(_detail(item, applied=False, note="Klucz nie należy do tego template."))
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            ignored.append(_detail(item, applied=False, note="Wartość sterownika nie jest liczbą."))
            continue
        if target == "revenue" and value <= 0:
            ignored.append(_detail(item, applied=False, note="Przychód musi być dodatni."))
            continue
        if target == "gross_margin_pct" and not 0 <= value <= 100:
            ignored.append(_detail(item, applied=False, note="Marża musi mieścić się w zakresie 0–100%."))
            continue
        if target == "tax_rate" and not 0 <= value <= 1:
            ignored.append(_detail(item, applied=False, note="Podatek musi być podany jako ratio 0–1."))
            continue
        setattr(projected, target, float(value))
        applied_keys.add(key)
        applied.append(_detail(item, applied=True, note="Zastosowano w równaniu template."))
    return projected, applied, ignored, applied_keys


def _upside(target: float | None, current: float | None) -> float | None:
    if target is None or current is None or current == 0:
        return None
    return round((target / current - 1.0) * 100.0, 2)


def _bridge_price(
    multiple_type: str,
    multiple_value: float | None,
    result: dict,
    net_cash: float | None,
    shares: int | None,
) -> tuple[float | None, str | None]:
    if multiple_value is None:
        return None, "Brak policzalnego mnożnika dla tego scenariusza."
    if multiple_type == "cz":
        eps = result.get("forward", {}).get("eps")
        if eps is None:
            return None, "Brak EPS z projekcji operacyjnej."
        return round(multiple_value * eps, 2), None
    if multiple_type == "ev_ebitda":
        ebitda = result.get("pnl", {}).get("ebitda")
        if ebitda is None or not shares:
            return None, "Brak EBITDA lub liczby akcji do mostu EV/EBITDA."
        equity = multiple_value * ebitda * 1000.0 + (net_cash or 0.0) * 1000.0
        return round(equity / shares, 2), None
    return None, "C/WK nie ma jeszcze projekcji wartości księgowej w tym template."


def build_operating_bridge(
    inputs: scenarios.ScenarioInputs,
    income: forecast.IncomeSeries,
    profile: base.StrategyProfile,
    approved_assumption_sets: list[dict] | None = None,
) -> dict:
    """Build explicit operating what-if rows for supported company templates."""
    sector = inputs.thesis_inputs.insights.sector_group
    if sector not in _SUPPORTED_SECTORS:
        return {
            "status": "unsupported_template",
            "template": None,
            "note": "Brak zatwierdzonego równania operacyjnego dla tego archetypu spółki.",
            "rows": [],
        }
    approved = [
        row for row in (approved_assumption_sets or [])
        if isinstance(row, dict)
        and row.get("status") == "approved"
        and row.get("scenario_kind") in {"negative", "base", "positive"}
    ]
    template = {
        "id": "industrial_consumer_pnl_v1",
        "label": "Industrial / consumer P&L v1",
        "sector_group": sector,
        "equation": "przychód × marża brutto − koszty sprzedaży − administracja + pozostałe + finansowe → podatek → zysk netto",
    }
    if not approved:
        return {
            "status": "none",
            "template": template,
            "note": "Brak zatwierdzonych założeń operacyjnych do projekcji.",
            "rows": [],
        }
    try:
        defaults = forecast.default_assumptions(income)
    except ValueError as exc:
        return {
            "status": "needs_human",
            "template": template,
            "note": str(exc),
            "rows": [],
        }

    baseline = scenarios.build_scenario_set(inputs, profile).to_dict()
    baseline_by_kind = {row["kind"]: row for row in baseline["scenarios"]}
    rows: list[dict] = []
    for assumption_set in approved:
        projected_assumptions, applied, ignored, applied_keys = _apply_items(
            defaults, assumption_set.get("assumptions") or []
        )
        missing = sorted(_REQUIRED_KEYS - applied_keys)
        result = forecast.compute_forecast(
            projected_assumptions,
            income,
            inputs.shares_outstanding,
            inputs.current_price,
        )
        kind = assumption_set["scenario_kind"]
        baseline_row = baseline_by_kind[kind]
        operating_price, gap = _bridge_price(
            baseline["valuation_multiple"],
            baseline_row["target_multiple"].get("value"),
            result,
            inputs.net_cash,
            inputs.shares_outstanding,
        )
        if missing:
            gap = "Brak wymaganych sterowników: " + ", ".join(missing) + "."
            operating_price = None
        rows.append(
            {
                "scenario_kind": kind,
                "label": assumption_set.get("label", kind),
                "baseline_target_price": baseline_row["target_price"],
                "operating_target_price": operating_price,
                "target_price_delta": (
                    round(operating_price - baseline_row["target_price"], 2)
                    if operating_price is not None and baseline_row["target_price"] is not None
                    else None
                ),
                "operating_upside_pct": _upside(operating_price, inputs.current_price),
                "projected_revenue": result["pnl"]["revenue"],
                "projected_gross_margin_pct": projected_assumptions.gross_margin_pct,
                "projected_net_profit": result["pnl"]["net_profit"],
                "projected_eps": result["forward"]["eps"],
                "projected_ebitda": result["pnl"]["ebitda"],
                "applied": applied,
                "ignored": ignored,
                "missing": missing or ([gap] if gap else []),
            }
        )
    return {
        "status": "applied" if any(row["operating_target_price"] is not None for row in rows) else "needs_human",
        "template": template,
        "note": "Projekcja używa wyłącznie zatwierdzonych wejść i jawnego równania; bazowa wycena pozostaje osobnym punktem odniesienia.",
        "rows": rows,
    }
