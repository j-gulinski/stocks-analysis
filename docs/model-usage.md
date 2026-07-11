# Model usage ledger

Concise audit of development/research model routing. Historical rows before the
2026-07-11 reset remain in Git at `2ac75d0`; empty queue checks are not model
usage and are no longer logged.

| Date | Stage | Work | Role | Selected tier | Reasoning | Concrete host | Substitution / escalation | Verification |
|---|---|---|---|---|---|---|---|---|
| 2026-07-11 | P0-AUDIT-DOC | repository-wide documentation/artifact audit | analyst_deep | Sol high | high | Codex host; exact deployment not exposed | host cannot select/report the named deployment | independent manager synthesis; no edits |
| 2026-07-11 | P0-AUDIT-FE | frontend/product-flow audit | analyst_deep | Sol high | high | Codex host; exact deployment not exposed | host cannot select/report the named deployment | source, browser, and cross-audit corroboration; no edits |
| 2026-07-11 | P0-AUDIT-BE | backend/data/orchestration audit | analyst_deep | Sol high | high | Codex host; exact deployment not exposed | host cannot select/report the named deployment | isolated TestClient reproduction, focused tests, DB/log evidence; no edits |
| 2026-07-11 | P0/P1-BE | bounded API, queue, read-boundary and memory implementation | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | requested Terra-high role mapped to available host; no escalation | focused contracts and full backend suite pass |
| 2026-07-11 | P0/P1-FE | Discover/Research simplification, proxy and explicit-action UI | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | requested Terra-high role mapped to available host; no escalation | TypeScript, production build and browser interaction pass |
| 2026-07-11 | P0-TEST | mechanical regression, skill validation and runtime checks | tester | GPT-5.3 high | high | Codex host; exact deployment not exposed | requested testing tier mapped to available host | full suites, diff check, service health and DB invariants pass |
| 2026-07-11 | P0-VERIFY | independent product/data/orchestration audit of integrated result | verifier_strict | Sol high | high | Codex subagent host; exact deployment not exposed | requested Sol-high verifier mapped to available host; no escalation | P0 approved; P1 snapshot/dashboard gap explicitly rejected as incomplete |
| 2026-07-11 | P0-INTEGRATE | product reset, documentation consolidation, P0/P1 entry implementation | manager / analyst_deep | Sol high | high | GPT-5-based Codex host; concrete deployment not exposed | requested Sol-high role mapped to available host; no escalation | P0 complete; P1 entry slice green; tailored research artifact remains open |
| 2026-07-11 | P1-BE | typed research artifact, migration, verification/save boundary and tests | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | requested Terra-high role mapped to available host; manager hardened gates after judge rejection | focused contracts and full backend suite pass |
| 2026-07-11 | P1-FE | fixed tailored Research renderer and snapshot-first company route | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | requested Terra-high role mapped to available host; no escalation | TypeScript, production build and browser renderer pass |
| 2026-07-11 | P1-INTEGRATE | architecture, integrity hardening and end-to-end integration | manager / analyst_deep | Sol high | high | GPT-5-based Codex host; concrete deployment not exposed | Sol-high manager retained after first verifier rejection exposed decision-integrity gaps | 560 tests, build, migration, runtime and browser pass |
| 2026-07-11 | P1-CODE-VERIFY | independent audit of artifact, provenance, point-in-time, lease and verifier gates | verifier_strict | Sol high | high | Codex subagent host; exact deployment not exposed | two rejection/fix cycles before approval; no tier escalation | final code gate approved |
| 2026-07-11 | P1-ABS-DRAFT | one real ABS collection and tailored research draft | worker_standard | Terra high | high | AgentRun records `gpt-5.6-terra`; concrete host deployment not exposed | no escalation; ordinary source gaps retained | exact draft schema/DB gates pass; saved provisional |
| 2026-07-11 | P1-ABS-VERIFY | exact-draft ABS source, identity, point-in-time and math review | verifier_strict | Sol high | high | `gpt-5.6-sol requested; host deployment not exposed` | first outline rejected; corrected exact draft passed without ultra escalation | all five checks pass; final status provisional due eight gaps |
| 2026-07-11 | P1-TEST | mechanical suites, migration/runtime and browser interaction | tester | GPT-5.3 high | high | Codex host; exact deployment not exposed | requested testing tier mapped to available host | 560 backend tests, frontend build, PostgreSQL 0024, skills and browser pass |

## Routing policy

- No model: fetch, parse, normalize, deterministic calculations, and DB
  assembly.
- GPT-5.3 high: mechanical extraction, tests, fixtures, formatting, and small
  repetitive fixes.
- Luna medium: bounded low-risk CRUD/UI wiring.
- Terra high: ordinary implementation, debugging, classification, and bounded
  company research.
- Sol high: architecture, financial/data design, deep company/valuation/
  portfolio synthesis, and independent strict verification.
- Sol ultra: one-tier escalation only after a concrete Sol-high failure or
  exceptional integrity/security ambiguity.

Always record actual host metadata when exposed; never infer a deployment from
the role name. UI-visible investment judgment requires a separate
`verifier_strict` result.
