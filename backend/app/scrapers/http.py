"""Single fetch path for ALL scraper traffic (non-negotiable, see CLAUDE.md).

Provides per-domain rate limiting with randomized jitter, a realistic browser
User-Agent, and exponential backoff with a hard stop — so no scraper can
accidentally hammer a site. Think of it as HttpClient + a Polly retry/throttle
policy, written by hand because the policy IS the point here.

This module is deliberately framework-free (stdlib + requests only): no DB,
no settings import. Callers own logging and caching.
"""
from __future__ import annotations

import random
import time
from urllib.parse import urlparse

import requests

DEFAULT_TIMEOUT_SECONDS = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# (min, max) seconds between requests to the same domain. Jitter within the
# range makes the traffic pattern irregular, i.e. human-ish.
DOMAIN_DELAY_RANGES: dict[str, tuple[float, float]] = {
    "biznesradar.pl": (2.0, 4.0),
    "portalanaliz.pl": (1.5, 3.0),
}
DEFAULT_DELAY_RANGE: tuple[float, float] = (1.0, 2.0)

RETRYABLE_STATUSES = {403, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 5.0

# Last request time per domain (monotonic clock — immune to wall-clock jumps).
# Module-level state is fine: the app is a single process by design.
_last_request_at: dict[str, float] = {}


class FetchError(Exception):
    """Base error for the polite fetcher."""


class FetchBlockedError(FetchError):
    """Hard stop: retries exhausted on retryable statuses / network errors.

    Callers must NOT retry on top of this — the site is telling us to back off.
    """


def _delay_range(host: str) -> tuple[float, float]:
    bare = host.removeprefix("www.")
    return DOMAIN_DELAY_RANGES.get(bare, DEFAULT_DELAY_RANGE)


def _wait_politely(host: str) -> None:
    """Sleep just enough so consecutive requests to `host` are jitter-spaced."""
    low, high = _delay_range(host)
    required_gap = random.uniform(low, high)
    last = _last_request_at.get(host)
    if last is not None:
        elapsed = time.monotonic() - last
        if elapsed < required_gap:
            time.sleep(required_gap - elapsed)
    _last_request_at[host] = time.monotonic()


def fetch(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> requests.Response:
    """GET `url` politely. Returns the response for terminal statuses (200, 404, …).

    Retryable statuses (403/429/5xx) and network errors are retried with
    exponential backoff; after MAX_ATTEMPTS the fetch raises FetchBlockedError.
    Pass `session` to reuse cookies (e.g. the logged-in forum session) — the
    rate limiter applies regardless of session.
    """
    host = urlparse(url).netloc
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", USER_AGENT)

    last_error: str = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _wait_politely(host)
        try:
            response = sess.get(url, timeout=timeout)
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
        else:
            if response.status_code not in RETRYABLE_STATUSES:
                return response
            last_error = f"HTTP {response.status_code}"

        if attempt < MAX_ATTEMPTS:
            # 5 s, 10 s, ... on top of the regular politeness delay.
            time.sleep(BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))

    raise FetchBlockedError(
        f"Giving up on {url} after {MAX_ATTEMPTS} attempts ({last_error}). "
        "Not retrying further — respect the site and try again later."
    )
