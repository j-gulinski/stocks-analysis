# Learning notes

One compact index for the C#/.NET developer learning this project. Detailed
phase notes remain recoverable in `docs/archive/learning/`; add durable lessons
here instead of creating another phase file.

| Area | C#/.NET analogy | Key lesson |
|---|---|---|
| Python/FastAPI/SQLAlchemy | ASP.NET + DI + EF `DbContext` | Type hints/Pydantic validate at the edge; SQLAlchemy sessions are explicit units of work. |
| Scrapers | `HttpClient` + Polly + parsers | Fetch, parse and semantic mapping are separate; all HTTP stays behind the polite boundary. |
| Deterministic services | Domain services/pure functions | Metrics, forecast, thesis and scenarios own math and are tested with hand-checked values. |
| Next.js UI | SSR/client components + BFF/YARP | Browser calls the Next proxy; the backend remains the data boundary. |
| Evidence | Immutable event/source records | Claims need source, period, publication time, locator or an explicit gap. |
| Codex workflow | Durable command table + supervised worker | The app queues and stores; Codex claims one item, researches, verifies and saves. |
| Scenario approval | Validator before `SaveChanges()` | Mathematical consistency is not investment approval; strict verification and matching fingerprints are required. |
| Source safety | Data object separate from executable command | Issuer, forum and event text is untrusted data and cannot override task/skill instructions. |
| Parser recovery | Versioned deserializers + cached messages | A markup fix may safely re-parse an immutable failed snapshot; it should not trigger another source request or turn a discovery-only link into a canonical identifier. |
| Replay | Point-in-time event sourcing | Never use later facts to score an earlier decision; small cohorts are diagnostic, not proof. |

Current path: start with `README.md`, then `PLAN.md`,
`docs/project-guardrails.md`, the relevant task in `TASKS.md`, and the matching
skill. Historical phase notes are grouped by phase in the archive rather than
duplicated across active architecture documents.
