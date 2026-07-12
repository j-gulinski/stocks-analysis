"""RT2.3 bounded issuer-IR parser and immutable evidence bridge."""
import pytest
from sqlalchemy import func, select

from tests.conftest import FakeResponse, load_fixture


@pytest.fixture(autouse=True)
def public_issuer_hosts(monkeypatch):
    from app.scrapers import issuer_ir

    monkeypatch.setattr(issuer_ir, "_host_resolves_public", lambda _url: True)
    monkeypatch.setattr(issuer_ir, "_peer_is_public", lambda _response: True)


def _seed_report_link(db, report_url: str, *, extractor_version: str | None = None):
    from app.db.models import Company
    from app.scrapers import issuer_ir
    from app.services import evidence

    company = Company(ticker="ABS", name="ASSECO BUSINESS SOLUTIONS SA")
    db.add(company)
    db.flush()
    index = evidence.record_document_version(
        db,
        company,
        source_name="ABS issuer IR",
        source_type="issuer_ir",
        scope_key="reports-index",
        requested_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        effective_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        content=b"index",
        text="index",
        response_status=200,
        mime_type="text/html",
    )
    evidence.mark_parse_result(index.version, success=True)
    evidence.record_text_fact(
        db,
        company,
        index.version,
        fact_type="issuer_ir_link",
        fact_key="issuer_ir.periodic_report.seed",
        text="Seed report",
        locator={"url": report_url},
        verification_state="unverified",
        extractor_version=extractor_version or issuer_ir.EXTRACTOR_VERSION,
    )
    db.commit()
    return company


@pytest.mark.parametrize(
    ("fixture", "base_url", "expected_title", "expected_count"),
    [
        (
            "issuer_ir_snt.html",
            "https://synektik.com.pl/centrum-inwestora/raporty-biezace/",
            "Raporty bieżące - Synektik",
            1,
        ),
        (
            "issuer_ir_abs.html",
            "https://assecobs.pl/inwestor/raporty-biezace/",
            "Raporty bieżące - Asseco Business Solutions",
            1,
        ),
        (
            "issuer_ir_opm.html",
            "https://opteam.pl/firma/relacje-inwestorskie",
            "Relacje inwestorskie | OPTeam",
            2,
        ),
        (
            "issuer_ir_asb.html",
            "https://investor.asbis.com/news/financial-reports-archive/financial-reports-2026",
            "Financial Reports 2026 - ASBIS",
            1,
        ),
        (
            "issuer_ir_art.html",
            "https://www.artifexmundi.com/en/quarterly-report-for-the-first-quarter-of-2026/",
            "Artifex Mundi - Quarterly report for the first quarter of 2026",
            1,
        ),
        (
            "issuer_ir_dig.html",
            "https://digitalnetwork.pl/raporty/raporty-okresowe/",
            "Raporty okresowe - Digital Network",
            1,
        ),
    ],
)
def test_parse_issuer_ir_index_shapes(
    fixture, base_url, expected_title, expected_count
):
    from app.scrapers.issuer_ir import parse_issuer_ir_index

    parsed = parse_issuer_ir_index(load_fixture(fixture), base_url=base_url)

    assert parsed.title == expected_title
    assert len(parsed.links) == expected_count
    assert all(link.url.startswith("https://") for link in parsed.links)
    assert all(link.locator["tag"] == "a" for link in parsed.links)


