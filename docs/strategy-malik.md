# Strategy spec — Paweł Malik ("OBS") · source-grounded

Reference spec for the investment-thesis layer (`services/thesis.py`, WP2). It
distils **Paweł Malik's** actual, sourced philosophy and maps each principle to
a **computed dossier field** or an explicit **gap** ("needs human/AI check").
Rule-based composition only — no buy/sell signals, no Phase-5 calls. Domain
terms Polish (user decision); access dates **2026-07-08**.

> Not investment advice. Malik himself: *"Odradzam naśladownictwo, szukania
> sobie guru… to są moje subiektywne przekonania, które mogą być i bywają
> błędne."* [F]

## Sources

Web (primary unless noted; all accessed 2026-07-08):
- **[F]** Forum *"Portfel IKE – OBS"*, portalanaliz.pl — real IKE portfolio,
  679 posts 2021-2025. `https://portalanaliz.pl/forum/viewtopic.php?f=7&t=569`.
  In-repo copy = `obs.txt`; digest = `Filozofia_inwestycyjna_OBS_Portfel_IKE.md`.
- **[SB]** Interview, *Stockbroker.pl* (A. Wiśniewski), pub. 2018-10-16, mod.
  2023-06-04. `https://stockbroker.pl/analiza-fundamentalna-spolki-pawel-malik-gazetagieldowa/`
  — the richest single Q&A on his method.
- **[ON]** Bio, *Portal Analiz — O nas*, mod. 2026-06-15.
  `https://portalanaliz.pl/o-nas/`.
- **[DT]** *"Nic za darmo" #153 — Jak wybierać spółki do portfela?* (episode
  index/notes), doradca.tv, mod. 2025-07-15.
  `https://www.doradca.tv/pawel-malik-jak-wybierac-spolki-do-portfela/`
  (audio: Spotify ep. `4hPjPoPQjmBD6Wdo4V3HkH`).
- **[DGN]** Malik's own analysis *"Digital Network SA na ścieżce wzrostu"*,
  2025-09-18. `https://portalanaliz.pl/analizy/digital-network-sa/`.
- **[AUT]** Author page (analysis list — DGN, Śnieżka, DINO, Wawel, Quercus,
  ATM, Enter Air…). `https://portalanaliz.pl/author/pawel-malik/`.
- **[YT]** *"Moja strategia inwestycyjna oraz błędy młodości…"*, YouTube
  `TZmetBqYAOI` — his own strategy talk (transcript not extractable; cited by
  title/topic only).
- **[SW]** sWIG80 profile — average constituent cap **≈ 1 mld zł** (Saxo Bank /
  SII) — anchor for the size threshold. `https://www.home.saxo/pl-pl/learn/guides/equities/indeks-swig80-analiza-inwestycji-w-male-spolki`.

Source-material files (reconciled in full below): `[M1]` `Filozofia_…OBS_Portfel_IKE.md`
(digest of [F]); `[M2]` `obs.txt` (raw [F]); `[M3]` `Strategia_Inwestycyjna_Pawla_Malika.pdf`
(a **secondary** *opracowanie*, not a primary quote source); `[M4]`
`transkrypcja_biznesradar_excel.docx` (**primary** transcript of Malik's own
BiznesRadar→Excel video). (`pa-scraper.zip` is code, out of scope.)

## Philosophy in one page

Malik is a licensed *doradca inwestycyjny* who has analysed **small/mid caps
not covered by brokerage recommendations** for ~12 yrs (blog GazetaGiełdowa, co-founder
of PortalAnaliz; 2026 SII *Heros Rynku Kapitałowego — Analityk Giełdowy*) [ON].
His public IKE compounded at **XIRR ~35 %** to >3,3 mln zł, negative in only one
year (2018) [M3][F]. Three load-bearing ideas:

1. **Stock-picking, not timing.** *"Nie jestem mistrzem timingu. Czuję się
   dobrze w selekcji."* [F] He doesn't predict hossa/bessa or cut the portfolio
   on macro; edge = selection. (Cash *does* build when no undervalued idea
   exists — a bottom-up by-product, not a market call [SB][M3].)
