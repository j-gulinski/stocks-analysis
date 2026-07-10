"""Small template-backed operating bridge for RT4.3c.

This module composes the existing pure next-quarter forecast with approved
case assumptions. It intentionally starts with the industrial/consumer P&L
template because DEC is the real pilot for this workflow; unsupported sectors
stay explicit instead of receiving a generic-looking equation.
"""
from __future__ import annotations

from dataclasses import replace
from math import isfinite

from app.services import forecast, metrics, scenarios
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
_FCF_KEYS = {"capex", "working_capital_change", "fcf_multiple"}
_REQUIRED_PRICED_CHECKS = (
    "representative_archetypes",
    "no_lookahead",
    "math_reconciliation",
    "source_lineage",
)


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


def build_cash_conversion_snapshot(
    cashflow_latest: dict[str, tuple[str, float]] | None,
    income: forecast.IncomeSeries,
    balance_series: dict[str, dict[str, float]] | None = None,
) -> dict:
    """Report cash-conversion readiness without inventing missing bridges."""
    cashflow_latest = cashflow_latest or {}
    operating = cashflow_latest.get("operating_cashflow")
    capex = cashflow_latest.get("capex")
    period = operating[0] if operating else None
    income_row = income.get(period or "", {})
    operating_value = operating[1] if operating else None
    net_profit = income_row.get("net_profit")
    revenue = income_row.get("revenue")
    conversion_ratio = (
        round(operating_value / net_profit, 2)
        if operating_value is not None and net_profit and net_profit > 0
        else None
    )
    capex_intensity = (
        round(abs(capex[1]) / revenue * 100.0, 2)
        if capex is not None and revenue and revenue > 0
        else None
    )
    observed_fcf = (
        round(operating_value + capex[1], 1)
        if operating_value is not None and capex is not None
        else None
    )
    balance_series = balance_series or {}
    working_capital_change = None
    if period and period in balance_series:
        try:
            periods = metrics.sort_periods(balance_series)
            previous_period = next((p for p in reversed(periods) if p < period), None)
        except ValueError:
            previous_period = None
        current = balance_series.get(period, {})
        previous = balance_series.get(previous_period or "", {})
        current_wc = sum(
            current.get(key, 0.0)
            for key in ("receivables_current", "receivables_noncurrent", "inventory")
        )
        previous_wc = sum(
            previous.get(key, 0.0)
            for key in ("receivables_current", "receivables_noncurrent", "inventory")
        )
        if previous_period and any(
            key in current and key in previous
            for key in ("receivables_current", "receivables_noncurrent", "inventory")
        ):
            working_capital_change = round(current_wc - previous_wc, 1)

    gaps: list[str] = []
    if conversion_ratio is None:
        gaps.append("Brak porównywalnego przepływu operacyjnego i zysku netto.")
    if capex_intensity is None:
        gaps.append("Brak capex lub przychodu do policzenia intensywności inwestycji.")
    if working_capital_change is None:
        gaps.append("Zmiana należności i zapasów wymaga jeszcze dwóch porównywalnych bilansów.")
    if operating_value is None:
        status = "needs_human"
    elif conversion_ratio is not None and capex_intensity is not None:
        status = "partial"
    else:
        status = "partial"
    return {
        "status": status,
        "period": period,
        "operating_cashflow": operating_value,
        "net_profit": net_profit,
        "conversion_ratio": conversion_ratio,
        "capex": capex[1] if capex is not None else None,
        "capex_intensity_pct": capex_intensity,
        "observed_fcf": observed_fcf,
        "working_capital_change": working_capital_change,
        "working_capital_cash_effect": (
            round(-working_capital_change, 1) if working_capital_change is not None else None
        ),
        "gaps": gaps,
    }


