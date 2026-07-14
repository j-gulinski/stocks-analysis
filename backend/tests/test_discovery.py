"""The single Workbench sieve reads one immutable market evidence batch."""

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import func, select

from app.db.models import AgentRun, Company, DocumentVersion, FetchLog, SourceDocument
from app.scrapers.biznesradar import ParseError, parse_market_rating
from tests.conftest import FakeResponse, load_fixture


def test_market_rating_parser_keeps_source_fields_and_missing_values():
    candidates = parse_market_rating(load_fixture("br_market_rating.html"))

    assert [candidate.ticker for candidate in candidates] == [
        "DEK", "RBW", "VGO", "XTB", "SHD"
    ]
    assert candidates[0].name == "DEKPOL"
    assert candidates[0].br_slug == "DEKPOL"
    assert candidates[1].br_slug == "RAINBOW"
    assert candidates[0].report_period == "2026Q1"
    assert candidates[0].rating == "AAA"
    assert candidates[0].rating_value == 8.6
    assert candidates[0].piotroski_f_score == 6
    assert candidates[3].rating == "A-"
    assert candidates[-1].piotroski_f_score is None


def test_market_rating_parser_rejects_wrong_or_incomplete_page():
    for html in (
        "<html><h1>maintenance</h1></html>",
        """
        <table><tr><th>Profil</th><th>Rating</th></tr>
        <tr><td><a href="/notowania/DEKPOL">DEK (DEKPOL)</a></td><td>AAA (8,6)</td></tr>
        </table>
        """,
    ):
        try:
            parse_market_rating(html)
        except ParseError:
            pass
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("incomplete source must not become an empty universe")


def test_market_rating_parser_requires_authoritative_profile_href():
    html = load_fixture("br_market_rating.html").replace(
        'href="/notowania/DEKPOL"', 'href="/firma/DEKPOL"'
    )
    assert "DEK" not in [row.ticker for row in parse_market_rating(html)]


def test_market_rating_parser_accepts_rating_links_without_promoting_slug():
    html = """
    <table class="table table--accent-header">
      <tr><th>Profil</th><th>Raport</th><th>Altman EM-Score</th><th>Piotroski F-Score</th></tr>
      <tr><td><a href="/rating/IFR">IFR (IFSA)</a></td><td>2025/Q3</td><td>AAA ( 1 582,2 )</td><td>5</td></tr>
      <tr><td><a href="/rating/ZAMET-INDUSTRY">ZMT (ZAMET)</a></td><td>2026/Q1</td><td>AAA ( 123,5 )</td><td>4</td></tr>
    </table>
    """
    candidates = parse_market_rating(html)

    assert [row.ticker for row in candidates] == ["IFR", "ZMT"]
    assert [row.br_slug for row in candidates] == [None, None]
    assert candidates[0].rating_value == 1582.2


def test_first_discovery_refresh_rejects_a_one_row_universe(
    client, monkeypatch, no_sleep
):
    html = """
    <table><tr><th>Profil</th><th>Rating</th><th>F-Score</th></tr>
    <tr><td><a href="/notowania/DEKPOL">DEK (DEKPOL)</a></td><td>2026/Q1</td><td>AAA (8,6)</td><td>8</td></tr>
    </table>
    """

    def fake_fetch(url, **_kwargs):
        response = FakeResponse(html)
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    response = client.post("/api/discovery/refresh")

    assert response.status_code == 503
    assert "only 1 rows" in response.json()["detail"]


def test_retired_discovery_workflows_are_not_exposed(client):
    assert client.get("/api/discovery/forecast-growth").status_code == 404
    assert client.get("/api/discovery/universe-policy").status_code == 404
    assert client.get("/api/discovery/triage-reviews").status_code == 404


def test_discovery_read_never_fetches_and_refresh_reports_parse_failure(
    client, monkeypatch, no_sleep
):
    calls: list[str] = []

    def fake_fetch(url, **_kwargs):
        calls.append(url)
        response = FakeResponse("<html><h1>maintenance</h1></html>")
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    assert client.get("/api/discovery").status_code == 404
    assert calls == []
    refreshed = client.post("/api/discovery/refresh")
    assert refreshed.status_code == 503
    assert "wymaga uwagi" in refreshed.json()["detail"]
    assert len(calls) == 1


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

    assert [row.ticker for row in result.candidates] == ["IFR"]
    assert recorded.version.parse_status == "parsed"


def test_discovery_reports_parser_version_on_its_singular_sieve(client, db):
    from app.services import evidence
    from app.services.discovery import DISCOVERY_URL

    html = load_fixture("br_market_rating.html")
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
        parser_version="biznesradar-market-rating@legacy",
        fetched_at=datetime.now(timezone.utc),
    )
    evidence.mark_parse_result(recorded.version, success=True)
    db.commit()

    body = client.get("/api/discovery").json()
    assert "sieves" not in body
    assert body["sieve"]["id"] == "workbench_sieve_v1"
    assert body["sieve"]["source"]["parser_version"] == (
        "biznesradar-market-rating@legacy"
    )


