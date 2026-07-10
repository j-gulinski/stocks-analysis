"""Record one authenticated PortalAnaliz topic as a sanitized test fixture.

    cd backend
    python scripts/record_topic_fixture.py "https://portalanaliz.pl/forum/viewtopic.php?f=7&t=1234"

Saves tests/fixtures/real/pa/topic.html — used to verify post/upvote parsing
against real markup (see skills/scraper-doctor/SKILL.md). PortalAnaliz topic
pages currently require a logged-in session, so credentials come from the
normal backend settings and every request still uses the polite fetcher.

Only the minimum post structure needed by parser tests is persisted. Account
navigation, session ids, post text and author names are deliberately removed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.scrapers import portalanaliz

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
TARGET = FIXTURES_DIR / "real" / "pa" / "topic.html"


def sanitize_topic_fixture(html: str) -> str:
    """Keep real post/vote markup while removing account and content data."""
    source = BeautifulSoup(html, "html.parser")
    output = BeautifulSoup("<html><head></head><body></body></html>", "html.parser")

    canonical = source.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        topic_id = portalanaliz.extract_topic_id(canonical["href"])
        if topic_id is not None:
            link = output.new_tag("link", rel="canonical")
            link["href"] = f"https://portalanaliz.pl/forum/viewtopic.php?t={topic_id}"
            output.head.append(link)

    title = output.new_tag("title")
    title.string = "Recorded PortalAnaliz topic fixture"
    output.head.append(title)

    for source_post in source.find_all("div", class_="post")[:3]:
        parsed = portalanaliz.parse_topic_page(str(source_post))
        if not parsed.posts:
            continue
        parsed_post = parsed.posts[0]
        post = output.new_tag("div")
        post["class"] = source_post.get("class", [])
        post["id"] = source_post.get("id", "")

        source_author = source_post.select_one(
            "a.username-coloured, a.username, span.username-coloured, span.username"
        )
        if source_author is not None:
            author = output.new_tag(source_author.name)
            author["class"] = source_author.get("class", [])
            author.string = "fixture-author"
            post.append(author)

        source_time = source_post.find("time", attrs={"datetime": True})
        if source_time is not None:
            time_element = output.new_tag("time")
            time_element["datetime"] = source_time["datetime"]
            post.append(time_element)

        source_content = source_post.select_one("div.content")
        if source_content is not None:
            content = output.new_tag("div")
            content["class"] = source_content.get("class", [])
            content.string = "fixture post content"
            post.append(content)

        # Preserve the real vote element/class but never the list of users who
        # voted. A numeric value is sufficient for the parser contract.
        if parsed_post.upvotes is not None:
            for selector in portalanaliz._UPVOTE_SELECTORS:
                source_vote = source_post.select_one(selector)
                if source_vote is not None:
                    vote = output.new_tag(source_vote.name)
                    vote["class"] = source_vote.get("class", [])
                    vote.string = str(parsed_post.upvotes)
                    post.append(vote)
                    break
        output.body.append(post)

    return str(output)


def record_topic(url: str, target: Path = TARGET) -> int:
    settings = get_settings()
    if not (settings.pa_username and settings.pa_password):
        print("PA_USERNAME / PA_PASSWORD not configured — nothing saved.")
        return 1

    client = portalanaliz.ForumClient(base_url=settings.pa_base_url)
    client.login(settings.pa_username, settings.pa_password)
    html = client.fetch_page(url)
    parsed = portalanaliz.parse_topic_page(html)
    if not parsed.posts:
        print("Authenticated page contains no parseable posts — nothing saved.")
        return 1
    if not any(post.upvotes is not None for post in parsed.posts):
        print("No visible vote markup recognized — nothing saved.")
        return 1

    sanitized = sanitize_topic_fixture(html)
    sanitized_page = portalanaliz.parse_topic_page(sanitized)
    if not sanitized_page.posts or not any(
        post.upvotes is not None for post in sanitized_page.posts
    ):
        print("Sanitization removed required parser structure — nothing saved.")
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sanitized, encoding="utf-8")
    print(f"saved sanitized {target} ({len(sanitized)} bytes)")
    print("Now run: pytest tests/test_forum.py -v")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    url = sys.argv[1]
    print(f"fetching authenticated {url} ...", flush=True)
    return record_topic(url)


if __name__ == "__main__":
    raise SystemExit(main())
