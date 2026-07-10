# Model usage ledger

Durable statistics for model routing and task division. Add one row for every
implementation, review, testing, or research session before marking the work
complete. The concrete host model must be reported honestly; a role such as
`verifier_strict` is not itself a model name.

| Date | Task ID | Work type | Model role | Selected tier/model | Reasoning | Concrete host model | Substitution/escalation | Verification/result |
|---|---|---|---|---|---|---|---|---|
| 2026-07-10 | CX.15a/CX.15b | implementation + tests | orchestrator / worker_standard | Legacy selection: Luna medium (before correction) | medium | GPT-5 current Codex host; exact deployment not exposed | Misrouted under the old policy; routing corrected afterward | Focused and full pytest green; fresh single-migration start/status/doctor green; live GPW HTTP 500 was kept incomplete and did not queue work |
| 2026-07-10 | Model routing correction | policy update | orchestrator / verifier | GPT-5.3 high → Luna medium fallback → Terra high → Sol high → Sol ultra | high | GPT-5 current Codex host; exact deployment not exposed | Corrected prior mapping; no delegation tool exposed in this surface | AGENTS, guardrails and active plan references aligned |
| 2026-07-10 | Process policy | documentation/mechanical | worker_standard / verifier_strict | Testing/mechanical: GPT-5.3 | high | GPT-5 current Codex host; exact deployment not exposed | Host substitution recorded; no delegation tool exposed in this surface | Added manager → worker → independent judge guidance; reviewed against AGENTS and guardrails |
| 2026-07-10 | Documentation compaction | documentation/review | worker_standard / verifier_strict | Testing/mechanical: GPT-5.3 | high | GPT-5 current Codex host; exact deployment not exposed | Host substitution recorded; no delegation tool exposed in this surface; no escalation | Reviewed all Markdown headings/references; compacted superseded plans and design/review notes; validation and operational docs retained |
| 2026-07-10 | Model-policy accuracy review | documentation/review | orchestrator / verifier | Testing/mechanical: GPT-5.3 | high | GPT-5 current Codex host; exact deployment not exposed | No escalation; corrected ambiguous fallback wording in AGENTS | Ladder matches the intended routing; uncertain classification now means lightest plausible tier, not automatic Medium |

## Recording rules

- Use the task ID from `TASKS.md`; split rows when materially different work
  uses different roles or tiers.
- Record the selected tier before work begins. Escalation is one tier at a time
  and needs an evidence-based reason.
- Record the actual model only when known from the host/run metadata. Otherwise
  use `not exposed` or the equivalent explicit statement.
- Keep verification separate from drafting: UI-visible investment output still
  requires `verifier_strict`, and a testing/mechanical pass is not a verifier
  pass.
