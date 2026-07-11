"""Worked examples as structured, honest data — the seed of a future
calibration set (stage TH extensibility; PLAN §10).

A `WorkedCase` is a *partial* snapshot of a real (or synthetic) situation:
whatever inputs we can actually reconstruct, each labelled with where it came
from, plus the read we expect and an explicit list of what could NOT be
reconstructed. `evaluate_case` runs the engine over that partial snapshot and
reports whether the read matches. DGN@20 / SNT content is filled in WP4; the
tuner that fits weights to these cases is a later stage — cases stay pure data
so tuning later means "produce a new profile", not "change engine code".

No I/O here; a case is hand-authored typed data, like a golden-file test row.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services import insights as insights_mod
from app.services import thesis as thesis_mod
from app.services.strategies import base


@dataclass
class WorkedCase:
    """One reconstructed example.

    - `inputs`       : the partial `ThesisInputs` we could rebuild (missing
                       pieces stay at their defaults → weighed as absent).
    - `sources`      : per-field provenance label, keyed by indicator/field id
                       (e.g. {"pe_vs_history": "BiznesRadar C/Z history",
                       "catalyst": "forum digest"}). Honesty, not computation.
    - `expected_read`: what a correct engine should output, e.g.
                       {"entry_quality": "attractive"}.
    - `citation`     : where the expected read / the data is documented.
    - `gaps`         : things that could not be reconstructed (no fabrication).
    - `outcome`      : the case's *documented* result — "hit" (repriced as the
                       thesis expected), "miss" (thesis/catalyst did NOT play
                       out), or "" (entry-pattern exemplar, outcome not
                       quantified in-source). Digit-free label; the survivorship-
                       bias guard (stage SC / WP4b) requires ≥1 "miss" so the
                       corpus is not just the wins.
    """

    ticker: str
    as_of: str
    inputs: thesis_mod.ThesisInputs
    sources: dict[str, str] = field(default_factory=dict)
    expected_read: dict = field(default_factory=dict)
    citation: str = ""
    gaps: list[str] = field(default_factory=list)
    outcome: str = ""  # "hit" | "miss" | "" — see docstring (WP4b bias guard)
    market_ticker: str | None = None
    isin: str | None = None
    market: str | None = None
    identity_source: str | None = None
    anchor_date: str | None = None
    cohort_label: str | None = None


# The worked-case comparison corpus. WP4 seeds it with DGN + SNT (defined at the
# bottom of this module, after `build_case_insights`). `thesis_ai.py` reads it
# via `getattr(cases, "CORPUS", ())` — position in the file does not matter for
# external access, but the entries must be built after their helper, so the
# tuple is assigned at the end. See `_DGN_CASE` / `_SNT_CASE` and their honesty
# notes (both are deliberately THIN — see docs/validation-thesis.md §Historia).


def build_case_insights(
    *,
    size_code: str | None,
    size_label: str | None,
    sector_group: str,
    indicators: list[insights_mod.Insight] | None = None,
    missing: list[insights_mod.MissingData] | None = None,
    sector: str | None = None,
) -> insights_mod.CompanyInsights:
    """Terse constructor for a *partial* CompanyInsights when authoring a case
    by hand — only the indicators the case actually has, plus honest gaps.
    Mirrors what `insights.build_insights` would emit, without needing the raw
    quarterly series."""
    indicators = indicators or []
    missing = missing or []
    company = insights_mod.CompanyInsights(
        size_code=size_code,
        size_label=size_label,
        sector_group=sector_group,
        sector_group_label=insights_mod.SECTOR_GROUP_LABELS.get(sector_group, "Pozostałe"),
        sector=sector,
        key_indicators=list(indicators),
        missing=list(missing),
    )
    selected = len(indicators) + len(missing)
    company.coverage = {
        "available": len(indicators),
        "selected": selected,
        "note": (
            f"Ocena oparta na {len(indicators)} z {selected} wskaźników "
            "(dane odtworzone częściowo)."
        ),
    }
    return company


def evaluate_case(profile: base.StrategyProfile, case: WorkedCase) -> dict:
    """Run the engine on the case's partial snapshot and report the match.

    Runs on whatever input subset exists — absent fields are weighed as absent,
    never invented (the same honesty rule as the live engine)."""
    result = thesis_mod.build_thesis(case.inputs, profile).to_dict()
    expected = dict(case.expected_read)

    matches: dict[str, bool] = {}
    if "entry_quality" in expected:
        matches["entry_quality"] = (
            result["entry_quality"]["code"] == expected["entry_quality"]
        )

    return {
        "ticker": case.ticker,
        "as_of": case.as_of,
        "strategy": {"id": profile.id, "label": profile.label},
        "thesis": result,
        "expected": expected,
        "matches": matches,
        "gaps": list(case.gaps),
        "sources": dict(case.sources),
        "citation": case.citation,
    }


# --------------------------------------------------------- WP4 worked cases
#
# The corpus is recorded HONESTLY (docs/plan-stage-scenarios.md §"WP4b" +
# §"Risks & honesty rules"; docs/strategy-malik.md §"Unverified / open
# questions"). Two honesty invariants hold for EVERY case below:
#
#   1. No reconstructed fundamentals. The local ledger does not contain the
#      immutable entry-era statements Malik acted on; current source access is
#      deep as BR still exposes. So each case's `inputs` are all `MissingData`
#      (routed to "co sprawdzić dalej", never invented) and `expected_read` is
#      the honest achievable read from what we CAN reconstruct point-in-time —
#      `insufficient_data`, NOT the catch's aspirational verdict. The `inputs`
#      therefore carry ZERO numbers — nothing to fabricate there.
#   2. Every NUMBER below is a *sourced provenance label*, living only in the
#      `sources` dict / `citation` / `as_of` / `gaps` (each with a [F]/[M1]/[DGN]
#      anchor), NEVER in the reconstructed fundamentals. These are the real
#      multiples + repricing durations WP4b adds (DGN's "+2500%/5 lat", OPTEX's
#      "C/Z ~12, prognoza <10"); they land in the WP3b/WP4a fabrication
#      allowed-set via `scenarios_ai.collect_corpus_numbers` (reads `sources`/
#      `gaps`/`citation`), so a scenario/valuation may legitimately CITE a
#      comparable — traceable, not fabricated. What is NOT sourced (DGN's
#      "~20 PLN" entry, Suntech's entry multiple) stays an explicit gap, deferred
#      to `scripts/validate_thesis.py <TICKER>` on a machine with egress.
#
# The corpus carries a documented **miss** (Suntech) alongside the wins so it is
# not survivorship-biased (plan §"No survivorship bias").


def _dgn_case() -> WorkedCase:
    """Digital Network (ex-4fun Media) — Malik's textbook catch. The catch is
    VERIFIED as an author-associated historical winner (POS PortalAnaliz 02.2023;
    his own analysis "+2500% w ciągu 5 lat", 2025-09-18 [DGN][AUT]). The source
    does not bind that five-year return to the 2023 flag, and the frequently-
    quoted "~20 PLN entry" is NOT sourced
    and is deliberately absent (docs/strategy-malik.md §Unverified). We can name
    the small-cap edge qualitatively but none of the entry-date fundamentals."""
    company = build_case_insights(
        size_code="small",  # Malik hunts small caps [SB]; DGN was a small cap.
        size_label="Mała spółka",
        sector_group="tech",  # Digital Network — cyfrowa reklama / media (tech).
        sector="Media / reklama cyfrowa",
        indicators=[],  # no entry-era fundamentals are reconstructed point-in-time
        missing=[
            insights_mod.MissingData(
                "pe_vs_history", "C/Z na tle własnej historii",
                "C/Z z daty flagi POS i własna historia C/Z nie są zapisane "
                "punkt-w-czas w lokalnym ledgerze; wymagają wersjonowanego "
                "źródła z epoki."),
            insights_mod.MissingData(
                "gross_margin", "Marża brutto na sprzedaży",
                "Trend marży z epoki wejścia niedostępny — motor tezy Malika, "
                "ale bez danych kwartalnych nie do policzenia."),
            insights_mod.MissingData(
                "revenue_growth", "Dynamika przychodów r/r",
                "Dynamika przychodów sprzed repricingu niedostępna."),
            insights_mod.MissingData(
                "net_cash", "Gotówka netto",
                "Bilans z daty wejścia nieodtworzony — noga marginesu "
                "bezpieczeństwa nieoceniona."),
        ],
    )
    return WorkedCase(
        ticker="DGN",
        as_of="2023-02 (flaga POS PortalAnaliz)",
        inputs=thesis_mod.ThesisInputs(insights=company),
        outcome="hit",  # udokumentowany repricing (patrz `repricing` niżej)
        market_ticker="DIG",
        isin="PL4FNMD00013",
        market="GPW",
        identity_source=(
            "GPW issuer list: DIGITANET / DIG / PL4FNMD00013; Digital Network "
            "issuer reports document the 4fun Media name change."
        ),
        cohort_label="documented_winner",
        sources={
            "size": "Mała spółka — teza o przewadze w małych spółkach [SB]; "
                    "DGN (ex-4fun Media) był małą spółką; dokładna kap. z daty "
                    "wejścia NIEodtworzona",
            "catch": "Dwa oddzielne fakty: POS 02.2023 oraz autorski opis "
                     "historycznego wzrostu „+2500% w ciągu 5 lat” [DGN, "
                     "analiza Malika 2025-09-18]; źródło nie wiąże tej stopy "
                     "zwrotu z datą flagi.",
            "repricing": "Historyczny opis „+2500% w ciągu 5 lat” (około 60 "
                         "miesięcy) z analizy "
                         "Malika [DGN, 2025-09-18]; nie jest to policzony wynik "
                         "od flagi POS 02.2023 i nie trafia do replay return.",
            "sector": "Media / reklama cyfrowa — z opisu spółki [DGN]",
            "catalyst": "Pivot na cyfrową dystrybucję treści — jakościowy, "
                        "nie liczbowy [DGN]",
        },
        expected_read={"entry_quality": "insufficient_data"},
        citation="docs/strategy-malik.md §Filozofia + §Unverified "
                 "(„DGN ~20 PLN” NIEzweryfikowane); anchors [DGN][AUT][SB]",
        gaps=[
            "Fundamenty z daty wejścia (przychody, marża brutto, C/Z, gotówka "
            "netto) nie są odtworzone w lokalnym ledgerze punkt-w-czas.",
            "Cena wejścia „~20 PLN” NIEzweryfikowana w źródłach [spec §Unverified].",
            "Głębokość własnej historii C/Z na BR z tamtego okresu nieznana — "
            "historyczny repricing znamy z opisu, ale nie jest związany z "
            "dokładną kotwicą replay ani mnożnikiem wejścia.",
            "Katalizator (pivot na digital) opisany jakościowo — nie da się go "
            "policzyć z danych (zawsze trafia do „co sprawdzić dalej”).",
            "Aby ocenić mechanicznie: uruchom scripts/validate_thesis.py DGN "
            "tam, gdzie działa egress, i zrekonstruuj fundamenty z epoki.",
        ],
    )


def _snt_case() -> WorkedCase:
    """Synektik — included per WP4 scope but the "early catch" attribution to
    Malik is UNVERIFIED: no primary Malik document ties him to an early SNT call
    (docs/strategy-malik.md §Unverified). SNT appears in the repo only as a
    scraper fixture (kalkulacyjny income layout, skills/scraper-doctor). This
    case therefore asserts NO Malik catch and carries the unverified flag first;
    it is a placeholder seed, not a validated success."""
    company = build_case_insights(
        size_code=None,  # entry-date size unknown; no fundamentals reconstructed
        size_label=None,
        sector_group="biotech_med",  # Synektik — sprzęt/medycyna nuklearna.
        sector="Sprzęt medyczny",
        indicators=[],
        missing=[
            insights_mod.MissingData(
                "pe_vs_history", "C/Z na tle własnej historii",
                "Brak zweryfikowanej kotwicy i danych SNT punkt-w-czas; bieżące "
                "C/Z i jego historia nie są dopuszczalnym zamiennikiem."),
            insights_mod.MissingData(
                "revenue_growth", "Dynamika przychodów r/r",
                "Dynamika przychodów niedostępna — brak danych."),
        ],
    )
    return WorkedCase(
        ticker="SNT",
        as_of="(brak zweryfikowanej daty wejścia)",
        inputs=thesis_mod.ThesisInputs(insights=company),
        market_ticker="SNT",
        market="GPW",
        cohort_label="unverified_placeholder",
        sources={
            "attribution": "UWAGA: brak pierwotnego źródła wiążącego Malika "
                           "z wczesnym wejściem w SNT [spec §Unverified] — "
                           "nie traktować jako catch Malika",
            "fixture": "SNT = historyczny ticker fixture'ów scrapera (układ "
                       "kalkulacyjny) [skills/scraper-doctor/SKILL.md]",
        },
        expected_read={"entry_quality": "insufficient_data"},
        citation="docs/strategy-malik.md §Unverified — „Synektik (SNT) 'early' "
                 "catch — UNVERIFIED”",
        gaps=[
            "Atrybucja do Malika NIEzweryfikowana — pozycja pozostaje jako "
            "nasienie kalibracyjne z jawną flagą, nie jako potwierdzony sukces.",
            "Brak fundamentów SNT związanych ze zweryfikowaną historyczną "
            "kotwicą; bieżący dossier nie potwierdza dawnego case'u.",
            "Aby cokolwiek ocenić: potwierdź atrybucję w źródłach i zrekonstruuj "
            "fundamenty (scripts/validate_thesis.py SNT tam, gdzie działa egress).",
        ],
    )


def _optex_case() -> WorkedCase:
    """OPTEX Systems (USA) — Malik's own textbook *margin-of-safety* entry
    pattern, and the corpus's one source of real ENTRY multiples. He bought it
    at trailing C/Z ~12 with forecast C/Z <10, a rising backlog and after a price
    drop — his "classic" trio (niska wycena + backlog + margines) [F][M1;
    docs/strategy-malik.md zasada 8]. A US (NASDAQ) name held under his harder
    ~20% foreign-stock stop [F; digest §5]. The multiples are sourced; the
    repricing OUTCOME is not quantified in the sources, so this is an
    entry-pattern exemplar (`outcome=""`), not a documented hit — the own-history
    C/Z depth and exact entry date remain gaps in the point-in-time ledger."""
    company = build_case_insights(
        size_code=None,  # entry-date size/cap not reconstructed point-in-time
        size_label=None,
        sector_group="industrial",  # spółka zbrojeniowa (optyka wojskowa)
        sector="Zbrojeniówka / optyka wojskowa (USA)",
        indicators=[],
        missing=[
            insights_mod.MissingData(
                "pe_vs_history", "C/Z na tle własnej historii",
                "Własna historia C/Z OPTEX nie jest odtworzona w lokalnym "
                "ledgerze (spółka spoza GPW) — mnożnik wejścia znamy z opisu autora, "
                "nie z policzonej historii."),
            insights_mod.MissingData(
                "backlog", "Portfel zamówień / backlog",
                "Rosnący backlog to trzecia noga marginesu bezpieczeństwa — "
                "opisany jakościowo przez autora, nie policzony z danych."),
        ],
    )
    return WorkedCase(
        ticker="OPTEX",
        as_of="analiza I.2025 (pierwsza inwestycja zagraniczna autora) [F]",
        inputs=thesis_mod.ThesisInputs(insights=company),
        outcome="",  # wzorzec WEJŚCIA — wynik repricingu nieskwantyfikowany w źródłach
        market_ticker="OPXS",
        market="NASDAQ",
        identity_source=(
            "SEC issuer filings identify Optex Systems Holdings, Inc. common "
            "stock as OPXS on Nasdaq (CIK 0001397016)."
        ),
        cohort_label="control_candidate",
        sources={
            # WP4b: the sourced ENTRY multiples (C/Z ~12 trailing, prognoza <10).
            "valuation": "Kupiona przy C/Z ~12, a wg prognozy zysku C/Z <10 — "
                         "niska wycena bezwzględna i względem prognozy [F][M1]",
            "margin_of_safety": "Klasyczny wzorzec marginesu bezpieczeństwa: "
                                "niska wycena + rosnący backlog + wejście po "
                                "spadku kursu [M1 §3; strategy-malik.md zasada 8]",
            "market": "Spółka z USA (NASDAQ) — twardsza reguła wyjścia ~20% dla "
                      "spółek zagranicznych, inaczej niż na GPW [F; digest §5]",
        },
        expected_read={"entry_quality": "insufficient_data"},
        citation="docs/strategy-malik.md zasada 8 („OPTEX: P/E~12, prog.<10, "
                 "rosnący backlog”) [F][M1]; obs.txt (Portfel IKE, OPTEX Systems)",
        gaps=[
            "Tożsamość została potwierdzona jako OPXS (Nasdaq), ale dokładny "
            "dzień analizy/wejścia i punkt-w-czas historia C/Z nie są zamrożone.",
            "Wynik inwestycji (magnituda i horyzont ewentualnego repricingu) nie "
            "jest w źródłach skwantyfikowany — to przykład WZORCA WEJŚCIA, nie "
            "udokumentowany „hit”.",
            "Backlog i gotówka netto z daty wejścia niepoliczone — trzecia noga "
            "marginesu bezpieczeństwa opisana jakościowo.",
        ],
    )


def _suntech_case() -> WorkedCase:
    """Suntech S.A. (produkty SunVizion / NetPlanner) — the corpus's documented
    **MISS** (survivorship-bias guard, plan §WP4b). Malik's thesis was that big
    new contracts would lift results; they did NOT materialise, Q4 disappointed,
    and he kept holding "na lata" against his own sell-discipline — he names it
    himself as "samousprawiedliwianie błędnych decyzji" (digest §7 [F][M1]). We
    have a sourced average entry price (~2,40 zł [F]) but NOT an entry multiple
    (gap). NOT to be confused with Synektik (SNT) above — a different company."""
    company = build_case_insights(
        size_code="small",  # mało płynna mała spółka [F]
        size_label="Mała spółka",
        sector_group="tech",  # oprogramowanie dla telekomów (SunVizion)
        sector="Oprogramowanie dla telekomów",
        indicators=[],
        missing=[
            insights_mod.MissingData(
                "pe_vs_history", "C/Z na tle własnej historii",
                "Mnożnik wejścia i własna historia C/Z nie są odtworzone "
                "punkt-w-czas — znamy tylko średnią cenę wejścia."),
            insights_mod.MissingData(
                "catalyst", "Katalizator (nowe kontrakty)",
                "Oczekiwany katalizator — duże nowe kontrakty — się nie "
                "zmaterializował; to jakościowy motor tezy, nie liczba."),
        ],
    )
    return WorkedCase(
        ticker="SUNTECH",
        as_of="portfel IKE 2021–2024 (trzymana wbrew własnej dyscyplinie) [F]",
        inputs=thesis_mod.ThesisInputs(insights=company),
        outcome="miss",  # teza/katalizator się nie potwierdziły (bias guard)
        market_ticker="SUN",
        isin="PLSNTCH00012",
        market="NewConnect",
        identity_source=(
            "Suntech Q3 2023 issuer report: ticker SUN, ISIN PLSNTCH00012."
        ),
        anchor_date="2023-03-31",
        cohort_label="documented_failure",
        sources={
            "identity": "Suntech S.A. (SunVizion, NetPlanner) — NIE mylić "
                        "z Synektik (SNT) [F]",
            "entry": "Akcje kupowane ze średnią ceną 2,40 zł [F, Portfel IKE]",
            # The MISS, in the author's own words (digest §7).
            "miss": "Teza (nowe znaczące kontrakty) się nie zmaterializowała, "
                    "wynik Q4 rozczarował, a autor trzymał „na lata” wbrew "
                    "własnym zasadom — sam nazywa to „samousprawiedliwianiem "
                    "błędnych decyzji” [F; M1 §7]",
        },
        expected_read={"entry_quality": "insufficient_data"},
        citation="docs/source-materials/Filozofia_inwestycyjna_OBS_Portfel_IKE.md "
                 "§7 (błędy poznawcze); obs.txt (Portfel IKE), wpisy o Suntechu",
        gaps=[
            "Mnożnik wejścia (C/Z) i własna historia C/Z nie są odtworzone "
            "punkt-w-czas; bieżące dane nie mogą ich zastąpić.",
            "Tożsamość SUN / PLSNTCH00012 jest potwierdzona, ale lokalny ledger "
            "nie ma jeszcze dopuszczalnej historii ceny od kotwicy 2023-03-31.",
            "To „miss” tezy/katalizatora (kontrakty się nie pojawiły) i błąd "
            "dyscypliny (trzymanie wbrew zasadom), nie udokumentowane derating "
            "samego mnożnika — rozróżnienie zachowane świadomie.",
        ],
    )


# `CORPUS` is built LAZILY on first access (PEP 562 module `__getattr__`), not at
# import: constructing a WorkedCase touches `thesis.ThesisInputs`, and
# `app.services.thesis` imports the strategies package — so evaluating the corpus
# at import time forms a circular import (thesis → strategies → cases → thesis,
# mid-init) that broke `import thesis`. Deferring the build to first access (always
# after imports settle) keeps this module import-pure and side-effect-free while
# still exposing `CORPUS` as a plain tuple to `cases.CORPUS` / `getattr(cases,
# "CORPUS", ())`. All four entries evaluate to `insufficient_data` BY CONSTRUCTION
# (0 computable indicators < the profile's min_key_indicators) — the honest
# consequence of the data gaps (docs/validation-thesis.md), not an engine failure.
# The corpus is DGN (hit) + OPTEX (entry-pattern, sourced multiples) + Suntech
# (documented miss — bias guard) + SNT (unverified placeholder); the sourced
# numbers on each land in the WP3b/WP4a fabrication allowed-set via
# `scenarios_ai.collect_corpus_numbers` (WP4b).
_CORPUS_CACHE: tuple[WorkedCase, ...] | None = None


def __getattr__(name: str):
    global _CORPUS_CACHE
    if name == "CORPUS":
        if _CORPUS_CACHE is None:
            _CORPUS_CACHE = (_dgn_case(), _optex_case(), _suntech_case(), _snt_case())
        return _CORPUS_CACHE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
