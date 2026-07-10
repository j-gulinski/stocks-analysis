"""Replay saved agent analyses against future outcomes.

This evaluates the quality of Codex/agent outputs saved in `analysis_runs`.
The prediction object comes only from the saved structured output. Future
prices are attached under `outcome`; they never enter `known_inputs` or
`prediction`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentEvaluationObservation,
    AgentEvaluationRun,
    AnalysisRun,
    Company,
    Price,
)

DEFAULT_OUTCOME_WINDOWS = (30, 90, 180, 365)
DEFAULT_POSITIVE_HURDLE_PCT = 10.0
DEFAULT_NEUTRAL_BAND_PCT = 5.0
STRATEGY_VALUATION_DIRECTION = "valuation_direction_v1"


class AgentEvaluationInputError(ValueError):
    """User-correctable agent evaluation request problem."""


def run_agent_evaluation(
    db: Session,
    *,
    strategy: str = STRATEGY_VALUATION_DIRECTION,
    from_date: date | None = None,
    to_date: date | None = None,
    ticker: str | None = None,
    workflow: str | None = None,
    outcome_windows: list[int] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    if strategy != STRATEGY_VALUATION_DIRECTION:
        raise AgentEvaluationInputError(f"Unsupported evaluation strategy '{strategy}'.")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise AgentEvaluationInputError("'from_date' must be on or before 'to_date'.")

    windows = _normalize_windows(outcome_windows)
    analyses = _load_analysis_runs(
        db,
        from_date=from_date,
        to_date=to_date,
        ticker=ticker,
        workflow=workflow,
    )
    parameters = {
        "outcome_windows_days": windows,
        "ticker": ticker.upper() if ticker else None,
        "workflow": workflow,
        "positive_hurdle_pct": DEFAULT_POSITIVE_HURDLE_PCT,
        "neutral_band_pct": DEFAULT_NEUTRAL_BAND_PCT,
        "prediction_policy": (
            "Only structured prediction/potential fields are parsed. Prose-only "
            "direction is marked unknown and needs-human."
        ),
    }

    run = None
    if persist:
        run = AgentEvaluationRun(
            strategy=strategy,
            from_date=from_date,
            to_date=to_date,
            status="running",
            model_role="deterministic",
            model="python",
            parameters=parameters,
            summary={},
            verification_status="pending",
        )
        db.add(run)
        db.flush()

    observations: list[dict[str, Any]] = []
    for analysis, company in analyses:
        observation = _build_observation(db, analysis, company, windows)
        observations.append(observation)
        if run is not None:
            db.add(
                AgentEvaluationObservation(
                    evaluation_run_id=run.id,
                    analysis_run_id=analysis.id,
                    company_id=company.id,
                    as_of_date=analysis.created_at.date(),
                    known_inputs=_json_safe(observation["known_inputs"]),
                    prediction=_json_safe(observation["prediction"]),
                    outcome=_json_safe(observation["outcome"]),
                    score=_json_safe(observation["score"]),
                )
            )

    summary = _summarize(observations)
    verification_status = (
        "needs-human"
        if summary["observation_count"] == 0
        or summary["data_quality"]["unknown_predictions"] > 0
        or summary["data_quality"]["missing_price_windows"] > 0
        else "pending"
    )
    if run is not None:
        run.status = "completed"
        run.summary = _json_safe(summary)
        run.verification_status = verification_status
        db.commit()

    return {
        "ok": True,
        "workflow": "stock-agent-evaluation",
        "status": "completed",
        "evaluation_run_id": run.id if run is not None else None,
        "strategy": strategy,
        "from_date": from_date,
        "to_date": to_date,
        "parameters": parameters,
        "summary": summary,
        "verification_status": verification_status,
        "observations": observations,
    }


def _normalize_windows(windows: list[int] | None) -> list[int]:
    values = list(DEFAULT_OUTCOME_WINDOWS if windows is None else windows)
    if not values:
        raise AgentEvaluationInputError("At least one outcome window is required.")
    normalized = sorted({int(value) for value in values})
    if normalized[0] <= 0 or normalized[-1] > 3650:
        raise AgentEvaluationInputError("Outcome windows must be between 1 and 3650 days.")
    return normalized


def _load_analysis_runs(
    db: Session,
    *,
    from_date: date | None,
    to_date: date | None,
    ticker: str | None,
    workflow: str | None,
) -> list[tuple[AnalysisRun, Company]]:
    stmt = (
        select(AnalysisRun, Company)
        .join(Company, AnalysisRun.company_id == Company.id)
        .order_by(AnalysisRun.created_at.asc(), AnalysisRun.id.asc())
    )
    if ticker:
        stmt = stmt.where(Company.ticker == ticker.upper())
    if workflow:
        stmt = stmt.where(AnalysisRun.workflow == workflow)
    rows = list(db.execute(stmt))
    filtered = []
    for analysis, company in rows:
        created = analysis.created_at.date()
        if from_date is not None and created < from_date:
            continue
        if to_date is not None and created > to_date:
            continue
        filtered.append((analysis, company))
    return filtered


def _build_observation(
    db: Session,
    analysis: AnalysisRun,
    company: Company,
    windows: list[int],
) -> dict[str, Any]:
    as_of = analysis.created_at.date()
    prediction = _extract_prediction(analysis.output or {})
    outcome = _outcome_windows(db, company.id, as_of, windows)
    score = _score_prediction(prediction, outcome)
    return {
        "ticker": company.ticker,
        "analysis_run_id": analysis.id,
        "as_of_date": as_of,
        "known_inputs": {
            "ticker": company.ticker,
            "analysis_run_id": analysis.id,
            "agent_run_id": analysis.agent_run_id,
            "workflow": analysis.workflow,
            "model_role": analysis.model_role,
            "model": analysis.model,
            "created_at": analysis.created_at,
            "input_snapshot_present": bool(analysis.input_snapshot),
            "input_snapshot_keys": sorted((analysis.input_snapshot or {}).keys()),
            "output_keys": sorted((analysis.output or {}).keys()),
        },
        "prediction": prediction,
        "outcome": outcome,
        "score": score,
    }


def _extract_prediction(output: dict[str, Any]) -> dict[str, Any]:
    explicit = _text_path(output, ("prediction", "direction"))
    potential = _number_path(output, ("potential", "value_pct"))
    if potential is None:
        potential = _number_path(output, ("valuation", "potential", "value_pct"))
    if potential is None:
        potential = _number_path(output, ("expected_upside_pct",))
    if potential is None:
        potential = _number_path(output, ("upside_pct",))

    if explicit in {"positive", "neutral", "negative", "unknown"}:
        direction = explicit
        source = "prediction.direction"
    elif potential is not None:
        direction = _direction_from_potential(potential)
        source = "structured_potential"
    else:
        direction = "unknown"
        source = "missing_structured_prediction"

    confidence = (
        _text_path(output, ("confidence", "level"))
        or _text_path(output, ("valuation", "confidence", "level"))
        or _text_path(output, ("confidence",))
        or "unknown"
    )
    return {
        "direction": direction,
        "source": source,
        "potential_pct": potential,
        "confidence": confidence,
        "needs_human": direction == "unknown" or source == "missing_structured_prediction",
        "drivers": _list_path(output, ("drivers",)) or _list_path(output, ("watch_items",)),
        "risks": _list_path(output, ("risks",)) or _list_path(output, ("red_flags",)),
        "verify_next": _list_path(output, ("verify_next",)),
    }


def _direction_from_potential(value: float) -> str:
    if value >= DEFAULT_POSITIVE_HURDLE_PCT:
        return "positive"
    if value <= -DEFAULT_POSITIVE_HURDLE_PCT:
        return "negative"
    if abs(value) <= DEFAULT_NEUTRAL_BAND_PCT:
        return "neutral"
    return "unknown"


def _score_prediction(prediction: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    direction = prediction["direction"]
    windows = outcome["windows"]
    scored: dict[str, Any] = {}
    hit_count = 0
    scored_count = 0
    missing_count = 0
    for window, row in windows.items():
        return_pct = row.get("return_pct")
        if return_pct is None:
            scored[window] = {"status": "missing_outcome", "hit": None}
            missing_count += 1
            continue
        if direction == "unknown":
            scored[window] = {"status": "not_scored", "hit": None}
            continue
        hit = _is_hit(direction, float(return_pct))
        scored[window] = {"status": "scored", "hit": hit}
        scored_count += 1
        if hit:
            hit_count += 1
    return {
        "windows": scored,
        "scored_windows": scored_count,
        "hit_windows": hit_count,
        "missing_windows": missing_count,
        "hit_rate_pct": round(hit_count / scored_count * 100, 2) if scored_count else None,
    }


def _is_hit(direction: str, return_pct: float) -> bool:
    if direction == "positive":
        return return_pct >= DEFAULT_POSITIVE_HURDLE_PCT
    if direction == "negative":
        return return_pct <= -DEFAULT_POSITIVE_HURDLE_PCT
    if direction == "neutral":
        return abs(return_pct) <= DEFAULT_NEUTRAL_BAND_PCT
    return False


def _outcome_windows(
    db: Session,
    company_id: int,
    as_of: date,
    windows: list[int],
) -> dict[str, Any]:
    base = _price_on_or_before(db, company_id, as_of)
    result: dict[str, Any] = {
        "base_price": float(base.close) if base else None,
        "base_price_date": base.date if base else None,
        "windows": {},
    }
    for days in windows:
        target = as_of + timedelta(days=days)
        future = _price_on_or_after(db, company_id, target)
        if base is None or future is None or float(base.close) == 0:
            result["windows"][str(days)] = {
                "target_date": target,
                "price_date": future.date if future else None,
                "price": float(future.close) if future else None,
                "return_pct": None,
            }
            continue
        future_close = float(future.close)
        base_close = float(base.close)
        result["windows"][str(days)] = {
            "target_date": target,
            "price_date": future.date,
            "price": future_close,
            "return_pct": round((future_close / base_close - 1) * 100, 2),
        }
    return result


def _price_on_or_before(db: Session, company_id: int, value: date) -> Price | None:
    return db.scalar(
        select(Price)
        .where(Price.company_id == company_id, Price.date <= value)
        .order_by(Price.date.desc())
        .limit(1)
    )


def _price_on_or_after(db: Session, company_id: int, value: date) -> Price | None:
    return db.scalar(
        select(Price)
        .where(Price.company_id == company_id, Price.date >= value)
        .order_by(Price.date.asc())
        .limit(1)
    )


def _summarize(observations: list[dict[str, Any]]) -> dict[str, Any]:
    prediction_counts: dict[str, int] = {}
    scored = 0
    hits = 0
    missing = 0
    unknown = 0
    for observation in observations:
        direction = observation["prediction"]["direction"]
        prediction_counts[direction] = prediction_counts.get(direction, 0) + 1
        if direction == "unknown":
            unknown += 1
        score = observation["score"]
        scored += score["scored_windows"]
        hits += score["hit_windows"]
        missing += score["missing_windows"]
    warnings = _warnings(unknown, missing)
    if not observations:
        warnings.insert(0, "No saved analysis runs matched the evaluation filters; no evidence was scored.")
    return {
        "observation_count": len(observations),
        "prediction_counts": prediction_counts,
        "scored_windows": scored,
        "hit_windows": hits,
        "hit_rate_pct": round(hits / scored * 100, 2) if scored else None,
        "data_quality": {
            "unknown_predictions": unknown,
            "missing_price_windows": missing,
            "warnings": warnings,
        },
    }


def _warnings(unknown_predictions: int, missing_price_windows: int) -> list[str]:
    warnings = []
    if unknown_predictions:
        warnings.append(
            "Some agent outputs lack structured direction/potential fields; prose is not inferred."
        )
    if missing_price_windows:
        warnings.append("Some future price windows are missing from stored price history.")
    return warnings


def _text_path(payload: dict[str, Any], path: tuple[str, ...]) -> str | None:
    value: Any = payload
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value if isinstance(value, str) and value.strip() else None


def _number_path(payload: dict[str, Any], path: tuple[str, ...]) -> float | None:
    value: Any = payload
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _list_path(payload: dict[str, Any], path: tuple[str, ...]) -> list[Any]:
    value: Any = payload
    for part in path:
        if not isinstance(value, dict):
            return []
        value = value.get(part)
    return value if isinstance(value, list) else []


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value
