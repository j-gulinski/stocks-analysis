"""P1.9 tests: BiznesRadar premium-session login.

Login mechanics were captured live from the Dialogs.login() modal on
2026-07-08 (see skills/scraper-doctor/SKILL.md "BiznesRadar — premium login"):
there is NO server-rendered login page — the form is built client-side and
POSTs to the fixed endpoint /login/ with {email, password}. Success is
confirmed by the 'account-settings' marker on the re-fetched homepage, with the
/user-data/ payload size as a fallback. These tests drive that flow with a
monkeypatched fetcher — no real network, no politeness sleep.
"""
import pytest

import app.scrapers.biznesradar as br
from app.services import refresh
from app.scrapers.biznesradar import (
    BASE_URL,
    BrClient,
    BrLoginError,
    _looks_logged_in,
    extract_login_fields,
)
from tests.conftest import FakeResponse, load_fixture

# Logged-in homepage carries the 'account-settings' marker; the anonymous page
# carries 'Dialogs.login'/'Logowanie' and lacks it (both verified live).
LOGGED_IN_HOMEPAGE = (
    "<html><body><script>Dialogs.accountSettings()</script>"
    "<a class='account-settings' href='#'>Ustawienia konta</a></body></html>"
)
ANON_HOMEPAGE = (
    "<html><body><a href='javascript:void(0)' onclick='Dialogs.login()'>"
    "Logowanie</a></body></html>"
)
UNKNOWN_HOMEPAGE = "<html><body>zupełnie inna strona</body></html>"
USER_DATA_ANON = "var brUser={loggedIn:false};"  # ~28 B, well under 1000
USER_DATA_LOGGED_IN = "var brUser={loggedIn:true," + "x" * 1700 + "};"  # > 1000 B


# ----------------------------------------------------------------- parsing

def test_extract_login_fields_live_fixture():
    """The captured modal form carries exactly email/password/remember_me."""
    assert extract_login_fields(load_fixture("br_login_live.html")) == {
        "email": "email",
        "password": "password",
        "remember_me": "checkbox",
    }


def test_extract_login_fields_missing_form_raises():
    with pytest.raises(BrLoginError):
        extract_login_fields("<html><body>nothing here</body></html>")


def test_looks_logged_in_marker_presence():
    assert _looks_logged_in(LOGGED_IN_HOMEPAGE) is True
    assert _looks_logged_in(ANON_HOMEPAGE) is False


# ------------------------------------------------------------------ client

def _install_fake_fetch(monkeypatch, *, homepage, user_data=USER_DATA_ANON):
    """Replace polite_http.fetch with a scripted, network-free fake.

    Records every call as (method, url, data). GET of the homepage returns
    `homepage`; GET of /user-data/ returns `user_data`; POST /login/ returns an
    empty 200 (BiznesRadar redirects — the body is not authoritative)."""
    calls: list[tuple[str, str, dict | None]] = []

    def fake_fetch(url, *, method="GET", data=None, session=None, timeout=30):
        calls.append((method, url, data))
        if method == "POST":
            return FakeResponse("", 200)
        if url.endswith("/user-data/"):
            return FakeResponse(user_data, 200)
        return FakeResponse(homepage, 200)  # homepage (warm-up + verify)

    monkeypatch.setattr(br.polite_http, "fetch", fake_fetch)
    return calls


def test_login_success_posts_email_password_and_confirms_marker(monkeypatch):
    calls = _install_fake_fetch(monkeypatch, homepage=LOGGED_IN_HOMEPAGE)

    client = BrClient()
    client.login("me@example.com", "secret")

    assert client.logged_in is True
    posts = [c for c in calls if c[0] == "POST"]
    assert len(posts) == 1
    _method, url, data = posts[0]
    # Trailing slash is required — /login and /logowanie both 404.
    assert url == BASE_URL + "/login/"
    assert data == {"email": "me@example.com", "password": "secret"}


def test_login_wrong_credentials_raises(monkeypatch):
    # BR re-serves the anonymous homepage + a short /user-data/ payload.
    _install_fake_fetch(monkeypatch, homepage=ANON_HOMEPAGE, user_data=USER_DATA_ANON)

    client = BrClient()
    with pytest.raises(BrLoginError, match="BR_USERNAME"):
        client.login("me@example.com", "wrongpass")
    assert client.logged_in is False


def test_login_user_data_fallback_confirms(monkeypatch):
    # Homepage lacks the marker (e.g. stale anon CDN cache) but /user-data/
    # proves the session is logged in.
    _install_fake_fetch(
        monkeypatch, homepage=ANON_HOMEPAGE, user_data=USER_DATA_LOGGED_IN
    )

    client = BrClient()
    client.login("me@example.com", "secret")
    assert client.logged_in is True


def test_login_unrecognized_page_raises(monkeypatch):
    # Neither marker present — recipe drift, distinct message from wrong-creds.
    _install_fake_fetch(
        monkeypatch, homepage=UNKNOWN_HOMEPAGE, user_data=USER_DATA_ANON
    )

    client = BrClient()
    with pytest.raises(BrLoginError, match="nierozpoznan"):
        client.login("me@example.com", "secret")
    assert client.logged_in is False


# ------------------------------------------------------------- diagnostics

def test_br_login_status_endpoint_without_credentials(client):
    """conftest neutralizes BR_USERNAME/BR_PASSWORD, so this must never hit
    the network — mirrors test_forum.py's test_login_status_without_credentials."""
    body = client.get("/api/diagnostics/br-login-status").json()
    assert body["ok"] is False
    assert body["status"] == "not_configured"
    assert "not configured" in body["detail"]


def test_br_login_status_get_is_configuration_only(client, monkeypatch):
    class Settings:
        br_username = "private@example.com"
        br_password = "secret"

    monkeypatch.setattr("app.api.diagnostics.get_settings", lambda: Settings())
    monkeypatch.setattr(
        "app.api.diagnostics.refresh_service.check_br_login",
        lambda: (_ for _ in ()).throw(AssertionError("GET attempted remote login")),
    )

    body = client.get("/api/diagnostics/br-login-status").json()

    assert body == {
        "ok": True,
        "status": "configured",
        "detail": (
            "BiznesRadar credentials are configured; login is attempted only "
            "by an explicit refresh or diagnostic command."
        ),
    }


def test_refresh_login_summary_never_exposes_account_identifier(monkeypatch):
    class Settings:
        br_username = "private@example.com"
        br_password = "secret"

    class FakeClient:
        session = object()

        def login(self, _username, _password):
            return None

    monkeypatch.setattr(refresh, "get_settings", lambda: Settings())
    monkeypatch.setattr(refresh.biznesradar, "BrClient", FakeClient)
    summary: dict[str, str] = {}

    session = refresh._build_br_session(summary)

    assert session is not None
    assert summary["br_login"] == "ok (zalogowano)"
    assert "private@example.com" not in summary["br_login"]

    diagnostic = refresh.check_br_login()
    assert diagnostic["ok"] is True
    assert diagnostic["detail"] == "BiznesRadar login verified."
    assert "private@example.com" not in diagnostic["detail"]
