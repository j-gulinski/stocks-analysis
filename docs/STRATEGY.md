# Strategy and sieve contract

## Role of strategy material

Investor methods are versioned analytical lenses, not authority and not a
substitute for evidence. Each method pack declares what it needs, what it can
calculate, what remains judgment, and how it can be evaluated later. Methods
stay separate so the user can compare them or deliberately choose a blend.

Unknown factors are excluded from a fit denominator and shown as coverage gaps.
No method may turn missing data into a negative company fact.

## Source hierarchy

Highest confidence comes from the investor's own dated writing/interviews and
worked analyses. Retained local source evidence includes:

- `docs/source-materials/obs.txt` — raw PortalAnaliz OBS portfolio thread;
- `docs/source-materials/transkrypcja_biznesradar_excel.docx` — Malik's
  BiznesRadar-to-Excel workflow transcript.

Useful public references include the PortalAnaliz OBS thread, PortalAnaliz
author/about pages, and investor portfolio threads. Forum statements are
opinions and require attribution. The repository currently has only partial,
unretained source coverage for Areczeks and Elendix; their packs remain draft
until the relevant snapshots and citations are stored.

Reference URLs:

- `https://portalanaliz.pl/forum/viewtopic.php?f=7&t=569` — OBS portfolio thread;
- `https://portalanaliz.pl/o-nas/` — PortalAnaliz investor/author context;
- `https://www.biznesradar.pl/spolki-rating/` — market-wide Altman/F-Score data;
- `https://www.biznesradar.pl/rating/FTH` — BiznesRadar explanation of the
  Altman financial-condition/distress interpretation.

Derived summaries and realised example outcomes are not primary evidence and
must not leak into current-company prompts or point-in-time backtests.

## Three Discover sieves

### `financial_health_br_v1` — Kondycja finansowa

Status: first supported market-wide sieve.

Inputs: BiznesRadar Altman EM-Score grade/value and Piotroski F-Score.
The versioned selection rule is server-owned: Altman value `>= 8.0` and
Piotroski F-Score `>= 7`. Request callers may paginate results but cannot
change membership without a new sieve version. The API returns these thresholds
with the immutable source-document and parser versions.

- Altman EM-Score estimates financial condition/distress risk; a high grade is
  not “the best stock”.
- Piotroski F-Score summarizes nine year-over-year profitability, leverage/
  liquidity, and operating-efficiency signals; it is not a valuation.
- Result factors show their real names, values, contribution, source version,
  and the missing strategy questions.

This sieve narrows the universe. It does not claim a catalyst, durable growth,
governance quality, or attractive price.

### `obs_operating_improvement_v1` — Wyniki i katalizator

Status: planned; do not publish until the market-wide factor snapshot exists.

Malik/OBS starts from reports and asks what can improve the next quarter/year
and whether the market already discounts it. Required factors:

- revenue trend and expected revenue driver;
- gross-margin trend and operating leverage;
- durable core result versus one-offs;
- operating cash conversion, working capital, capex, and net cash/debt;
- forward C/Z or another suitable multiple versus the company's own history;
- concrete catalyst/backlog, horizon, and priced-in assessment.

Discovery may use deterministic proxies, but catalyst and management credibility
remain explicit gaps until Research. A cheap multiple without an improvement
mechanism does not pass.

### `pa_value_catalyst_v1` — Wartość i asymetria zdarzeń

Status: draft pending retained Areczeks/Elendix source evidence and a bounded
market-wide data snapshot.

This sieve deliberately combines complementary PortalAnaliz opportunity
factors while preserving each factor's origin:

- EV/EBITDA, ROE/ROIC, C/WK, liquidity, debt, and net cash relative to market
  value;
- normalized EBIT/earnings and base-effect checks;
- PEG or business-specific unit economics where meaningful;
- dividend/buyback and capital-allocation discipline;
- insider/major-shareholder reference prices and management credibility;
- policy, regulatory, contract, product-launch, or other event economics;
- valuation asymmetry: defined downside, plausible upside mechanism, and time
  horizon.

Soft attention/forum signals may suggest what to inspect but never add a hard
score. The UI must expose which factors come from Areczeks, which from Elendix,
and which are Workbench operationalizations.

## Valuation method packs

### Malik/OBS

- Forecast the next quarter and year from company drivers.
- Prefer forward earnings and compare the chosen multiple with the company's
  own history.
- Distinguish durable operating improvement from one-offs.
- Require a catalyst and falsifier; cheapness alone is insufficient.
- Treat net cash, backlog, and cash conversion as margin-of-safety evidence.

### Areczeks

Draft until source snapshots are retained. Expected emphasis: balance-sheet
strength, multiple/quality set, insider alignment, policy/contract catalysts,
capital returns, and disciplined position/risk framing.

### Elendix

Draft until fuller source snapshots are retained. Expected emphasis: normalized
earnings, event/unit-economics modelling, adjusted enterprise value, relative
opportunity cost, explicit upside/downside asymmetry, and adding only when the
catalyst confirms.

Each pack supplies questions, compatible templates, valuation lenses, red
flags, and falsifiers. It never supplies unsourced company numbers.

## Scenario output

Every researched valuation contains mutually exclusive downside/base/upside
outcomes and an optional event outcome. Per outcome store:

- mechanism and horizon;
- probability plus evidence/rationale;
- named driver assumptions and provenance;
- deterministic next-quarter/year revenue, operating result, net result,
  EPS/FCF or sector-marker effects;
- valuation bridge and price range;
- catalyst/counter-driver and falsifier;
- calculation and verifier status.

Probabilities should sum to approximately 100%. Show unweighted ranges beside
probability-weighted values. A provisional scenario still shows the full
computed picture and names the assumptions that replace missing evidence.

## Backtest and learning gate

Do not optimize strategy weights or publish performance from current serving
data. A valid replay requires:

- facts and source versions available as of the historical decision time;
- a declared point-in-time universe including failures/delistings;
- corporate-action-aware total-return prices and benchmark;
- frozen method/template versions and no outcome text in prompts;
- mixed cases, untouched holdout, and 3/6/12/24-month outcome windows;
- direction/range accuracy, falsifier timing, Brier/calibration measures, and
  costs/latency.

Small worked cases diagnose contracts; they do not prove an investor method.