def test_ingest_issuer_ir_pilot_records_versions_and_unverified_link_claims(
    db, monkeypatch
):
    from app.db.models import Company, DocumentVersion, Fact, FetchLog, SourceDocument
    from app.scrapers import issuer_ir

    db.add_all(
        [
            Company(ticker="SNT", name="SYNEKTIK SA"),
            Company(ticker="ABS", name="ASSECO BUSINESS SOLUTIONS SA"),
            Company(ticker="OPM", name="OPTEAM SA"),
            Company(ticker="ASB", name="ASBISc ENTERPRISES PLC"),
            Company(ticker="ART", name="ARTIFEX MUNDI SA"),
            Company(ticker="DIG", name="DIGITAL NETWORK SA"),
        ]
    )
    db.commit()
    fixtures = {
        "SNT": "issuer_ir_snt.html",
        "ABS": "issuer_ir_abs.html",
        "OPM": "issuer_ir_opm.html",
        "ASB": "issuer_ir_asb.html",
        "ART": "issuer_ir_art.html",
        "DIG": "issuer_ir_dig.html",
    }
    calls = []

    def fake_fetch(url, **_kwargs):
        calls.append(url)
        ticker = next(key for key, value in issuer_ir.ISSUER_IR_SOURCES.items() if value == url)
        response = FakeResponse(load_fixture(fixtures[ticker]), 200)
        response.url = url
        return response

    monkeypatch.setattr(issuer_ir.http, "fetch", fake_fetch)
    results = [issuer_ir.ingest_issuer_ir_index(db, ticker) for ticker in fixtures]

    assert all(result["ok"] for result in results)
    assert len(calls) == 6
    assert db.scalar(select(func.count()).select_from(SourceDocument)) == 6
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 6
    assert db.scalar(select(func.count()).select_from(Fact)) == 7
    assert db.scalar(
        select(func.count())
        .select_from(Fact)
        .where(Fact.verification_state == "unverified")
    ) == 7
    assert db.scalar(
        select(func.count())
        .select_from(FetchLog)
        .where(FetchLog.document_version_id.is_not(None))
    ) == 6

    cached = issuer_ir.ingest_issuer_ir_index(db, "SNT")
    assert cached["status"] == "cached"
    assert len(calls) == 6


def test_ingest_issuer_ir_returns_temporary_state_on_polite_hard_stop(db, monkeypatch):
    from app.db.models import Company, FetchLog
    from app.scrapers import issuer_ir

    db.add(Company(ticker="SNT", name="SYNEKTIK SA"))
    db.commit()
    monkeypatch.setattr(
        issuer_ir.http,
        "fetch",
        lambda _url, **_kwargs: (_ for _ in ()).throw(
            issuer_ir.http.FetchBlockedError("Giving up after HTTP 403")
        ),
    )

    result = issuer_ir.ingest_issuer_ir_index(db, "SNT")

    assert result["ok"] is False
    assert result["status"] == "temporarily_unavailable"
    assert result["retry_later"] is True
    assert db.query(FetchLog).one().status == 403


def test_parse_issuer_ir_caps_links_and_rejects_external_or_malformed_urls():
    from app.scrapers.issuer_ir import MAX_LINKS_PER_INDEX, parse_issuer_ir_index

    links = "".join(
        f'<h2>Raport {index}/2026</h2><a href="/raport-{index}.pdf">Raport</a>'
        for index in range(40)
    )
    html = (
        f"<html><body><main>{links}"
        '<a href="https://other.example/raport.pdf">Raport zewnętrzny</a>'
        '<a href="/broken/%22">Raport błędny</a>'
        "</main></body></html>"
    )

    parsed = parse_issuer_ir_index(html, base_url="https://issuer.example/raporty/")

    assert len(parsed.links) == MAX_LINKS_PER_INDEX
    assert all("other.example" not in link.url for link in parsed.links)
    assert all("%22" not in link.url for link in parsed.links)


def test_extract_pdf_pages_reads_bounded_pdf():
    from io import BytesIO
    from pypdf import PdfWriter

    from app.scrapers.issuer_ir import extract_pdf_pages

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)

    assert extract_pdf_pages(output.getvalue()) == [""]


