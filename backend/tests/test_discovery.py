"""Market discovery is one cached source pull, not hundreds of company scrapes."""
from datetime import datetime, timezone
from sqlalchemy import func, select

from app.db.models import (
    AgentRun,
    Company,
    DocumentVersion,
    FetchLog,
    SourceDocument,
    WatchlistItem,
)
from app.scrapers.biznesradar import ParseError, parse_market_rating
from tests.conftest import FakeResponse, load_fixture


def test_market_rating_parser_keeps_source_fields_and_missing_values():
    candidates = parse_market_rating(load_fixture("br_market_rating.html"))

    assert [candidate.ticker for candidate in candidates] == ["DEK", "RBW", "VGO", "XTB", "SHD"]
    assert candidates[0].name == "DEKPOL"
    assert candidates[0].br_slug == "DEKPOL"
    assert candidates[1].br_slug == "RAINBOW"
    assert candidates[0].report_period == "2026Q1"
    assert candidates[0].rating == "AAA"
    assert candidates[0].rating_value == 8.6
    assert candidates[0].piotroski_f_score == 6
    assert candidates[3].rating == "A-"
    assert candidates[-1].piotroski_f_score is None


def test_market_rating_parser_rejects_wrong_page():
    try:
        parse_market_rating("<html><h1>maintenance</h1></html>")
    except ParseError as exc:
        assert "No market-rating candidates" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("wrong page must not look like an empty universe")


def test_retired_discovery_workflows_are_not_exposed(client):
    assert client.get("/api/discovery/forecast-growth").status_code == 404
    assert client.get("/api/discovery/universe-policy").status_code == 404
    assert client.get("/api/discovery/triage-reviews").status_code == 404


def test_discovery_read_never_fetches_and_explicit_refresh_reports_parse_failure(
    client, monkeypatch, no_sleep
):
    calls: list[str] = []

    def fake_fetch(url, **_kwargs):
        calls.append(url)
        response = FakeResponse("<html><h1>maintenance</h1></html>")
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    response = client.get("/api/discovery")

    assert response.status_code == 404
    assert calls == []

    refreshed = client.post("/api/discovery/refresh")
    assert refreshed.status_code == 503
    assert "wymaga uwagi" in refreshed.json()["detail"]
    assert len(calls) == 1


def test_market_rating_parser_requires_authoritative_profile_href():
    html = load_fixture("br_market_rating.html").replace(
        'href="/notowania/DEKPOL"',
        'href="/firma/DEKPOL"',
    )

    candidates = parse_market_rating(html)

    assert "DEK" not in [candidate.ticker for candidate in candidates]


def test_market_rating_parser_accepts_current_rating_links_without_promoting_slug():
    html = """
    <table class="table table--accent-header">
      <tr><th>Profil</th><th>Raport</th><th>Altman EM-Score</th><th>Piotroski F-Score</th></tr>
      <tr><td><a href="/rating/IFR">IFR (IFSA)</a></td><td>2025/Q3</td><td>AAA ( 1 582,2 )</td><td>5</td></tr>
      <tr><td><a href="/rating/ZAMET-INDUSTRY">ZMT (ZAMET)</a></td><td>2026/Q1</td><td>AAA ( 123,5 )</td><td>4</td></tr>
    </table>
    """

    candidates = parse_market_rating(html)

    assert [candidate.ticker for candidate in candidates] == ["IFR", "ZMT"]
    assert [candidate.br_slug for candidate in candidates] == [None, None]
    assert candidates[0].rating_value == 1582.2


def test_discovery_reparses_cached_failed_snapshot_without_a_new_request(db, monkeypatch):
    from app.services import evidence
    from app.services.discovery import DISCOVERY_URL, discover_candidates

    html = """
    <table><tr><th>Profil</th><th>Raport</th><th>Altman EM-Score</th><th>Piotroski F-Score</th></tr>
    <tr><td><a href="/rating/IFR">IFR (IFSA)</a></td><td>2025/Q3</td><td>AAA ( 1 582,2 )</td><td>5</td></tr></table>
    """
    recorded = evidence.record_market_document_version(
        db,
        market_key="__GPW__",
        source_name="biznesradar",
        source_type="market_rating",
        scope_key="akcje_gpw",
        requested_url=DISCOVERY_URL,
        effective_url=DISCOVERY_URL,
        content=html.encode(),
        text=html,
        response_status=200,
        mime_type="text/html",
        parser_version="biznesradar-market-rating@1",
        fetched_at=datetime.now(timezone.utc),
    )
    evidence.mark_parse_result(recorded.version, success=False, error="old parser")
    db.commit()
    monkeypatch.setattr("app.services.discovery._get_page", lambda *_args, **_kwargs: None)

    result = discover_candidates(db)

    assert [candidate.ticker for candidate in result.candidates] == ["IFR"]
    assert recorded.version.parse_status == "parsed"


