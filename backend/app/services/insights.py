"""Dynamic per-company analysis: which indicators matter for THIS stock.

A bank is judged by ROE and C/WK, a biotech by cash runway, an industrial by
gross-margin trend — one fixed checklist can't serve them all. This module
picks the indicator set from the company's sector group and size class, gives
each a good/bad verdict with a Polish one-liner, and — crucially — stays
honest about gaps: a missing number is reported as missing (with why it would
matter), never faked. The summary weighs pros and cons from the data that WAS
fetched.

Pure functions over plain dicts/dataclasses, like metrics.py — no DB, no
framework. Consumed by dossier.py; rendered on the stock page; later reused
as structured input for the AI analysis (Phase 5).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.services import metrics

# --------------------------------------------------------------- sector map

# BR "Branża" strings → coarse groups the playbook understands. Substring
# match on the lowercased sector; first hit wins, "other" is the fallback.
SECTOR_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("finance", (
        "bank", "ubezpiecz", "windykac", "faktoring", "leasing", "kapitałowy",
        "wierzytelno", "dom maklerski", "fundusz",
    )),
    ("biotech_med", (
        "biotechnolog", "farmac", "medyc", "ochrona zdrowia", "szpital",
        "sprzęt medyczny", "wyroby medyczne",
    )),
    ("tech", (
        "informatyk", "gry", "gaming", "oprogramowanie", "telekomunikac",
        "internet", "media", "e-commerce", "nowe technologie", "fotonika",
    )),
    ("energy", (
        "energet", "paliw", "górnic", "wydobyc", "surowc", "gaz", "ropa",
        "węgiel", "fotowoltaik", "oze",
    )),
    ("realestate", ("deweloper", "nieruchomo", "budownictwo mieszkaniowe")),
    ("consumer", (
        "handel", "detaliczn", "hurtow", "spożywcz", "odzież", "obuwie",
        "kosmetyk", "meble", "dystrybuc", "fmcg", "restaurac", "turystyk",
    )),
    ("industrial", (
        "przemysł", "produkc", "budownictw", "budowlan", "chemi", "motoryzac",
        "maszyn", "elektromaszynow", "metalow", "tworzyw", "drzewn",
        "papiernic", "elektrotechnic", "recykling", "transport", "logistyk",
        "opakowa",
    )),
)

SECTOR_GROUP_LABELS = {
    "finance": "Finanse",
    "biotech_med": "Biotech / medycyna",
    "tech": "Technologie",
    "energy": "Energetyka / surowce",
    "realestate": "Deweloperzy / nieruchomości",
    "consumer": "Handel / konsument",
    "industrial": "Przemysł / produkcja",
    "other": "Pozostałe",
}


def classify_sector(sector: str | None) -> str:
    if not sector:
        return "other"
    lowered = sector.lower()
    for group, needles in SECTOR_GROUPS:
        if any(needle in lowered for needle in needles):
            return group
    return "other"


# ------------------------------------------------------------- data classes

@dataclass
class Insight:
    id: str
    name: str  # Polish, user-facing
    value: str  # formatted value, e.g. "34,2%" / "b/d"
    verdict: str  # good | neutral | bad | unknown
    comment: str  # Polish one-liner: why this matters for THIS company
    importance: int  # 3 = kluczowy, 2 = ważny, 1 = kontekst
    # short numeric fragment for the summary ("EV/EBITDA 5,8", "ROE 4,3%") —
    # the summary is COMPOSED from these computed values, never from canned
    # prose, so it always reflects the metrics that actually exist.
    brief: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("brief", None)  # summary-internal, not part of the API shape
        return data


@dataclass
class MissingData:
    id: str
    name: str
    why: str  # Polish: why it would matter here + where it usually comes from

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompanyInsights:
    size_code: str | None
    size_label: str | None
    sector_group: str
    sector_group_label: str
    sector: str | None
    key_indicators: list[Insight] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    missing: list[MissingData] = field(default_factory=list)
    data_notes: list[str] = field(default_factory=list)
    coverage: dict | None = None
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "size_code": self.size_code,
            "size_label": self.size_label,
            "sector_group": self.sector_group,
            "sector_group_label": self.sector_group_label,
            "sector": self.sector,
            "key_indicators": [i.to_dict() for i in self.key_indicators],
            "strengths": self.strengths,
            "concerns": self.concerns,
            "missing": [m.to_dict() for m in self.missing],
            "data_notes": self.data_notes,
            "coverage": self.coverage,
            "summary": self.summary,
        }


# ---------------------------------------------------------------- helpers

def _fmt_pct(value: float | None) -> str:
    return "b/d" if value is None else f"{value:.1f}%".replace(".", ",")


def _signed_pct(value: float) -> str:
    return f"{value:+.1f}%".replace(".", ",")


def _fmt_x(value: float | None) -> str:
    return "b/d" if value is None else f"{value:.1f}".replace(".", ",")


def _fmt_mln(value_tys: float | None) -> str:
    """tys. PLN → 'X mln zł' display."""
    if value_tys is None:
        return "b/d"
    return f"{value_tys / 1000.0:,.0f} mln zł".replace(",", " ")


def _last_known(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _trend(values: list[float | None], recent: int = 2, base: int = 4) -> float | None:
    """Mean of last `recent` known values minus mean of the `base` before —
    the same idea the prescore uses for margin trend (in percentage points)."""
    known = [v for v in values if v is not None]
    if len(known) < recent + base:
        return None
    recent_avg = sum(known[-recent:]) / recent
    base_avg = sum(known[-recent - base:-recent]) / base
    return round(recent_avg - base_avg, 1)


# ---------------------------------------------------------------- playbook

# Which indicator specs matter per sector group, most important first.
# Common core is prepended/appended around the group-specific picks.
_GROUP_PLAYBOOK: dict[str, list[str]] = {
    "finance": ["roe", "cwk", "pe_vs_history", "dividend", "net_profit_trend"],
    "biotech_med": ["cash_runway", "revenue_growth", "one_offs", "gross_margin",
                    "pe_vs_history"],
    "tech": ["revenue_growth", "gross_margin", "net_margin", "net_cash",
             "pe_vs_history", "one_offs"],
    "energy": ["ev_ebitda", "debt_load", "dividend", "one_offs", "pe_vs_history"],
    "realestate": ["cwk", "debt_load", "dividend", "revenue_growth",
                   "pe_vs_history"],
    "consumer": ["revenue_growth", "gross_margin", "net_margin", "liquidity",
                 "debt_load", "pe_vs_history"],
    "industrial": ["gross_margin", "revenue_growth", "operating_leverage",
                   "debt_load", "one_offs", "pe_vs_history"],
    "other": ["revenue_growth", "gross_margin", "net_margin", "net_cash",
              "one_offs", "pe_vs_history"],
}

_IMPORTANCE = {0: 3, 1: 3, 2: 2, 3: 2, 4: 2}  # position in playbook → weight


def build_insights(
    *,
    sector: str | None,
    quarters: list[dict],
    ttm: dict,
    pe_history: dict,
    net_cash_value: float | None,
    balance_latest: dict[str, float],
    indicators_latest: dict[str, tuple[str, float]],
    dividend_years: list[int],
    dividend_yield_latest: float | None,
    price_age_days: int | None,
) -> CompanyInsights:
    """Assemble the dynamic analysis. All inputs are plain dicts as produced
    by dossier.py (QuarterMetrics.to_dict() etc.), so this stays testable
    without a DB and reusable by the AI layer."""
    group = classify_sector(sector)
    size_code, size_label = metrics.classify_size(ttm.get("market_cap"))

    result = CompanyInsights(
        size_code=size_code,
        size_label=size_label,
        sector_group=group,
        sector_group_label=SECTOR_GROUP_LABELS[group],
        sector=sector,
    )

    # ---- data-quality notes (honesty first) --------------------------------
    if price_age_days is not None and price_age_days > 7:
        result.data_notes.append(
            f"Kurs sprzed {price_age_days} dni — kapitalizacja i C/Z mogą być "
            "nieaktualne."
        )
    if ttm.get("market_cap_source") == "derived":
        result.data_notes.append(
            "Kapitalizacja liczona z kursu × liczby akcji (brak wartości "
            "raportowanej) — traktuj jako przybliżenie."
        )
    check_pct = ttm.get("market_cap_check_pct")
    if check_pct is not None and check_pct > 20:
        result.data_notes.append(
            f"Kapitalizacja raportowana i liczona różnią się o {check_pct:.0f}% "
            "— prawdopodobnie nieświeży kurs lub liczba akcji; ufaj raportowanej."
        )
    if group == "finance":
        result.data_notes.append(
            "Spółka finansowa: układ sprawozdania różni się od spółek "
            "produkcyjnych (brak klasycznych przychodów/marż) — ocena opiera "
            "się na ROE, C/WK i zysku netto."
        )

    # ---- spec evaluation ----------------------------------------------------
    revenue_yoy = [q.get("revenue_yoy_pct") for q in quarters]
    gross_margins = [q.get("gross_margin_pct") for q in quarters]
    net_margins = [q.get("net_margin_pct") for q in quarters]
    latest_quarter = quarters[-1] if quarters else {}

    def latest_indicator(code: str) -> float | None:
        entry = indicators_latest.get(code)
        return entry[1] if entry else None

    evaluated: dict[str, Insight | MissingData] = {}

    def spec_revenue_growth() -> Insight | MissingData:
        known = [v for v in revenue_yoy if v is not None]
        if not known:
            return MissingData(
                "revenue_growth", "Dynamika przychodów r/r",
                "Brak porównywalnych przychodów kwartalnych (r/r) — to "
                "podstawowy sygnał, czy biznes rośnie. Źródło: rachunek "
                "zysków i strat (BiznesRadar).",
            )
        recent = known[-2:]
        avg = sum(recent) / len(recent)
        if avg > 10:
            verdict, comment = "good", (
                f"Przychody rosną śr. {_fmt_pct(avg)} r/r w ostatnich "
                f"kwartałach — {'kluczowe dla wyceny spółki wzrostowej' if group in ('tech', 'biotech_med') else 'zdrowa dynamika'}."
            )
        elif avg >= 0:
            verdict, comment = "neutral", (
                f"Przychody mniej więcej płaskie ({_fmt_pct(avg)} r/r) — "
                "wzrost zysku musiałby przyjść z marż."
            )
        else:
            verdict, comment = "bad", (
                f"Przychody spadają ({_fmt_pct(avg)} r/r) — pierwszy sygnał "
                "ostrzegawczy strategii; sprawdź przyczynę w raporcie."
            )
        return Insight("revenue_growth", "Dynamika przychodów r/r",
                       _fmt_pct(avg), verdict, comment,
                       3 if group in ("tech", "biotech_med", "consumer") else 2,
                       brief=f"przychody {_signed_pct(avg)} r/r")

    def spec_gross_margin() -> Insight | MissingData:
        trend = _trend(gross_margins)
        last = _last_known(gross_margins)
        if last is None:
            return MissingData(
                "gross_margin", "Marża brutto na sprzedaży",
                "Nie da się policzyć marży brutto — spółka raportuje w "
                "układzie porównawczym (brak kosztu wytworzenia). Oceń marżę "
                "operacyjną/netto zamiast niej; dokładna marża brutto bywa w "
                "notach raportu.",
            )
        value = _fmt_pct(last)
        if trend is None:
            return Insight(
                "gross_margin", "Marża brutto na sprzedaży", value, "neutral",
                f"Marża brutto {value}; za mało kwartałów na ocenę trendu "
                "(potrzeba 6).", 3 if group == "industrial" else 2,
                brief=f"marża brutto {value}",
            )
        if trend > 0.5:
            verdict, comment = "good", (
                f"Marża brutto rośnie ({trend:+.1f} p.p. vs 4 wcześniejsze "
                "kwartały) — u Malika to główny motor tezy inwestycyjnej."
            )
        elif trend < -1.5:
            verdict, comment = "bad", (
                f"Marża brutto spada ({trend:+.1f} p.p.) — sprawdź ceny "
                "surowców/konkurencję zanim uznasz zysk za powtarzalny."
            )
        else:
            verdict, comment = "neutral", (
                f"Marża brutto stabilna ({trend:+.1f} p.p.) — ani motor, ani "
                "hamulec."
            )
        trend_txt = f"{trend:+.1f}".replace(".", ",")
        return Insight("gross_margin", "Marża brutto na sprzedaży", value,
                       verdict, comment, 3 if group == "industrial" else 2,
                       brief=f"marża brutto {value} ({trend_txt} p.p.)")

    def spec_net_margin() -> Insight | MissingData:
        last = _last_known(net_margins)
        if last is None:
            return MissingData(
                "net_margin", "Marża netto",
                "Brak zysku netto lub przychodów w danych kwartalnych — "
                "źródło: rachunek zysków i strat.",
            )
        threshold_good = {"tech": 15.0, "consumer": 4.0}.get(group, 8.0)
        trend = _trend(net_margins)
        if last >= threshold_good and (trend is None or trend >= -1):
            verdict = "good"
            comment = (
                f"Marża netto {_fmt_pct(last)} — solidna jak na "
                f"{SECTOR_GROUP_LABELS[group].lower()}."
            )
        elif last <= 0:
            verdict = "bad"
            comment = "Spółka na poziomie netto jest stratna w ostatnim kwartale."
        else:
            verdict = "neutral"
            comment = (
                f"Marża netto {_fmt_pct(last)} — przeciętna; zwróć uwagę na "
                "trend i one-offy."
            )
        return Insight("net_margin", "Marża netto", _fmt_pct(last), verdict,
                       comment, 2, brief=f"marża netto {_fmt_pct(last)}")

    def spec_operating_leverage() -> Insight | MissingData:
        latest = latest_quarter
        pos = latest.get("profit_on_sales")
        rev_yoy = latest.get("revenue_yoy_pct")
        prev = None
        if quarters and latest.get("period"):
            try:
                prev_period = metrics.previous_year_period(latest["period"])
                prev = next((q for q in quarters if q.get("period") == prev_period), None)
            except ValueError:
                prev = None
        if (pos is None or rev_yoy is None or prev is None
                or prev.get("profit_on_sales") in (None, 0)
                or prev.get("profit_on_sales") <= 0):
            return MissingData(
                "operating_leverage", "Dźwignia operacyjna",
                "Brak porównywalnego zysku ze sprzedaży r/r — dźwignia "
                "operacyjna pokazuje, czy zysk rośnie szybciej niż przychody.",
            )
        profit_yoy = (pos / prev["profit_on_sales"] - 1) * 100
        delta = profit_yoy - rev_yoy
        if delta > 0:
            verdict, comment = "good", (
                f"Zysk ze sprzedaży {profit_yoy:+.0f}% vs przychody "
                f"{rev_yoy:+.0f}% r/r — koszty rosną wolniej niż biznes."
            )
        else:
            verdict, comment = "bad", (
                f"Zysk ze sprzedaży {profit_yoy:+.0f}% przy przychodach "
                f"{rev_yoy:+.0f}% r/r — marże pod presją."
            )
        return Insight("operating_leverage", "Dźwignia operacyjna",
                       f"{profit_yoy:+.0f}% vs {rev_yoy:+.0f}%", verdict, comment, 2,
                       brief=f"zysk ze sprzedaży {profit_yoy:+.0f}% przy "
                             f"przychodach {rev_yoy:+.0f}% r/r")

    def spec_one_offs() -> Insight | MissingData:
        share = latest_quarter.get("one_off_share_pct")
        if share is None:
            return MissingData(
                "one_offs", "Udział zdarzeń jednorazowych",
                "Brak danych o pozostałej działalności operacyjnej — bez tego "
                "nie widać, ile zysku jest powtarzalne.",
            )
        if share < 15:
            verdict, comment = "good", (
                f"One-offy to tylko {_fmt_pct(share)} zysku operacyjnego — "
                "wynik wygląda na powtarzalny."
            )
        elif share <= metrics.ONE_OFF_SHARE_LIMIT_PCT:
            verdict, comment = "neutral", (
                f"One-offy {_fmt_pct(share)} zysku operacyjnego — akceptowalne, "
                "ale sprawdź noty."
            )
        else:
            verdict, comment = "bad", (
                f"Aż {_fmt_pct(share)} zysku operacyjnego to pozostała "
                "działalność — zysk może być jednorazowy (sprzedaż aktywów, "
                "odpisy, przeszacowania)."
            )
        return Insight("one_offs", "Udział zdarzeń jednorazowych", _fmt_pct(share),
                       verdict, comment, 3 if group in ("biotech_med", "energy") else 2,
                       brief=f"one-offy {_fmt_pct(share)} zysku oper.")

    def spec_pe_vs_history() -> Insight | MissingData:
        current = pe_history.get("current")
        median = pe_history.get("median")
        if current is None or median is None:
            why = (
                "Brak bieżącego C/Z (spółka nierentowna TTM lub brak kursu) "
                if current is None else
                "Brak historii C/Z z BiznesRadar "
            )
            return MissingData(
                "pe_vs_history", "C/Z na tle własnej historii",
                why + "— strategia porównuje wycenę do WŁASNEJ historii spółki, "
                      "nie do rynku.",
            )
        percentile = pe_history.get("percentile")
        if current < median * 0.85:
            verdict, comment = "good", (
                f"C/Z {_fmt_x(current)} wyraźnie poniżej własnej mediany "
                f"{_fmt_x(median)} — historycznie tanio, jeśli wyniki się "
                "utrzymają."
            )
        elif current <= median * 1.15:
            verdict, comment = "neutral", (
                f"C/Z {_fmt_x(current)} blisko mediany {_fmt_x(median)} — "
                "wycena neutralna; potrzebny katalizator."
            )
        else:
            verdict, comment = "bad", (
                f"C/Z {_fmt_x(current)} powyżej własnej mediany {_fmt_x(median)} "
                f"({'' if percentile is None else f'{percentile:.0f}. percentyl — '}"
                "rynek już wycenia poprawę)."
            )
        return Insight("pe_vs_history", "C/Z na tle własnej historii",
                       _fmt_x(current), verdict, comment, 3,
                       brief=f"C/Z {_fmt_x(current)} vs własna mediana {_fmt_x(median)}")

    def spec_net_cash() -> Insight | MissingData:
        if net_cash_value is None:
            return MissingData(
                "net_cash", "Gotówka netto",
                "Brak pozycji gotówki w bilansie — gotówka netto to bufor "
                "bezpieczeństwa i paliwo dywidendy.",
            )
        if net_cash_value > 0:
            verdict, comment = "good", (
                f"Gotówka netto {_fmt_mln(net_cash_value)} — bilans bez ryzyka "
                "zadłużenia, plus u Malika."
            )
        else:
            verdict, comment = "neutral", (
                f"Dług netto {_fmt_mln(abs(net_cash_value))} — samo w sobie "
                "nie dyskwalifikuje, patrz obsługa długu."
            )
        label = "gotówka netto" if net_cash_value > 0 else "dług netto"
        return Insight("net_cash", "Gotówka netto", _fmt_mln(net_cash_value),
                       verdict, comment, 2,
                       brief=f"{label} {_fmt_mln(abs(net_cash_value))}")

    def spec_cash_runway() -> Insight | MissingData:
        ttm_net = ttm.get("net_profit")
        if net_cash_value is None:
            return MissingData(
                "cash_runway", "Zapas gotówki (runway)",
                "Brak danych o gotówce — dla spółki na wczesnym etapie to "
                "wskaźnik nr 1: jak długo sfinansuje badania bez emisji.",
            )
        if ttm_net is not None and ttm_net < 0:
            years = abs(net_cash_value) / abs(ttm_net) if net_cash_value > 0 else 0.0
            if net_cash_value <= 0:
                return Insight(
                    "cash_runway", "Zapas gotówki (runway)",
                    _fmt_mln(net_cash_value), "bad",
                    "Spółka pali gotówkę i ma dług netto — realne ryzyko "
                    "emisji akcji (rozwodnienia).", 3,
                    brief="pali gotówkę przy długu netto",
                )
            verdict = "good" if years >= 2 else ("neutral" if years >= 1 else "bad")
            return Insight(
                "cash_runway", "Zapas gotówki (runway)",
                f"~{years:.1f} roku", verdict,
                f"Gotówka netto {_fmt_mln(net_cash_value)} przy stracie TTM "
                f"{_fmt_mln(ttm_net)} — wystarczy na ~{years:.1f} roku "
                "działalności bez emisji.", 3,
                brief=f"runway ~{years:.1f} roku".replace(".", ","),
            )
        return Insight(
            "cash_runway", "Zapas gotówki (runway)", _fmt_mln(net_cash_value),
            "good" if net_cash_value > 0 else "neutral",
            "Spółka jest rentowna TTM — runway nie jest ograniczeniem; "
            f"gotówka netto {_fmt_mln(net_cash_value)}.", 2,
            brief=f"gotówka netto {_fmt_mln(net_cash_value)}",
        )

    def spec_debt_load() -> Insight | MissingData:
        if net_cash_value is None:
            return MissingData(
                "debt_load", "Zadłużenie",
                "Brak danych bilansowych o długu — dla spółki "
                f"{'kapitałochłonnej' if group in ('industrial', 'energy', 'realestate') else 'tej branży'} "
                "poziom długu decyduje o przetrwaniu dekoniunktury.",
            )
        if net_cash_value >= 0:
            return Insight(
                "debt_load", "Zadłużenie", "gotówka netto", "good",
                f"Więcej gotówki niż długu ({_fmt_mln(net_cash_value)}) — "
                "bilans bezpieczny.", 2,
                brief=f"gotówka netto {_fmt_mln(net_cash_value)}",
            )
        equity = balance_latest.get("equity")
        if equity and equity > 0:
            gearing = abs(net_cash_value) / equity * 100
            if gearing < 40:
                verdict, comment = "neutral", (
                    f"Dług netto to {gearing:.0f}% kapitału własnego — "
                    "umiarkowane."
                )
            elif gearing < 100:
                verdict, comment = "bad", (
                    f"Dług netto {gearing:.0f}% kapitału własnego — wysoka "
                    "dźwignia; zysk wrażliwy na stopy."
                )
            else:
                verdict, comment = "bad", (
                    f"Dług netto przekracza kapitał własny ({gearing:.0f}%) — "
                    "czerwona flaga bilansowa."
                )
            return Insight("debt_load", "Zadłużenie",
                           f"{gearing:.0f}% k.wł.", verdict, comment, 2,
                           brief=f"dług netto {gearing:.0f}% kapitału własnego")
        return Insight(
            "debt_load", "Zadłużenie", _fmt_mln(net_cash_value), "neutral",
            f"Dług netto {_fmt_mln(abs(net_cash_value))}; brak kapitału "
            "własnego w danych, nie można policzyć dźwigni.", 2,
            brief=f"dług netto {_fmt_mln(abs(net_cash_value))}",
        )

    def spec_liquidity() -> Insight | MissingData:
        current_assets = balance_latest.get("current_assets")
        current_liabilities = balance_latest.get("current_liabilities")
        if not current_assets or not current_liabilities:
            return MissingData(
                "liquidity", "Płynność bieżąca",
                "Brak sum aktywów/zobowiązań krótkoterminowych w danych "
                "bilansowych — płynność mówi, czy spółka domknie najbliższy "
                "rok bez kredytu.",
            )
        ratio = current_assets / current_liabilities
        if ratio >= 1.5:
            verdict, comment = "good", (
                f"Wskaźnik płynności {ratio:.1f} — wygodny zapas nad "
                "zobowiązaniami krótkoterminowymi."
            )
        elif ratio >= 1.0:
            verdict, comment = "neutral", (
                f"Płynność {ratio:.1f} — wystarczająca, bez zapasu."
            )
        else:
            verdict, comment = "bad", (
                f"Płynność {ratio:.1f} — zobowiązania krótkoterminowe "
                "przewyższają aktywa obrotowe."
            )
        return Insight("liquidity", "Płynność bieżąca", f"{ratio:.1f}",
                       verdict, comment, 1,
                       brief=f"płynność bieżąca {ratio:.1f}".replace(".", ","))

    def spec_roe() -> Insight | MissingData:
        roe = latest_indicator("roe")
        if roe is None:
            return MissingData(
                "roe", "ROE",
                "Brak ROE ze strony wskaźników rentowności — dla "
                f"{'banku/ubezpieczyciela' if group == 'finance' else 'tej spółki'} "
                "to kluczowa miara jakości biznesu.",
            )
        one_off = latest_quarter.get("one_off_share_pct")
        distorted = one_off is not None and one_off > metrics.ONE_OFF_SHARE_LIMIT_PCT
        if roe > 40 or distorted:
            return Insight(
                "roe", "ROE", _fmt_pct(roe), "neutral",
                f"ROE {_fmt_pct(roe)} wygląda świetnie, ale "
                f"{'duży udział one-offów' if distorted else 'tak wysoki poziom'} "
                "sugeruje zdarzenia jednorazowe — sprawdź powtarzalność.", 3,
                brief=f"ROE {_fmt_pct(roe)} (możliwe one-offy)",
            )
        threshold = 10.0 if group == "finance" else 12.0
        if roe >= threshold:
            verdict, comment = "good", (
                f"ROE {_fmt_pct(roe)} powyżej progu {threshold:.0f}% — kapitał "
                "pracuje efektywnie."
            )
        elif roe > 5:
            verdict, comment = "neutral", (
                f"ROE {_fmt_pct(roe)} — przeciętne; poniżej oczekiwań dla "
                "dobrej spółki."
            )
        else:
            verdict, comment = "bad", (
                f"ROE {_fmt_pct(roe)} — kapitał własny prawie nie zarabia."
            )
        return Insight("roe", "ROE", _fmt_pct(roe), verdict, comment,
                       3 if group == "finance" else 2,
                       brief=f"ROE {_fmt_pct(roe)}")

    def spec_cwk() -> Insight | MissingData:
        cwk = latest_indicator("cwk")
        if cwk is None:
            return MissingData(
                "cwk", "C/WK",
                "Brak C/WK — dla "
                f"{'instytucji finansowej' if group == 'finance' else 'dewelopera'} "
                "cena względem wartości księgowej to podstawowa miara wyceny.",
            )
        roe = latest_indicator("roe")
        if cwk < 1.0:
            comment = (
                f"C/WK {_fmt_x(cwk)} — rynek wycenia spółkę poniżej księgowej"
                + (
                    f", mimo ROE {_fmt_pct(roe)} — potencjalna okazja lub rynek "
                    "nie wierzy w bilans." if roe is not None and roe > 8
                    else " — tanio, ale sprawdź jakość aktywów."
                )
            )
            verdict = "good"
        elif cwk <= 2.5:
            verdict, comment = "neutral", (
                f"C/WK {_fmt_x(cwk)} — typowy przedział; sama liczba nie "
                "rozstrzyga."
            )
        else:
            verdict, comment = "bad", (
                f"C/WK {_fmt_x(cwk)} — wysoko ponad księgową; wycena zakłada "
                "trwałą wysoką rentowność."
            )
        return Insight("cwk", "C/WK", _fmt_x(cwk), verdict, comment,
                       3 if group in ("finance", "realestate") else 1,
                       brief=f"C/WK {_fmt_x(cwk)}")

    def spec_ev_ebitda() -> Insight | MissingData:
        ev_ebitda = latest_indicator("ev_ebitda")
        if ev_ebitda is None:
            return MissingData(
                "ev_ebitda", "EV/EBITDA",
                "Brak EV/EBITDA — dla spółki surowcowej/energetycznej to "
                "lepsza miara wyceny niż C/Z (uwzględnia dług i amortyzację).",
            )
        if ev_ebitda <= 0:
            return Insight(
                "ev_ebitda", "EV/EBITDA", _fmt_x(ev_ebitda), "unknown",
                "EV/EBITDA ujemne — EBITDA pod kreską lub dane niepełne.", 2,
                brief=f"EV/EBITDA {_fmt_x(ev_ebitda)}",
            )
        if ev_ebitda < 6:
            verdict, comment = "good", (
                f"EV/EBITDA {_fmt_x(ev_ebitda)} — nisko; typowe dno wyceny w "
                "cyklu (uwaga: bywa tanio z powodu szczytu cyklu wyników)."
            )
        elif ev_ebitda <= 12:
            verdict, comment = "neutral", (
                f"EV/EBITDA {_fmt_x(ev_ebitda)} — środek przedziału."
            )
        else:
            verdict, comment = "bad", (
                f"EV/EBITDA {_fmt_x(ev_ebitda)} — drogo względem generowanej "
                "EBITDA."
            )
        return Insight("ev_ebitda", "EV/EBITDA", _fmt_x(ev_ebitda), verdict,
                       comment, 3 if group == "energy" else 2,
                       brief=f"EV/EBITDA {_fmt_x(ev_ebitda)}")

    def spec_dividend() -> Insight | MissingData:
        if not dividend_years:
            return MissingData(
                "dividend", "Dywidenda",
                "Brak historii dywidend — regularna wypłata uwiarygadnia "
                "zyski (gotówka jest prawdziwa) i dyscyplinuje zarząd.",
            )
        latest_year = max(dividend_years)
        streak = 0
        for offset, year in enumerate(sorted(dividend_years, reverse=True)):
            if year == latest_year - offset:
                streak += 1
            else:
                break
        yield_text = (
            f", stopa {_fmt_pct(dividend_yield_latest)}"
            if dividend_yield_latest is not None else ""
        )
        if streak >= 3:
            verdict, comment = "good", (
                f"Dywidenda płacona {streak} lat z rzędu (ostatnio "
                f"{latest_year}{yield_text}) — zyski mają pokrycie w gotówce."
            )
        elif streak >= 1:
            verdict, comment = "neutral", (
                f"Dywidenda wypłacona w {latest_year}{yield_text}, ale bez "
                "długiej serii — obserwuj kontynuację."
            )
        else:
            verdict, comment = "neutral", (
                f"Ostatnia dywidenda: {latest_year} — historia nieregularna."
            )
        value = f"{streak} lat z rzędu" if streak >= 2 else f"ost. {latest_year}"
        brief = (
            f"dywidenda {streak} lat z rzędu" if streak >= 2
            else f"dywidenda ost. {latest_year}"
        )
        if dividend_yield_latest is not None:
            brief += f" (stopa {_fmt_pct(dividend_yield_latest)})"
        return Insight("dividend", "Dywidenda", value, verdict, comment,
                       2 if group in ("finance", "energy", "realestate") else 1,
                       brief=brief)

    def spec_net_profit_trend() -> Insight | MissingData:
        nets = [q.get("net_profit") for q in quarters if q.get("net_profit") is not None]
        if len(nets) < 5:
            return MissingData(
                "net_profit_trend", "Trend zysku netto",
                "Za mało kwartałów z zyskiem netto, by ocenić trend r/r.",
            )
        latest_net, year_ago = nets[-1], nets[-5]
        if year_ago <= 0:
            comment = (
                f"Zysk netto {_fmt_mln(latest_net)} vs strata rok wcześniej — "
                "zwrot wyników, sprawdź trwałość."
            )
            verdict = "good" if latest_net > 0 else "bad"
        else:
            change = (latest_net / year_ago - 1) * 100
            if change > 10:
                verdict, comment = "good", (
                    f"Zysk netto {change:+.0f}% r/r — wynik rośnie."
                )
            elif change >= -10:
                verdict, comment = "neutral", (
                    f"Zysk netto {change:+.0f}% r/r — płasko."
                )
            else:
                verdict, comment = "bad", (
                    f"Zysk netto {change:+.0f}% r/r — regres wyników."
                )
        brief = (
            f"zysk netto {change:+.0f}% r/r" if year_ago > 0
            else f"zysk netto {_fmt_mln(latest_net)} vs strata rok temu"
        )
        return Insight("net_profit_trend", "Trend zysku netto",
                       _fmt_mln(latest_net), verdict, comment, 2, brief=brief)

    _SPECS = {
        "revenue_growth": spec_revenue_growth,
        "gross_margin": spec_gross_margin,
        "net_margin": spec_net_margin,
        "operating_leverage": spec_operating_leverage,
        "one_offs": spec_one_offs,
        "pe_vs_history": spec_pe_vs_history,
        "net_cash": spec_net_cash,
        "cash_runway": spec_cash_runway,
        "debt_load": spec_debt_load,
        "liquidity": spec_liquidity,
        "roe": spec_roe,
        "cwk": spec_cwk,
        "ev_ebitda": spec_ev_ebitda,
        "dividend": spec_dividend,
        "net_profit_trend": spec_net_profit_trend,
    }

    playbook = list(_GROUP_PLAYBOOK[group])
    # ROE is context for every non-financial company too (when scraped).
    if "roe" not in playbook:
        playbook.append("roe")

    selected = 0
    for position, spec_id in enumerate(playbook):
        outcome = _SPECS[spec_id]()
        selected += 1
        if isinstance(outcome, Insight):
            # position in the playbook sets importance unless the spec already
            # raised it for this sector
            outcome.importance = max(outcome.importance, _IMPORTANCE.get(position, 1))
            evaluated[spec_id] = outcome
            result.key_indicators.append(outcome)
        else:
            result.missing.append(outcome)

    # ---- strengths / concerns (weighted by importance) ----------------------
    for insight in sorted(result.key_indicators,
                          key=lambda i: -i.importance):
        if insight.verdict == "good" and len(result.strengths) < 4:
            result.strengths.append(insight.comment)
        elif insight.verdict == "bad" and len(result.concerns) < 4:
            result.concerns.append(insight.comment)

    available = len(result.key_indicators)
    result.coverage = {
        "available": available,
        "selected": selected,
        "note": (
            f"Ocena oparta na {available} z {selected} kluczowych wskaźników "
            f"dla tej spółki."
            + (" Braki wymienione niżej." if result.missing else "")
        ),
    }

    # ---- summary: COMPOSED from the computed metrics, never canned prose ----
    # Each sentence quotes real values (the Insight.brief fragments); parts
    # without data are simply absent instead of papered over with boilerplate.
    intro_bits: list[str] = []
    if size_label:
        intro_bits.append(size_label.lower())
    intro_bits.append(SECTOR_GROUP_LABELS[group].lower())
    mcap = ttm.get("market_cap")
    if mcap and mcap >= 1e9:
        mcap_value = f"{mcap / 1e9:.2f}".replace(".", ",") + " mld zł"
    elif mcap:
        mcap_value = f"{mcap / 1e6:,.0f}".replace(",", " ") + " mln zł"
    mcap_text = f" ({mcap_value})" if mcap else ""

    def briefs(verdict: str, limit: int) -> list[str]:
        picked = [
            i.brief or f"{i.name} {i.value}"
            for i in sorted(
                (i for i in result.key_indicators if i.verdict == verdict),
                key=lambda i: -i.importance,
            )
        ]
        return picked[:limit]

    plus_frags = briefs("good", 3)
    minus_frags = briefs("bad", 3)

    sentences: list[str] = [f"{', '.join(intro_bits).capitalize()}{mcap_text}."]
    if plus_frags:
        sentences.append(f"Na plus: {'; '.join(plus_frags)}.")
    if minus_frags:
        sentences.append(f"Na minus: {'; '.join(minus_frags)}.")
    if not plus_frags and not minus_frags:
        if available:
            neutral_frags = [
                i.brief or f"{i.name} {i.value}"
                for i in sorted(result.key_indicators, key=lambda i: -i.importance)
                if i.brief
            ][:3]
            if neutral_frags:
                sentences.append(
                    f"Kluczowe odczyty (bez jednoznacznego sygnału): "
                    f"{'; '.join(neutral_frags)}."
                )
        else:
            sentences.append(
                "Za mało danych liczbowych na ocenę — odśwież dane i sprawdź "
                "braki poniżej."
            )

    if size_code in ("mid", "large"):
        sentences.append(
            "Spółka powyżej sweet spotu strategii (< 1 mld zł) — przewaga "
            "informacyjna jest tu mniejsza."
        )
    if result.missing and available:
        sentences.append(
            f"Ocena częściowa: {available} z {selected} wskaźników "
            "(braki niżej)."
        )

    result.summary = " ".join(sentences)
    return result
