"""P1.9 tests: BiznesRadar premium-session plumbing.

IMPORTANT — tests/fixtures/br_login.html is a SYNTHETIC fixture (see its own
header comment): nobody has ever recorded BiznesRadar's real login page in
this codebase (sandboxed egress to biznesradar.pl was blocked while this was
written). These tests prove the plumbing — parsing hidden fields, building
the login payload, treating login failure as non-fatal — works against a
plausible login form. They do NOT prove the parser matches the real site.
Once a real login page is recorded (scripts/record_fixtures.py or a manual
capture), replace the fixture and re-verify extract_login_fields()/
BrClient against it, then do one real login by hand.
"""
import pytest

from app.scrapers.biznesradar import BrClient, BrLoginError, extract_login_fields
from tests.conftest import FakeResponse, load_fixture

import app.scrapers.biznesradar as br


# ----------------------------------------------------------------- parsing

def test_extract_login_fields_fixture():
    fields = extract_login_fields(load_fixture("br_login.html"))
    assert fields == {"csrf_token": "synthetic-token-abc123", "redirect": "/"}


def test_extract_login_fields_missing_form_raises():
    with pytest.raises(BrLoginError):
        extract_login_fields("<html><body>nothing here</body></html>")


# ------------------------------------------------------------------ client

class _FakePostResponse:
    """Minimal stand-in for requests.Response used only by these tests."""

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


def _stub_login_page_fetch(monkeypatch, html: str) -> None:
    """Replace polite_http.fetch (the GET of the login page) with a canned
    response — no real network, no politeness sleep."""
    monkeypatch.setattr(
        br.polite_http,
        "fetch",
        lambda url, session=None, timeout=30: FakeResponse(html, 200),
    )


def test_br_client_login_posts_expected_payload(monkeypatch):
    login_html = load_fixture("br_login.html")
    _stub_login_page_fetch(monkeypatch, login_html)

    client = BrClient()
    captured: dict = {}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return _FakePostResponse(
            "<html><body>Zalogowano. <a href='/logout'>Wyloguj</a></body></html>", 200
        )

    monkeypatch.setattr(client.session, "post", fake_post)

    client.login("testuser", "testpass")

    assert client.logged_in is True
    assert captured["url"].endswith("/logowanie")
    # Hidden fields echoed back unchanged + credentials added — same shape as
    # portalanaliz.ForumClient.login's payload.
    assert captured["data"] == {
        "csrf_token": "synthetic-token-abc123",
        "redirect": "/",
        "login": "testuser",
        "password": "testpass",
    }


def test_br_client_login_raises_on_failure_response(monkeypatch):
    login_html = load_fixture("br_login.html")
    _stub_login_page_fetch(monkeypatch, login_html)

    client = BrClient()

    def fake_post(url, data=None, timeout=None):
        # BiznesRadar re-serves the login form (still has a password field)
        # on bad credentials — no logout link appears anywhere.
        return _FakePostResponse(login_html, 200)

    monkeypatch.setattr(client.session, "post", fake_post)

    with pytest.raises(BrLoginError, match="BR_USERNAME"):
        client.login("testuser", "wrongpass")
    assert client.logged_in is False


def test_br_client_login_page_http_error_raises(monkeypatch):
    _stub_login_page_fetch(monkeypatch, "")
    monkeypatch.setattr(
        br.polite_http,
        "fetch",
        lambda url, session=None, timeout=30: FakeResponse("", 503),
    )
    client = BrClient()
    with pytest.raises(BrLoginError):
        client.login("testuser", "testpass")


# ------------------------------------------------------------- diagnostics

def test_br_login_status_endpoint_without_credentials(client):
    """conftest neutralizes BR_USERNAME/BR_PASSWORD, so this must never hit
    the network — mirrors test_forum.py's test_login_status_without_credentials."""
    body = client.get("/api/diagnostics/br-login-status").json()
    assert body["ok"] is False
    assert body["status"] == "not_configured"
    assert "not configured" in body["detail"]
