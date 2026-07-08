"""Render the Teza + Scenariusze preview as a NATIVE SVG (then -> PNG).

WHY (preview helper): the sandbox has no headless browser, and ImageMagick's
built-in SVG renderer ignores <foreignObject> (so HTML can't be screenshotted).
To still give the user an inline-viewable PNG, this builds a NATIVE SVG
(rect/text only — what MSVG can rasterize) that reproduces the post-Part-A
panels: verdict hero, muted chips, the weighted-potential headline, the
per-scenario rows with badge + metric strip, and the valuation block. Colours,
sizes and copy come from `globals.scss` + the real engine output in
`dossier-DEC.json`; every number is formatted with the `lib/format.ts` rules.
It is a faithful STATIC preview ("podgląd statyczny"), not a pixel screenshot —
the pixel-faithful version is the sibling `scenarios-DEC-after.html`.

Run:  python3 docs/previews/_render_svg.py   (writes .svg, rasterises to .png)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "dossier-DEC.json").read_text())

# ---- design tokens (globals.scss) -------------------------------------------
C = {
    "surface0": "#0e1217", "surface1": "#151b22", "surface2": "#1b232c",
    "border": "#2a3440", "accent": "#58a6ff", "primary": "#e8edf2",
    "secondary": "#9fb0bf", "muted": "#64748b", "success": "#3fd0a4",
    "danger": "#f28b8a", "warning": "#efb454",
}
BADGE = {  # tone -> (fill, opacity, text)
    "success": ("#1d9e75", 0.15, C["success"]),
    "warning": ("#ef9f27", 0.15, C["warning"]),
    "neutral": ("#151b22", 1.0, C["secondary"]),
    "muted": ("#151b22", 1.0, C["muted"]),
}
KIND_TONE = {"negative": "warning", "base": "neutral", "positive": "success", "event": "muted"}
MULTIPLE_LABEL = {"cz": "C/Z", "cwk": "C/WK", "ev_ebitda": "EV/EBITDA"}
CONF = {"high": ("success", "wysoka"), "medium": ("neutral", "umiarkowana"), "low": ("warning", "niska")}

W = 720
PAD = 18          # page side padding (.wrap)
CARD_X = PAD
CARD_W = W - 2 * PAD           # 684
INNER_X = CARD_X + 16         # card padding 16
INNER_W = CARD_W - 32         # 652


# ---- pl-PL number formatting (mirror lib/format.ts) -------------------------
def _grp(v, d):
    body = f"{abs(v):,.{d}f}".replace(",", " ").replace(".", ",")
    return ("-" + body) if v < 0 else body


def pln(v):
    return "—" if v is None else f"{_grp(v, 2)} zł"


def pct(v, signed=False, d=1):
    if v is None:
        return "—"
    s = f"{_grp(v, d)}%"
    return f"+{s}" if signed and v > 0 else s


def mcap(v):
    if v is None:
        return "—"
    return f"{_grp(v/1e9, 2)} mld zł" if v >= 1e9 else f"{_grp(v/1e6, 0)} mln zł"


def sign_cls(v):
    if v is None:
        return "muted"
    return "success" if v > 0 else "danger" if v < 0 else "secondary"


# ---- tiny SVG builder with deferred card backgrounds ------------------------
class Canvas:
    def __init__(self):
        self.parts: list[str] = []
        self.y = 0.0

    def ph(self) -> int:
        self.parts.append("")
        return len(self.parts) - 1

    def set(self, i, s):
        self.parts[i] = s

    def add(self, s):
        self.parts.append(s)


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _wrap(text, size, maxw, factor=0.54):
    max_chars = max(6, int(maxw / (size * factor)))
    lines, cur = [], ""
    for word in str(text).split():
        cand = (cur + " " + word).strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            while len(word) > max_chars:
                lines.append(word[:max_chars])
                word = word[max_chars:]
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def text(cv, x, s, size, color, *, weight=None, italic=False, anchor="start", dy_baseline=None):
    """One line of text at current cv.y (baseline = y + size*0.8). Does NOT advance y."""
    w = f' font-weight="{weight}"' if weight else ""
    it = ' font-style="italic"' if italic else ""
    an = f' text-anchor="{anchor}"' if anchor != "start" else ""
    base = cv.y + (dy_baseline if dy_baseline is not None else size * 0.8)
    cv.add(f'<text x="{x:.1f}" y="{base:.1f}" font-family="Lato, DejaVu Sans, sans-serif" '
           f'font-size="{size}"{w}{it}{an} fill="{color}">{esc(s)}</text>')


def para(cv, x, s, size, color, maxw, *, leading=None, weight=None, italic=False):
    """Wrapped paragraph; advances cv.y. (No inline tspan suffix: MSVG resets a
    tspan without an explicit x to the parent x, which overlaps the line — so
    trailing tags like the pro/con `principle` are rendered as their own line.)"""
    leading = leading or size * 1.5
    for ln in _wrap(s, size, maxw):
        base = cv.y + size * 0.8
        w = f' font-weight="{weight}"' if weight else ""
        it = ' font-style="italic"' if italic else ""
        cv.add(f'<text x="{x:.1f}" y="{base:.1f}" font-family="Lato, DejaVu Sans, sans-serif" '
               f'font-size="{size}"{w}{it} fill="{color}">{esc(ln)}</text>')
        cv.y += leading


def point(cv, x, txt, principle, bullet_color, maxw):
    """A pros/cons bullet: coloured dot + wrapped text, principle on a subtle
    muted line beneath (trailing tag; kept off the wrapped line — see para())."""
    cv.add(f'<circle cx="{x + 3:.1f}" cy="{cv.y + 6:.1f}" r="2" fill="{bullet_color}"/>')
    para(cv, x + 14, txt, 13, C["secondary"], maxw - 14, leading=18)
    if principle:
        text(cv, x + 14, "· " + principle, 11, C["muted"])
        cv.y += 15
    cv.y += 5


def badge(cv, x, y, label, tone, size=12):
    fill, op, fg = BADGE.get(tone, BADGE["muted"])
    w = len(label) * size * 0.55 + 18
    cv.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="22" rx="10" ry="10" '
           f'fill="{fill}" fill-opacity="{op}"/>')
    cv.add(f'<text x="{x + w/2:.1f}" y="{y + 15:.1f}" text-anchor="middle" '
           f'font-family="Lato, DejaVu Sans, sans-serif" font-size="{size}" font-weight="500" '
           f'fill="{fg}">{esc(label)}</text>')
    return w


def divider(cv, x, w):
    cv.y += 12
    cv.add(f'<line x1="{x:.1f}" y1="{cv.y:.1f}" x2="{x + w:.1f}" y2="{cv.y:.1f}" stroke="{C["border"]}" stroke-width="0.5"/>')
    cv.y += 12


def metric_strip(cv, x, w, cols):
    """cols = [(k, v, color), ...] laid out in equal columns."""
    n = len(cols)
    colw = w / n
    top = cv.y
    for i, (k, v, color) in enumerate(cols):
        cx = x + i * colw
        cv.y = top
        text(cv, cx, k.upper(), 11, C["muted"])
        cv.y += 15
        text(cv, cx, v, 14, color, weight="500")
    cv.y = top + 15 + 18


def card(cv, render):
    """Draw a rounded card behind whatever `render(cv)` emits (padding 14x16)."""
    start = cv.y
    bg = cv.ph()
    cv.y = start + 14
    render(cv)
    cv.y += 14
    end = cv.y
    cv.set(bg, f'<rect x="{CARD_X}" y="{start:.1f}" width="{CARD_W}" height="{end - start:.1f}" '
                f'rx="12" ry="12" fill="{C["surface2"]}" stroke="{C["border"]}" stroke-width="0.5"/>')
    cv.y = end


# ---- panels -----------------------------------------------------------------
def render_thesis(cv):
    t = DATA["thesis"]
    eq = t["entry_quality"]
    tone_color = {"attractive": C["success"], "neutral": C["primary"],
                  "weak": C["warning"], "insufficient_data": C["muted"]}[eq["code"]]
    # verdict hero (icon + label) left; chips right
    iy = cv.y
    cx = INNER_X + 12
    cv.add(f'<circle cx="{cx:.1f}" cy="{iy + 11:.1f}" r="9" fill="none" stroke="{tone_color}" stroke-width="1.8"/>')
    cv.add(f'<path d="M{cx-4:.1f} {iy+11:.1f} l3 3 l5 -5" fill="none" stroke="{tone_color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>')
    text(cv, cx + 16, eq["label"], 17, tone_color, weight="500", dy_baseline=16)
    # muted chips demoted to their own row below the hero (flex-wrap at this width)
    cv.y = iy + 30
    bx = INNER_X
    for lbl in (f'wg strategii: {t["strategy"]["label"]}',
                f'silnik: {"AI" if t.get("engine") == "ai" else "deterministyczny"}'):
        bw = len(lbl) * 12 * 0.55 + 18
        badge(cv, bx, cv.y, lbl, "muted")
        bx += bw + 6
    cv.y += 30
    para(cv, INNER_X, eq["rationale"], 13, C["secondary"], INNER_W, leading=19)

    divider(cv, INNER_X, INNER_W)
    text(cv, INNER_X, "Mocne strony tezy", 13, C["primary"], weight="500")
    cv.y += 20
    for p in t["pros"]:
        point(cv, INNER_X, p["text"], p["principle"], C["success"], INNER_W)

    divider(cv, INNER_X, INNER_W)
    text(cv, INNER_X, "Ryzyka dla tezy", 13, C["primary"], weight="500")
    cv.y += 20
    if t["cons"]:
        for c in t["cons"]:
            point(cv, INNER_X, c["text"], c["principle"], C["danger"], INNER_W)
    else:
        text(cv, INNER_X, "brak", 13, C["muted"])
        cv.y += 18

    divider(cv, INNER_X, INNER_W)
    text(cv, INNER_X, "Co sprawdzić dalej", 13, C["primary"], weight="500")
    cv.y += 20
    for v in t["verify_next"]:
        para(cv, INNER_X, v["text"] + "  —  " + v["why"], 12.5, C["secondary"], INNER_W, leading=17)
        cv.y += 3

    divider(cv, INNER_X, INNER_W)
    para(cv, INNER_X, t["thesis_read"], 13, C["secondary"], INNER_W, leading=19)
    cv.y += 6
    para(cv, INNER_X, t["valuation_basis"], 12, C["muted"], INNER_W, leading=17)
    cv.y += 8
    para(cv, INNER_X, t["disclaimer"], 11.5, C["muted"], INNER_W, leading=17, italic=True)


def render_scenario_row(cv, s):
    tone = KIND_TONE.get(s["kind"], "muted")
    ix = INNER_X + 12
    iw = INNER_W - 24

    def inner(cv):
        top = cv.y
        badge(cv, ix, top, s["label"], tone)
        text(cv, ix + iw, f'p ≈ {pct(s["probability"] * 100, d=0)}', 12, C["secondary"],
             anchor="end", dy_baseline=15)
        cv.y = top + 26
        para(cv, ix, s["narrative"], 13, C["secondary"], iw, leading=19)
        cv.y += 4
        metric_strip(cv, ix, iw, [
            ("Cena docelowa", pln(s["target_price"]), C["primary"]),
            ("Potencjał", pct(s["implied_upside_pct"], signed=True), C[sign_cls(s["implied_upside_pct"])]),
            ("Horyzont", f'{s["horizon"]["low_months"]}–{s["horizon"]["high_months"]} mies.', C["primary"]),
        ])
        cv.y += 4
        para(cv, ix, s["target_multiple"]["basis_label"], 11.5, C["muted"], iw, leading=16)
        cv.y += 2
        for a in s["assumptions"]:
            cv.add(f'<circle cx="{ix + 3:.1f}" cy="{cv.y + 6:.1f}" r="1.6" fill="{C["muted"]}"/>')
            para(cv, ix + 12, a, 11.5, C["muted"], iw - 12, leading=16)

    # inset rounded rect behind the row
    start = cv.y
    bg = cv.ph()
    cv.y = start + 10
    inner(cv)
    cv.y += 10
    end = cv.y
    cv.set(bg, f'<rect x="{INNER_X}" y="{start:.1f}" width="{INNER_W}" height="{end - start:.1f}" '
                f'rx="8" ry="8" fill="{C["surface2"]}" stroke="{C["border"]}" stroke-width="0.5"/>')
    cv.y = end + 10


def render_scenarios(cv):
    sc, val = DATA["scenarios"], DATA["valuation"]
    top = cv.y
    badge(cv, INNER_X, top, f'wycena wg mnożnika: {MULTIPLE_LABEL.get(sc["valuation_multiple"], sc["valuation_multiple"])}', "muted")
    eng = f'silnik: {"AI" if sc.get("engine") == "ai" else "deterministyczny"}'
    bw = len(eng) * 12 * 0.55 + 18
    badge(cv, INNER_X + INNER_W - bw, top, eng, "muted")
    cv.y = top + 34

    text(cv, INNER_X, "OCZEKIWANY POTENCJAŁ (WAŻONY SCENARIUSZAMI)", 11, C["muted"])
    cv.y += 16
    up = sc["weighted_expected_upside_pct"]
    text(cv, INNER_X, pct(up, signed=True), 26, C[sign_cls(up)], weight="500", dy_baseline=22)
    if sc["weighted_expected_price"] is not None:
        text(cv, INNER_X + 150, f'{pln(sc["current_price"])} → {pln(sc["weighted_expected_price"])}',
             12, C["secondary"], dy_baseline=20)
    cv.y += 30
    para(cv, INNER_X, "Analiza: " + sc["framing"], 12, C["muted"], INNER_W, leading=17)
    cv.y += 6
    for s in sc["scenarios"]:
        render_scenario_row(cv, s)

    # valuation section
    divider(cv, INNER_X, INNER_W)
    top = cv.y
    text(cv, INNER_X, "Potencjał (ocena)", 13, C["primary"], weight="500", dy_baseline=15)
    ctone, clabel = CONF.get(val["confidence"]["level"], ("muted", val["confidence"]["level"]))
    bx = INNER_X + INNER_W
    for lbl, tn in ((f'silnik: {"AI" if val.get("engine") == "ai" else "deterministyczny"}', "muted"),
                    (f'pewność: {clabel}', ctone)):
        bw = len(lbl) * 12 * 0.55 + 18
        badge(cv, bx - bw, top, lbl, tn)
        bx -= bw + 6
    cv.y = top + 30
    pot = val["potential"]
    cols = [("Potencjał", pct(pot["value_pct"], signed=True), C[sign_cls(pot["value_pct"])])]
    if pot.get("range_pct"):
        lo, hi = pot["range_pct"]
        cols.append(("Pasmo scenariuszy", f'{pct(lo, signed=True)} … {pct(hi, signed=True)}', C["secondary"]))
    metric_strip(cv, INNER_X, INNER_W, cols)
    cv.y += 6
    para(cv, INNER_X, pot["basis_label"], 11.5, C["muted"], INNER_W, leading=16)
    cv.y += 4
    para(cv, INNER_X, val["confidence"]["rationale"], 13, C["secondary"], INNER_W, leading=19)
    cv.y += 8
    text(cv, INNER_X, "Co zmieniłoby ocenę", 13, C["primary"], weight="500")
    cv.y += 20
    for wch in val["what_would_change"]:
        para(cv, INNER_X, wch["text"] + "  —  " + wch["why"], 12.5, C["secondary"], INNER_W, leading=17)
        cv.y += 3
    para(cv, INNER_X, val["narrative"], 13, C["secondary"], INNER_W, leading=19)
    cv.y += 6
    para(cv, INNER_X, "Analiza: " + val["framing"], 12, C["muted"], INNER_W, leading=17)
    cv.y += 8
    para(cv, INNER_X, sc["disclaimer"], 11.5, C["muted"], INNER_W, leading=17, italic=True)


def section_label(cv, s):
    cv.y += 20
    text(cv, PAD, s.upper(), 12, C["muted"])
    cv.y += 20


def build():
    cv = Canvas()
    cv.y = 18
    c, ttm, meta = DATA["company"], DATA["ttm"], DATA["_meta"]
    # preview banner
    bh = cv.ph()
    start = cv.y
    cv.y += 10
    para(cv, PAD + 12, f'Podgląd statyczny (render SVG, po Part A) · {c["ticker"]} · {c["name"]} '
         f'· 2026-07-08 · dane z fixture DECORA, silnik deterministyczny. Liczby z realnego '
         f'uruchomienia silników (dossier-DEC.json).', 12, C["accent"], W - 2 * PAD - 24, leading=17)
    cv.y += 8
    cv.set(bh, f'<rect x="{PAD}" y="{start:.1f}" width="{W - 2*PAD}" height="{cv.y - start:.1f}" rx="8" ry="8" '
               f'fill="#378add" fill-opacity="0.15" stroke="{C["accent"]}" stroke-width="0.5"/>')
    cv.y += 8
    # page head
    text(cv, PAD, f'{c["ticker"]} · {c["name"]}', 19, C["primary"], weight="500")
    text(cv, PAD + 200, c["sector"], 12, C["muted"], dy_baseline=15)
    cv.y += 24
    text(cv, PAD, pln(ttm["price"]), 15, C["primary"])
    text(cv, PAD + 70, f'kurs z 1.07.2025 · mcap {mcap(ttm["market_cap"])}', 12, C["muted"], dy_baseline=12)
    cv.y += 20

    section_label(cv, "Teza inwestycyjna")
    card(cv, render_thesis)
    section_label(cv, "Scenariusze")
    card(cv, render_scenarios)

    cv.y += 20
    height = cv.y
    body = "\n".join(cv.parts)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height:.0f}" '
            f'viewBox="0 0 {W} {height:.0f}">\n'
            f'<rect width="{W}" height="{height:.0f}" fill="{C["surface0"]}"/>\n{body}\n</svg>\n')


def main():
    svg = build()
    svg_path = HERE / "scenarios-DEC-after.svg"
    png_path = HERE / "scenarios-DEC-after.png"
    svg_path.write_text(svg, encoding="utf-8")
    # density 192 = 2x (SVG default 96 dpi) for a crisp raster.
    subprocess.run(["convert", "-density", "192", "-background", C["surface0"],
                    str(svg_path), str(png_path)], check=True)
    print(f"wrote {svg_path.name} + {png_path.name}")


if __name__ == "__main__":
    main()
