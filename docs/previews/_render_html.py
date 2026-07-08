"""Render the ThesisPanel + ScenariosPanel PREVIEW as self-contained HTML.

WHY (preview helper, not a product module): turns `dossier-DEC.json` (real
deterministic engine output — see `_render_engine_output.py`) into a single HTML
file that mirrors the post-Part-A `ThesisPanel.tsx` / `ScenariosPanel.tsx` DOM
1:1, styled with CSS compiled by hand from the real `frontend/src/styles/
globals.scss`. Everything is inlined (no CDN, no fonts, no scripts) so it opens
offline on a phone. Numbers are formatted with the SAME rules as
`frontend/src/lib/format.ts` (pl-PL, signed, PLN) so the render never diverges
from what the app would show.

Run:  python3 docs/previews/_render_html.py
"""
from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "dossier-DEC.json").read_text())

# --- pl-PL formatting, mirroring frontend/src/lib/format.ts -------------------
NBSP = " "


def _grp(value: float, digits: int) -> str:
    """Intl.NumberFormat('pl-PL') for our magnitudes: NBSP thousands, comma
    decimal, fixed number of fraction digits."""
    body = f"{abs(value):,.{digits}f}".replace(",", NBSP).replace(".", ",")
    return ("-" + body) if value < 0 else body


def fmt_pln(value):
    return "—" if value is None else f"{_grp(value, 2)} zł"


def fmt_pct(value, signed=False, digits=1):
    if value is None:
        return "—"
    body = f"{_grp(value, digits)}%"
    return f"+{body}" if signed and value > 0 else body


def fmt_mcap(value):
    if value is None:
        return "—"
    if value >= 1e9:
        return f"{_grp(value / 1e9, 2)} mld zł"
    return f"{_grp(value / 1e6, 0)} mln zł"


def sign_class(value):
    if value is None:
        return "muted"
    return "pos" if value > 0 else "neg" if value < 0 else "secondary"


def esc(text) -> str:
    return html.escape(str(text), quote=False)


# --- component fragments (DOM mirrors the .tsx) -------------------------------
KIND_TONE = {"negative": "warning", "base": "neutral", "positive": "success", "event": "muted"}
MULTIPLE_LABEL = {"cz": "C/Z", "cwk": "C/WK", "ev_ebitda": "EV/EBITDA"}
CONFIDENCE = {"high": ("success", "wysoka"), "medium": ("neutral", "umiarkowana"),
              "low": ("warning", "niska")}

# Tabler IconCircleCheck (attractive verdict) — inline so there is no icon font.
ICON_CIRCLE_CHECK = (
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round"><path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/>'
    '<path d="M9 12l2 2l4 -4"/></svg>'
)


def thesis_panel(t: dict) -> str:
    eq = t["entry_quality"]
    tone = {"attractive": "success", "neutral": "neutral", "weak": "warning",
            "insufficient_data": "muted"}.get(eq["code"], "muted")
    pros = "".join(
        f'<li>{esc(p["text"])}<span class="principle">{esc(p["principle"])}</span></li>'
        for p in t["pros"]
    )
    cons_html = (
        '<ul class="points bad">'
        + "".join(f'<li>{esc(c["text"])}<span class="principle">{esc(c["principle"])}</span></li>'
                  for c in t["cons"])
        + "</ul>"
        if t["cons"] else '<p class="points-empty">brak</p>'
    )
    verify = "".join(
        f'<p class="verify-item">{esc(v["text"])} — <span class="why">{esc(v["why"])}</span></p>'
        for v in t["verify_next"]
    )
    engine_label = "AI" if t.get("engine") == "ai" else "deterministyczny"
    return f"""
    <div class="card thesis">
      <div class="spread" style="flex-wrap:wrap;gap:8px">
        <div class="verdict {tone}">
          <span class="verdict-icon">{ICON_CIRCLE_CHECK}</span>
          <span class="verdict-label">{esc(eq["label"])}</span>
        </div>
        <div class="row" style="gap:6px;flex-wrap:wrap">
          <span class="badge muted">wg strategii: {esc(t["strategy"]["label"])}</span>
          <span class="badge muted">silnik: {engine_label}</span>
        </div>
      </div>
      <p class="rationale">{esc(eq["rationale"])}</p>
      <div class="thesis-section grid-2">
        <div>
          <p class="thesis-title">Mocne strony tezy</p>
          <ul class="points good">{pros}</ul>
        </div>
        <div>
          <p class="thesis-title">Ryzyka dla tezy</p>
          {cons_html}
        </div>
      </div>
      <div class="thesis-section">
        <p class="thesis-title">Co sprawdzić dalej</p>
        {verify}
      </div>
      <div class="thesis-section">
        <p class="thesis-read">{esc(t["thesis_read"])}</p>
        <p class="valuation-basis">{esc(t["valuation_basis"])}</p>
      </div>
      <p class="disclaimer">{esc(t["disclaimer"])}</p>
    </div>"""


