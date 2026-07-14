# Strategy contract — one Workbench strategy

Defers to `docs/VISION.md` (V1, V2, V4, V8). There are no method packs, no
author-branded perspectives, and no per-investor lenses in the product. The
retained investor materials are raw ore: they were read once, the useful
mechanics were extracted, and the result is a single versioned Workbench
strategy split into two engines — the **sieve** (Discover) and the
**valuation lens** (Valuation). Source files stay in `docs/source-materials/`
for audit; their authors are never displayed.

## What was actually taken from the sources (synthesis, not attribution)

From the retained materials (a PortalAnaliz portfolio thread, a
BiznesRadar-to-Excel workflow transcript, and PA opportunity write-ups) the
Workbench keeps these mechanics, merged into one strategy:

1. **Improvement beats cheapness.** The core question is "what can be better
   next quarter/year, and is it already priced in?" — revenue drivers,
   margin trend, operating leverage, durable result vs one-offs.
2. **Compare a company against its own history**, not only cross-section:
   forward multiple vs the company's own historical range; today's dynamics
   vs its own base period.
3. **Cash is evidence.** Operating cash conversion, working capital, capex,
   net cash/debt — margin-of-safety facts, not narrative.
4. **Value needs asymmetry and a mechanism.** Defined downside, plausible
   upside path, a concrete catalyst with a horizon, and capital-allocation
   discipline (dividend/buyback, insider reference prices).
5. **Every thesis needs a falsifier** — a dated, checkable statement that
   would prove it wrong.
6. **Financial health is a floor, not a verdict** — Altman EM-Score and
   Piotroski F-Score narrow the universe; they never conclude it.

Anything not listed here that appears in the sources is deliberately unused.
New source material may extend this list only through a new strategy
version.

## Engine 1 — the sieve (`workbench_sieve_v1`)

Exclusion-first over a versioned market-wide factor snapshot (immutable
BiznesRadar market pages: rating, value multiples, profitability, debt,
dynamics; premium session where needed). Server-owned rules; a rule change
is a new sieve version. Missing data is a visible coverage gap, never a
synthetic negative — hard kills fire only on *present* bad facts, with the
single exception of fundamentals that must exist (equity).

**Layer A — wykluczenia (any hit → out, reason stored):**

| Rule | Kill condition (v1) |
|---|---|
| A1 zagrożenie wypłacalności | Altman EM-Score value < 4.0 (distress zone) |
| A2 zapaść jakości | Piotroski F-Score ≤ 3 |
| A3 ujemny kapitał własny | book value ≤ 0 (C/WK non-computable from negative equity) |
| A4 trwały regres | revenue r/r < 0 **and** operating profitability falling in the same snapshot |
| A5 dźwignia ekstremalna | net debt / EBITDA > 6 (where EBITDA > 0; else general debt ratio ceiling) |
| A6 brak obrotu | no price/turnover data in the snapshot window |
| A7 chroniczna strata | trailing net loss **and** F-Score ≤ 5 (loss without improvement signal) |

**Layer B — wymóg poprawy (survivors must show ≥ 2, else out as
`stagnacja`):**

- B1 F-Score ≥ 6 (year-over-year quality improving);
- B2 revenue r/r > 0;
- B3 operating margin / profitability trend up vs prior period;
- B4 C/Z (or sector-appropriate multiple) below the company's own snapshot
  history median — cheaper than usual *while* B1–B3 give a mechanism;
- B5 net cash or falling net debt.

Survivor ordering: count of B-signals, then magnitude of improvement deltas.
Ordering is presentation; membership is the contract. Every survivor row
exposes its passed/failed factors with values, deltas vs own history,
source document version, and freshness. Excluded companies keep kill
reasons and stay inspectable.

Thresholds are v1 starting points, expected to be tuned — every tune is a
new version with a one-line rationale in this file's changelog section.

## Engine 2 — the valuation lens (V4)

Applied by the Codex valuation skill to one company's frozen research
snapshot. The lens dictates *what must be reasoned about*; all numbers come
from the company's own evidence:

1. Identify the 2–4 drivers that actually move this company's next
   quarter/year (from research Outlook), and state the mechanism per
   scenario (bad/base/good, optional mutually-exclusive event).
2. Set assumption values per scenario bound to fact IDs (reported dynamics,
   backlog, contracts, margin history) or named judgment with rationale.
3. Distinguish durable result from one-offs; model cash conversion and
   capex explicitly.
4. Choose the valuation bridge appropriate to the archetype (earnings
   multiple vs own history band, sector marker where earnings are
   meaningless); never re-rate above own-history evidence without a stated
   mechanism.
5. Assign probabilities from evidence weight (catalyst proximity, base-rate
   of the driver materializing, management credibility facts) — with the
   rationale written down. House defaults do not exist.
6. State per scenario: catalyst, counter-driver, falsifier with a date.
7. Net cash, backlog, and cash conversion function as margin-of-safety
   adjustments, stated explicitly.

Structural gates (enforced in backend code, not by agent goodwill):
probability sum ≈ 100, no seed/default equality, no cross-company
near-duplicate assumption vectors, every probability has rationale text and
every core assumption has fact bindings or an explicit judgment flag, math
recomputation matches, drafter ≠ verifier.

## The learning loop (V8)

Valuation is an engine that improves, which requires scoring:

- When the next actual report lands for a valued company, an outcome job
  compares actuals against every live scenario set: direction correct?
  actual inside bad↔good range? which scenario was closest? probability
  calibration (Brier) per engine version.
- Scores persist per company and per engine/skill version and render in the
  Valuation stage. A version that scores worse than its predecessor on the
  rolling window is a regression to investigate, not a coin flip.
- No optimized weights and no performance claims until a point-in-time
  replay exists (frozen universe incl. delistings, corporate-action-adjusted
  total returns, frozen versions, holdout, 3/6/12/24-month windows).

## Source hierarchy

For company facts: issuer/regulatory documents and lineage-linked
deterministic records outrank everything. Market data pages are versioned
snapshots. Forum/commentary material may suggest what to inspect; it never
supplies company numbers. Derived summaries never leak into point-in-time
replays.

## Changelog

- `workbench_sieve_v1`, valuation lens v1 — initial synthesis replacing the
  three author-branded sieves and method packs (2026-07, per VISION).
