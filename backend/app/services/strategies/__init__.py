"""Investor-strategy profiles as data (PLAN §10 extension point; stage TH).

The thesis engine (`services/thesis.py`) is strategy-agnostic: it reads a
`StrategyProfile` (criteria, weights, thresholds, applicability) and composes a
per-stock read from the already-computed dossier. A new investor's strategy is
therefore a new *data* module here (like `malik.py`) plus registration — no
engine changes. `cases.py` stores worked examples so a future stage can tune
weights against them. Nothing here does I/O; it is plain typed data + tiny
helpers, the way a C# strategy-pattern config object would be.
"""
from app.services.strategies import base, cases, malik

# The registry a future stage grows; today Malik is the only profile.
PROFILES = {malik.MALIK.id: malik.MALIK}

__all__ = ["base", "cases", "malik", "PROFILES"]