def test_ingest_discovered_issuer_pdf_records_page_claims_and_cache(
    db, monkeypatch
):
    from app.db.models import Company, Fact, SourceDocument
    from app.scrapers import issuer_ir
    from app.services import evidence

    report_url = "https://assecobs.pl/reports/governance.pdf"
    company = Company(ticker="ABS", name="ASSECO BUSINESS SOLUTIONS SA")
    db.add(company)
    db.flush()
    index = evidence.record_document_version(
        db,
        company,
        source_name="ABS issuer IR",
        source_type="issuer_ir",
        scope_key="reports-index",
        requested_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        effective_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        content=b"index",
        text="index",
        response_status=200,
        mime_type="text/html",
    )
    evidence.mark_parse_result(index.version, success=True)
    evidence.record_text_fact(
        db,
        company,
        index.version,
        fact_type="issuer_ir_link",
        fact_key="issuer_ir.periodic_report.test",
        text="Sprawozdanie Rady Nadzorczej",
        locator={"url": report_url},
        verification_state="unverified",
        extractor_version=issuer_ir.EXTRACTOR_VERSION,
    )
    db.commit()
    response = FakeResponse("", 200)
    response.url = report_url
    response.content = b"%PDF-test"
    response.headers = {"content-type": "application/pdf"}
    calls = []
    monkeypatch.setattr(
        issuer_ir.http,
        "fetch",
        lambda _url, **_kwargs: calls.append(_url) or response,
    )
    monkeypatch.setattr(
        issuer_ir,
        "extract_pdf_pages",
        lambda _content: ["Page one governance claim", "Page two risk claim"],
    )

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["ok"] is True
    assert result["version_created"] is True
    assert result["page_count"] == 2
    assert result["page_claim_count"] == 2
    report_document = db.scalar(
        select(SourceDocument).where(SourceDocument.source_type == "issuer_ir_report")
    )
    assert report_document.title == "Sprawozdanie Rady Nadzorczej"
    page_facts = list(
        db.scalars(select(Fact).where(Fact.fact_type == "issuer_ir_page"))
    )
    assert [fact.locator["page"] for fact in page_facts] == [1, 2]
    assert all(fact.verification_state == "unverified" for fact in page_facts)

    cached = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)
    assert cached["status"] == "cached"
    assert len(calls) == 1


def test_ingest_issuer_pdf_rejects_url_not_discovered_in_index(db):
    from app.db.models import Company
    from app.scrapers.issuer_ir import ingest_issuer_ir_report

    db.add(Company(ticker="ABS", name="ASSECO BUSINESS SOLUTIONS SA"))
    db.commit()

    with pytest.raises(ValueError, match="not present"):
        ingest_issuer_ir_report(db, "ABS", "https://other.example/report.pdf")


def test_prior_scoped_extractor_can_authorize_report_fetch(db, monkeypatch):
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/prior-scoped.pdf"
    _seed_report_link(db, report_url, extractor_version="issuer-ir-links@4")
    response = FakeResponse("", 200)
    response.url = report_url
    response.content = b"%PDF-prior"
    response.headers = {"content-type": "application/pdf"}
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url, **_kwargs: response)
    monkeypatch.setattr(issuer_ir, "extract_pdf_pages", lambda _content: ["Prior claim"])

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "fetched"


def test_noisy_legacy_extractor_cannot_authorize_report_fetch(db):
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/noisy-legacy.pdf"
    _seed_report_link(db, report_url, extractor_version="issuer-ir-links@3")

    with pytest.raises(ValueError, match="not present"):
        issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)


def test_ingest_issuer_pdf_rejects_cross_host_redirect(db, monkeypatch):
    from app.db.models import Company, Fact
    from app.scrapers import issuer_ir
    from app.services import evidence

    report_url = "https://assecobs.pl/reports/redirect.pdf"
    company = Company(ticker="ABS", name="ASSECO BUSINESS SOLUTIONS SA")
    db.add(company)
    db.flush()
    index = evidence.record_document_version(
        db,
        company,
        source_name="ABS issuer IR",
        source_type="issuer_ir",
        scope_key="reports-index",
        requested_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        effective_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        content=b"index",
        text="index",
        response_status=200,
        mime_type="text/html",
    )
    evidence.record_text_fact(
        db,
        company,
        index.version,
        fact_type="issuer_ir_link",
        fact_key="issuer_ir.periodic_report.redirect",
        text="Redirected report",
        locator={"url": report_url},
        verification_state="unverified",
        extractor_version=issuer_ir.EXTRACTOR_VERSION,
    )
    evidence.mark_parse_result(index.version, success=True)
    db.commit()
    response = FakeResponse("", 302)
    response.url = report_url
    response.headers["location"] = "https://files.example/report.pdf"
    calls = []
    monkeypatch.setattr(
        issuer_ir.http,
        "fetch",
        lambda url, **_kwargs: calls.append(url) or response,
    )

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "rejected"
    assert "redirect" in result["error"].lower()
    assert calls == [report_url]
    assert not list(db.scalars(select(Fact).where(Fact.fact_type == "issuer_ir_page")))