def scenario_row(s: dict) -> str:
    tone = KIND_TONE.get(s["kind"], "muted")
    assumptions = "".join(f"<li>{esc(a)}</li>" for a in s["assumptions"])
    hz = s["horizon"]
    return f"""
      <div class="scenario">
        <div class="spread" style="flex-wrap:wrap;gap:6px">
          <span class="badge {tone}">{esc(s["label"])}</span>
          <span class="prob">p ≈ {fmt_pct(s["probability"] * 100, digits=0)}</span>
        </div>
        <p class="narrative">{esc(s["narrative"])}</p>
        <div class="scenario-metrics">
          <div><span class="k">Cena docelowa</span><span class="v">{fmt_pln(s["target_price"])}</span></div>
          <div><span class="k">Potencjał</span><span class="v {sign_class(s["implied_upside_pct"])}">{fmt_pct(s["implied_upside_pct"], signed=True)}</span></div>
          <div><span class="k">Horyzont</span><span class="v">{hz["low_months"]}–{hz["high_months"]} mies.</span></div>
        </div>
        <p class="basis">{esc(s["target_multiple"]["basis_label"])}</p>
        <ul class="assumptions">{assumptions}</ul>
      </div>"""


def scenarios_panel(sc: dict, val: dict) -> str:
    mlabel = MULTIPLE_LABEL.get(sc["valuation_multiple"], sc["valuation_multiple"])
    engine_label = "AI" if sc.get("engine") == "ai" else "deterministyczny"
    rows = "".join(scenario_row(s) for s in sc["scenarios"])

    if sc["weighted_expected_price"] is not None:
        sub = (f'<span class="headline-sub">{fmt_pln(sc["current_price"])} → '
               f'{fmt_pln(sc["weighted_expected_price"])}</span>')
    else:
        sub = ('<span class="headline-gap">wycena niedostępna — brak ceny docelowej '
               'w scenariuszach</span>')

    conf_tone, conf_label = CONFIDENCE.get(val["confidence"]["level"], ("muted", val["confidence"]["level"]))
    val_engine = "AI" if val.get("engine") == "ai" else "deterministyczny"
    pot = val["potential"]
    band = ""
    if pot.get("range_pct"):
        lo, hi = pot["range_pct"]
        band = (f'<div><span class="k">Pasmo scenariuszy</span>'
                f'<span class="v secondary">{fmt_pct(lo, signed=True)} … {fmt_pct(hi, signed=True)}</span></div>')
    wwc = "".join(
        f'<p class="wwc-item">{esc(w["text"])} — <span class="why">{esc(w["why"])}</span></p>'
        for w in val["what_would_change"]
    )

    return f"""
    <div class="card scenarios">
      <div class="spread" style="flex-wrap:wrap;gap:8px">
        <span class="badge muted">wycena wg mnożnika: {mlabel}</span>
        <span class="badge muted">silnik: {engine_label}</span>
      </div>
      <div class="headline">
        <div>
          <span class="headline-k">Oczekiwany potencjał (ważony scenariuszami)</span>
          <span class="potential {sign_class(sc["weighted_expected_upside_pct"])}">{fmt_pct(sc["weighted_expected_upside_pct"], signed=True)}</span>
        </div>
        {sub}
      </div>
      <p class="framing">Analiza: {esc(sc["framing"])}</p>
      <div class="scenario-list">{rows}</div>

      <div class="thesis-section valuation">
        <div class="spread" style="flex-wrap:wrap;gap:8px">
          <p class="thesis-title" style="margin:0">Potencjał (ocena)</p>
          <div class="row" style="gap:6px;flex-wrap:wrap">
            <span class="badge {conf_tone}">pewność: {conf_label}</span>
            <span class="badge muted">silnik: {val_engine}</span>
          </div>
        </div>
        <div class="scenario-metrics">
          <div><span class="k">Potencjał</span><span class="v {sign_class(pot["value_pct"])}">{fmt_pct(pot["value_pct"], signed=True)}</span></div>
          {band}
        </div>
        <p class="basis">{esc(pot["basis_label"])}</p>
        <p class="rationale">{esc(val["confidence"]["rationale"])}</p>
        <p class="thesis-title" style="margin-top:12px">Co zmieniłoby ocenę</p>
        {wwc}
        <p class="rationale">{esc(val["narrative"])}</p>
        <p class="framing">Analiza: {esc(val["framing"])}</p>
      </div>
      <p class="disclaimer">{esc(sc["disclaimer"])}</p>
    </div>"""


