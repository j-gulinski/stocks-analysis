# Phase 4 — Next.js frontend

## What was built
The full UI: watchlist dashboard, stock page with five tabs, settings page —
dark theme per `docs/design/`, talking to FastAPI exclusively through the
route-handler proxy.

## Concepts worth understanding

**Server vs client components** — `layout.tsx` is a server component (renders
HTML on the server, ships no JS); anything with `useState`/`useEffect` starts
with `"use client"`. Closest Blazor analogy: static SSR page vs interactive
component, chosen per file.

**The BFF proxy** (`src/app/api/[...path]/route.ts`) — one ~50-line file is
the entire trust boundary: browser calls same-origin `/api/...`, Next forwards
server-to-server to FastAPI. In Phase 6 the Auth.js session check and the
bearer token land here and nowhere else. This is the YARP/BFF pattern you know
from .NET, minus the framework.

**Contracts without codegen** (`src/lib/types.ts`) — TS interfaces mirror the
Pydantic schemas snake_case-for-snake_case. No mapping layer to drift; the
compiler checks every property access. (Extension path: generate types from
FastAPI's OpenAPI JSON when the API grows.)

**Hooks as data plumbing** (`src/lib/hooks.ts`) — `useApi` is ~40 lines of
loading/error/reload state. The `cancelled` flag in the effect cleanup is the
React idiom for "don't set state after unmount" (think CancellationToken).
React Query replaces this the day caching/retries are needed — documented
extension, not v1.

**Live recompute with one source of truth** (`ForecastPanel`) — inputs are
debounced 400 ms, then the *backend* computes the preview (`save=false`). The
math lives in exactly one place (Python); the UI never re-implements it. This
is the same "no duplicated business logic" rule you'd enforce between a WPF
client and a server.

**pl-PL edge** (`src/lib/format.ts`) — all display formatting and the decimal
comma parsing (`parseNum("33,5")`) concentrate in one module, mirroring how
units concentrate in `metrics.py` on the backend.

## Where to look
`src/app/api/[...path]/route.ts` → `src/lib/{types,api,hooks,format}.ts` →
`src/app/page.tsx` → `src/app/stock/[ticker]/page.tsx` → `src/components/ForecastPanel.tsx`.
