"""The common strategy interface — strategy = data, engine = generic.

A `StrategyProfile` is a bundle of `Criterion` rows (what to weigh, how much,
for which companies) plus an `EntryQualityRule` (how the weighed signals combine
into an entry-point verdict) and a list of `VerifyGap`s (things the strategy
cares about that the app cannot compute — routed to "what to check next").

Everything here is **pure immutable data + trivial helpers**. No numbers are
computed and no indicators are read here; that is the engine's job
(`services/thesis.py`). Think of it as a C# record/config object consumed by a
strategy-pattern scorer: swapping the object swaps the behaviour, no `if
strategy == "malik"` branches anywhere.

Design decision (stage TH): the engine consumes the *verdicts* already produced
by `insights.py` (good/neutral/bad per indicator). So a `Criterion` does NOT
carry raw-number thresholds like "C/Z < 0.85× median" — those live once in
`insights.py` and must not be duplicated (would risk divergence, PLAN non-goal).
A `Criterion` carries how much a strategy *weighs* an indicator and which
verdict counts as a strength; the `EntryQualityRule` names which criteria act as
the valuation / growth / veto signals for the entry gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- direction: how an insights verdict maps to a strength/weakness ----------
# Most criteria are "good = strength". A contrarian strategy could invert one
# (e.g. treat an expensive multiple as a momentum strength); the toy profile in
# the tests exercises this so `direction` is a real lever, not decoration.
GOOD_IS_STRENGTH = "good_is_strength"
BAD_IS_STRENGTH = "bad_is_strength"


@dataclass(frozen=True)
class Criterion:
    """One thing a strategy weighs, mapped to a computed dossier indicator.

    - `id`         : criterion identity (stable, e.g. "gross_margin").
    - `principle`  : the investor-principle tag shown next to the pro/con
                     (Polish, cited to the strategy's spec doc in the profile).
    - `selector`   : which `insights.Insight.id` to read the verdict from
                     (defaults to `id`; kept separate so a criterion can point
                     at a differently-named dossier field).
    - `weight`     : relative importance — orders pros/cons and weighs the read.
    - `direction`  : GOOD_IS_STRENGTH (default) or BAD_IS_STRENGTH.
    - `applies_to_sizes`/`applies_to_sectors`: `None` = every company; otherwise
                     the size codes / sector groups (metrics/insights taxonomy)
                     this criterion is relevant for. Applicability is a first-
                     class strategy lever, so a profile can say "this only
                     matters for banks" without any engine change.
    - `thresholds` : optional per-criterion tunables for future profiles /
                     the calibration stage; unused by the verdict-based engine
                     today, kept so the data shape is ready (PLAN §10).
    """

    id: str
    principle: str
    weight: float
    selector: str = ""
    direction: str = GOOD_IS_STRENGTH
    applies_to_sizes: frozenset[str] | None = None
    applies_to_sectors: frozenset[str] | None = None
    thresholds: dict = field(default_factory=dict)

    @property
    def field_id(self) -> str:
        """The insights indicator this criterion reads."""
        return self.selector or self.id

    def applies(self, size_code: str | None, sector_group: str | None) -> bool:
        if self.applies_to_sizes is not None and size_code not in self.applies_to_sizes:
            return False
        if (
            self.applies_to_sectors is not None
            and sector_group not in self.applies_to_sectors
        ):
            return False
        return True

    def strength_verdict(self) -> str:
        """Which insights verdict makes this criterion a *pro*."""
        return "good" if self.direction == GOOD_IS_STRENGTH else "bad"

    def weakness_verdict(self) -> str:
        """Which insights verdict makes this criterion a *con*."""
        return "bad" if self.direction == GOOD_IS_STRENGTH else "good"


@dataclass(frozen=True)
class EntryQualityRule:
    """Parameters that turn the weighed signals into an entry-point verdict.

    The engine (`thesis.py`) is the only place that knows the *shape* of the
    rule (attractive/neutral/weak/insufficient_data); this object supplies the
    strategy-specific *numbers and signal groupings* it plugs in, so no
    threshold ever lives in the engine.

    - `valuation`/`growth`/`veto` : sets of criterion ids acting as the
      valuation signal, the growth signals, and the quality veto for the gate.
    - `min_key_indicators` : below this many computable indicators the read is
      `insufficient_data` (honesty over a guessed verdict).
    - `weak_bad_count`     : this many high-importance bad factors ⇒ `weak`.
    - `high_importance_level` : the `Insight.importance` counted as "high".
    - `sweet_spot_sizes`   : size codes the strategy actively prefers (adds a
      pro + may support `attractive`).
    - `penalised_sizes`    : size codes outside the strategy's edge (adds a con
      and blocks `attractive` — the sweet-spot penalty).
    """

    valuation: frozenset[str]
    growth: frozenset[str]
    veto: frozenset[str]
    min_key_indicators: int
    weak_bad_count: int
    high_importance_level: int
    sweet_spot_sizes: frozenset[str]
    penalised_sizes: frozenset[str]


@dataclass(frozen=True)
class VerifyGap:
    """A strategy concern the app cannot compute — always routed to
    "what to check next". Text is deliberately digit-free (qualitative)."""

    id: str
    text: str  # Polish call to action
    why: str  # Polish: why this strategy cares (cited in the profile comments)


@dataclass(frozen=True)
class StrategyProfile:
    """A whole investor strategy expressed as data.

    `size_pro_text`/`size_con_text` are the profile's own wording for the
    sweet-spot factor (kept here, not in the engine, so the framing stays
    strategy-specific); `{size}` is filled with the company's size label
    (e.g. "Mała spółka"). Do NOT hardcode that class word in the template too —
    it would render duplicated as "Mała spółka (Mała spółka)".
    """

    id: str
    label: str
    spec_ref: str  # documentation this profile is cited against
    criteria: tuple[Criterion, ...]
    entry_rule: EntryQualityRule
    verify_gaps: tuple[VerifyGap, ...]
    size_weight: float
    size_pro_text: str
    size_con_text: str
    size_principle: str  # principle tag shown on the sweet-spot pro/con

    def applicable_criteria(
        self, size_code: str | None, sector_group: str | None
    ) -> list[Criterion]:
        return [c for c in self.criteria if c.applies(size_code, sector_group)]

    def get(self, criterion_id: str) -> Criterion | None:
        return next((c for c in self.criteria if c.id == criterion_id), None)
