"""Shared stdlib Anthropic HTTP helper.

The official SDK is preferred when installed. When services fall back to
``urllib``, local Python certificate stores can be incomplete on macOS; use
certifi's CA bundle when available so Claude calls do not fail with
CERTIFICATE_VERIFY_FAILED.
"""
from __future__ import annotations


def urlopen_with_certifi(request, *, timeout: int):
    import urllib.request

    try:
        import ssl

        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.urlopen(request, timeout=timeout, context=context)  # noqa: S310
    except ImportError:
        return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310
