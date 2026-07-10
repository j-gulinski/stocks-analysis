"""CX.6 GPW ESPI/EBI parser and watchlist ingestion tests."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from tests.conftest import load_fixture


def _watched_kruk(db, *, added_at=None):
    from app.db.models import Company, WatchlistItem

    kruk = Company(ticker="KRU", name="KRUK")
    db.add(kruk)
    db.commit()
    item = WatchlistItem(company_id=kruk.id)
    if added_at is not None:
        item.added_at = added_at
    db.add(item)
    db.commit()
    return kruk


def _summary(report_id: str, published_at: datetime, *, issuer: str = "KRUK"):
    from app.scrapers import espi

    base = espi.parse_report_list(load_fixture("gpw_espi_list.html"))[0]
    return replace(
        base,
        report_id=report_id,
        published_at=published_at,
        issuer_name=issuer,
        title=f"Raport {report_id}",
        detail_url=f"https://www.gpw.pl/espi-ebi-report?geru_id={report_id}",
    )


def _page(reports, *, next_offset=None, next_limit=15):
    from app.scrapers import espi

    return espi.GpwReportListPage(
        reports=list(reports),
        next_offset=next_offset,
        next_limit=next_limit if next_offset is not None else None,
    )


def _detail(label="detail"):
    from app.scrapers import espi

    return espi.GpwReportDetail(raw_text=f"raw {label}", parsed={"subject": label})


def _patch_pages(monkeypatch, pages):
    from app.scrapers import espi

    calls = []
    monkeypatch.setattr(
        espi,
        "utcnow",
        lambda: datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc),
    )

    def fake_fetch_page(*, offset=0, limit=espi.GPW_REPORTS_LIMIT):
        calls.append({"offset": offset, "limit": limit})
        index = len(calls) - 1
        page = pages[index]
        if isinstance(page, Exception):
            raise page
        return page

    monkeypatch.setattr(espi, "fetch_report_list_page", fake_fetch_page)
    return calls


def _set_watermark(db, value):
    from app.db.models import ListPollState
    from app.scrapers import espi

    state = ListPollState(source_key=espi.SOURCE_KEY, last_polled_at=value)
    db.add(state)
    db.commit()
    return state


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


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


def test_gpw_espi_list_get_request_and_pager_are_fixture_testable(monkeypatch):
    from app.scrapers import espi

    captured = {}

    def fake_fetch(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            text=load_fixture("gpw_espi_list_get_with_pager.html"),
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(espi.http, "fetch", fake_fetch)

    page = espi.fetch_report_list_page(offset=0, limit=15)

    assert captured["url"] == "https://www.gpw.pl/espi-ebi-reports"
    assert captured["kwargs"].get("method", "GET") == "GET"
    assert "data" not in captured["kwargs"]
    assert captured["kwargs"]["params"] == [
        ("action", "GPWEspiReportUnion"),
        ("start", "ajaxSearch"),
        ("page", "espi-ebi-reports"),
        ("format", "html"),
        ("lang", "EN"),
        ("offset", "0"),
        ("limit", "15"),
        ("categoryRaports[]", "EBI"),
        ("categoryRaports[]", "ESPI"),
        ("typeRaports[]", "RB"),
        ("typeRaports[]", "P"),
        ("typeRaports[]", "Q"),
        ("typeRaports[]", "O"),
        ("typeRaports[]", "R"),
    ]
    assert len(page.reports) == 1
    assert page.next_offset == 15
    assert page.next_limit == 30


def test_gpw_espi_list_params_builds_continuation_tuple():
    from app.scrapers import espi

    assert espi.gpw_report_list_params(offset=15, limit=30)[5:7] == [
        ("offset", "15"),
        ("limit", "30"),
    ]


def test_parse_gpw_espi_empty_present_list_is_rejected():
    from app.scrapers import espi

    with pytest.raises(espi.GpwReportParseError):
        espi.parse_report_list_page('<ul id="search-result"></ul>')


@pytest.mark.parametrize(
    "html",
    [
        "<html><body>No reports here</body></html>",
        '<ul id="search-result"><li><span class="date">09-07-2026 14:00:00 | Current | ESPI | 33/2026</span></li></ul>',
        '<ul id="search-result"><li><span class="date">bad | Current | ESPI | 33/2026</span><strong class="name"><a href="espi-ebi-report?geru_id=1">KRUK</a></strong><p>T</p></li></ul>',
        '<ul id="search-result"><li><span class="date">09-07-2026 14:00:00 | Current | XYZ | 33/2026</span><strong class="name"><a href="espi-ebi-report?geru_id=1">KRUK</a></strong><p>T</p></li></ul>',
        '<ul id="search-result"><li><span class="date">09-07-2026 14:00:00 | Current | ESPI | 33/2026</span><strong class="name"><a href="espi-ebi-report?geru_id=abc">KRUK</a></strong><p>T</p></li></ul>',
    ],
)
def test_parse_gpw_espi_list_rejects_malformed_pages(html):
    from app.scrapers import espi

    with pytest.raises(espi.GpwReportParseError):
        espi.parse_report_list_page(html)


def test_parse_gpw_espi_list_rejects_malformed_pager():
    from app.scrapers import espi

    html = (
        load_fixture("gpw_espi_list.html")
        + '<a class="more" data-type="pager" data-offset="not-int" data-limit="15">'
        + "More</a>"
    )

    with pytest.raises(espi.GpwReportParseError):
        espi.parse_report_list_page(html)


@pytest.mark.parametrize(
    "pager",
    [
        '<a class="more" data-type="pager" data-limit="15">More</a>',
        '<a class="more" data-type="pager" data-offset="15">More</a>',
        '<a class="more" data-type="pager" data-offset="0" data-limit="15">More</a>',
        '<a class="more" data-type="pager" data-offset="30" data-limit="15">More</a>',
    ],
)
def test_parse_gpw_espi_list_rejects_bad_pager_continuity(pager):
    from app.scrapers import espi

    with pytest.raises(espi.GpwReportParseError):
        espi.parse_report_list_page(load_fixture("gpw_espi_list.html") + pager)


def test_parse_gpw_espi_detail_fixture():
    from app.scrapers.espi import parse_report_detail

    detail = parse_report_detail(load_fixture("gpw_espi_detail.html"))

    assert "KRUK S.A. informuje" in detail.raw_text
    assert detail.parsed["company"] == "KRUK SPÓŁKA AKCYJNA"
    assert detail.parsed["date"] == "2026-07-09"
    assert detail.parsed["subject"].startswith("Informacja o nakładach")
    assert "MAR" in detail.parsed["legal_basis"]


@pytest.mark.parametrize(
    "html",
    [
        "<html><body>not a report page</body></html>",
        '<div class="report-data"></div>',
        '<div class="report-data"><p>Treść raportu:</p></div>',
        '<div class="report-data"><p>Firma: KRUK</p><p>Data: 2026-07-09</p><p>Temat</p><p>Raport</p><p>Treść raportu: Service temporarily unavailable</p></div>',
    ],
)
def test_parse_gpw_espi_detail_rejects_non_ingestable_pages(html):
    from app.scrapers import espi

    with pytest.raises(espi.GpwReportParseError):
        espi.parse_report_detail(html)


def test_parse_gpw_espi_detail_accepts_credible_english_labels():
    from app.scrapers import espi

    html = """
    <div class="report-data">
      <p>Date: 2026-07-09</p>
      <p>Company: KRUK SPOLKA AKCYJNA</p>
      <p>Subject</p>
      <p>Current report about portfolio investments</p>
      <p>Legal basis</p>
      <p>Article 17 MAR</p>
      <p>Report content:</p>
      <p>The issuer reports a material portfolio investment update for investors.</p>
    </div>
    """

    detail = espi.parse_report_detail(html)

    assert detail.parsed["company"] == "KRUK SPOLKA AKCYJNA"
    assert detail.parsed["subject"] == "Current report about portfolio investments"


def test_poll_watchlist_reports_upserts_matching_company(db, monkeypatch):
    from app.db.models import Company, DocumentVersion, Event, EventReport, WatchlistItem
    from app.scrapers import espi

    kruk = Company(ticker="KRU", name="KRUK")
    eurotel = Company(ticker="ETL", name="EUROTEL")
    db.add_all([kruk, eurotel])
    db.commit()
    db.add(WatchlistItem(company_id=kruk.id))
    db.commit()

    summaries = espi.parse_report_list(load_fixture("gpw_espi_list.html"))
    detail = espi.parse_report_detail(load_fixture("gpw_espi_detail.html"))
    monkeypatch.setattr(
        espi,
        "fetch_report_list_page",
        lambda **_kwargs: espi.GpwReportListPage(
            reports=summaries,
            next_offset=None,
            next_limit=None,
        ),
    )
    monkeypatch.setattr(espi, "fetch_report_detail", lambda _url: detail)

    result = espi.poll_watchlist_reports(db)
    assert result["ok"] is True
    assert result["complete"] is True
    assert result["pages_fetched"] == 1
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
    evidence_version = db.query(DocumentVersion).one()
    assert report.parsed["evidence_source_version_id"] == evidence_version.id
    event = db.query(Event).one()
    assert event.source_version_id == evidence_version.id
    assert event.verification_state == "unverified"
    assert event.claims[1]["locator"] == {"section": "report-data", "field": "subject"}

    second = espi.poll_watchlist_reports(db)
    assert second["matched"] == 1
    assert second["new"] == 0
    assert second["complete"] is True
    assert second["boundary_reached"] is True
    assert db.query(EventReport).count() == 1
    assert db.query(Event).count() == 1


def test_poll_watchlist_reports_can_scope_to_ticker(db, monkeypatch):
    from app.db.models import Company, EventReport
    from app.scrapers import espi

    db.add(Company(ticker="KRU", name="KRUK"))
    db.commit()

    summaries = espi.parse_report_list(load_fixture("gpw_espi_list.html"))
    monkeypatch.setattr(
        espi,
        "fetch_report_list_page",
        lambda **_kwargs: espi.GpwReportListPage(
            reports=summaries,
            next_offset=None,
            next_limit=None,
        ),
    )
    monkeypatch.setattr(
        espi,
        "fetch_report_detail",
        lambda _url: espi.parse_report_detail(load_fixture("gpw_espi_detail.html")),
    )

    result = espi.poll_watchlist_reports(db, ticker="KRU")

    assert result["matched"] == 1
    assert db.query(EventReport).count() == 1


def test_poll_unknown_ticker_fails_without_fetch_or_state(db, monkeypatch):
    from app.db.models import ListPollState
    from app.scrapers import espi

    def fail_fetch(**_kwargs):
        raise AssertionError("unknown ticker must not fetch")

    monkeypatch.setattr(espi, "fetch_report_list_page", fail_fetch)

    result = espi.poll_watchlist_reports(db, ticker="NOPE")

    assert result["ok"] is False
    assert result["complete"] is False
    assert result["incomplete_reason"] == "unknown_ticker"
    assert result["pages_fetched"] == 0
    assert db.query(ListPollState).count() == 0


def test_global_empty_watchlist_fails_without_fetch_or_state(db, monkeypatch):
    from app.db.models import Company, ListPollState
    from app.scrapers import espi

    db.add(Company(ticker="KRU", name="KRUK"))
    db.commit()

    def fail_fetch(**_kwargs):
        raise AssertionError("empty watchlist must not fetch")

    monkeypatch.setattr(espi, "fetch_report_list_page", fail_fetch)

    result = espi.poll_watchlist_reports(db)

    assert result["ok"] is False
    assert result["complete"] is False
    assert result["incomplete_reason"] == "empty_watchlist"
    assert result["pages_fetched"] == 0
    assert db.query(ListPollState).count() == 0


def test_first_run_bootstrap_walks_to_pager_end_and_records_stable_cutoff(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    bootstrap_target = datetime(2026, 7, 10, 6, 30, tzinfo=timezone.utc)
    _watched_kruk(db, added_at=bootstrap_target)
    p1 = _page(
        [_summary("1", datetime(2026, 7, 10, 10, 0, tzinfo=espi.WARSAW_TZ))],
        next_offset=15,
    )
    p2 = _page([_summary("2", datetime(2026, 7, 10, 9, 0, tzinfo=espi.WARSAW_TZ))])
    calls = _patch_pages(monkeypatch, [p1, p2])
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    result = espi.poll_watchlist_reports(db)

    assert result["complete"] is True
    assert result["previous_watermark"] is None
    assert result["next_watermark"] is not None
    assert result["scan_target_at"] == _iso_utc(bootstrap_target)
    assert result["pages_fetched"] == 2
    assert calls == [
        {"offset": 0, "limit": espi.GPW_REPORTS_LIMIT},
        {"offset": 15, "limit": 15},
    ]
    assert db.query(EventReport).count() == 2
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == result["next_watermark"]
    assert state.scan_started_at is None
    assert state.scan_target_at is None
    assert state.scan_next_offset is None
    assert state.scan_next_limit is None


def test_poll_walks_multiple_pages_until_inclusive_boundary_page(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 10, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    calls = _patch_pages(
        monkeypatch,
        [
            _page(
                [
                    _summary("1", datetime(2026, 7, 10, 15, 0, tzinfo=espi.WARSAW_TZ)),
                    _summary("2", datetime(2026, 7, 10, 14, 0, tzinfo=espi.WARSAW_TZ)),
                ],
                next_offset=15,
            ),
            _page(
                [
                    _summary("3", datetime(2026, 7, 10, 13, 30, tzinfo=espi.WARSAW_TZ)),
                    _summary("4", watermark),
                    _summary("5", datetime(2026, 7, 10, 12, 30, tzinfo=espi.WARSAW_TZ)),
                ],
                next_offset=30,
            ),
        ],
    )
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    result = espi.poll_watchlist_reports(db)

    assert result["complete"] is True
    assert result["boundary_reached"] is True
    assert result["pages_fetched"] == 2
    assert len(calls) == 2
    assert result["previous_watermark"] == watermark.isoformat()
    assert result["next_watermark"] != watermark.isoformat()
    assert result["matched"] == 5
    assert result["new"] == 5
    assert {row["external_id"] for row in result["reports"]} == {
        "gpw:1",
        "gpw:2",
        "gpw:3",
        "gpw:4",
        "gpw:5",
    }
    assert db.query(EventReport).count() == 5
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == result["next_watermark"]


def test_poll_dedupes_duplicate_ids_and_equal_timestamp_boundary(db, monkeypatch):
    from app.db.models import EventReport
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 10, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    _patch_pages(
        monkeypatch,
        [
            _page(
                [_summary("1", datetime(2026, 7, 10, 14, 0, tzinfo=espi.WARSAW_TZ))],
                next_offset=15,
            ),
            _page(
                [
                    _summary("1", datetime(2026, 7, 10, 14, 0, tzinfo=espi.WARSAW_TZ)),
                    _summary("2", watermark),
                    _summary("3", watermark),
                ]
            ),
        ],
    )
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    result = espi.poll_watchlist_reports(db)

    assert result["complete"] is True
    assert result["boundary_reached"] is True
    assert result["matched"] == 3
    assert result["new"] == 3
    assert db.query(EventReport).count() == 3
    assert [row["external_id"] for row in result["reports"]] == [
        "gpw:1",
        "gpw:2",
        "gpw:3",
    ]


def test_poll_rejects_non_descending_timestamps_within_page(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 9, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    _patch_pages(
        monkeypatch,
        [
            _page(
                [
                    _summary("1", datetime(2026, 7, 10, 10, 0, tzinfo=espi.WARSAW_TZ)),
                    _summary("2", datetime(2026, 7, 10, 11, 0, tzinfo=espi.WARSAW_TZ)),
                ]
            )
        ],
    )
    monkeypatch.setattr(
        espi,
        "fetch_report_detail",
        lambda _url: (_ for _ in ()).throw(AssertionError("must fail before details")),
    )

    result = espi.poll_watchlist_reports(db)

    assert result["ok"] is False
    assert result["complete"] is False
    assert result["incomplete_reason"].startswith("list_page_error:")
    assert db.query(EventReport).count() == 0
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == watermark.isoformat()


def test_poll_rejects_non_descending_timestamps_across_pages(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 9, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    _patch_pages(
        monkeypatch,
        [
            _page([_summary("1", datetime(2026, 7, 10, 10, 0, tzinfo=espi.WARSAW_TZ))], next_offset=15),
            _page([_summary("2", datetime(2026, 7, 10, 10, 30, tzinfo=espi.WARSAW_TZ))]),
        ],
    )
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    result = espi.poll_watchlist_reports(db)

    assert result["ok"] is False
    assert result["complete"] is False
    assert result["pages_fetched"] == 1
    assert result["continuation_offset"] == 15
    assert db.query(EventReport).count() == 1
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == watermark.isoformat()
    assert state.scan_next_offset == 15


def test_existing_watermark_cap_resumes_cursor_and_advances_once(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 9, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    monkeypatch.setattr(espi, "GPW_REPORTS_HARD_PAGE_CAP", 1)
    first_calls = _patch_pages(
        monkeypatch,
        [
            _page([_summary("1", datetime(2026, 7, 10, 15, 0, tzinfo=espi.WARSAW_TZ))], next_offset=15),
        ],
    )
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    first = espi.poll_watchlist_reports(db)

    assert first["complete"] is False
    assert first["cap_reached"] is True
    assert first["incomplete_reason"] == "hard_page_cap_reached_before_watermark"
    assert first["next_watermark"] == watermark.isoformat()
    assert first["continuation_offset"] == 15
    assert first_calls == [{"offset": 0, "limit": espi.GPW_REPORTS_LIMIT}]
    assert db.query(EventReport).count() == 1
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == watermark.isoformat()
    assert state.scan_next_offset == 15
    assert state.scan_next_limit == 15
    scan_started = _iso_utc(state.scan_started_at)

    second_calls = _patch_pages(
        monkeypatch,
        [_page([_summary("2", watermark)])],
    )

    second = espi.poll_watchlist_reports(db)

    assert second["complete"] is True
    assert second["previous_watermark"] == watermark.isoformat()
    assert second["next_watermark"] == scan_started
    assert second_calls == [{"offset": 15, "limit": 15}]
    assert db.query(EventReport).count() == 2
    assert _iso_utc(state.last_polled_at) == scan_started
    assert state.scan_started_at is None
    assert state.scan_target_at is None
    assert state.scan_next_offset is None
    assert state.scan_next_limit is None


def test_first_run_bootstrap_cap_resumes_cursor_and_advances_once(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    bootstrap_target = datetime(2026, 7, 10, 12, 30, tzinfo=timezone.utc)
    _watched_kruk(db, added_at=bootstrap_target)
    monkeypatch.setattr(espi, "GPW_REPORTS_HARD_PAGE_CAP", 1)
    first_calls = _patch_pages(
        monkeypatch,
        [
            _page(
                [_summary("1", datetime(2026, 7, 10, 15, 0, tzinfo=espi.WARSAW_TZ))],
                next_offset=15,
            ),
        ],
    )
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    first = espi.poll_watchlist_reports(db)

    assert first["ok"] is False
    assert first["complete"] is False
    assert first["cap_reached"] is True
    assert first["previous_watermark"] is None
    assert first["next_watermark"] is None
    assert first["scan_target_at"] == _iso_utc(bootstrap_target)
    assert first["continuation_offset"] == 15
    assert first_calls == [{"offset": 0, "limit": espi.GPW_REPORTS_LIMIT}]
    assert db.query(EventReport).count() == 1
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert state.last_polled_at is None
    assert state.scan_next_offset == 15
    scan_started = _iso_utc(state.scan_started_at)

    second_calls = _patch_pages(
        monkeypatch,
        [_page([_summary("2", bootstrap_target)])],
    )

    second = espi.poll_watchlist_reports(db)

    assert second["ok"] is True
    assert second["complete"] is True
    assert second["next_watermark"] == scan_started
    assert second_calls == [{"offset": 15, "limit": 15}]
    assert db.query(EventReport).count() == 2
    assert _iso_utc(state.last_polled_at) == scan_started
    assert state.scan_started_at is None
    assert state.scan_target_at is None
    assert state.scan_next_offset is None
    assert state.scan_next_limit is None


def test_list_page_failure_is_incomplete_and_keeps_watermark(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 9, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    _patch_pages(
        monkeypatch,
        [
            _page([_summary("1", datetime(2026, 7, 10, 15, 0, tzinfo=espi.WARSAW_TZ))], next_offset=15),
            RuntimeError("HTTP 500"),
        ],
    )
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    result = espi.poll_watchlist_reports(db)

    assert result["complete"] is False
    assert result["pages_fetched"] == 1
    assert result["incomplete_reason"].startswith("list_page_error:")
    assert db.query(EventReport).count() == 1
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == watermark.isoformat()


def test_first_run_bootstrap_fetch_failure_preserves_stable_cutoff(db, monkeypatch):
    from app.db.models import ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    first_calls = _patch_pages(monkeypatch, [RuntimeError("HTTP 500")])

    result = espi.poll_watchlist_reports(db)

    assert result["ok"] is False
    assert result["complete"] is False
    assert result["incomplete_reason"].startswith("list_page_error:")
    assert first_calls == [{"offset": 0, "limit": espi.GPW_REPORTS_LIMIT}]
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert state.last_polled_at is None
    first_cutoff = _iso_utc(state.scan_started_at)

    retry_calls = _patch_pages(monkeypatch, [RuntimeError("HTTP 500")])
    retry = espi.poll_watchlist_reports(db)

    assert retry["ok"] is False
    assert retry_calls == [{"offset": 0, "limit": espi.GPW_REPORTS_LIMIT}]
    assert _iso_utc(state.scan_started_at) == first_cutoff


def test_later_page_parse_failure_is_incomplete_and_keeps_watermark(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 9, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    _patch_pages(
        monkeypatch,
        [
            _page(
                [_summary("1", datetime(2026, 7, 10, 15, 0, tzinfo=espi.WARSAW_TZ))],
                next_offset=15,
            ),
            espi.GpwReportParseError("malformed later page"),
        ],
    )
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    result = espi.poll_watchlist_reports(db)

    assert result["ok"] is False
    assert result["complete"] is False
    assert result["pages_fetched"] == 1
    assert result["incomplete_reason"].startswith("list_page_error:")
    assert db.query(EventReport).count() == 1
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == watermark.isoformat()


def test_detail_failure_after_successful_page_retries_same_cursor(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 9, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    first_calls = _patch_pages(
        monkeypatch,
        [
            _page(
                [_summary("1", datetime(2026, 7, 10, 15, 0, tzinfo=espi.WARSAW_TZ))],
                next_offset=15,
            ),
            _page([_summary("2", watermark)]),
        ],
    )

    def fake_detail(url):
        if "geru_id=2" in url:
            raise RuntimeError("detail unavailable")
        return _detail(url)

    monkeypatch.setattr(espi, "fetch_report_detail", fake_detail)

    result = espi.poll_watchlist_reports(db)

    assert result["complete"] is False
    assert result["incomplete_reason"].startswith("detail_error:")
    assert result["matched"] == 2
    assert result["new"] == 1
    assert result["continuation_offset"] == 15
    assert first_calls == [
        {"offset": 0, "limit": espi.GPW_REPORTS_LIMIT},
        {"offset": 15, "limit": 15},
    ]
    assert db.query(EventReport).count() == 1
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == watermark.isoformat()
    assert state.scan_next_offset == 15

    second_calls = _patch_pages(monkeypatch, [_page([_summary("2", watermark)])])
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    retry = espi.poll_watchlist_reports(db)

    assert retry["complete"] is True
    assert second_calls == [{"offset": 15, "limit": 15}]
    assert db.query(EventReport).count() == 2
    assert _iso_utc(state.last_polled_at) == retry["next_watermark"]


def test_no_details_ingests_metadata_but_never_advances_watermark(db, monkeypatch):
    from app.db.models import EventReport, ListPollState
    from app.scrapers import espi

    _watched_kruk(db)
    watermark = datetime(2026, 7, 10, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    _patch_pages(monkeypatch, [_page([_summary("1", watermark)])])

    def fail_detail(_url):
        raise AssertionError("metadata-only mode must not fetch details")

    monkeypatch.setattr(espi, "fetch_report_detail", fail_detail)

    result = espi.poll_watchlist_reports(db, fetch_details=False)

    assert result["ok"] is False
    assert result["complete"] is False
    assert result["metadata_only"] is True
    assert result["incomplete_reason"] == "details_skipped_metadata_only"
    assert result["next_watermark"] is None
    report = db.query(EventReport).one()
    assert report.raw_text is None
    state = db.query(ListPollState).filter_by(source_key=espi.SOURCE_KEY).one()
    assert _iso_utc(state.last_polled_at) == watermark.isoformat()
    assert state.scan_started_at is None
    assert state.scan_target_at is None
    assert state.scan_next_offset is None
    assert state.scan_next_limit is None


def test_scoped_poll_does_not_initialize_global_watermark_then_global_ingests_other(
    db, monkeypatch
):
    from app.db.models import Company, EventReport, ListPollState, WatchlistItem
    from app.scrapers import espi

    kruk = Company(ticker="KRU", name="KRUK")
    eurotel = Company(ticker="ETL", name="EUROTEL")
    db.add_all([kruk, eurotel])
    db.commit()
    added_at = datetime(2026, 7, 10, 6, 30, tzinfo=timezone.utc)
    db.add_all(
        [
            WatchlistItem(company_id=kruk.id, added_at=added_at),
            WatchlistItem(company_id=eurotel.id, added_at=added_at),
        ]
    )
    db.commit()
    p1 = _page(
        [_summary("1", datetime(2026, 7, 10, 10, 0, tzinfo=espi.WARSAW_TZ))],
        next_offset=15,
    )
    p2 = _page(
        [
            _summary(
                "2",
                datetime(2026, 7, 10, 9, 0, tzinfo=espi.WARSAW_TZ),
                issuer="EUROTEL",
            )
        ]
    )
    calls = _patch_pages(monkeypatch, [p1, p2])
    monkeypatch.setattr(espi, "fetch_report_detail", lambda url: _detail(url))

    scoped = espi.poll_watchlist_reports(db, ticker="KRU")

    assert scoped["ok"] is True
    assert scoped["complete"] is True
    assert scoped["next_watermark"] is None
    assert db.query(ListPollState).count() == 0
    assert db.query(EventReport).count() == 1

    calls.clear()
    _patch_pages(monkeypatch, [p1, p2])
    global_result = espi.poll_watchlist_reports(db)

    assert global_result["ok"] is True
    assert global_result["complete"] is True
    assert global_result["pages_fetched"] == 2
    assert {report.company_id for report in db.query(EventReport).all()} == {
        kruk.id,
        eurotel.id,
    }


def test_existing_raw_text_skips_detail_refetch(db, monkeypatch):
    from app.db.models import EventReport
    from app.scrapers import espi

    kruk = _watched_kruk(db)
    watermark = datetime(2026, 7, 10, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    db.add(
        EventReport(
            company_id=kruk.id,
            source="espi",
            external_id="gpw:1",
            raw_url="old",
            published_at=watermark,
            title="old title",
            raw_text="already fetched",
            parsed={"detail": {"subject": "existing"}},
            materiality={"level": "reviewed", "reason": "human"},
        )
    )
    db.commit()
    _patch_pages(monkeypatch, [_page([_summary("1", watermark)])])

    def fail_detail(_url):
        raise AssertionError("detail should not be re-fetched")

    monkeypatch.setattr(espi, "fetch_report_detail", fail_detail)

    result = espi.poll_watchlist_reports(db)

    assert result["complete"] is True
    report = db.query(EventReport).one()
    assert report.raw_text == "already fetched"
    assert report.parsed["detail"]["subject"] == "existing"
    assert report.materiality == {"level": "reviewed", "reason": "human"}


def test_revisit_fills_missing_raw_text_without_resetting_reviewed_materiality(
    db, monkeypatch
):
    from app.db.models import EventReport
    from app.scrapers import espi

    kruk = _watched_kruk(db)
    watermark = datetime(2026, 7, 10, 11, 0, tzinfo=timezone.utc)
    _set_watermark(db, watermark)
    db.add(
        EventReport(
            company_id=kruk.id,
            source="espi",
            external_id="gpw:1",
            raw_url="old",
            published_at=watermark,
            title="old title",
            raw_text=None,
            parsed={"detail": {"subject": "reviewed detail"}, "custom": "keep"},
            materiality={"level": "material", "reviewed_by": "analyst"},
        )
    )
    db.commit()
    _patch_pages(monkeypatch, [_page([_summary("1", watermark)])])
    monkeypatch.setattr(espi, "fetch_report_detail", lambda _url: _detail("new detail"))

    result = espi.poll_watchlist_reports(db)

    assert result["complete"] is True
    report = db.query(EventReport).one()
    assert report.raw_text == "raw new detail"
    assert report.parsed["detail"] == {"subject": "reviewed detail"}
    assert report.parsed["custom"] == "keep"
    assert report.materiality == {"level": "material", "reviewed_by": "analyst"}


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
    monkeypatch.setattr(
        espi,
        "fetch_report_list_page",
        lambda **_kwargs: espi.GpwReportListPage(
            reports=summaries,
            next_offset=None,
            next_limit=None,
        ),
    )
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
