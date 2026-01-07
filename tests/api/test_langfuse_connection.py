"""
Unit tests for the Langfuse connection test endpoint.
"""

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from langfuse.api.resources.commons.errors.unauthorized_error import (
    UnauthorizedError,
)

from src.web.routes.ai import api_test_langfuse_connection


class _DummySessionResult:
    def scalar_one_or_none(self):
        return None


class _DummySession:
    async def execute(self, *args, **kwargs):
        return _DummySessionResult()


class _DummySessionContext:
    async def __aenter__(self):
        return _DummySession()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyDBManager:
    def get_session(self):
        return _DummySessionContext()


@pytest.fixture(autouse=True)
def _stub_database(monkeypatch):
    """Prevent real database I/O."""
    monkeypatch.setattr(
        "src.web.routes.ai.async_db_manager",
        _DummyDBManager(),
    )


def _make_request():
    return Request({"type": "http", "app": None})


@pytest.mark.asyncio
async def test_langfuse_connection_success(monkeypatch):
    """Successful connection returns a success message with resolved project ID."""

    captured_fern_kwargs = {}

    class _DummyProjectsClient:
        async def get(self):
            return SimpleNamespace(data=[SimpleNamespace(id="proj_resolved")])

    class _DummyFernClient:
        def __init__(self, **kwargs):
            captured_fern_kwargs.update(kwargs)
            self.projects = _DummyProjectsClient()

    class _DummyGeneration:
        def __init__(self):
            self._langfuse_ended = False

        def update(self, **kwargs):
            self.update_kwargs = kwargs

        def end(self):
            self._langfuse_ended = True

    class _DummySpan:
        trace_id = "trace_123"

        def end(self):
            return None

    class _DummyLangfuse:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start_span(self, **kwargs):
            return _DummySpan()

        def start_generation(self, **kwargs):
            return _DummyGeneration()

        def flush(self):
            return None

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk_test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", "")
    monkeypatch.setattr("langfuse.api.client.AsyncFernLangfuse", _DummyFernClient)
    monkeypatch.setattr("langfuse.Langfuse", _DummyLangfuse)

    result = await api_test_langfuse_connection(_make_request())

    assert result["valid"] is True
    assert "Langfuse connection successful" in result["message"]
    assert "proj_resolved" in result["message"]
    assert captured_fern_kwargs["base_url"] == "https://us.cloud.langfuse.com"


@pytest.mark.asyncio
async def test_langfuse_connection_invalid_keys(monkeypatch):
    """Unauthorized errors are converted into clear validation failures."""

    class _ErrorProjectsClient:
        async def get(self):
            raise UnauthorizedError({"message": "Invalid credentials"})

    class _ErrorFernClient:
        def __init__(self, **kwargs):
            self.projects = _ErrorProjectsClient()

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk_bad")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_bad")
    monkeypatch.setattr("langfuse.api.client.AsyncFernLangfuse", _ErrorFernClient)

    result = await api_test_langfuse_connection(_make_request())

    assert result["valid"] is False
    assert "Invalid Langfuse API keys" in result["message"]
