# Scoring rubric — alignment_score 0–100

How to turn the checklist read into a single `alignment_score`. The score
answers one question: **how well does this company fit Malik's strategy right
now**, given what the dossier can actually see. It is not a price target and not
a buy signal.

## The one rule that dominates: unknown ≠ fail

Malik's strategy leans on things the dossier cannot compute (catalyst, backlog,
management credibility, cash-flow quality). If those counted as failures, every
company would score low for reasons that are really *our data gaps*, not the
company's flaws.

So: score each item as **spełnia** (meets), **nie spełnia** (fails), or
**nieznane** (unknown). **`nieznane` items are removed from the denominator** —
they neither add nor subtract. The score is:

```
alignment_score = round(100 × Σ(earned weight on known items)
                              / Σ(weight of known items))
```

Then apply the vetoes and the catalyst cap below. If fewer than **3** key
indicators are computable, do **not** emit a number — return the verdict
`insufficient_data` and an honest `summary_pl` instead.

## Item weights

Weights reflect Malik's own priorities: the two growth motors and own-history
valuation carry the most; safety and quality are meaningful guards; dividend and
framing are light. Portfolio-level items are out of per-stock scope and unweighted.

| # | Item | Weight | Meets when… |
|---|------|-------:|-------------|
| 2 | Revenue growth | 12 | `revenue_growth` good (rising yoy) |
| 3 | Gross-margin trend | 15 | `gross_margin` rising |
| 4 | Operating leverage | 12 | profit growing faster than sales |
| 5 | Profit quality (durable vs one-off) | 12 | `one_offs` low; jump is core-driven |
| 6 | Valuation vs own history | 15 | forward-preferred C/Z < 0.85× own median |
| 7 | Catalyst present & not priced in | 10 | a concrete, not-yet-priced catalyst is named |
| 8 | Margin-of-safety legs (net cash + valuation) | 8 | `net_cash ≥ 0` and cheap vs own history |
| 9 | Small-cap sweet spot | 6 | small/micro cap; not a moloch |
| 10 | Balance-sheet safety | 6 | net cash / manageable debt, ok liquidity |
| 12 | Dividend (bonus only) | 2 | pays a dividend — small positive, never required |
| 1 | Framing / entry-quality coherence | 2 | verdict is internally consistent |
| **—** | **Total weightable** | **100** | |

Out of per-stock scope (never scored, may appear in `verify_next`): #11 cash-flow
quality, #13 sell discipline, #14 management credibility, #15 position sizing,
#16 hype-avoidance. Items #7 and #14/#11 are usually **nieznane** from data
alone — that is expected and correct.

## Vetoes (cap the score regardless of the weighted sum)

- **One-off profit veto** — if the profit improvement is materially one-off
  (high `one_off_share_pct`), a cheap multiple is an illusion: cap
  `alignment_score` at **50** and flag it in `red_flags`.
- **Balance-sheet veto** — net loss **and** net debt: cap at **40**.
- **No-catalyst cap** — if no catalyst can be named (item 7 fails or is
  unknown), cap at **75**. A company can look statistically perfect and still
  not be a Malik buy without a catalyst — the cap encodes "cheap ≠ sufficient".

Apply the **lowest** applicable cap.

## Bands (interpretation, not instruction)

- **80–100** — strong fit: cheap vs own history, durable growth motor, net cash,
  and at least a candidate catalyst. Still requires human catalyst + governance
  confirmation.
- **60–79** — partial fit: some pillars present, usually missing the catalyst or
  carrying a quality/safety caveat.
- **40–59** — weak fit: valuation above own median, thin growth, or a one-off
  veto in play.
- **< 40** — poor fit or a balance-sheet veto.

## Consistency with the engine

The narrative verdict must not contradict its own score, and both should track
the deterministic `entry_quality` (`attractive` / `neutral` / `weak` /
`insufficient_data`). If you score, say, 82 while the engine says `weak`, either
your evidence genuinely overrides the engine (justify it explicitly) or the
score is wrong. Prefer agreement; explain every divergence.
