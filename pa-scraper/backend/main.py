"""
Backend FastAPI — łączy scraper forum PortalAnaliz (phpBB, z logowaniem)
i scraper rachunku zysków i strat z BiznesRadar.

Uruchomienie:
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from forum_scraper import PhpBBScraper, ForumScraperError, topic_to_markdown, DEFAULT_BASE
from biznesradar_scraper import fetch_income_statement, BiznesRadarError

app = FastAPI(title="PA Scraper", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sesje trzymane w pamięci procesu (token -> zalogowany scraper).
# Credentiale NIE są nigdzie zapisywane — żyją tylko w sesji requests.
_SESSIONS: dict[str, PhpBBScraper] = {}
_LAST_TOPIC: dict[str, dict] = {}


# ------------------------------------------------------------------- models

class LoginRequest(BaseModel):
    username: str
    password: str
    base_url: str = DEFAULT_BASE


class ScrapeTopicRequest(BaseModel):
    session_token: str | None = None
    topic_url: str
    all_pages: bool = True
    max_pages: int = Field(default=50, ge=1, le=200)


# -------------------------------------------------------------------- forum

@app.post("/api/forum/login")
def forum_login(req: LoginRequest):
    scraper = PhpBBScraper(base_url=req.base_url)
    try:
        scraper.login(req.username, req.password)
    except ForumScraperError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:  # network itp.
        raise HTTPException(status_code=502, detail=f"Błąd połączenia: {e}")

    token = uuid.uuid4().hex
    _SESSIONS[token] = scraper
    return {"session_token": token, "message": "Zalogowano."}


@app.post("/api/forum/scrape")
def forum_scrape(req: ScrapeTopicRequest):
    if req.session_token and req.session_token in _SESSIONS:
        scraper = _SESSIONS[req.session_token]
    else:
        # Bez logowania — publiczne wątki phpBB też da się pobrać.
        scraper = PhpBBScraper()

    try:
        result = scraper.scrape_topic(
            req.topic_url, all_pages=req.all_pages, max_pages=req.max_pages
        )
    except ForumScraperError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Błąd pobierania: {e}")

    data = result.to_dict()
    if req.session_token:
        _LAST_TOPIC[req.session_token] = data
    _LAST_TOPIC["_last"] = data
    return data


@app.get("/api/forum/export/markdown", response_class=PlainTextResponse)
def forum_export_markdown(session_token: str | None = None):
    data = _LAST_TOPIC.get(session_token or "_last") or _LAST_TOPIC.get("_last")
    if not data:
        raise HTTPException(status_code=404, detail="Brak pobranego wątku do eksportu.")
    lines = [f"# {data['title']}", f"\nŹródło: {data['url']}", f"Postów: {data['post_count']}\n"]
    for p in data["posts"]:
        lines.append(f"\n---\n\n**{p['author']}** — {p['datetime_iso']}\n")
        lines.append(p["content_text"])
    return "\n".join(lines)


# -------------------------------------------------------------- biznesradar

@app.get("/api/biznesradar/{ticker}")
def biznesradar(ticker: str, quarterly: bool = True):
    try:
        return fetch_income_statement(ticker, quarterly=quarterly)
    except BiznesRadarError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Błąd pobierania: {e}")


@app.get("/api/health")
def health():
    return {"status": "ok"}
