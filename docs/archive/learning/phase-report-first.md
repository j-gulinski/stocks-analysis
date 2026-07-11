# Learning note — report-first research and source tactics

## Why the UI is now a report, not a database browser

The workbench stores more evidence than a person should read on every visit.
The default company screen is therefore a prepared read model: conclusion,
four key numbers, result-quality bridge, important factors, risks, next checks
and a small set of charts. Raw statements, forum leads and historical model
runs remain available only in audit views.

For a C# analogy, Postgres plus source versions are the write/domain model,
while the company report is a small CQRS read model. Adding a source field does
not automatically add a UI tile. It earns a place only when it changes a
decision or explains uncertainty.

The same separation now applies to the analysis queue. `agent_runs` is a
durable command table; FastAPI does not contain a Codex runtime. A local Codex
automation is the hosted-service equivalent: it starts/checks the app, claims
one command and writes the verified result back. `queued` therefore means
"persisted and waiting", not "a thread is already reasoning".

## How to read and run scenarios

The current scenario set is a deterministic projection rebuilt from the latest
dossier, not model prose. Think of `build_scenario_set` as a pure C# domain
service: the same facts and assumptions produce the same negative/base/positive
rows and weighted potential. Saving a forecast changes an explicit input; the
next dossier read recomputes the projection. Codex interprets and challenges
the result later, while the strict verifier owns the displayed confidence and
score.

This distinction matters because scenario v1 mainly tests reversion to the
company's own valuation history. It does not yet simulate company drivers such
as backlog conversion or contract timing. Those are researched and reported as
evidence/gaps now; RT.4 will make them first-class scenario equations.

## Reported profit versus continuing profit

An explicit discontinued-operation result is subtracted from reported net
profit only when every quarter in the TTM window contains that row. Missing is
never treated as zero. The system keeps both views:

- reported net profit/EPS/C/Z for reconciliation with the source;
- continuing net profit/EPS/C/Z for decision-related valuation when the bridge
  is complete.

Synektik is the motivating case: the latest statement proves a large
discontinued result, but the economic cause cannot be considered durable app
evidence until an official issuer/ESPI document is persisted. The prepared
report therefore explains the bridge and stays a draft instead of showing the
raw `477.7%` proxy as a headline KPI.

## What PortalAnaliz portfolio records can teach us

Public portfolio performance can prioritize a process tactic, not validate a
company claim. A bounded audit found the strongest accessible record in the
collective FIPA portfolio: a reported four-year return of `+239.7%` for
2020–2023, contemporary transaction commentary, disclosed cash movements,
benchmarks and material drawdowns. The record is useful but still
`needs-human`: the exact TWR/XIRR method is not published on PortalAnaliz.

Reusable rules receiving higher research priority:

- write the case, maximum acceptable price and invalidation before execution;
- compare the current thesis with the frozen prior thesis after every report;
- prefer patience/low turnover while operating drivers improve;
- review concentration after exceptional gains;
- keep a point-in-time decision journal.

The older individual IKE record is long (2011–2020) but methodologically less
reproducible: the published `+380%` portfolio-value increase and `31% average
annually` cannot be reconciled without dated contributions and a TWR/XIRR
calculation. It remains a lead, not an authority multiplier.

Public audit sources:

- [FIPA 2020](https://portalanaliz.pl/artykuly-edukacyjne/portfel-czytelnikow-portalu-analiz-podsumowanie-2020-roku/)
- [FIPA 2021](https://portalanaliz.pl/artykuly-edukacyjne/portfel-czytelnikow-portalu-analiz-zarobil-56-procent-w-2021-roku/)
- [FIPA 2022](https://portalanaliz.pl/artykuly-edukacyjne/na-gieldzie-wiekszosc-nie-ma-racji-za-wyjatkiem-abonentow-pa-wyniki-portfela-akcji-czytelnikow-za-2022-rok-i-ostatnie-3-lata/)
- [FIPA 2023 / four years](https://portalanaliz.pl/artykuly-edukacyjne/portfel-czytelnikow-portalu-analiz-fipa-wyniki-za-2023-rok-i-ostatnie-4-lata/)
- [Individual IKE summary](https://portalanaliz.pl/artykuly-edukacyjne/co-roku-pobity-swig80-sredniorocznie-31-procent-w-ciagu-9-lat-moj-portfel-ike/)

## Where BiznesRadar adds value

BiznesRadar remains a source and reconciliation surface, not an investment
oracle. The useful next additions are:

1. Diff consecutive immutable market snapshots and prioritize new entrants,
   rating/F-Score/report-period changes instead of always reviewing the same
   static top twelve.
2. Add NewConnect as a separately labelled recall universe with stricter
   liquidity and evidence gates.
3. Retain sector medians as context for positive valuation multiples and
   profitability gaps, with fiscal-period and peer-count caveats.
4. Use per-share rows and price/share/EV arithmetic only as data-conflict
   checks.
5. Compute a 20-session median traded-value measure from already stored prices
   and volume to label execution risk.

Do not ingest RSI, MACD, candlestick labels or BiznesRadar buy/sell signals for
the fundamental report. Raw Altman EM-Score magnitude is also not predictive
truth: the stored GPW snapshot is extremely heavy-tailed, so it is used only
for recall/ranking context.

## Verification rule

Forum reputation may change which question Codex investigates first. It may
not increase factual confidence, prediction confidence or a company score.
Any formal contributor reliability claim needs dated transactions/valuations,
cash flows, dividends, costs, a matched total-return benchmark, drawdown and a
point-in-time publication trail.
