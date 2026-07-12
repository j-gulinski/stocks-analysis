"""Market discovery is one cached source pull, not hundreds of company scrapes."""
from datetime import datetime, timezone
from types import SimpleNamespace
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


def test_market_rating_parser_rejects_table_without_both_declared_factors():
    html = """
    <table><tr><th>Profil</th><th>Rating</th></tr>
    <tr><td><a href=\"/notowania/DEKPOL\">DEK (DEKPOL)</a></td><td>AAA (8,6)</td></tr>
    </table>
    """

    try:
        parse_market_rating(html)
    except ParseError as exc:
        assert "required rating/F-Score headers" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("a structurally incomplete rating table must fail")


def test_first_discovery_refresh_rejects_a_one_row_universe(client, monkeypatch, no_sleep):
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


def test_discovery_reports_the_immutable_parser_version_for_a_stored_snapshot(client, db):
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

    response = client.get("/api/discovery")

    assert response.status_code == 200
    assert response.json()["sieves"][0]["source"]["parser_version"] == "biznesradar-market-rating@legacy"


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
    assert body["result_count"] == 0
    assert body["candidates"] == []
    assert body["sieves"][0]["selection_rules"] == [
        {
            "factor_id": "altman_em_score",
            "label": "Wartość Altman EM-Score",
            "operator": "gte",
            "threshold": 8.0,
        },
        {
            "factor_id": "piotroski_f_score",
            "label": "Piotroski F-Score",
            "operator": "gte",
            "threshold": 7.0,
        },
    ]
    assert db.scalar(select(func.count()).select_from(Company)) == 0
    assert db.scalar(select(func.count()).select_from(WatchlistItem)) == 0

    second = client.get("/api/discovery?min_rating=6.5&min_f_score=0")
    assert second.status_code == 200
    assert second.json()["candidates"] == body["candidates"]
    assert second.json()["sieves"][0]["candidate_count"] == 0
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


def test_failed_discovery_refresh_keeps_last_good_snapshot_and_reports_failure(
    client, db, monkeypatch, no_sleep
):
    responses = iter([
        load_fixture("br_market_rating.html"),
        "<table><tr><th>Profil</th><th>Rating</th></tr></table>",
    ])

    def fake_fetch(url, **_kwargs):
        response = FakeResponse(next(responses))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    first = client.post("/api/discovery/refresh")
    assert first.status_code == 200
    source_version_id = first.json()["source_version_id"]

    failed = client.post("/api/discovery/refresh")
    assert failed.status_code == 503

    stored = client.get("/api/discovery")
    assert stored.status_code == 200
    body = stored.json()
    assert body["source_version_id"] == source_version_id
    assert body["freshness"]["last_failed_refresh_at"] is not None
    assert "Nie rozpoznano źródła" in body["freshness"]["last_failed_refresh_reason"]
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 2


def test_discovery_rejects_implausibly_truncated_universe(client, monkeypatch, no_sleep):
    def universe_html(count: int, *, offset: int = 0) -> str:
        rows = "".join(
            f'<tr><td><a href="/notowania/T{index + offset:03}">T{index + offset:03} (TEST)</a></td>'
            '<td>2026/Q1</td><td>AAA (8,6)</td><td>7</td></tr>'
            for index in range(count)
        )
        return f"<table><tr><th>Profil</th><th>Rating</th><th>F-Score</th></tr>{rows}</table>"

    responses = iter([universe_html(100), universe_html(50)])

    def fake_fetch(url, **_kwargs):
        response = FakeResponse(next(responses))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    first = client.post("/api/discovery/refresh")
    assert first.status_code == 200
    failed = client.post("/api/discovery/refresh")
    assert failed.status_code == 503
    assert "dropped from 100 to 50" in failed.json()["detail"]
    assert client.get("/api/discovery").json()["universe_count"] == 100


def test_discovery_rejects_same_size_universe_without_ticker_continuity(client, monkeypatch, no_sleep):
    def universe_html(offset: int) -> str:
        rows = "".join(
            f'<tr><td><a href="/notowania/T{index + offset:03}">T{index + offset:03} (TEST)</a></td>'
            '<td>2026/Q1</td><td>AAA (8,6)</td><td>7</td></tr>'
            for index in range(100)
        )
        return f"<table><tr><th>Profil</th><th>Rating</th><th>F-Score</th></tr>{rows}</table>"

    responses = iter([universe_html(0), universe_html(200)])

    def fake_fetch(url, **_kwargs):
        response = FakeResponse(next(responses))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)
    assert client.post("/api/discovery/refresh").status_code == 200
    failed = client.post("/api/discovery/refresh")

    assert failed.status_code == 503
    assert "retains only 0/100 prior tickers" in failed.json()["detail"]
    assert client.get("/api/discovery").json()["universe_count"] == 100


