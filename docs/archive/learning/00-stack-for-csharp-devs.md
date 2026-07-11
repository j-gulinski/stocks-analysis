# The stack, translated for a C# developer

Read this once before Phase 0. Each phase later gets its own one-page note (`phase-N.md`).

## Backend (Python)

| You know (.NET) | Here (Python) | Notes |
|---|---|---|
| ASP.NET Core + Kestrel | FastAPI + uvicorn | uvicorn is the ASGI server (≈ Kestrel), FastAPI the framework. ASGI ≈ the middleware pipeline abstraction |
| Minimal APIs / controllers | FastAPI routers + decorated functions | `@router.get("/companies/{ticker}")` ≈ `app.MapGet(...)` |
| DTOs + model binding + FluentValidation | Pydantic models | Validation and serialization at the edge, declared as typed classes. Type hints ≈ C# types, but checked at runtime, not compile time |
| EF Core (DbContext, LINQ) | SQLAlchemy 2 (Session, `select()`) | Same unit-of-work idea; queries are explicit expressions instead of LINQ |
| EF migrations | Alembic | `alembic revision --autogenerate` ≈ `dotnet ef migrations add` |
| `appsettings.json` + IOptions + user-secrets | pydantic-settings + `.env` | Typed settings class reading environment variables |
| Built-in DI container | FastAPI `Depends()` | Function-based DI: dependencies are parameters, resolved per request. No container registration |
| HttpClient + Polly | requests + our `scrapers/http.py` | Retry/backoff/rate-limit written by hand (~50 lines) instead of a library policy |
| xUnit + fixtures | pytest | Test functions, `assert` keyword, fixtures via parameters — less ceremony than xUnit |
| NuGet / `.csproj` | pip / `requirements.txt` | Flat text file, no lock semantics in v1 — good enough here |
| `async Task<T>` | `async def` / `await` | Same model; we mostly stay sync in v1 (scrapers are deliberately slow — async would buy nothing) |
| records / classes | dataclasses / Pydantic models | |

## Frontend (TypeScript + React/Next.js)

| You know | Here | Notes |
|---|---|---|
| Blazor components / Razor partials | React components | Functions returning JSX; props ≈ component parameters |
| Blazor `@bind` + state | `useState`, `useEffect` hooks | State changes trigger re-render; effects ≈ lifecycle hooks |
| Razor Pages routing | Next.js App Router | Folder = route: `app/spolka/[ticker]/page.tsx` ≈ `/spolka/DEC` |
| Server-side rendering vs WebAssembly | Server vs client components | `"use client"` marks interactivity; default components render on the server |
| BFF pattern / YARP | Next route-handler proxy | `app/api/[...path]/route.ts` forwards to FastAPI adding the bearer token — the browser never sees backend URL or token |
| ASP.NET auth middleware + OIDC | Auth.js (NextAuth) + Next middleware | Google OAuth flow, session cookie, allowlist check in one callback |
| CSS isolation (`.razor.css`) | SCSS modules (`.module.scss`) | Class names scoped per component at build time |
| TypeScript | TypeScript | Same language; interfaces for API DTOs live in `src/lib/` |

## Concepts each phase will teach

- **P0** — project layout in both ecosystems, env-based config, migrations, dev servers
- **P1** — HTTP scraping and parsing, idempotent upserts, rate limiting/backoff, fixture-based testing
- **P2** — cookies/sessions without a browser, pagination, incremental sync design
- **P3** — pure functions as business logic, designing JSON APIs, financial math (TTM, margins)
- **P4** — React mental model, server/client components, data fetching, charts, SCSS
- **P5** — LLM API integration: prompt assembly, structured output (tool use), token budgets
- **P6** — OAuth in practice, BFF/token trust boundary, cloud envs and secrets, backups