def test_refresh_exposes_one_honestly_blocked_sieve_and_schedules_nothing(
    client, db, monkeypatch, no_sleep
):
    calls: list[str] = []

    def fake_fetch(url, **_kwargs):
        calls.append(url)
        response = FakeResponse(load_fixture("br_market_rating.html"))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    assert client.get("/api/discovery").status_code == 404
    first = client.post("/api/discovery/refresh")
    assert first.status_code == 200
    body = first.json()
    assert body["source"] == "BiznesRadar"
    assert body["universe_count"] == 5
    assert body["result_count"] == 0
    assert body["candidates"] == []
    assert body["excluded"] == []
    assert "sieves" not in body
    assert body["sieve"]["id"] == "workbench_sieve_v1"
    assert body["sieve"]["status"] == "blocked"
    assert body["sieve"]["survivor_count"] == 0
    assert body["sieve"]["excluded_count"] == 0
    assert {rule["layer"] for rule in body["sieve"]["rules"]} == {
        "hard_kill", "improvement"
    }
    assert {row["id"] for row in body["sieve"]["factor_coverage"]} >= {
        "altman_em_score",
        "piotroski_f_score",
        "revenue_and_margin_trend",
        "valuation_vs_own_history",
        "debt_and_cash",
        "turnover",
    }
    assert body["sieve"]["gaps"]
    assert db.scalar(select(func.count()).select_from(Company)) == 0
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0

    stored = client.get("/api/discovery")
    assert stored.status_code == 200
    assert stored.json() == body
    assert len(calls) == 1
    assert db.scalar(select(func.count()).select_from(FetchLog)) == 1
    assert db.scalar(select(func.count()).select_from(SourceDocument)) == 1
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 1

    forced = client.post("/api/discovery/refresh")
    assert forced.status_code == 200
    assert len(calls) == 2
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


def test_failed_refresh_keeps_last_good_snapshot(client, db, monkeypatch, no_sleep):
    responses = iter(
        [
            load_fixture("br_market_rating.html"),
            "<table><tr><th>Profil</th><th>Rating</th></tr></table>",
        ]
    )

    def fake_fetch(url, **_kwargs):
        response = FakeResponse(next(responses))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    source_version_id = client.post("/api/discovery/refresh").json()[
        "source_version_id"
    ]
    assert client.post("/api/discovery/refresh").status_code == 503

    stored = client.get("/api/discovery").json()
    assert stored["source_version_id"] == source_version_id
    assert stored["freshness"]["last_failed_refresh_at"] is not None
    assert "Nie rozpoznano źródła" in stored["freshness"]["last_failed_refresh_reason"]
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 2


def test_blocked_refresh_logs_failure_and_keeps_last_good_snapshot(
    client, db, monkeypatch, no_sleep
):
    from app.scrapers.http import FetchBlockedError

    def good_fetch(url, **_kwargs):
        response = FakeResponse(load_fixture("br_market_rating.html"))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", good_fetch)
    assert client.post("/api/discovery/refresh").status_code == 200
    monkeypatch.setattr(
        "app.scrapers.http.fetch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FetchBlockedError("blocked")),
    )

    assert client.post("/api/discovery/refresh").status_code == 503
    stored = client.get("/api/discovery")
    assert stored.status_code == 200
    assert stored.json()["freshness"]["last_failed_refresh_reason"] == "Błąd sieci"
    assert db.scalar(
        select(func.count()).select_from(FetchLog).where(FetchLog.status.is_(None))
    ) == 1


def test_blocked_sieve_reports_market_wide_coverage_without_candidates():
    from app.api.discovery import _discovery_out
    from app.scrapers.biznesradar import MarketCandidate

    candidates = [
        MarketCandidate(
            ticker=f"T{index:03}",
            br_slug=None,
            name=None,
            report_period="2026Q1",
            rating="AAA",
            rating_value=8.0,
            piotroski_f_score=None if index >= 366 else 7,
        )
        for index in range(384)
    ]
    result = SimpleNamespace(
        candidates=candidates,
        source_url="https://example.test/rating",
        fetched_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        source_note="fixture",
        source_version_id=31,
    )

    body = _discovery_out(result)

    assert body.result_count == 0
    assert body.candidates == []
    assert body.excluded == []
    assert body.sieve.id == "workbench_sieve_v1"
    assert body.sieve.universe_count == 384
    assert body.sieve.survivor_count == 0
    assert body.sieve.excluded_count == 0
    assert body.sieve.factor_coverage[1].covered_count == 366
    assert body.sieve.source is not None
    assert body.sieve.source.document_version_id == body.source_version_id == 31
    assert body.sieve.gaps