2. **Sprawozdania-first.** *"Nie kupuję spółek bez analizy sprawozdań."* [F]
   The **rachunek zysków i strat is the entry point**; he pastes quarterly
   BiznesRadar data into Excel and tracks **marża na sprzedaży brutto** and
   **dźwignia operacyjna** quarter-to-quarter [M4][SB].
3. **Teza-first, then patience.** For every buy he needs a **teza inwestycyjna**
   — *"co się zadzieje, żeby wyniki się poprawiały i rynek to docenił"* [F] — a
   concrete **katalizator** the market hasn't priced yet [M3][SB]; then the hard
   part: *"trzyma akcje spółki, dopóki perspektywy są dobre"* [DGN]. Each report
   re-verifies the thesis; if it breaks, he exits regardless of P&L [F][SB].

His edge is deliberately in **small caps** — big money and sell-side crowd the
large caps, *"można zakładać, że już wszystko jest w cenach"*, whereas in small
caps *"zanim coś dotrze na rynek, można to przewidzieć"* [SB]; he dislikes
static *molochy* (*"nie lubię spółek typu Orlen"*) [F]. **Digital Network**
(ex-4fun Media) is his textbook catch. Two separately sourced facts are retained:
a PortalAnaliz POS flag in Feb 2023 and his later description of the company's
historical *"+2500 % w ciągu 5 lat…"* path [DGN]. The latter is not treated as a
return measured from the POS flag.

## Screening principles → dossier fields

Every row is cited; every row names a computed field **or** a labelled gap.
Fields refer to `insights.py` Insight ids / `metrics.py` outputs consumed by the
dossier. Evidence: **S**=multiple primary sources, **M**=one primary, **W**=weak/inferred.

| # | Principle (Malik) | Cite | Ev | Dossier field — or **gap** |
|---|---|---|---|---|
| 1 | Stock-picking over market timing; entry-quality is an analysis entrance, not a signal | [F][SB] | S | *Framing* — governs `entry_quality` + `disclaimer`; not a number |
| 2 | Sprawozdania/P&L first; growth = **rising revenue** | [F][SB][M4] | S | `revenue_growth` (revenue_yoy_pct); prescore `revenue_growth` |
| 3 | **Marża na sprzedaży brutto** is the key motor, watched as a trend | [M4][SB][M1] | S | `gross_margin` (+trend); prescore `gross_margin_trend` |
| 4 | **Dźwignia operacyjna** — profit growing faster than sales | [M4][M1] | S | `operating_leverage`; prescore `operating_leverage` |
| 5 | Profit **quality**: durable vs one-off (pozostała dz. operacyjna, księgowe wyskoki) | [SB][M1] | S | `one_offs` (one_off_share_pct); prescore `profit_quality` |
| 6 | Valuation = **forward C/Z vs the company's OWN history**, not vs market | [F][SB][M1][M4] | S | `pe_vs_history` (current vs median) + forward `latest_forecast.result.forward.pe`, fallback `ttm.pe` |
| 7 | Cheap **alone is insufficient** — needs a katalizator; *"C/Z… nigdy nie biorę jako wystarczającej przesłanki"* | [SB][M3][F] | S | `pe_vs_history` treated as necessary-not-sufficient + **gap: katalizator** |
| 8 | **Margines bezpieczeństwa** = low valuation + **backlog** + **gotówka netto** together (OPTEX: P/E~12, prog.<10, rosnący backlog) | [F][M1] | S | `net_cash` + `pe_vs_history`; **gap: backlog / portfel zamówień** |
| 9 | Small-cap **sweet spot**; avoid *molochy*; sWIG80 his favourite index | [SB][ON][F][DT] | S | `classify_size` / prescore `small_cap` (see valuation doctrine on the number) |
| 10 | **Balance-sheet safety**: net cash a plus; watch debt | [SB][M1] | S | `net_cash`, `debt_load`, `cwk`, `liquidity` |
| 11 | Cash-flow quality: operating CF vs profit, CAPEX capitalisation, receivables/inventory turnover | [SB] | M | **gap: needs human check** (not fully computed) → `verify_next` |
| 12 | **Dividend = bonus**, never the foundation | [M1][M3] | S | `dividend` (low importance) |
| 13 | Sell when thesis stops confirming / improvement was one-off | [F][SB] | S | partial `one_offs`; **gap → verify_next** (re-verify after next report); no sell signal |
| 14 | **Management credibility & ład korporacyjny** (related-party txns, mgmt pay, unmet promises; FAM/minority abuse) | [F][SB] | S | **gap: needs human/AI check** → `verify_next` |
| 15 | Position sizing ~**10 %** max, **~10–kilkanaście** spółek | [M3][F] | S | **gap: portfolio-level** — out of per-stock scope |
| 16 | Avoid hype/"modne" tech, US growth, hard-to-value NewConnect PR | [F][M1] | M | **gap: qualitative** → honesty note when data thin |