def test_blocked_discovery_refresh_logs_failure_and_keeps_last_good_snapshot(
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

    failed = client.post("/api/discovery/refresh")
    assert failed.status_code == 503
    stored = client.get("/api/discovery")
    assert stored.status_code == 200
    assert stored.json()["freshness"]["last_failed_refresh_reason"] == "Błąd sieci"
    assert db.scalar(
        select(func.count()).select_from(FetchLog).where(FetchLog.status.is_(None))
    ) == 1


def test_explicit_discovery_refresh_explains_rank_without_scheduling_research(
    client, db, monkeypatch, no_sleep
):
    def fake_fetch(url, **_kwargs):
        html = load_fixture("br_market_rating.html").replace(
            "<td><span>6</span></td>", "<td><span>7</span></td>", 1
        )
        response = FakeResponse(html)
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    response = client.post("/api/discovery/refresh")
    assert response.status_code == 200
    body = response.json()
    dek = next(row for row in body["candidates"] if row["ticker"] == "DEK")
    assert dek["rank"] == 1
    assert dek["rank_basis"][0] == "Pozycja 1/1 w sicie kondycji finansowej."
    assert "modelu Altmana: 8.6 (klasa AAA)" in dek["rank_basis"][2]

    assert db.scalar(select(func.count()).select_from(AgentRun)) == 0


def test_three_sieves_report_market_wide_coverage_and_limit_does_not_change_count():
    from app.api.discovery import _discovery_out
    from app.scrapers.biznesradar import MarketCandidate

    candidates = [
        MarketCandidate(
            ticker=f"T{index:03}",
            br_slug=None,
            name=None,
            report_period="2026Q1",
            rating="AAA",
            rating_value=8.0 if index < 45 else 4.0,
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

    body = _discovery_out(result, limit=10)
    assert body.result_count == 10
    assert len(body.sieves) == 3
    financial, obs, pa = body.sieves
    assert financial.id == "financial_health_br_v1"
    assert financial.universe_count == 384
    assert financial.candidate_count == 45
    assert financial.coverage_count == 366
    assert financial.coverage_pct == 95.3
    assert financial.source is not None
    assert financial.source.document_version_id == body.source_version_id == 31
    assert financial.source.version == "31"
    assert financial.factor_coverage[1].covered_count == 366
    assert [rule.threshold for rule in financial.selection_rules] == [8.0, 7.0]
    assert "18 spółek" in financial.gaps[0]
    for blocked in (obs, pa):
        assert blocked.status == "blocked"
        assert blocked.candidate_count == 0
        assert blocked.coverage_count == 0
        assert blocked.source is None
        assert blocked.factor_coverage
        assert blocked.gaps


def test_stale_discovery_does_not_expose_a_current_rank():
    from app.api.discovery import _discovery_out
    from app.scrapers.biznesradar import MarketCandidate

    result = SimpleNamespace(
        candidates=[MarketCandidate("TST", None, "Test", "2020Q1", "AAA", 8.6, 8)],
        source_url="https://example.test/rating",
        fetched_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source_note="fixture",
        source_version_id=31,
    )

    body = _discovery_out(result, limit=10)
    assert body.freshness.status == "stale"
    assert body.candidates[0].rank is None
    assert body.candidates[0].membership_factors[0].source_document_version_id == 31
    assert body.candidates[0].neutral_context[0].value is None


def test_old_report_period_is_stale_even_after_a_current_source_check():
    from app.api.discovery import _discovery_out
    from app.scrapers.biznesradar import MarketCandidate

    now = datetime.now(timezone.utc)
    result = SimpleNamespace(
        candidates=[MarketCandidate("TST", None, "Test", "2020Q1", "AAA", 8.6, 8)],
        source_url="https://example.test/rating",
        fetched_at=now,
        source_note="fixture",
        source_version_id=31,
        last_successful_source_check_at=now,
    )

    body = _discovery_out(result, limit=10)
    assert body.freshness.status == "current"
    assert body.candidates[0].factor_status == "stale"
    assert body.candidates[0].rank is None