# --- page shell + CSS compiled from globals.scss -----------------------------
CSS = """
:root{
  --surface-0:#0e1217;--surface-1:#151b22;--surface-2:#1b232c;--border:#2a3440;
  --border-strong:#3a4653;--border-accent:#378add;--text-primary:#e8edf2;
  --text-secondary:#9fb0bf;--text-muted:#64748b;--text-accent:#58a6ff;
  --text-success:#3fd0a4;--text-danger:#f28b8a;--text-warning:#efb454;
  --bg-accent:rgba(55,138,221,.15);--bg-success:rgba(29,158,117,.15);
  --bg-danger:rgba(226,75,74,.15);--bg-warning:rgba(239,159,39,.15);
  --fill-accent:#378add;--fill-success:#1d9e75;--radius:8px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--surface-0);color:var(--text-primary);
  font-family:-apple-system,"Segoe UI",Roboto,"Lato",sans-serif;font-size:14px;
  -webkit-font-smoothing:antialiased;}
.wrap{max-width:720px;margin:0 auto;padding:20px 18px 48px;}
h1,h2,h3{font-weight:500;margin:0}

.preview-banner{background:var(--bg-accent);color:var(--text-accent);
  border:0.5px solid var(--border-accent);border-radius:8px;padding:8px 12px;
  font-size:12px;line-height:1.5;margin-bottom:16px;}
.preview-banner b{color:var(--text-primary)}

.page-head{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:6px;}
.page-head .tick{font-size:19px;font-weight:500}
.page-head .meta{font-size:12px;color:var(--text-muted);margin-left:10px}
.page-head .price{font-size:15px}
.page-head .price-meta{font-size:12px;color:var(--text-muted);margin-left:8px}

.section-label{font-size:12px;color:var(--text-muted);letter-spacing:.3px;
  text-transform:uppercase;margin:20px 0 8px;}

.card{background:var(--surface-2);border:0.5px solid var(--border);border-radius:12px;padding:14px 16px;}
.card + .card{margin-top:0}

.badge{display:inline-block;padding:3px 9px;border-radius:10px;font-size:12px;font-weight:500;}
.badge.success{background:var(--bg-success);color:var(--text-success)}
.badge.warning{background:var(--bg-warning);color:var(--text-warning)}
.badge.neutral{background:var(--surface-1);color:var(--text-secondary)}
.badge.muted{background:var(--surface-1);color:var(--text-muted)}

.row{display:flex;align-items:center;gap:10px}
.spread{display:flex;align-items:center;justify-content:space-between;gap:12px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:760px){.grid-2{grid-template-columns:1fr}}

/* thesis */
.thesis .rationale{color:var(--text-secondary);line-height:1.5;margin:10px 0 0}
.thesis .verdict{display:flex;align-items:center;gap:9px}
.thesis .verdict .verdict-icon{flex:none;display:flex}
.thesis .verdict .verdict-label{font-size:17px;font-weight:500;line-height:1.2}
.thesis .verdict.success{color:var(--text-success)}
.thesis .verdict.warning{color:var(--text-warning)}
.thesis .verdict.neutral{color:var(--text-primary)}
.thesis .verdict.muted{color:var(--text-muted)}
.thesis .thesis-section{margin-top:14px;padding-top:12px;border-top:0.5px solid var(--border)}
.thesis .thesis-title{font-weight:500;margin:0 0 8px}
.thesis .points{margin:0;padding-left:16px;color:var(--text-secondary);font-size:13px}
.thesis .points li{padding:3px 0}
.thesis .points.good li::marker{color:var(--text-success)}
.thesis .points.bad li::marker{color:var(--text-danger)}
.thesis .points-empty{color:var(--text-muted);font-size:13px;margin:0}
.thesis .principle{display:inline-block;margin-left:6px;font-size:11px;color:var(--text-muted)}
.thesis .verify-item{font-size:12.5px;color:var(--text-secondary);margin:0;padding:3px 0}
.thesis .verify-item .why{color:var(--text-muted)}
.thesis .thesis-read{color:var(--text-secondary);line-height:1.55;margin:0}
.thesis .valuation-basis{font-size:12px;color:var(--text-muted);margin:10px 0 0}
.thesis .disclaimer{font-size:11.5px;color:var(--text-muted);font-style:italic;line-height:1.5;margin:12px 0 0}

/* scenarios */
.scenarios .framing{font-size:12px;color:var(--text-muted);margin:10px 0 0}
.scenarios .headline{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 18px;margin:12px 0 2px}
.scenarios .headline .headline-k{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.3px;color:var(--text-muted);margin-bottom:2px}
.scenarios .headline .potential{font-size:26px;font-weight:500;line-height:1}
.scenarios .headline .potential.pos{color:var(--text-success)}
.scenarios .headline .potential.neg{color:var(--text-danger)}
.scenarios .headline .potential.muted,.scenarios .headline .potential.secondary{color:var(--text-muted);font-size:18px}
.scenarios .headline .headline-sub{font-size:12px;color:var(--text-secondary)}
.scenarios .headline .headline-gap{font-size:12px;color:var(--text-warning)}
.scenarios .thesis-section{margin-top:14px;padding-top:12px;border-top:0.5px solid var(--border)}
.scenarios .thesis-title{font-weight:500;margin:0 0 8px;font-size:13px}
.scenarios .scenario-list{margin-top:12px;display:flex;flex-direction:column;gap:10px}
.scenarios .scenario{padding:10px 12px;border:0.5px solid var(--border);border-radius:8px;background:var(--surface-2)}
.scenarios .scenario .prob{font-size:12px;color:var(--text-secondary);white-space:nowrap}
.scenarios .scenario .narrative{color:var(--text-secondary);line-height:1.5;margin:8px 0 0;font-size:13px}
.scenarios .scenario .basis{font-size:11.5px;color:var(--text-muted);margin:8px 0 0}
.scenarios .scenario .assumptions{margin:8px 0 0;padding-left:16px;font-size:11.5px;color:var(--text-muted)}
.scenarios .scenario .assumptions li{padding:2px 0}
.scenarios .scenario-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-top:10px}
.scenarios .scenario-metrics > div{display:flex;flex-direction:column;gap:2px}
.scenarios .scenario-metrics .k{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.3px}
.scenarios .scenario-metrics .v{font-size:14px;font-weight:500}
.scenarios .scenario-metrics .v.pos{color:var(--text-success)}
.scenarios .scenario-metrics .v.neg{color:var(--text-danger)}
.scenarios .scenario-metrics .v.muted{color:var(--text-muted)}
.scenarios .scenario-metrics .v.secondary{color:var(--text-secondary)}
.scenarios .valuation .basis{font-size:11.5px;color:var(--text-muted);margin:8px 0 0}
.scenarios .valuation .rationale{color:var(--text-secondary);line-height:1.5;margin:8px 0 0;font-size:13px}
.scenarios .valuation .wwc-item{margin:6px 0 0;font-size:12.5px;line-height:1.5}
.scenarios .valuation .wwc-item .why{color:var(--text-muted)}
.scenarios .disclaimer{font-size:11.5px;color:var(--text-muted);font-style:italic;line-height:1.5;margin:12px 0 0}
"""