## Valuation doctrine

- **Forward C/Z first.** Malik forecasts the *next quarter's* result and asks
  how the market will re-rate it [SB][M4]; he compares that **forward C/Z to the
  company's own historical C/Z**, *"a nie tylko do rynku czy branży"* [M1][F].
  Engine: prefer `latest_forecast.result.forward.pe`; **fall back to `ttm.pe`
  when no forecast exists, and say which** (`valuation_basis`). No DCF, no target
  price — *"czym dalszą przyszłość prognozujemy, tym większym błędem jest
  obarczona"* [SB]. This is exactly `spec_pe_vs_history` (good < 0.85× own
  median; neutral ≤ 1.15×; else *"rynek już wycenia poprawę"*).
- **Cheap is necessary, not sufficient.** *"Samo C/Z czy C/WK są zwodnicze"*
  [SB]; low multiple must pair with a growth signal + catalyst, else it's a
  value trap ("tanie nie bez powodu") [M3].
- **Margin of safety = a trio, not a single ratio:** low valuation **+** rising
  backlog **+** net cash [F][M1]. The engine can see two legs (`pe_vs_history`,
  `net_cash`); **backlog is a gap** → so a data-only "attractive" is provisional
  and must push *"zidentyfikuj katalizator/backlog"* to `verify_next`.
- **The size number is ours, not his.** Malik states a **qualitative** small/mid
  preference (sWIG80, spółki bez pokrycia) [SB][ON][DT]; he does **not** publish
  a PLN cutoff. The repo's `SMALL_CAP_THRESHOLD_PLN = 1 mld` operationalises it,
  anchored to sWIG80's ~1 mld avg cap [SW]. Keep it labelled as an
  operationalisation, not a Malik quote.

## Entry-quality decision rule (confirms WP2 reference)

Sources support the WP2 rule; tuning notes below. All thresholds → named constants.

- **`attractive`** — valuation good (forward-preferred C/Z **< 0.85× own
  median**) **AND** ≥1 visible growth signal (`revenue_growth` good **OR**
  `gross_margin` rising **OR** `net_profit_trend` good) **AND** `net_cash ≥ 0`,
  with **no dominant red flag** (high `one_offs`, or net loss + net debt).
  Small/micro size **adds** weight (sweet spot). *Tuning:* because the
  **katalizator is uncomputable**, engine-`attractive` = *"attractive setup,
  catalyst to confirm"* — `verify_next` must always carry catalyst + next-report
  re-check. Profit-quality is a **veto**: a good C/Z on one-off profit is the
  classic trap [SB][M1] → high `one_offs` blocks `attractive`.
- **`weak`** — C/Z **above** own median (*"rynek już wycenia poprawę"*) **OR**
  ≥2 high-importance `bad` factors **OR** net loss with net debt.
- **`insufficient_data`** — < 3 computable key indicators **OR** neither a
  valuation nor a growth signal available (honesty over a guessed verdict).