def test_discovery_refresh_is_explicit_and_reads_use_immutable_cache_without_jobs(
    client, db, monkeypatch, no_sleep
):
    calls: list[str] = []

    def fake_fetch(url, **_kwargs):
        calls.append(url)
        response = FakeResponse(load_fixture("br_market_rating.html"))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    missing = client.get("/api/discovery")
    assert missing.status_code == 404
    assert calls == []

    first = client.post("/api/discovery/refresh")
    assert first.status_code == 200
    body = first.json()
    assert body["source"] == "BiznesRadar"
    assert body["universe_count"] == 5
    assert body["result_count"] == 5
    assert [row["ticker"] for row in body["candidates"]] == [
        "DEK",
        "SHD",
        "RBW",
        "VGO",
        "XTB",
    ]
    assert body["candidates"][0]["reasons"] == [
        "Odporność finansowa: 8.6 (klasa AAA)",
        "Jakość zmian w wynikach: 6/9 pozytywnych sygnałów",
    ]
    missing_f_score = next(row for row in body["candidates"] if row["ticker"] == "SHD")
    assert "Brak danych o jakości zmian w wynikach" in missing_f_score["caveat"]
    assert db.scalar(select(func.count()).select_from(Company)) == 0
    assert db.scalar(select(func.count()).select_from(WatchlistItem)) == 0

    second = client.get("/api/discovery?min_rating=6.5&min_f_score=0")
    assert second.status_code == 200
    assert [row["ticker"] for row in second.json()["candidates"]] == [
        "DEK",
        "RBW",
        "VGO",
        "XTB",
    ]
    assert len(calls) == 1
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0
    assert db.scalar(select(func.count()).select_from(FetchLog)) == 1
    assert db.scalar(select(func.count()).select_from(SourceDocument)) == 1
    version = db.scalar(select(DocumentVersion))
    assert version is not None
    assert version.parse_status == "parsed"
    assert "DEKPOL" in version.raw_content

    ignored_force = client.get("/api/discovery?force=true")
    assert ignored_force.status_code == 200
    assert len(calls) == 1

    forced = client.post("/api/discovery/refresh")
    assert forced.status_code == 200
    assert len(calls) == 2
    # Identical bytes reuse the immutable version, while both fetches are logged.
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 1
    assert db.scalar(select(func.count()).select_from(FetchLog)) == 2
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0

def test_changed_market_snapshot_persists_without_scheduling_jobs(
    client, db, monkeypatch, no_sleep
):
    original = load_fixture("br_market_rating.html")
    changed = original.replace(">8,6<", ">8,7<", 1)
    responses = iter([original, changed])

    def fake_fetch(url, **_kwargs):
        response = FakeResponse(next(responses))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    first = client.post("/api/discovery/refresh")
    second = client.post("/api/discovery/refresh")

    assert first.status_code == second.status_code == 200
    assert first.json()["source_version_id"] != second.json()["source_version_id"]
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 2
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0


def test_explicit_discovery_refresh_explains_rank_without_scheduling_research(
    client, db, monkeypatch, no_sleep
):
    def fake_fetch(url, **_kwargs):
        response = FakeResponse(load_fixture("br_market_rating.html"))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    response = client.post("/api/discovery/refresh")
    assert response.status_code == 200
    body = response.json()
    dek = next(row for row in body["candidates"] if row["ticker"] == "DEK")
    assert dek["rank"] == 1
    assert dek["rank_basis"][0] == "Pozycja 1/5 w sicie kondycji finansowej."
    assert "modelu Altmana: 8.6 (klasa AAA)" in dek["rank_basis"][2]

    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0
