"""Offline regression tests for real-fixture recorder safety."""

from pathlib import Path
from types import SimpleNamespace

from scripts.record_fixtures import recording_plan
from scripts import record_topic_fixture


def test_br_recording_plan_uses_profile_slug_for_every_non_profile_page():
    profile_html = (
        "<html><head><title>SYNEKTIK SA (SNT)</title></head><body>"
        '<a href="/notowania/SYNEKTIK">Profil</a>'
        "<p>Rynek: GPW</p></body></html>"
    )
    metadata, urls = recording_plan("SNT", profile_html)

    assert metadata["slug"] == "SYNEKTIK"
    assert urls["profile"].endswith("/notowania/SNT")
    assert urls["income_q"].endswith("/SYNEKTIK,Q")
    assert all("/SNT,Q" not in url for url in urls.values())


def test_br_recording_plan_aborts_without_canonical_slug():
    try:
        recording_plan("SNT", "<html><title>SYNEKTIK (SNT)</title></html>")
        raise AssertionError("missing slug must abort the recorder")
    except ValueError as exc:
        assert "canonical BiznesRadar slug" in str(exc)


def test_pa_recorder_requires_credentials(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        record_topic_fixture,
        "get_settings",
        lambda: SimpleNamespace(
            pa_username=None,
            pa_password=None,
            pa_base_url="https://portalanaliz.pl/forum/",
        ),
    )

    target = tmp_path / "topic.html"
    assert record_topic_fixture.record_topic("https://example.test/topic", target) == 1
    assert not target.exists()


def test_pa_fixture_sanitizer_keeps_posts_and_votes_without_account_data():
    html = """
    <html><head>
      <link rel="canonical" href="https://portalanaliz.pl/forum/viewtopic.php?t=1234&amp;sid=secret">
    </head><body>
      <a href="./ucp.php?mode=logout&amp;sid=secret">private-user@example.com</a>
      <div class="post" id="p101">
        <a class="username" href="./memberlist.php?u=7&amp;sid=secret">Real Author</a>
        <time datetime="2026-07-10T08:00:00+00:00">today</time>
        <div class="content">Private post body</div>
        <p class="author">by <a class="username">Second Author</a></p>
        <dd class="profile-location">Private Location</dd>
        <div class="signature">Private Signature</div>
        <span class="post-rating"><a href="./thanks?sid=secret">Users: Alice, Bob +4</a></span>
      </div>
    </body></html>
    """

    sanitized = record_topic_fixture.sanitize_topic_fixture(html)

    assert "secret" not in sanitized
    assert "private-user@example.com" not in sanitized
    assert "Real Author" not in sanitized
    assert "Second Author" not in sanitized
    assert "Private post body" not in sanitized
    assert "Private Location" not in sanitized
    assert "Private Signature" not in sanitized
    assert "Alice" not in sanitized
    assert "fixture-author" in sanitized
    assert "fixture post content" in sanitized
    assert "post-rating" in sanitized
    assert ">4<" in sanitized