def test_empty_same_host_redirect_is_upgraded_before_pdf_fetch(db, monkeypatch):
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/q1.pdf"
    _seed_report_link(db, report_url)
    redirect = FakeResponse("", 302)
    redirect.url = report_url
    redirect.headers["content-length"] = "0"
    redirect.headers["location"] = "http://assecobs.pl/reports/cache/q1.pdf?cid=1"
    pdf = FakeResponse("", 200)
    pdf.url = "https://assecobs.pl/reports/cache/q1.pdf?cid=1"
    pdf.content = b"%PDF-q1"
    pdf.headers = {"content-type": "application/pdf"}
    calls = []

    def fake_fetch(url, **_kwargs):
        calls.append(url)
        return redirect if len(calls) == 1 else pdf

    monkeypatch.setattr(issuer_ir.http, "fetch", fake_fetch)
    peer_checks = iter((False, True))
    monkeypatch.setattr(issuer_ir, "_peer_is_public", lambda _response: next(peer_checks))
    monkeypatch.setattr(issuer_ir, "extract_pdf_pages", lambda _content: ["Q1 claim"])

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "fetched"
    assert calls == [
        report_url,
        "https://assecobs.pl/reports/cache/q1.pdf?cid=1",
    ]


def test_empty_cross_host_redirect_cannot_bypass_missing_peer(db, monkeypatch):
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/q1.pdf"
    _seed_report_link(db, report_url)
    redirect = FakeResponse("", 302)
    redirect.url = report_url
    redirect.headers["content-length"] = "0"
    redirect.headers["location"] = "https://files.example/q1.pdf"
    calls = []
    monkeypatch.setattr(
        issuer_ir.http,
        "fetch",
        lambda url, **_kwargs: calls.append(url) or redirect,
    )
    monkeypatch.setattr(issuer_ir, "_peer_is_public", lambda _response: False)

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "rejected"
    assert "peer" in result["error"].lower()
    assert calls == [report_url]


def test_ingest_issuer_pdf_preserves_parse_failure_without_raising(db, monkeypatch):
    from app.db.models import Company, Fact, SourceDocument, DocumentVersion
    from app.scrapers import issuer_ir
    from app.services import evidence

    report_url = "https://assecobs.pl/reports/broken.pdf"
    company = Company(ticker="ABS", name="ASSECO BUSINESS SOLUTIONS SA")
    db.add(company)
    db.flush()
    index = evidence.record_document_version(
        db,
        company,
        source_name="ABS issuer IR",
        source_type="issuer_ir",
        scope_key="reports-index",
        requested_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        effective_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        content=b"index",
        text="index",
        response_status=200,
        mime_type="text/html",
    )
    evidence.record_text_fact(
        db,
        company,
        index.version,
        fact_type="issuer_ir_link",
        fact_key="issuer_ir.periodic_report.broken",
        text="Broken report",
        locator={"url": report_url},
        verification_state="unverified",
        extractor_version=issuer_ir.EXTRACTOR_VERSION,
    )
    evidence.mark_parse_result(index.version, success=True)
    db.commit()
    response = FakeResponse("", 200)
    response.url = report_url
    response.content = b"%PDF-broken"
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url, **_kwargs: response)
    monkeypatch.setattr(
        issuer_ir,
        "extract_pdf_pages",
        lambda _content: (_ for _ in ()).throw(ValueError("invalid xref")),
    )

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "parse_failed"
    assert "invalid xref" in result["error"]
    document = db.scalar(
        select(SourceDocument).where(SourceDocument.source_type == "issuer_ir_report")
    )
    version = db.scalar(
        select(DocumentVersion).where(DocumentVersion.source_document_id == document.id)
    )
    assert version.parse_status == "failed"
    assert "invalid xref" in version.parse_error
    assert not list(db.scalars(select(Fact).where(Fact.fact_type == "issuer_ir_page")))


