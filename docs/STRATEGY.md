# Strategy and sieve contract

## Role of strategy material

Investor methods are versioned analytical lenses, not authority and not a
substitute for evidence. Each method pack declares what it needs, what it can
calculate, what remains judgment, and how it can be evaluated later. Methods
stay separate so the user can compare them or deliberately choose a blend.

Unknown factors are excluded from a fit denominator and shown as coverage gaps.
No method may turn missing data into a negative company fact.

## Method-pack governance

Each expert-derived method is represented by a versioned pack, not by a
simulated persona. Its manifest declares:

- stable identifier, version, neutral label, attribution and a non-endorsement
  disclaimer;
- retained source manifest with document version/hash, publication or known
  date, exact locator, author identity, and retention status;
- readiness separately for Discover, Research, and Valuation, because a pack
  may be usable for company Research before market-wide Discover inputs exist;
- required and optional factors or questions, each labelled as author-stated,
  standard finance, or a Workbench operationalization;
- deterministic formulas, judgment questions, compatible archetypes and
  templates, red flags, falsifiers, exclusions, and known blind spots;
- skill, output-schema, calculation-engine, and verifier versions; and
- evaluation maturity: `untested`, `diagnostic-cases`, or
  `point-in-time-calibrated`. Readiness never implies proven performance.

Stage readiness is explicit: `draft` means source or interpretation coverage is
insufficient; `planned` means the contract exists but serving data is missing;
`supported` may produce decision-support output subject to company coverage;
and `retired` is preserved only for historical artifacts and replay.

A new pack version is required when selection rules, required inputs,
calculations, material judgment framing, or source interpretation changes.
Every Research, Valuation, synthesis, and backtest artifact freezes the exact
pack and method-source versions it used. Method-source corpora remain separate
from company-evidence manifests.

Method outputs remain separate. Codex may synthesize them only after showing
each applicable pack's conclusion, evidence coverage, disagreement, and
company-specific blind spots. A deliberate blend is itself named and versioned,
preserves every input contribution, and is never labelled as one expert's
method. Expert popularity, reputation, anecdotal performance, or agreement
between packs cannot increase company confidence by themselves.

The strict verifier checks attribution, source sufficiency, method
applicability, separation of fact/calculation/judgment, unknown handling,
look-ahead boundaries, non-impersonation, and whether synthesis accurately
represents disagreement.

## Current method readiness

| Method | Discover | Research | Valuation |
|---|---|---|---|
| Malik/OBS | `planned` — market-wide factors are missing | source-grounded Codex lens exists; canonical persisted/rendered perspective is planned in M1 | `supported` — `malik_obs_v1` is ready |
| Areczeks | `draft` — retained method evidence and market inputs are incomplete | `draft` | `draft` |
| Elendix | `draft` — partial retained evidence and market inputs are incomplete | `draft` — two dated fragments are not a reproducible method | `draft` |

The financial-health BiznesRadar sieve is a supported deterministic data lens,
not an expert-derived method pack.

## Source hierarchy

For interpreting an investor method, highest confidence comes from that
investor's own dated writing, interviews, and worked analyses. For current
company facts, issuer and regulatory documents plus lineage-linked
deterministic records outrank investor commentary. Investor material supplies
analytical questions, lenses, and attributed leads; it never supplies
unsourced company numbers or proves that its author endorses the Workbench
interpretation.

Retained local method-source evidence includes:

- `docs/source-materials/obs.txt` — raw PortalAnaliz OBS portfolio thread;
- `docs/source-materials/transkrypcja_biznesradar_excel.docx` — Malik's
  BiznesRadar-to-Excel workflow transcript.

The retained OBS thread also contains two dated Elendix entries that establish
only partial provenance: a 2022 discussion of discount-rate mechanics and a
2024 question about risk/reward, liquidity, and a complete investment cycle.
They are visible in the draft catalog with their exact locators and hash. They
do not establish selection rules, a company conclusion, or a reproducible
method.

Useful public references include the PortalAnaliz OBS thread, PortalAnaliz
author/about pages, and investor portfolio threads. Forum statements are
opinions and require attribution. The repository has no retained Areczeks
corpus and only the partial Elendix coverage above. Both packs remain draft
until relevant source snapshots and citations establish their methods.

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

Draft. Two retained thread fragments establish only a discount-rate explanation
and questions about risk/reward/process; they do not justify the expected
emphases below as author-stated rules. Fuller dated source snapshots are needed
before any Research or Valuation pack can be reconstructed. Until then,
normalized earnings, event/unit-economics modelling, adjusted enterprise value,
relative opportunity cost, upside/downside asymmetry, and catalyst confirmation
remain unverified hypotheses—not Elendix method claims.

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

The first canonical implementation is deliberately narrow. It uses an
archetype-framed earnings/C-Z bridge for industrial/consumer and
software/services companies: revenue growth, gross margin, operating-cost
ratio, financial result, tax, cash conversion, positive capex spend and target
C/Z produce next-quarter and F12M P&L, CFO, FCF, EPS and price. A non-positive
F12M EPS has no C/Z price. An optional event must be mutually exclusive and
show its one-off explicitly. The UI labels every starting value as a human
assumption; it never promotes a seed to evidence.

Own-history multiple reversion stays unavailable until a comparable,
point-in-time series exists. Current raw prices and timestamp-frozen
shares/market cap remain visible provisional limitations. This first bridge is
not a DCF, unit-economics model, proof of Malik/OBS performance, or permission
to blend the blocked Areczeks/Elendix packs.

## Cross-method Codex synthesis

For one company and as-of time, Codex may produce a synthesis only from
supported, applicable packs and the same frozen company-evidence set. It must
state:

- why each pack is or is not applicable;
- conclusions shared across packs without treating them as independent votes;
- material disagreements and the assumptions causing them;
- risks or questions visible through only one pack;
- missing evidence that could change the comparison; and
- the next dated evidence checks, without a buy/sell instruction.

Draft or planned packs may be shown as unavailable perspectives with named
source or data gaps, but their expected company conclusions must not be
invented. The default product path uses the canonical `ResearchSnapshot` and
`ValuationSnapshot`; legacy analysis or alignment scores do not become a
universal expert-backed verdict.

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
