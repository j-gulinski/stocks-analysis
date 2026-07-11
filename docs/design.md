# UI design contract

This is the single live visual reference. Product workflow and acceptance live
in `PLAN.md`, `docs/plan-research-platform.md` and `TASKS.md`; HTML mockups
remain under `docs/design/`.

## Workflow and composition

`Discover → Research → Brief → Evidence/Financials → Scenarios → Review → Monitor/Journal`

- Use Polish domain labels and existing English navigation.
- Show one canonical conclusion, then progressive disclosure for evidence,
  thesis, scenarios and review; do not repeat the same conclusion in cards.
- Keep the workspace dense but readable: stable panel sizes, 4/8/12/16/24/32
  spacing, layered navy surfaces, restrained teal/amber/red/violet states.
- Place freshness, `as_of`, workflow state, blockers and primary action in the
  company header.
- Research queue rows are cards, not a dense table: company/status first,
  dossier signals and the main gap second, and exactly one prominent `Teraz`
  action last. Maintenance actions remain quiet secondary icons.
- Every workflow surface starts with a short typical-path rail. Secondary
  controls (sieve presets, audit panels, model history) remain available but do
  not compete with the next action.
- Codex model selection is explicit and audit-visible. It stores a requested
  role/model such as `Sol high`; the UI must say when the host deployment is not
  exposed and must never imply that the dropdown itself executed a provider.
- Distinguish sourced facts, deterministic calculations, human assumptions,
  model suggestions and verified/rejected/needs-human output.

## Quality bar

Every component needs loading, empty, stale, conflict and error states. Use
semantic headings, visible focus, keyboard navigation, AA contrast, responsive
desktop/mobile layouts and Polish number/date formatting. Verify representative
industrial, financial and event-driven cases with a production build,
accessibility checks and screenshots before closing RT4.5–RT4.7.

Retired design variants and first-workspace detail are in
`docs/archive/design/`.