def test_scanned_pdf_keeps_needs_ocr_on_cached_retry(db, monkeypatch):
    from app.db.models import DocumentVersion
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/scanned.pdf"
    _seed_report_link(db, report_url)
    response = FakeResponse("", 200)
    response.url = report_url
    response.content = b"%PDF-scan"
    calls = []
    monkeypatch.setattr(
        issuer_ir.http,
        "fetch",
        lambda url, **_kwargs: calls.append(url) or response,
    )
    monkeypatch.setattr(issuer_ir, "extract_pdf_pages", lambda _content: ["", ""])

    first = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)
    second = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert first["status"] == second["status"] == "needs_ocr"
    assert len(calls) == 1
    assert db.get(DocumentVersion, first["document_version_id"]).parse_status == "needs_ocr"


def test_oversized_pdf_is_stopped_from_content_length(db, monkeypatch):
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/oversized.pdf"
    _seed_report_link(db, report_url)
    response = FakeResponse("", 200)
    response.url = report_url
    response.headers["content-length"] = str(issuer_ir.MAX_PDF_BYTES + 1)
    response.iter_content = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("body must not be read")
    )
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url, **_kwargs: response)

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "rejected"
    assert "exceeds" in result["error"]


def test_chunked_pdf_is_stopped_at_byte_limit(db, monkeypatch):
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/chunked.pdf"
    _seed_report_link(db, report_url)
    response = FakeResponse("", 200)
    response.url = report_url
    response.headers.pop("content-length", None)
    response.iter_content = lambda **_kwargs: iter((b"1234", b"56"))
    monkeypatch.setattr(issuer_ir, "MAX_PDF_BYTES", 5)
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url, **_kwargs: response)

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "rejected"
    assert "exceeds" in result["error"]


def test_terminal_missing_report_is_structured(db, monkeypatch):
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/missing.pdf"
    _seed_report_link(db, report_url)
    response = FakeResponse("", 404)
    response.url = report_url
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url, **_kwargs: response)

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "source_not_found"
    assert result["retry_later"] is False


def test_bounded_claim_extraction_is_durable_partial(db, monkeypatch):
    from app.db.models import DocumentVersion, Fact
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/long.pdf"
    _seed_report_link(db, report_url)
    response = FakeResponse("", 200)
    response.url = report_url
    response.content = b"%PDF-long"
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url, **_kwargs: response)
    monkeypatch.setattr(
        issuer_ir,
        "extract_pdf_pages",
        lambda _content: ["x" * (issuer_ir.MAX_CLAIM_CHARS + 1)]
        + ["page"] * issuer_ir.MAX_PAGE_CLAIMS,
    )

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    version = db.get(DocumentVersion, result["document_version_id"])
    first_fact = db.scalar(
        select(Fact).where(Fact.source_version_id == version.id).order_by(Fact.id)
    )
    assert result["status"] == "fetched_partial"
    assert version.parse_status == "partial"
    assert result["page_claim_count"] == issuer_ir.MAX_PAGE_CLAIMS
    assert first_fact.locator["text_truncated"] is True


