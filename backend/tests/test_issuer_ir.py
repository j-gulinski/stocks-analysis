"""RT2.3 bounded issuer-IR parser and immutable evidence bridge."""
import pytest
from sqlalchemy import func, select

from tests.conftest import FakeResponse, load_fixture


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
        ]
    )
    db.commit()
    fixtures = {
        "SNT": "issuer_ir_snt.html",
        "ABS": "issuer_ir_abs.html",
        "OPM": "issuer_ir_opm.html",
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
    assert len(calls) == 3
    assert db.scalar(select(func.count()).select_from(SourceDocument)) == 3
    assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 3
    assert db.scalar(select(func.count()).select_from(Fact)) == 4
    assert db.scalar(
        select(func.count())
        .select_from(Fact)
        .where(Fact.verification_state == "unverified")
    ) == 4
    assert db.scalar(
        select(func.count())
        .select_from(FetchLog)
        .where(FetchLog.document_version_id.is_not(None))
    ) == 3

    cached = issuer_ir.ingest_issuer_ir_index(db, "SNT")
    assert cached["status"] == "cached"
    assert len(calls) == 3


def test_ingest_issuer_ir_returns_temporary_state_on_polite_hard_stop(db, monkeypatch):
    from app.db.models import Company, FetchLog
    from app.scrapers import issuer_ir

    db.add(Company(ticker="SNT", name="SYNEKTIK SA"))
    db.commit()
    monkeypatch.setattr(
        issuer_ir.http,
        "fetch",
        lambda _url: (_ for _ in ()).throw(
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
        extractor_version="test",
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
        lambda _url: calls.append(_url) or response,
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
        extractor_version="test",
    )
    db.commit()
    response = FakeResponse("", 200)
    response.url = "https://files.example/report.pdf"
    response.content = b"%PDF-test"
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url: response)

    result = issuer_ir.ingest_issuer_ir_report(db, "ABS", report_url)

    assert result["status"] == "rejected"
    assert "redirect" in result["error"].lower()
    assert not list(db.scalars(select(Fact).where(Fact.fact_type == "issuer_ir_page")))


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
        extractor_version="test",
    )
    db.commit()
    response = FakeResponse("", 200)
    response.url = report_url
    response.content = b"%PDF-broken"
    monkeypatch.setattr(issuer_ir.http, "fetch", lambda _url: response)
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
