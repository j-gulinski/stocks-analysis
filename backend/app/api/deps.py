"""Shared FastAPI dependencies."""
from fastapi import Header


def get_user_email(x_user_email: str | None = Header(default=None)) -> str | None:
    """Identity forwarded by the Next.js proxy in production (Phase 6).

    Optional everywhere: local dev has no auth, so this is simply None.
    """
    return x_user_email
