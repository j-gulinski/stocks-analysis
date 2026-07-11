# Stage TH — Investment-thesis layer

## What was built
A per-stock **investment-thesis read** in Paweł Malik's spirit: weighted
pros/cons + an entry-point-quality verdict + a "co sprawdzić dalej" list,
composed by pure functions on top of `services/insights.py` (it reuses the
`Insight` verdicts, recomputes nothing). The Malik read is the *first instance*
of a **generic strategy framework** — strategy is data, the engine is
strategy-agnostic. An optional Claude-API refiner deepens the read when a key is
present, behind a no-key fallback. Frontend renders it as the top card of the
Przegląd tab. It is an entrance to human analysis, **not** a buy signal, and
**not** the Phase-5 AI verdict.

## Concepts worth understanding

**Strategy = data, engine = generic** (`services/strategies/base.py`,
`malik.py`) — a `StrategyProfile` is a bundle of frozen dataclasses
(`Criterion`, `EntryQualityRule`, `VerifyGap`): weights, applicability, which
signals gate the entry verdict. The engine reads those off the object; there is
**no `if strategy == "malik"`** branch anywhere. This is the classic *strategy
pattern*, but without virtual dispatch — closer to a C# `record` config object
handed to one generic scorer than to an interface with overrides. Swap the
object → swap the behaviour (a toy profile in the tests proves it). Note the
dataclass idioms vs C# records: `@dataclass(frozen=True)` ≈ an init-only
immutable `record`; `field(default_factory=dict)` is the Python answer to
"never share a mutable default" (there is no `readonly` collection literal).

**The engine is a pure function over DTOs** (`services/thesis.py`,
`build_thesis(inputs, profile)`) — no DB, no framework, plain data in →
`InvestmentThesis` out, exactly like `metrics.py`/`insights.py`. Think hexagonal
domain service / a C# mapping service over DTOs. Two rules make it trustworthy:
it reads `insights.py`'s existing verdicts (so the UI can never show two values
for one metric), and a **fabrication guard** (unit-tested) forbids any number in
the read that is not in the inputs — a *missing* indicator is weighed as absent
and routed to `verify_next`, never invented.

**Lazy module init to break an import cycle** (`services/strategies/cases.py`)
— building a `WorkedCase` touches `thesis.ThesisInputs`, but `thesis` imports
the strategies package, so eager construction of `CORPUS` deadlocks the imports.
`cases.py` uses **PEP 562** (a module-level `__getattr__`) to build `CORPUS`
only on first access — a *lazy static initializer* / `Lazy<T>`, but at module
scope. Reach for this when a constant is expensive or would form a cycle if
evaluated at import time.

**Injectable transport** (`services/thesis_ai.py`, `default_transport` +
`refine_thesis(..., transport=None)`) — the Claude call is a plain callable
`(messages, model) -> dict`. The default tries `import anthropic` *lazily*
(optional dependency) then falls back to a stdlib `urllib` POST; tests inject a
`StubTransport` with scripted responses. This is `HttpClient`/`ITransport`
constructor-injection + a test double, and it is why the module imports and
tests run green with **no PyPI and no network**. The no-key path is a transparent
pass-through of the deterministic read (`engine: "deterministic"`) — the AI is
never on the critical path.

**Frontend: narrowing a string-literal union** (`components/ThesisPanel.tsx`,
`lib/types.ts`) — `engine: "deterministic" | "ai"` is a *string-literal union*,
not a class hierarchy. Writing `thesis.engine === "ai" && thesis.ai_notes && …`
makes the compiler **narrow** the type so `ai_notes` is known-present inside the
branch — the ergonomic version of the discriminated-union/pattern-match you'd
hand-roll in C#. Values arrive preformatted from the backend and render as-is
(no client-side number formatting — same rule as `InsightsPanel`).

## Where to look
`services/strategies/base.py` → `malik.py` → `cases.py` → `services/thesis.py`
→ `tests/test_thesis.py` (13 checks incl. genericity + fabrication guard) →
`services/thesis_ai.py` → `tests/test_thesis_ai.py` (17 checks, stub transport)
→ `components/ThesisPanel.tsx`. Spec: `docs/strategy-malik.md`; validation +
gaps: `docs/validation-thesis.md`.
