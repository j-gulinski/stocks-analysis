"""Offline regression tests for real-fixture recorder safety."""

from scripts.record_fixtures import recording_plan


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