def _apply_fcf_items(items: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    values: dict = {}
    applied: list[dict] = []
    ignored: list[dict] = []
    for raw in items:
        item = raw if isinstance(raw, dict) else {}
        key = item.get("key")
        value = item.get("value")
        if item.get("provenance") == "model_suggestion":
            ignored.append(_detail(item, applied=False, note="Sugestia modelu wymaga jawnego przyjęcia."))
            continue
        if key not in _FCF_KEYS:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            ignored.append(_detail(item, applied=False, note="Wartość FCF nie jest liczbą."))
            continue
        if key == "fcf_multiple" and value <= 0:
            ignored.append(_detail(item, applied=False, note="Mnożnik FCF musi być dodatni."))
            continue
        if key == "capex" and value > 0:
            ignored.append(_detail(item, applied=False, note="Capex musi zachować ujemny znak przepływu gotówki."))
            continue
        values[key] = float(value)
        applied.append(_detail(item, applied=True, note="Zastosowano wyłącznie w soczewce FCF."))
    return values, applied, ignored


def _build_fcf_lens(rows: list[dict], approved_sets: list[dict], shares: int | None) -> dict:
    """Price FCF only with a complete, explicitly approved FCF input trio."""
    if not rows:
        return {
            "status": "none",
            "method": "FCF/share × jawny mnożnik FCF",
            "note": "Brak zatwierdzonego scenariusza operacyjnego do soczewki FCF.",
            "rows": [],
        }
    by_kind = {row["scenario_kind"]: row for row in rows}
    lens_rows: list[dict] = []
    for assumption_set in approved_sets:
        kind = assumption_set["scenario_kind"]
        source_row = by_kind.get(kind)
        if source_row is None:
            continue
        values, applied, ignored = _apply_fcf_items(assumption_set.get("assumptions") or [])
        missing = sorted(_FCF_KEYS - values.keys())
        projected_fcf = None
        target_price = None
        gap = None
        if missing:
            gap = "Brak jawnych wejść FCF: " + ", ".join(missing) + "."
        elif source_row["projected_net_profit"] is None or source_row["projected_depreciation"] is None:
            gap = "Brak zysku netto lub amortyzacji z projekcji P&L."
        elif shares is None or shares <= 0:
            gap = "Brak liczby akcji do przeliczenia FCF na akcję."
        else:
            projected_fcf = round(
                source_row["projected_net_profit"]
                + source_row["projected_depreciation"]
                - values["working_capital_change"]
                + values["capex"],
                1,
            )
            if projected_fcf <= 0:
                gap = "Projected FCF jest niedodatni — ceny z soczewki FCF nie wyznaczono."
            else:
                target_price = round(
                    projected_fcf * 1000.0 / shares * values["fcf_multiple"], 2
                )
        lens_rows.append(
            {
                "scenario_kind": kind,
                "label": assumption_set.get("label", kind),
                "baseline_target_price": source_row["baseline_target_price"],
                "projected_fcf": projected_fcf,
                "fcf_multiple": values.get("fcf_multiple"),
                "fcf_target_price": target_price,
                "target_price_delta": (
                    round(target_price - source_row["baseline_target_price"], 2)
                    if target_price is not None and source_row["baseline_target_price"] is not None
                    else None
                ),
                "applied": applied,
                "ignored": ignored,
                "missing": missing,
                "gap": gap,
            }
        )
    return {
        "status": "applied" if any(row["fcf_target_price"] is not None for row in lens_rows) else "needs_human",
        "method": "FCF/share × jawny mnożnik FCF",
        "note": "Soczewka FCF jest opcjonalna i nie zmienia bazowej wyceny mnożnikowej.",
        "rows": lens_rows,
    }


def _check_pass(value) -> bool:
    if value is True:
        return True
    if not isinstance(value, dict):
        return False
    if value.get("passed") is True:
        return True
    return value.get("verdict") in {"pass", "passed", "spełnia"}


def evaluate_priced_outcome_gate(
    operating_bridge: dict,
    verification: dict | None,
) -> dict:
    """Allow priced company outcomes only after an independent strict pass."""
    reasons: list[str] = []
    if operating_bridge.get("fcf_lens", {}).get("status") != "applied":
        reasons.append("Soczewka FCF nie ma kompletnego zatwierdzonego wejścia.")
    if not verification:
        reasons.append("Brak zapisanego wyniku verifier_strict dla priced outcomes.")
    else:
        if verification.get("model_role") != "verifier_strict":
            reasons.append("Wynik nie pochodzi z roli verifier_strict.")
        if verification.get("verdict") != "pass":
            reasons.append("Verifier nie potwierdził priced outcomes.")
        checks = verification.get("checks") or {}
        coverage = checks.get("representative_archetypes")
        covered = coverage.get("archetypes") if isinstance(coverage, dict) else coverage
        if not isinstance(covered, list) or not {
            "industrial", "financial", "event-driven"
        }.issubset(set(covered)):
            reasons.append("Brak potwierdzenia trzech reprezentatywnych archetypów.")
        for check_id in ("no_lookahead", "math_reconciliation", "source_lineage"):
            if not _check_pass(checks.get(check_id)):
                reasons.append(f"Verifier nie potwierdził: {check_id}.")
    return {
        "status": "approved" if not reasons else "blocked",
        "reason": " ".join(reasons) if reasons else "Priced outcomes mają niezależne potwierdzenie verifier_strict.",
        "required_checks": list(_REQUIRED_PRICED_CHECKS),
        "verification": verification,
    }


def attach_priced_company_outcomes(scenario_rows: list[dict], fcf_lens: dict) -> list[dict]:
    """Replace the qualitative condition only after the gate has passed."""
    priced_by_kind = {row["scenario_kind"]: row for row in fcf_lens.get("rows", [])}
    output: list[dict] = []
    for row in scenario_rows:
        updated = dict(row)
        priced = priced_by_kind.get(row.get("kind"))
        if priced is None or priced.get("fcf_target_price") is None:
            output.append(updated)
            continue
        delta = priced.get("target_price_delta")
        if delta is None or delta == 0:
            direction, label = "neutral", "Wynik operacyjny zgodny z bazą FCF"
        elif delta > 0:
            direction, label = "positive", "Wynik operacyjny wspiera wycenę FCF"
        else:
            direction, label = "negative", "Wynik operacyjny obniża wycenę FCF"
        updated["company_outcome"] = {
            "direction": direction,
            "label": label,
            "description": (
                f"Soczewka FCF wyznacza {priced['fcf_target_price']:.2f} zł wobec "
                f"{priced['baseline_target_price']:.2f} zł w bazowym mnożniku; "
                "wynik operacyjny jest wyceniony po zatwierdzonych założeniach."
            ),
            "mode": "priced",
        }
        output.append(updated)
    return output


def build_operating_bridge(
    inputs: scenarios.ScenarioInputs,
    income: forecast.IncomeSeries,
    profile: base.StrategyProfile,
    approved_assumption_sets: list[dict] | None = None,
    cashflow_latest: dict[str, tuple[str, float]] | None = None,
    balance_series: dict[str, dict[str, float]] | None = None,
) -> dict:
    """Build explicit operating what-if rows for supported company templates."""
    sector = inputs.thesis_inputs.insights.sector_group
    cash_conversion = build_cash_conversion_snapshot(cashflow_latest, income, balance_series)
    if sector not in _SUPPORTED_SECTORS:
        return {
            "status": "unsupported_template",
            "template": None,
            "note": "Brak zatwierdzonego równania operacyjnego dla tego archetypu spółki.",
            "rows": [],
            "cash_conversion": cash_conversion,
            "fcf_lens": {
                "status": "none",
                "method": "FCF/share × jawny mnożnik FCF",
                "note": "Brak template operacyjnego dla tej spółki.",
                "rows": [],
            },
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
            "cash_conversion": cash_conversion,
            "fcf_lens": {
                "status": "none",
                "method": "FCF/share × jawny mnożnik FCF",
                "note": "Brak zatwierdzonego scenariusza operacyjnego do soczewki FCF.",
                "rows": [],
            },
        }
    try:
        defaults = forecast.default_assumptions(income)
    except ValueError as exc:
        return {
            "status": "needs_human",
            "template": template,
            "note": str(exc),
            "rows": [],
            "cash_conversion": cash_conversion,
            "fcf_lens": {
                "status": "needs_human",
                "method": "FCF/share × jawny mnożnik FCF",
                "note": str(exc),
                "rows": [],
            },
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
        projected_fcf = None
        fcf_gap = None
        if cash_conversion["capex"] is None:
            fcf_gap = "Brak obserwowanego capex do mostu FCF."
        elif cash_conversion["working_capital_cash_effect"] is None:
            fcf_gap = "Brak zmiany kapitału obrotowego do mostu FCF."
        elif projected_assumptions.depreciation is None:
            fcf_gap = "Brak amortyzacji do mostu FCF."
        else:
            # Capex keeps its cash-flow sign (normally negative). Observed
            # operating CF is not adjusted here because it already includes
            # working-capital movement; this is a separate P&L-to-FCF bridge.
            projected_fcf = round(
                result["pnl"]["net_profit"]
                + projected_assumptions.depreciation
                + cash_conversion["working_capital_cash_effect"]
                + cash_conversion["capex"],
                1,
            )
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
                "projected_depreciation": projected_assumptions.depreciation,
                "projected_fcf": projected_fcf,
                "fcf_gap": fcf_gap,
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
        "cash_conversion": cash_conversion,
        "fcf_lens": _build_fcf_lens(rows, approved, inputs.shares_outstanding),
    }
