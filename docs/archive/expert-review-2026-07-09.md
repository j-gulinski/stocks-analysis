# Expert review — compact decision record (2026-07-09)

The review confirmed that the first vertical slice is useful but still a
data-backed workspace, not yet a trustworthy research system. The canonical
response is [`plan-research-platform.md`](../plan-research-platform.md); current
work is in [`TASKS.md`](../../TASKS.md).

## Findings retained

- Keep the polite scrapers, pure metrics, strategy skill, explicit unknowns,
  fixture coverage and watchlist workspace.
- Fix the non-green baseline before deployment.
- Add immutable source/publication lineage and point-in-time reads.
- Remove hidden AI from dossier reads; persist explicit, validated runs.
- Make scores and valuation arithmetic deterministic.
- Replace generic multiple sensitivity with company-specific operating drivers.
- Use primary issuer/ESPI evidence and claim-level citations.
- Treat backtesting as unavailable until data, universe, delistings,
  corporate actions and frozen versions support honest replay.

## Product decision

Organize around a persistent research case and an investor decision loop:
evidence → business/driver review → thesis/falsifiers → scenarios → Codex
review → journal/monitoring. Deployment and broad automation follow local
evidence and evaluation gates, not precede them.

## Open scope

The remaining items are represented by RT.0–RT.7, Stage IL and CX.15–CX.17 in
`TASKS.md`. This review note is historical and should not become a second
roadmap.
