"""Record one real PortalAnaliz topic page as a test fixture.

    cd backend
    python scripts/record_topic_fixture.py "https://portalanaliz.pl/forum/viewtopic.php?f=7&t=1234"

Saves tests/fixtures/real_pa_topic.html — used to verify post/upvote parsing
against real markup (see skills/scraper-doctor/SKILL.md). Uses the polite
fetcher; public topics need no login.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scrapers import http as polite_http

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    url = sys.argv[1]
    print(f"fetching {url} ...", flush=True)
    response = polite_http.fetch(url)
    if response.status_code != 200:
        print(f"HTTP {response.status_code} — nothing saved.")
        return 1
    target = FIXTURES_DIR / "real_pa_topic.html"
    target.write_text(response.text, encoding="utf-8")
    print(f"saved {target} ({len(response.text)} bytes)")
    print("Now run: pytest tests/test_forum.py -v")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