def test_unrelated_source_fact_cannot_authorize_report_fetch(db):
    from app.db.models import Company
    from app.scrapers import issuer_ir
    from app.services import evidence

    report_url = "https://assecobs.pl/reports/unrelated.pdf"
    company = Company(ticker="ABS", name="ASSECO BUSINESS SOLUTIONS SA")
    db.add(company)
    db.flush()
    unrelated = evidence.record_document_version(
        db,
        company,
        source_name="aggregator",
        source_type="financial_report",
        scope_key="income_q",
        requested_url=report_url,
        effective_url=report_url,
        content=b"unrelated",
        text="unrelated",
        response_status=200,
        mime_type="text/html",
    )
    evidence.mark_parse_result(unrelated.version, success=True)
    evidence.record_text_fact(
        db,
        company,
        unrelated.version,
        fact_type="issuer_ir_link",
        fact_key="issuer_ir.periodic_report.unrelated",
        text="Unrelated",
        locator={"url": report_url},
        verification_state="unverified",
        extractor_version=issuer_ir.EXTRACTOR_VERSION,
    )
    db.commit()

    with pytest.raises(ValueError, match="not present"):
        issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)


def test_wrong_issuer_scope_cannot_authorize_report_fetch(db):
    from app.db.models import Company
    from app.scrapers import issuer_ir
    from app.services import evidence

    report_url = "https://assecobs.pl/reports/wrong-scope.pdf"
    company = Company(ticker="ABS", name="ASSECO BUSINESS SOLUTIONS SA")
    db.add(company)
    db.flush()
    wrong_scope = evidence.record_document_version(
        db,
        company,
        source_name="ABS issuer IR",
        source_type="issuer_ir",
        scope_key="other-index",
        requested_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        effective_url=issuer_ir.ISSUER_IR_SOURCES["ABS"],
        content=b"wrong scope",
        text="wrong scope",
        response_status=200,
        mime_type="text/html",
    )
    evidence.mark_parse_result(wrong_scope.version, success=True)
    evidence.record_text_fact(
        db,
        company,
        wrong_scope.version,
        fact_type="issuer_ir_link",
        fact_key="issuer_ir.periodic_report.wrong_scope",
        text="Wrong scope",
        locator={"url": report_url},
        verification_state="unverified",
        extractor_version=issuer_ir.EXTRACTOR_VERSION,
    )
    db.commit()

    with pytest.raises(ValueError, match="not present"):
        issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)


def test_forced_reprocessing_does_not_downgrade_parsed_version(db, monkeypatch):
    from app.db.models import DocumentVersion
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/stable.pdf"
    _seed_report_link(db, report_url)
    response = FakeResponse("", 200)
    response.url = report_url
    response.content = b"%PDF-stable"
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url, **_kwargs: response)
    monkeypatch.setattr(issuer_ir, "extract_pdf_pages", lambda _content: ["Stable claim"])
    first = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)
    version = db.get(DocumentVersion, first["document_version_id"])
    assert version.parse_status == "parsed"
    original_parser = version.parser_version

    monkeypatch.setattr(issuer_ir, "extract_pdf_pages", lambda _content: [""])
    second = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url, force=True)

    db.refresh(version)
    assert second["status"] == "cached"
    assert version.parse_status == "parsed"
    assert version.parser_version == original_parser


def test_actual_loopback_peer_is_rejected_before_body_read(db, monkeypatch):
    from app.scrapers import issuer_ir

    report_url = "https://assecobs.pl/reports/rebound.pdf"
    _seed_report_link(db, report_url)
    response = FakeResponse("", 200)
    response.url = report_url
    body_read = []
    response.iter_content = lambda **_kwargs: body_read.append(True) or iter((b"%PDF",))
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url, **_kwargs: response)
    monkeypatch.setattr(issuer_ir, "_peer_is_public", lambda _response: False)

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "rejected"
    assert "peer" in result["error"].lower()
    assert body_read == []


def test_network_target_checks_reject_private_or_mixed_addresses():
    from app.scrapers import issuer_ir

    assert issuer_ir._addresses_are_public({"8.8.8.8", "127.0.0.1"}) is False
    assert issuer_ir._addresses_are_public({"169.254.1.1"}) is False
    assert issuer_ir._addresses_are_public({"8.8.8.8"}) is True

    assert issuer_ir._address_is_public("127.0.0.1") is False
    assert issuer_ir._address_is_public("8.8.8.8") is True
