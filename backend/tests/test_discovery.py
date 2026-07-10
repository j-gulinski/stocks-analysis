"""Market discovery is one cached source pull, not hundreds of company scrapes."""
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


def test_discovery_api_fetches_once_then_uses_immutable_cache(
    client, db, monkeypatch, no_sleep
):
    calls: list[str] = []

    def fake_fetch(url, **_kwargs):
        calls.append(url)
        response = FakeResponse(load_fixture("br_market_rating.html"))
        response.url = url
        return response

    monkeypatch.setattr("app.scrapers.http.fetch", fake_fetch)

    first = client.get("/api/discovery")
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
        "Rating BR AAA (8.6)",
        "Piotroski F-Score 6/9",
    ]
    missing_f_score = next(row for row in body["candidates"] if row["ticker"] == "SHD")
    assert "Brak Piotroski F-Score" in missing_f_score["caveat"]
    first_job = body["evaluation_job"]
    assert first_job == {
        "id": first_job["id"],
        "status": "queued",
        "candidate_count": 5,
        "evaluation_budget": 5,
        "reused": False,
    }

    job = db.get(AgentRun, first_job["id"])
    assert job is not None
    assert job.model_role == "worker_standard"
    assert job.model == "gpt-5.3-codex-spark"
    assert job.orchestrator_model == "gpt-5.3-codex-spark"
    assert job.idempotency_key.endswith(":recall-v1")
    assert job.inputs["policy"] == "recall-v1"
    assert job.inputs["evaluation_budget"] == 5
    assert job.inputs["batch_size"] == 4
    assert [row["ticker"] for row in job.inputs["candidates"]] == [
        "DEK",
        "SHD",
        "RBW",
        "VGO",
        "XTB",
    ]
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
    assert second.json()["evaluation_job"]["id"] == first_job["id"]
    assert second.json()["evaluation_job"]["reused"] is True
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
    assert db.scalar(select(func.count()).select_from(FetchLog)) == 1
    assert db.scalar(select(func.count()).select_from(SourceDocument)) == 1
    version = db.scalar(select(DocumentVersion))
    assert version is not None
    assert version.parse_status == "parsed"
    assert "DEKPOL" in version.raw_content

    forced = client.get("/api/discovery?force=true")
    assert forced.status_code == 200
    assert len(calls) == 2
    # Identical bytes reuse the immutable version, while both fetches are logged.
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 1
    assert db.scalar(select(func.count()).select_from(FetchLog)) == 2
    assert forced.json()["evaluation_job"]["id"] == first_job["id"]
    assert forced.json()["evaluation_job"]["reused"] is True
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 1


def test_changed_market_snapshot_queues_one_new_scout_job(
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

    first = client.get("/api/discovery")
    second = client.get("/api/discovery?force=true")

    assert first.status_code == second.status_code == 200
    assert first.json()["evaluation_job"]["id"] != second.json()["evaluation_job"]["id"]
    assert second.json()["evaluation_job"]["reused"] is False
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 2
    assert db.scalar(select(func.count()).select_from(AgentRun)) == 2
