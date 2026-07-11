# Phase 2 — PortalAnaliz forum scraper

## What was built
phpBB login with an in-memory session, topic-page parser, topic↔company
linking with URL canonicalization, and incremental post sync.

## Concepts worth understanding

**Cookies without a browser** (`scrapers/portalanaliz.py`) — a
`requests.Session` is `HttpClient` + `CookieContainer`: the login POST stores
the phpBB session cookie, every later GET sends it automatically. Login means
scraping the form's hidden anti-CSRF fields (`form_token`, `creation_time`)
first and posting them back — the same dance a browser does invisibly.

**Credentials hygiene** — username/password come from settings at call time
and live only inside the process session object. Nothing touches the DB or
logs; restart forgets them.

**URL canonicalization** — many URLs point at one thread (page offsets,
post permalinks, `hilit` search params). Storing the canonical
`viewtopic.php?f=…&t=…` form makes "already linked" checks trivial. General
lesson: normalize external identifiers at the boundary, once.

**Incremental sync** (`services/forum_sync.py`) — resume from the last
partial page (`start = count // 50 * 50`) and skip known post ids. First sync
pulls history; every later one costs a page or two. The known limitation
(deleted posts shift offsets) is documented instead of hidden — pragmatic
correctness over speculative robustness.

**Testing seams** — `_make_client()` is module-level precisely so tests can
monkeypatch it with a fake client (the Python idiom where C# would inject an
`IForumClient`). The parser itself is tested against a fixture page.

## Where to look
`app/scrapers/portalanaliz.py` → `app/services/forum_sync.py` →
`app/api/forum.py` → `tests/test_forum.py`.
