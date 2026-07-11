"""FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload --port 8000
No CORS is configured on purpose — the browser only ever talks to the
Next.js route-handler proxy, which calls this API server-to-server.
"""
import logging

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import (
    agent_evaluations,
    agent_runs,
    analyses,
    backtests,
    companies,
    diagnostics,
    discovery,
    evidence,
    falsifiers,
    forum,
    journal,
    monitor,
    positions,
    research_cases,
    watchlist,
)
from app.db.base import get_db

# Scraper warnings (per-page refresh failures) should reach the uvicorn console.
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Stock Analysis Workbench API", version="0.1.0")

app.include_router(watchlist.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
app.include_router(forum.router, prefix="/api")
app.include_router(diagnostics.router, prefix="/api")
app.include_router(analyses.router, prefix="/api")
app.include_router(agent_runs.router, prefix="/api")
app.include_router(backtests.router, prefix="/api")
app.include_router(agent_evaluations.router, prefix="/api")
app.include_router(evidence.router, prefix="/api")
app.include_router(falsifiers.router, prefix="/api")
app.include_router(discovery.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(monitor.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(research_cases.router, prefix="/api")


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Liveness + DB connectivity check (used by Railway healthcheck later)."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover — depends on local environment
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Database unreachable: {exc}. "
                "Is Postgres running? Try: docker compose up -d postgres"
            ),
        )
    return {"status": "ok"}