- **`neutral`** — everything else.

## Reconciliation with existing docs

- **[M1] digest & [M2] raw forum** — the primary spine; everything above traces
  to them. Nickname **"OBS"** was read by a forum user as *"Only the Best
  Stocks"* [M2] — plausible but **not author-confirmed**; treat as folk gloss.
- **[M3] PDF *opracowanie*** — broadly **consistent** and adds the crisp
  *katalizator* framing, the IKE end-2025 figures and a "7 złotych zasad"
  summary. But it is a **secondary compilation**; its in-quotes lines are not
  independently sourced here, so **do not treat PDF quotations as primary** —
  prefer [F]/[SB]/[M4] wording.
- **[M4] DOCX transcript** — **direct primary evidence** for principles 3, 4, 6:
  his real workflow is quarterly BiznesRadar→Excel, watching **marża ze
  sprzedaży brutto** + **dźwignia operacyjna** and building a **next-quarter
  forecast**. Strongest corroboration of the valuation doctrine.
- **Codebase** — `insights.py`/`metrics.py` already encode principles 2-10, 12;
  the `pe_vs_history` thresholds and `SMALL_CAP_THRESHOLD_PLN` match his
  own-history + small-cap logic. No contradiction; WP2 only **composes/weights**
  these, recomputing nothing.
- **Two genuine evolutions (note, don't flatten):** (a) **Foreign stocks** — in
  2018 *"nie inwestowałem nigdy w spółki zagraniczne"* [SB]; by 2021-25 he held
  US names (OPTEX) under a harder ~20 % stop [F]. App is GPW-only, so moot. (b)
  **Holding horizon** — 2018 event-driven, short [SB]; later multi-year holds of
  compounders (DGN) [DGN]. Shared invariant both times: *hold while perspectives
  are good and valuation hasn't outrun future results.*

## Implications for the thesis engine (WP2 weights/priorities)

- **Two pillars, top weight:** (1) growth signal — `revenue_growth` +
  `gross_margin` trend + `operating_leverage`; (2) valuation vs own history
  (`pe_vs_history`, forward preferred). These drive `entry_quality`.
- **Profit-quality (`one_offs`) is a discount/veto**, not a side note — it
  guards pillar 2 against one-off "cheapness".
- **Safety leg:** `net_cash` (+`debt_load`); **bonus/low:** `dividend`;
  **size** modifies weight (small/micro +, mid/large −).
- **Gaps WP2 must respect (route to `verify_next`, never fabricate):**
  1. **Katalizator** ("co ma się wydarzyć") — uncomputable.
  2. **Backlog / portfel zamówień** — not scraped (breaks the margin-of-safety trio).
  3. **Management credibility / ład korporacyjny.**
  4. **Cash-flow quality** (operating CF vs profit, CAPEX, receivables/inventory).
  5. **Thesis re-verification after the next report.**
  6. **Portfolio concentration / sizing** — portfolio-level, not per-stock.
- **Forward-C/Z honesty:** state `valuation_basis` (forward vs trailing) and flag
  a missing forecast; own-C/Z history is only as deep as BiznesRadar shows.

## Unverified / open questions

- **Synektik (SNT) "early" catch — UNVERIFIED.** No primary Malik document found
  tying him to an early SNT call; do not assert it as a Malik catch. (SNT appears
  in the repo only as a scraper fixture.)
- **DGN "near 20 PLN years before repricing"** — association with the author
  and the historical winner is verified (his analyses; POS Feb 2023;
  *"+2500 %/5 lat"* [DGN]), but these facts do not establish a post-POS return.
  The specific **20 PLN entry price is not** sourced — leave it unstated.
- **"< 1 mld zł" cutoff** — operationalisation, not a Malik-stated figure (see
  valuation doctrine).
- **[YT] transcript** not extracted — cited by title/topic only, no verbatim
  quotes attributed to it.
- **"OBS" = "Only the Best Stocks"** — community reading, not author-confirmed.
