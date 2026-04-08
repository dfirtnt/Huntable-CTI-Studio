"""
Unit tests for the Langfuse connection test endpoint.

Updated for Langfuse Python SDK v4 (observations-first API).
"""

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from src.web.routes.ai import api_test_langfuse_connection

pytestmark = pytest.mark.api


def _patch_langfuse_api_client(monkeypatch, api_client_class):
    """Inject AsyncLangfuseAPI on langfuse.api.client for v4 SDK."""
    import langfuse.api.client as client_module

    monkeypatch.setattr(client_module, "AsyncLangfuseAPI", api_client_class, raising=False)


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


class _FakeApiError(Exception):
    pass


class _FakeAccessDeniedError(Exception):
    pass


class _FakeUnauthorizedError(Exception):
    pass


class _TraceContext:
    """Minimal stand-in for langfuse.types.TraceContext(trace_id=...)."""

    def __init__(self, trace_id: str):
        self.trace_id = trace_id


@pytest.mark.asyncio
async def test_langfuse_connection_success(monkeypatch):
    """Successful connection returns a success message with resolved project ID."""

    captured_api_kwargs = {}

    class _DummyProjectsClient:
        async def get(self):
            return SimpleNamespace(data=[SimpleNamespace(id="proj_resolved")])

    class _DummyAPIClient:
        def __init__(self, **kwargs):
            captured_api_kwargs.update(kwargs)
            self.projects = _DummyProjectsClient()

    class _DummyObservation:
        """Mocks a Langfuse v4 observation (used for both spans and generations)."""

        trace_id = "trace_123"

        def __init__(self):
            self._langfuse_ended = False

        def update(self, **kwargs):
            self.update_kwargs = kwargs

        def end(self):
            self._langfuse_ended = True

    class _DummyLangfuse:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start_observation(self, **kwargs):
            return _DummyObservation()

        def flush(self):
            return None

    import langfuse.types as lf_types

    monkeypatch.setattr(lf_types, "TraceContext", _TraceContext, raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk_test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", "")
    _patch_langfuse_api_client(monkeypatch, _DummyAPIClient)
    monkeypatch.setattr("langfuse.Langfuse", _DummyLangfuse)

    result = await api_test_langfuse_connection(_make_request())

    assert result["valid"] is True
    assert "Langfuse connection successful" in result["message"]
    assert "proj_resolved" in result["message"]
    assert captured_api_kwargs["base_url"] == "https://us.cloud.langfuse.com"


@pytest.mark.asyncio
async def test_langfuse_connection_invalid_keys(monkeypatch):
    """Unauthorized errors are converted into clear validation failures."""

    class _TestUnauthorizedError(Exception):
        """Mock for langfuse UnauthorizedError."""

        def __init__(self, message):
            self.message = message
            super().__init__(message)

    class _ErrorProjectsClient:
        async def get(self):
            raise _TestUnauthorizedError({"message": "Invalid credentials"})

    class _ErrorAPIClient:
        def __init__(self, **kwargs):
            self.projects = _ErrorProjectsClient()

    # Patch the v4 error classes into the langfuse.api module so the route's imports resolve
    import langfuse.api as lf_api

    monkeypatch.setattr(lf_api, "UnauthorizedError", _TestUnauthorizedError, raising=False)
    monkeypatch.setattr(lf_api, "AccessDeniedError", _FakeAccessDeniedError, raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk_bad")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_bad")
    _patch_langfuse_api_client(monkeypatch, _ErrorAPIClient)

    result = await api_test_langfuse_connection(_make_request())

    assert result["valid"] is False
    assert "Invalid Langfuse API keys" in result["message"]
