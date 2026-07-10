"""CX.6 GPW ESPI/EBI parser and watchlist ingestion tests."""
from tests.conftest import load_fixture


def test_parse_gpw_espi_list_fixture():
    from app.scrapers.espi import parse_report_list

    reports = parse_report_list(load_fixture("gpw_espi_list.html"))

    assert len(reports) == 2
    first = reports[0]
    assert first.report_id == "493537"
    assert first.external_id == "gpw:493537"
    assert first.source == "espi"
    assert first.report_no == "33/2026"
    assert first.issuer_name == "KRUK SPÓŁKA AKCYJNA"
    assert first.isin == "PLKRK0000010"
    assert first.published_at.isoformat() == "2026-07-09T14:00:00+02:00"
    assert "Informacja o nakładach" in first.title
    assert first.detail_url.startswith("https://www.gpw.pl/espi-ebi-report")


def test_parse_gpw_espi_detail_fixture():
    from app.scrapers.espi import parse_report_detail

    detail = parse_report_detail(load_fixture("gpw_espi_detail.html"))

    assert "KRUK S.A. informuje" in detail.raw_text
    assert detail.parsed["company"] == "KRUK SPÓŁKA AKCYJNA"
    assert detail.parsed["date"] == "2026-07-09"
    assert detail.parsed["subject"].startswith("Informacja o nakładach")
    assert "MAR" in detail.parsed["legal_basis"]


def test_poll_watchlist_reports_upserts_matching_company(db, monkeypatch):
    from app.db.models import Company, EventReport, WatchlistItem
    from app.scrapers import espi

    kruk = Company(ticker="KRU", name="KRUK")
    eurotel = Company(ticker="ETL", name="EUROTEL")
    db.add_all([kruk, eurotel])
    db.commit()
    db.add(WatchlistItem(company_id=kruk.id))
    db.commit()

    summaries = espi.parse_report_list(load_fixture("gpw_espi_list.html"))
    detail = espi.parse_report_detail(load_fixture("gpw_espi_detail.html"))
    monkeypatch.setattr(espi, "fetch_latest_reports", lambda: summaries)
    monkeypatch.setattr(espi, "fetch_report_detail", lambda _url: detail)

    result = espi.poll_watchlist_reports(db)
    assert result["ok"] is True
    assert result["matched"] == 1
    assert result["new"] == 1
    assert result["reports"][0]["ticker"] == "KRU"

    report = db.query(EventReport).one()
    assert report.source == "espi"
    assert report.external_id == "gpw:493537"
    assert report.company_id == kruk.id
    assert report.published_at.isoformat().startswith("2026-07-09T14:00:00")
    assert report.materiality["level"] == "unreviewed"
    assert "KRUK S.A. informuje" in report.raw_text

    second = espi.poll_watchlist_reports(db)
    assert second["matched"] == 1
    assert second["new"] == 0
    assert db.query(EventReport).count() == 1


def test_poll_watchlist_reports_can_scope_to_ticker(db, monkeypatch):
    from app.db.models import Company, EventReport
    from app.scrapers import espi

    db.add(Company(ticker="KRU", name="KRUK"))
    db.commit()

    summaries = espi.parse_report_list(load_fixture("gpw_espi_list.html"))
    monkeypatch.setattr(espi, "fetch_latest_reports", lambda: summaries)
    monkeypatch.setattr(
        espi,
        "fetch_report_detail",
        lambda _url: espi.parse_report_detail(load_fixture("gpw_espi_detail.html")),
    )

    result = espi.poll_watchlist_reports(db, ticker="KRU")

    assert result["matched"] == 1
    assert db.query(EventReport).count() == 1


def test_prepare_pre_session_brief_polls_and_queues_codex_task(db, monkeypatch):
    from app.db.models import AgentRun, Company, EventReport, WatchlistItem
    from app.mcp import stock_tools
    from app.scrapers import espi

    kruk = Company(ticker="KRU", name="KRUK")
    db.add(kruk)
    db.commit()
    db.add(WatchlistItem(company_id=kruk.id))
    db.commit()

    summaries = espi.parse_report_list(load_fixture("gpw_espi_list.html"))
    detail = espi.parse_report_detail(load_fixture("gpw_espi_detail.html"))
    monkeypatch.setattr(espi, "fetch_latest_reports", lambda: summaries)
    monkeypatch.setattr(espi, "fetch_report_detail", lambda _url: detail)

    result = stock_tools.prepare_pre_session_brief(
        {"trigger": "scheduled", "orchestrator_model": "gpt-5.5"}
    )

    assert result["ok"] is True
    assert result["espi_poll"]["new"] == 1
    assert result["agent_run"]["workflow"] == "stock-pre-session-brief"
    assert result["agent_run"]["status"] == "queued"
    assert result["agent_run"]["trigger"] == "scheduled"
    assert result["agent_run"]["orchestrator_model"] == "gpt-5.5"
    assert db.query(EventReport).count() == 1
    agent = db.get(AgentRun, result["agent_run"]["id"])
    assert agent.inputs["task"]["skill"] == "stock-pre-session-brief"
    assert agent.inputs["espi_poll"]["source"] == "gpw-espi-ebi"


def test_get_recent_source_deltas_reads_stored_events(db):
    from datetime import datetime, timezone

    from app.db.models import Company, EventReport, WatchlistItem
    from app.mcp import stock_tools

    kruk = Company(ticker="KRU", name="KRUK")
    db.add(kruk)
    db.commit()
    db.add(WatchlistItem(company_id=kruk.id))
    db.add(
        EventReport(
            company_id=kruk.id,
            source="espi",
            external_id="gpw:493537",
            raw_url="https://www.gpw.pl/espi-ebi-report?geru_id=493537",
            published_at=datetime(2026, 7, 9, 14, 0, tzinfo=timezone.utc),
            title="Raport bieżący",
            parsed={"gpw_id": "493537"},
            materiality={"level": "unreviewed"},
        )
    )
    db.commit()

    result = stock_tools.get_recent_source_deltas(
        {"ticker": "KRU", "since": "2026-07-09T00:00:00+00:00"}
    )

    assert result["ok"] is True
    assert result["events"][0]["ticker"] == "KRU"
    assert result["events"][0]["external_id"] == "gpw:493537"
