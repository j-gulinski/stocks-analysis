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
| 2026-07-11 | P2-AUDIT | market coverage, second-pilot and archetype evidence audit | analyst_deep | Sol high | high | Codex subagent host; exact deployment not exposed | no escalation; chose SNT over a second software company | v31 counts and SNT source/sector distinction independently established |
| 2026-07-11 | P2-BE | typed sieves, archetype registry, v2 write gates and legacy path | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | two judge-driven hardening passes; no tier escalation | focused contracts and full backend suite pass |
| 2026-07-11 | P2-FE | concise sieve comparison and tailored pack audit states | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | manager integrated evidence/assumption semantics after judge finding | TypeScript, production build and browser rendering pass |
| 2026-07-11 | P2-CODE-VERIFY | independent sieve, version, marker and UI-semantics audit | verifier_strict | Sol high | high | Codex subagent host; exact deployment not exposed | rejected bundled markers, mutable sieve thresholds and incomplete legacy routing before approval | final code gate approved; 569-test baseline and build green |
| 2026-07-11 | P2-SNT-DRAFT | bounded SNT refresh and industrial/consumer research draft | worker_standard | Terra high | high | AgentRun records `gpt-5.6-terra`; concrete host deployment not exposed | replacement runs used only after frozen-boundary failures; no model escalation | Run 28 exact draft saved provisional after reproducible source/dossier/calculation checks |
| 2026-07-11 | P2-SNT-VERIFY | exact-draft SNT provenance, arithmetic, marker and leakage review | verifier_strict | Sol high | high | `gpt-5.6-sol requested; host deployment not exposed` | rejected incorrect working-capital provenance, unfrozen handoff and nondeterministic ORM hash before fresh pass | VerificationRun 2 pass; all five checks true; final status provisional due nine gaps |
| 2026-07-11 | P2-TEST | mechanical suites, skills, runtime/DB and browser interaction | tester | GPT-5.3 high | high | Codex host; exact deployment not exposed | requested testing tier mapped to available host | 569 backend tests, frontend build, three skill validators, 384/366/45 runtime and ABS/SNT browser QA pass |
| 2026-07-11 | P2-INTEGRATE | P2 architecture, integrity hardening and end-to-end integration | manager / analyst_deep | Sol high | high | GPT-5-based Codex host; concrete deployment not exposed | retained Sol high after repeated verifier findings; ultra not justified | P2 exit gate complete; independent code and investment-output verifiers approve |
| 2026-07-12 | P3-AUDIT | valuation architecture, source/pilot and UI boundary audit | analyst_deep | Sol high | high | Codex subagent host; exact deployment not exposed | no escalation; legacy scenario paths rejected | SNT/ABS immutable fact bases and P3 risks established |
| 2026-07-12 | P3-BE | immutable valuation engine, API, queue, verifier/save boundary and tests | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | ordinary implementation tier; manager required engine-v2 integrity corrections | 585 backend tests and live previews pass |
| 2026-07-12 | P3-FE | calm Valuation list/editor/results/audit and Research navigation | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | no escalation | production build and browser interaction pass |
| 2026-07-12 | P3-SKILL | company-valuation skill and one-job queue routing | worker_standard | Terra high | high | Codex subagent host; exact deployment not exposed | no escalation | both skill validators pass and scripts/MCP names reconcile |
| 2026-07-12 | P3-CODE-VERIFY | independent financial/source/queue/UI integrity audit | verifier_strict | Sol high | high | Codex subagent host; exact deployment not exposed | first pass rejected six blockers; fresh context approved corrected engine-v2 vertical | adversarial tests, full suite, build and diff check pass |
| 2026-07-12 | P3-SNT-DRAFT | complex industrial valuation mechanism and rationale | analyst_deep | Sol high | high | AgentRun 31 records `gpt-5.6-sol`; concrete host deployment not exposed | explicit one-tier escalation from Terra due discontinued operation and material one-off | exact draft verified and saved provisional |
| 2026-07-12 | P3-SNT-VERIFY | SNT exact source, one-off, math, method and probability review | verifier_strict | Sol high | high | `Sol high; concrete host model not exposed` | no ultra escalation | VerificationRun 3 pass; 40/45/15; weighted 305.41 PLN |
| 2026-07-12 | P3-ABS-DRAFT | ordinary software/services valuation mechanism and rationale | worker_standard | Terra high | high | AgentRun 32 records `gpt-5.6-terra`; concrete host deployment not exposed | no escalation | exact draft verified and saved provisional |
| 2026-07-12 | P3-ABS-VERIFY | ABS exact source, math, method and probability review | verifier_strict | Sol high | high | `Sol high; concrete host model not exposed` | no escalation | VerificationRun 4 pass; 35/45/20; weighted 78.11 PLN |
| 2026-07-12 | P3-TEST | mechanical suites, migration/runtime, skills and browser interaction | tester | GPT-5.3 high | high | Codex host; exact deployment not exposed | requested testing tier mapped to available host | 585 backend tests, build, validators, DB/runtime and browser gates pass |
| 2026-07-12 | P3-INTEGRATE | P3 integrity hardening, real pilots and stage close | manager / analyst_deep | Sol high | high | GPT-5-based Codex host; concrete deployment not exposed | retained Sol high after independent rejection; ultra not justified | code verifier approved; two verifier-gated pilots and P3 exit gate complete |

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