def page() -> str:
    c = DATA["company"]
    ttm = DATA["ttm"]
    meta = DATA["_meta"]
    # header, mirroring frontend/src/app/stock/[ticker]/page.tsx
    price_date_pl = "1.07.2025"  # pl-PL of ttm.price_date 2025-07-01 (Intl short date)
    head = f"""
    <div class="page-head">
      <div>
        <span class="tick">{esc(c["ticker"])} · {esc(c["name"])}</span>
        <span class="meta">{esc(c["sector"])}</span><br>
        <span class="price">{fmt_pln(ttm["price"])}</span>
        <span class="price-meta">kurs z {price_date_pl} · mcap {fmt_mcap(ttm["market_cap"])}</span>
      </div>
    </div>"""
    banner = (
        '<div class="preview-banner"><b>Podgląd statyczny (po Part A)</b> · '
        f'{esc(c["ticker"])} · {esc(c["name"])} · 2026-07-08 · dane z fixture DECORA '
        '(engine deterministyczny, bez klucza AI). Wszystkie liczby pochodzą z '
        'realnego uruchomienia silników — <code>docs/previews/dossier-DEC.json</code>. '
        f'Kurs {fmt_pln(ttm["price"])} ze stooq_daily.csv ({meta["price_source"].split(" (")[0]}).'
        '</div>'
    )
    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Podgląd — Teza + Scenariusze — {esc(c["ticker"])} {esc(c["name"])}</title>
<style>{CSS}</style></head>
<body><div class="wrap">
{banner}
{head}
<p class="section-label">Teza inwestycyjna</p>
{thesis_panel(DATA["thesis"])}
<p class="section-label">Scenariusze</p>
{scenarios_panel(DATA["scenarios"], DATA["valuation"])}
</div></body></html>"""


def main() -> int:
    out = HERE / "scenarios-DEC-after.html"
    out.write_text(page(), encoding="utf-8")
    print(f"wrote {out.relative_to(HERE.parents[1])} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
