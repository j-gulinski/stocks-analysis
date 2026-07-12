"""FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload --port 8000
No CORS is configured on purpose — the browser only ever talks to the
Next.js route-handler proxy, which calls this API server-to-server.
"""
import logging
import hmac

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
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
    portfolios,
    research_cases,
    valuations,
    watchlist,
)
from app.db.base import get_db
from app.config import get_settings

# Scraper warnings (per-page refresh failures) should reach the uvicorn console.
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Stock Analysis Workbench API", version="0.1.0")


@app.middleware("http")
async def require_backend_token(request: Request, call_next):
    """Protect all domain API routes when a deployment token is configured."""
    expected = get_settings().api_token
    if expected and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        supplied = request.headers.get("authorization", "")
        candidate = supplied[7:] if supplied.startswith("Bearer ") else ""
        if not hmac.compare_digest(candidate.encode(), expected.encode()):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized."})
    return await call_next(request)

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
app.include_router(portfolios.router, prefix="/api")
app.include_router(research_cases.router, prefix="/api")
app.include_router(valuations.router, prefix="/api")


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
