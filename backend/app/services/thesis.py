"""Investment-thesis engine — composes a per-stock *entry-point* read from the
already-computed dossier, for ANY strategy profile (stage TH / PLAN §10).

What this is:
  - A pure aggregation over `insights.CompanyInsights` + a few dossier scalars
    (`ttm`, `pe_history`, `net_cash`, `latest_forecast`). Like `insights.py`:
    plain functions over plain data, no DB, no framework — a C# mapping service
    over DTOs.
  - Strategy-agnostic. Every weight/threshold/label that is *strategy-specific*
    lives on the `StrategyProfile` (see `strategies/malik.py`); this module
    contains no Malik numbers. Swap the profile → swap the read.

What this is NOT (PLAN non-goals, binding):
  - Not a buy/sell signal. The output is framed as an entrance to human
    analysis, with a standing not-advice disclaimer.
  - Not a re-computation of any indicator. It reads the verdicts and the number
    fragments (`Insight.comment`/`Insight.brief`) that `insights.py` already
    produced, so the UI can never show two different values for one metric.
    A *missing* indicator is weighed as absent and routed to `verify_next` —
    never invented (the `test_thesis.py` fabrication guard enforces this).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services import insights as insights_mod
from app.services.strategies import base

# --- generic output vocabulary (shared by every profile, not strategy data) --
ATTRACTIVE = "attractive"
NEUTRAL = "neutral"
WEAK = "weak"
INSUFFICIENT = "insufficient_data"

# Labels are Polish and deliberately framed as an *analysis entrance*, never a
# buy signal. They describe the engine's verdict codes (same for any strategy),
# so they belong here, not on a profile.
_ENTRY_LABELS = {
    ATTRACTIVE: "Ciekawy punkt wejścia w analizę",
    NEUTRAL: "Neutralny punkt wejścia w analizę",
    WEAK: "Mało zachęcający punkt wejścia",
    INSUFFICIENT: "Za mało danych na tezę",
}

# Fixed not-advice line (PLAN §12). Generic — the same standing disclaimer for
# every strategy.
DISCLAIMER = (
    "To nie jest rekomendacja inwestycyjna ani sygnał kupna/sprzedaży — to "
    "punkt wyjścia do własnej analizy. Decyzję podejmujesz samodzielnie i na "
    "własną odpowiedzialność."
)

_COMPUTED_VERDICTS = ("good", "neutral", "bad")


# --------------------------------------------------------------- data classes


@dataclass
class ThesisInputs:
    """The dossier pieces the engine consumes. All optional except `insights`,
    so `evaluate_case` can run on whatever partial snapshot a WorkedCase has.

    `latest_forecast` is the forecast dict as stored on the dossier (carries a
    `result.forward.pe`), or None when the company has no saved forecast.
    """

    insights: insights_mod.CompanyInsights
    ttm: dict = field(default_factory=dict)
    pe_history: dict = field(default_factory=dict)
    net_cash: dict = field(default_factory=dict)  # {"value": float|None, "note": str}
    latest_forecast: dict | None = None
    prescore: dict | None = None


@dataclass
class ThesisFactor:
    """A weighted pro or con. `text` is copied verbatim from the source
    `Insight` (so its numbers equal the dossier's), `principle` is the strategy
    tag, `weight` comes from the profile."""

    id: str
    text: str
    weight: float
    principle: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "weight": self.weight,
            "principle": self.principle,
        }


@dataclass
class VerifyItem:
    """One "co sprawdzić dalej" entry — a data gap or a human/AI-check gap."""

    id: str
    text: str
    why: str

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "why": self.why}


@dataclass
class EntryQuality:
    code: str
    label: str
    rationale: str

    def to_dict(self) -> dict:
        return {"code": self.code, "label": self.label, "rationale": self.rationale}


@dataclass
class InvestmentThesis:
    entry_quality: EntryQuality
    pros: list[ThesisFactor]
    cons: list[ThesisFactor]
    verify_next: list[VerifyItem]
    thesis_read: str
    disclaimer: str
    valuation_basis: str
    strategy: dict  # {"id": ..., "label": ...}

    def to_dict(self) -> dict:
        return {
            "entry_quality": self.entry_quality.to_dict(),
            "pros": [p.to_dict() for p in self.pros],
            "cons": [c.to_dict() for c in self.cons],
            "verify_next": [v.to_dict() for v in self.verify_next],
            "thesis_read": self.thesis_read,
            "disclaimer": self.disclaimer,
            "valuation_basis": self.valuation_basis,
            "strategy": self.strategy,
        }


# ------------------------------------------------------------------- helpers


def _fmt_pe(value: float) -> str:
    """Render a C/Z value keeping its exact stored precision (no re-rounding),
    Polish decimal comma. Exactness matters: the value must stay identical to
    the input so the fabrication guard sees no invented number."""
    return str(value).replace(".", ",")


def _forward_pe(inputs: ThesisInputs) -> float | None:
    """Forward C/Z from the saved forecast, honouring the dossier path
    `latest_forecast.result.forward.pe`; None when there is no forecast."""
    forecast = inputs.latest_forecast or {}
    result = forecast.get("result") if isinstance(forecast, dict) else None
    if not isinstance(result, dict):
        return None
    forward = result.get("forward")
    if not isinstance(forward, dict):
        return None
    pe = forward.get("pe")
    return pe if isinstance(pe, (int, float)) else None


def _valuation_basis(inputs: ThesisInputs, forward_pe: float | None) -> str:
    """Honest statement of which C/Z the read leans on. Forward preferred; fall
    back to trailing; say plainly when neither exists (spec §Valuation
    doctrine). Numbers here are copied straight from the inputs."""
    ttm_pe = inputs.ttm.get("valuation_pe", inputs.ttm.get("pe"))
    valuation_basis = inputs.ttm.get("valuation_basis")
    if forward_pe is not None:
        return (
            f"Wycena wg C/Z prognozowanego (forward) {_fmt_pe(forward_pe)} — "
            "zgodnie z preferencją strategii (forward przed kroczącym)."
        )
    if ttm_pe is not None:
        basis_note = (
            " działalności kontynuowanej"
            if valuation_basis == "continuing"
            else ""
        )
        return (
            f"Brak prognozy — użyto C/Z kroczącego (TTM){basis_note} "
            f"{_fmt_pe(ttm_pe)}; "
            "strategia woli C/Z prognozowane, gdy pojawi się prognoza "
            "(zbuduj ją w zakładce Prognoza)."
        )
    return (
        "Brak C/Z (spółka nierentowna lub brak kursu) — wyceny nie można "
        "ocenić; oprzyj tezę na pozostałych sygnałach."
    )


def _insight_index(company: insights_mod.CompanyInsights) -> dict[str, insights_mod.Insight]:
    return {ins.id: ins for ins in company.key_indicators}


# ------------------------------------------------------------- entry-quality


@dataclass
class _EntryReasons:
    """Signals the entry rule derives once and reuses for the rationale."""

    computable: int
    valuation_available: bool
    valuation_good: bool
    valuation_bad: bool
    growth_available: bool
    growth_good: bool
    veto_bad: bool
    net_loss: bool
    net_debt: bool
    net_cash_ok: bool
    high_bad_count: int


def _collect_signals(
    profile: base.StrategyProfile,
    idx: dict[str, insights_mod.Insight],
    applicable: list[base.Criterion],
    inputs: ThesisInputs,
) -> _EntryReasons:
    rule = profile.entry_rule

    def verdicts(ids: frozenset[str]) -> list[str]:
        out = []
        for crit in applicable:
            if crit.id in ids and crit.field_id in idx:
                out.append(idx[crit.field_id].verdict)
        return out

    val = verdicts(rule.valuation)
    growth = verdicts(rule.growth)
    veto = verdicts(rule.veto)

    # A "computable" indicator is one insights actually resolved (not unknown),
    # counted only over criteria this strategy applies to the company.
    computable = sum(
        1
        for crit in applicable
        if crit.field_id in idx and idx[crit.field_id].verdict in _COMPUTED_VERDICTS
    )

    high_bad = sum(
        1
        for crit in applicable
        if crit.field_id in idx
        and idx[crit.field_id].verdict == "bad"
        and idx[crit.field_id].importance >= rule.high_importance_level
    )

    net_cash_value = inputs.net_cash.get("value")
    net_profit = inputs.ttm.get("continuing_net_profit")
    if net_profit is None:
        net_profit = inputs.ttm.get("net_profit")

    return _EntryReasons(
        computable=computable,
        valuation_available=bool(val),
        valuation_good=any(v == "good" for v in val),
        # "bad" only when no valuation leg says good (mixed → not a red flag).
        valuation_bad=any(v == "bad" for v in val) and not any(v == "good" for v in val),
        growth_available=bool(growth),
        growth_good=any(v == "good" for v in growth),
        veto_bad=any(v == "bad" for v in veto),
        net_loss=net_profit is not None and net_profit < 0,
        net_debt=net_cash_value is not None and net_cash_value < 0,
        net_cash_ok=net_cash_value is not None and net_cash_value >= 0,
        high_bad_count=high_bad,
    )


def _entry_code(
    profile: base.StrategyProfile, size_code: str | None, sig: _EntryReasons
) -> tuple[str, str]:
    """Apply the profile's EntryQualityRule to the collected signals.

    Order matters and follows the spec §Entry-quality decision rule:
    insufficient_data (honesty first) → weak → attractive → neutral, then the
    small-cap sweet-spot penalty. Returns (code, reason_key); the reason_key
    drives the Polish rationale so the wording never drifts from the logic.
    """
    rule = profile.entry_rule

    # 1. Too little to judge — an honest "don't know" beats a guessed verdict.
    if sig.computable < rule.min_key_indicators:
        return INSUFFICIENT, "insufficient_thin"
    if not sig.valuation_available and not sig.growth_available:
        return INSUFFICIENT, "insufficient_no_signal"

    # 2. Weak — the market already prices the improvement, too many red flags,
    #    or a loss on a levered balance sheet.
    if sig.valuation_bad:
        return WEAK, "weak_valuation"
    if sig.net_loss and sig.net_debt:
        return WEAK, "weak_loss_debt"
    if sig.high_bad_count >= rule.weak_bad_count:
        return WEAK, "weak_bad_factors"

    # 3. Attractive setup — valuation good AND a growth signal AND no net debt,
    #    with no dominant red flag (profit-quality veto).
    dominant_red_flag = sig.veto_bad or (sig.net_loss and sig.net_debt)
    if sig.valuation_good and sig.growth_good and sig.net_cash_ok and not dominant_red_flag:
        # Sweet-spot penalty: outside the strategy's size edge, an otherwise
        # attractive setup is demoted (spec principle 9 — dislikes molochy).
        if size_code in rule.penalised_sizes:
            return NEUTRAL, "size_downgrade"
        return ATTRACTIVE, "attractive"

    return NEUTRAL, "mixed"


# --------------------------------------------------------- prose composition


def _rationale(
    reason_key: str,
    good_briefs: list[str],
    bad_briefs: list[str],
    coverage_note: str | None,
) -> str:
    """Compose the entry-quality rationale from the computed brief fragments
    (each already carries dossier numbers, so nothing is invented here)."""
    joined_good = "; ".join(good_briefs[:3])
    joined_bad = "; ".join(bad_briefs[:3])
    if reason_key == "attractive":
        return (
            "Dobra wycena na tle własnej historii i sygnał wzrostu przy braku "
            f"długu netto ({joined_good}) — bez dominującej czerwonej flagi. "
            "Katalizator wciąż wymaga potwierdzenia (patrz „co sprawdzić dalej”)."
        )
    if reason_key == "size_downgrade":
        return (
            "Zestaw sygnałów byłby atrakcyjny, ale spółka jest poza sweet spotem "
            "strategii — przy dużej spółce przewaga informacyjna jest mniejsza, "
            f"więc ocenę obniżono ({joined_good})."
        )
    if reason_key == "weak_valuation":
        return (
            "Wycena powyżej własnej mediany — rynek prawdopodobnie już wycenia "
            f"poprawę ({joined_bad or joined_good})."
        )
    if reason_key == "weak_loss_debt":
        return (
            "Strata przy zadłużeniu netto — podwyższone ryzyko emisji / presja "
            f"bilansowa ({joined_bad})."
        )
    if reason_key == "weak_bad_factors":
        return f"Przewaga istotnych sygnałów negatywnych ({joined_bad})."
    if reason_key == "insufficient_thin":
        note = f" {coverage_note}" if coverage_note else ""
        return (
            "Za mało policzalnych wskaźników, by odpowiedzialnie ocenić punkt "
            f"wejścia — odśwież dane i sprawdź braki.{note}"
        )
    if reason_key == "insufficient_no_signal":
        return (
            "Brakuje zarówno sygnału wyceny, jak i sygnału wzrostu — bez nich "
            "teza wzrostowa jest nieweryfikowalna z obecnych danych."
        )
    # mixed / neutral
    body = joined_good or joined_bad
    return (
        "Sygnały mieszane — brak wyraźnej przewagi po żadnej stronie"
        + (f" ({body})." if body else ".")
    )


def _thesis_read(
    *,
    profile: base.StrategyProfile,
    company: insights_mod.CompanyInsights,
    entry_label: str,
    good_briefs: list[str],
    bad_briefs: list[str],
    valuation_basis: str,
    lead_check: str | None,
) -> str:
    """A short Polish paragraph weighing pros vs cons. Every number in it comes
    from a brief fragment or the valuation basis (both sourced from inputs);
    the size/sector framing is textual. Ends with the disclaimer (PLAN)."""
    who = company.size_label or "Spółka"
    sentences = [
        f"{who} · {company.sector_group_label}. "
        f"Ocena punktu wejścia wg strategii {profile.label}: {entry_label.lower()}."
    ]
    if good_briefs:
        sentences.append("Za tezą: " + "; ".join(good_briefs[:3]) + ".")
    if bad_briefs:
        sentences.append("Przeciw / ryzyka: " + "; ".join(bad_briefs[:3]) + ".")
    sentences.append(valuation_basis)
    if lead_check:
        sentences.append("Zanim uznasz tezę za potwierdzoną: " + lead_check)
    sentences.append(DISCLAIMER)
    return " ".join(sentences)


# ------------------------------------------------------------------- verify


def _build_verify_next(
    profile: base.StrategyProfile,
    company: insights_mod.CompanyInsights,
    idx: dict[str, insights_mod.Insight],
) -> list[VerifyItem]:
    """Compose "co sprawdzić dalej": data gaps first (from insights.missing),
    then a one-off durability check when profit quality is not clean, then the
    strategy's standing human/AI-check gaps (catalyst, backlog, management, …).
    Missing data is routed here — never fabricated into a pro/con."""
    items: list[VerifyItem] = []
    seen: set[str] = set()

    for miss in company.missing:
        items.append(
            VerifyItem(
                id=miss.id,
                text=f"Uzupełnij lub oszacuj: {miss.name}.",
                why=miss.why,
            )
        )
        seen.add(miss.id)

    one_off = idx.get("one_offs")
    if one_off is not None and one_off.verdict != "good" and "one_offs" not in seen:
        items.append(
            VerifyItem(
                id="one_off_risk",
                text="Zweryfikuj powtarzalność zysku — ile pochodzi ze zdarzeń "
                "jednorazowych.",
                why=one_off.comment,
            )
        )
        seen.add("one_off_risk")

    for gap in profile.verify_gaps:
        if gap.id in seen:
            continue
        items.append(VerifyItem(id=gap.id, text=gap.text, why=gap.why))
        seen.add(gap.id)

    return items


# --------------------------------------------------------------- entry point


def build_thesis(
    inputs: ThesisInputs, profile: base.StrategyProfile
) -> InvestmentThesis:
    """Compose the investment-thesis read for `profile` from `inputs`.

    Strategy-agnostic: every strategy-specific number/label is read from
    `profile`. Recomputes nothing — pros/cons text and the read's numbers are
    the fragments `insights.py` already produced.
    """
    company = inputs.insights
    idx = _insight_index(company)
    applicable = profile.applicable_criteria(company.size_code, company.sector_group)

    # ---- weighted pros / cons from the applicable criteria ------------------
    pros: list[ThesisFactor] = []
    cons: list[ThesisFactor] = []
    good_briefs: list[tuple[float, int, str]] = []  # (weight, importance, brief)
    bad_briefs: list[tuple[float, int, str]] = []

    for crit in applicable:
        ins = idx.get(crit.field_id)
        if ins is None:
            continue  # not computed → handled as a data gap in verify_next
        brief = ins.brief or f"{ins.name} {ins.value}"
        if ins.verdict == crit.strength_verdict():
            pros.append(ThesisFactor(crit.id, ins.comment, crit.weight, crit.principle))
            good_briefs.append((crit.weight, ins.importance, brief))
        elif ins.verdict == crit.weakness_verdict():
            cons.append(ThesisFactor(crit.id, ins.comment, crit.weight, crit.principle))
            bad_briefs.append((crit.weight, ins.importance, brief))

    # ---- sweet-spot size factor (a weighted pro or con, profile-worded) -----
    rule = profile.entry_rule
    size_label = company.size_label or "b/d"
    if company.size_code in rule.sweet_spot_sizes:
        pros.append(
            ThesisFactor(
                "size",
                profile.size_pro_text.format(size=size_label),
                profile.size_weight,
                profile.size_principle,
            )
        )
    elif company.size_code in rule.penalised_sizes:
        cons.append(
            ThesisFactor(
                "size",
                profile.size_con_text.format(size=size_label),
                profile.size_weight,
                profile.size_principle,
            )
        )

    # Order by weight desc; tie-break on importance then id for determinism.
    def _rank(factor: ThesisFactor) -> tuple:
        ins = idx.get(factor.id)
        importance = ins.importance if ins else 0
        return (-factor.weight, -importance, factor.id)

    pros.sort(key=_rank)
    cons.sort(key=_rank)
    good_briefs.sort(key=lambda t: (-t[0], -t[1]))
    bad_briefs.sort(key=lambda t: (-t[0], -t[1]))
    good_brief_texts = [b for _, _, b in good_briefs]
    bad_brief_texts = [b for _, _, b in bad_briefs]

    # ---- entry-quality verdict ---------------------------------------------
    sig = _collect_signals(profile, idx, applicable, inputs)
    code, reason_key = _entry_code(profile, company.size_code, sig)
    coverage_note = (company.coverage or {}).get("note")
    rationale = _rationale(reason_key, good_brief_texts, bad_brief_texts, coverage_note)
    entry_label = _ENTRY_LABELS[code]

    # ---- valuation basis + verify_next + read -------------------------------
    forward_pe = _forward_pe(inputs)
    valuation_basis = _valuation_basis(inputs, forward_pe)
    verify_next = _build_verify_next(profile, company, idx)
    lead_check = verify_next[0].text if verify_next else None
    thesis_read = _thesis_read(
        profile=profile,
        company=company,
        entry_label=entry_label,
        good_briefs=good_brief_texts,
        bad_briefs=bad_brief_texts,
        valuation_basis=valuation_basis,
        lead_check=lead_check,
    )

    return InvestmentThesis(
        entry_quality=EntryQuality(code=code, label=entry_label, rationale=rationale),
        pros=pros,
        cons=cons,
        verify_next=verify_next,
        thesis_read=thesis_read,
        disclaimer=DISCLAIMER,
        valuation_basis=valuation_basis,
        strategy={"id": profile.id, "label": profile.label},
    )


# --------------------------------------------- coverage accessor (stage SC/WP4a)


def count_computable_key_indicators(
    inputs: ThesisInputs, profile: base.StrategyProfile
) -> int:
    """How many of the strategy's applicable key indicators `insights` actually
    resolved (verdict good/neutral/bad, not `unknown`).

    This is the SAME `computable` count the entry-quality gate keys on
    (`_collect_signals`) — exposed as a one-liner so the valuation-confidence
    heuristic (services/valuation_ai.py, stage SC / WP4a) reads coverage from the
    single source of truth instead of re-deriving it, which would risk diverging
    from the entry verdict (PLAN non-goal: no recompute / no divergence).
    """
    company = inputs.insights
    idx = _insight_index(company)
    applicable = profile.applicable_criteria(company.size_code, company.sector_group)
    return _collect_signals(profile, idx, applicable, inputs).computable
