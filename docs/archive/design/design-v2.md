# Design system v2 — compact analyst workspace

This is a visual reference. Product workflow and acceptance live in
[`research-workspace.md`](research-workspace.md) and
[`plan-research-platform.md`](../../plan-research-platform.md).

## Language and tone

Use Polish domain labels and English navigation where already established.
Write like an analyst: precise, calm, explicit about uncertainty. The surface
is dense but readable, with evidence/status visible near conclusions.

## Tokens

- Canvas: deep blue-black; surfaces: layered navy; borders: low-contrast slate.
- Text: high-contrast warm white; secondary text: cool muted grey.
- Accents: restrained teal for positive/active, amber for caution, red for
  risk/error, violet for model-generated suggestions.
- Use a small spacing scale (4/8/12/16/24/32), consistent radii and stable
  panel dimensions. Avoid decorative gradients and excess shadows.

## Composition

- Persistent case header: company, `as_of`, freshness, workflow state, blocker
  and primary action.
- Decision brief first; progressive disclosure for evidence, business,
  performance, thesis, scenarios and review.
- One canonical conclusion. Do not repeat thesis/valuation/verdict in separate
  cards merely to fill space.
- Use tables for comparable financial facts, charts for trends, and badges for
  provenance/status. Keep source links one click away.

## Components and states

Every data/review component needs loading, empty, error, conflict and stale
states. Model output shows `draft`, `verified`, `rejected` or `needs-human`.
Separate sourced facts, deterministic calculations, human assumptions, model
suggestions and approved conclusions by label and treatment.

## Accessibility and QA

Keyboard navigation, visible focus, readable contrast, semantic headings,
responsive desktop/mobile layouts and Polish number/date formatting are
required. Verify representative industrial, financial and event-driven cases
with build, accessibility checks and screenshots before RT.4 closes.
