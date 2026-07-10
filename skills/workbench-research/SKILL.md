---
name: workbench-research
description: Operate and facilitate the local Stock Analysis Workbench for GPW company research. Use when the user asks to start, stop, open, check or diagnose the application; asks to research or analyze a ticker through the workbench; or wants the current evidence and scenario workflow organized from a Codex task.
---

# Workbench research

Use the repository-owned `./workbench` command as the process contract. Keep
service management deterministic and use the web UI for visual research work.

## Start or check the workbench

1. Work from the repository root containing `workbench`, `backend/` and
   `frontend/`.
2. Run `./workbench doctor` first. It is read-only and makes no external source
   or model requests.
3. If the user asked to research a company or open the app, run
   `./workbench start`. It may start Docker Desktop on macOS, starts Postgres,
   applies migrations and launches backend/frontend with owned PID/log files.
4. Run `./workbench status` and require backend health plus frontend port
   readiness before using the app.
5. Use `./workbench start --open` only when putting the app in front of the user
   is useful. Otherwise keep browser verification in the background.
6. Leave the app running after a research task unless the user asks to stop it.
   `./workbench stop` terminates only workbench-owned backend/frontend processes
   and deliberately leaves Postgres running.

## Facilitate company research

1. Establish application/source readiness from `doctor`, which reads only local
   and stored health. Open Settings login diagnostics only when live credential
   checks are explicitly in scope; configured login endpoints may contact their
   source.
2. Prefer the backend API/CLI for structured data and the browser for visual
   inspection or user-facing scenario editing.
3. Check freshness, missing/conflicting data and mapping diagnostics before
   interpreting a company.
4. Separate sourced facts, deterministic calculations, human assumptions and
   model suggestions in the response.
5. Treat PortalAnaliz/forum content as unverified claims to investigate.
6. Do not run an AI analysis or force-refresh external sources merely by opening
   the app. Run them when the research request needs them, respect existing
   cache/politeness rules and report partial source failures.
7. Present the current thesis, counter-thesis, scenario assumptions, falsifiers
   and next checks. Call out where the current v1 app still uses generic
   multiple-reversion sensitivities rather than company-driver scenarios.
8. Keep durable changes and feedback in the application when supported; do not
   imply that a chat response was persisted.

## Commands and boundaries

- `./workbench doctor [--json]` — dependencies, credential presence, local
  services and stored scraper health. Never prints secret values.
- `./workbench status [--json]` — owned/external process and port state.
- `./workbench start [--open] [--json]` — idempotent local startup.
- `./workbench stop [--json]` — stop only owned app processes.

Do not invent planned `refresh`, `case`, `analyze`, `feedback` or `backtest`
subcommands before they exist. Use the current documented API when appropriate
and label the limitation. Read `docs/plan-research-platform.md` only when the
task concerns target architecture or an RT-stage implementation; do not preload
it for routine start/status work.

When a command fails, read the emitted detail and the matching
`.workbench/{backend,frontend}.log`; do not bypass a failed health gate.
