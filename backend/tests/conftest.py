"""Shared pytest fixtures.

The in-memory SQLite URL must be set BEFORE any app import: the engine is
created when app.db.base is first imported (module import order matters in
Python the way static initializers do in C#).
"""
import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
# Neutralize any developer .env so tests never attempt a real forum login.
os.environ["PA_USERNAME"] = ""
os.environ["PA_PASSWORD"] = ""

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base, SessionLocal, engine, get_db
from app.main import app as fastapi_app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.fixture()
def db():
    """Fresh schema per test — cheap on in-memory SQLite."""
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db):
    """TestClient with the request-scoped DB dependency overridden."""

    def _override_get_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


class FakeResponse:
    """Minimal stand-in for requests.Response used by scraper tests."""

    def __init__(self, text: str = "", status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def no_sleep(monkeypatch):
    """Disable politeness delays and backoff sleeps — tests must be instant."""
    import app.scrapers.http as polite_http

    monkeypatch.setattr(polite_http.time, "sleep", lambda _s: None)
