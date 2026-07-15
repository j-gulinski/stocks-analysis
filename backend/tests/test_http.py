"""Tests for the polite fetcher: retry/backoff/hard-stop behavior.

Politeness delays are monkeypatched away (no_sleep) — we assert *that* sleeps
would happen, not how long they take.
"""
import pytest
import requests

import app.scrapers.http as polite_http
from tests.conftest import FakeResponse


class StubSession:
    """Session returning a scripted sequence of responses/exceptions."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.headers: dict = {}

    def get(self, url, timeout, **_kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_returns_first_terminal_response(no_sleep):
    session = StubSession([FakeResponse("ok", 200)])
    response = polite_http.fetch("https://www.biznesradar.pl/x", session=session)
    assert response.status_code == 200
    assert session.calls == 1
    assert "User-Agent" in session.headers  # realistic UA is always set


def test_replaces_requests_default_user_agent(no_sleep):
    session = StubSession([FakeResponse("ok", 200)])
    session.headers["User-Agent"] = requests.utils.default_user_agent()

    polite_http.fetch("https://www.biznesradar.pl/x", session=session)

    assert session.headers["User-Agent"] == polite_http.USER_AGENT


def test_preserves_explicit_session_user_agent(no_sleep):
    session = StubSession([FakeResponse("ok", 200)])
    session.headers["User-Agent"] = "WorkbenchForumSession/1.0"

    polite_http.fetch("https://www.biznesradar.pl/x", session=session)

    assert session.headers["User-Agent"] == "WorkbenchForumSession/1.0"


def test_404_is_terminal_not_retried(no_sleep):
    session = StubSession([FakeResponse("", 404)])
    response = polite_http.fetch("https://www.biznesradar.pl/x", session=session)
    assert response.status_code == 404
    assert session.calls == 1


def test_retryable_status_then_success(no_sleep):
    session = StubSession([FakeResponse("", 503), FakeResponse("ok", 200)])
    response = polite_http.fetch("https://www.biznesradar.pl/x", session=session)
    assert response.status_code == 200
    assert session.calls == 2


def test_hard_stop_after_max_attempts(no_sleep):
    session = StubSession([FakeResponse("", 429)] * polite_http.MAX_ATTEMPTS)
    with pytest.raises(polite_http.FetchBlockedError):
        polite_http.fetch("https://www.biznesradar.pl/x", session=session)
    assert session.calls == polite_http.MAX_ATTEMPTS


def test_network_errors_are_retried(no_sleep):
    import requests

    session = StubSession(
        [requests.ConnectionError("boom"), FakeResponse("ok", 200)]
    )
    response = polite_http.fetch("https://portalanaliz.pl/forum/x", session=session)
    assert response.status_code == 200


def test_domain_delay_ranges_configured():
    assert polite_http._delay_range("www.biznesradar.pl") == (2.0, 4.0)
    assert polite_http._delay_range("portalanaliz.pl") == (1.5, 3.0)
    assert polite_http._delay_range("example.com") == polite_http.DEFAULT_DELAY_RANGE
