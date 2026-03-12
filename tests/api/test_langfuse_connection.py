"""
Unit tests for the Langfuse connection test endpoint.
"""

import sys
from types import ModuleType, SimpleNamespace

import pytest
from starlette.requests import Request

from src.web.routes.ai import api_test_langfuse_connection

pytestmark = pytest.mark.api

# Langfuse 4.x removed AsyncFernLangfuse and restructured api.resources; we inject fakes so the route's imports succeed.


def _make_fake_langfuse_modules(UnauthorizedErrorCls, AccessDeniedErrorCls, ApiErrorCls):
    """Create minimal fake langfuse submodules so the route's try block imports succeed (langfuse 4.x removed these).
    Returns the set of module keys we added so the test can remove them in teardown."""
    added = set()
    for path in (
        "langfuse.api.resources",
        "langfuse.api.resources.commons",
        "langfuse.api.resources.commons.errors",
        "langfuse.api.resources.commons.errors.access_denied_error",
        "langfuse.api.resources.commons.errors.unauthorized_error",
    ):
        if path not in sys.modules:
            sys.modules[path] = ModuleType(path)
            added.add(path)
    sys.modules["langfuse.api.resources.commons.errors.unauthorized_error"].UnauthorizedError = UnauthorizedErrorCls
    sys.modules["langfuse.api.resources.commons.errors.access_denied_error"].AccessDeniedError = AccessDeniedErrorCls
    # Do not add langfuse.api.core (real package); only add api_error if missing so we don't break langfuse.api.client imports.
    if "langfuse.api.core.api_error" not in sys.modules:
        sys.modules["langfuse.api.core.api_error"] = ModuleType("langfuse.api.core.api_error")
        added.add("langfuse.api.core.api_error")
    sys.modules["langfuse.api.core.api_error"].ApiError = ApiErrorCls
    return added


def _patch_langfuse_fern_client(monkeypatch, fern_client_class):
    """Inject AsyncFernLangfuse on langfuse.api.client (removed in langfuse 4.x) so app import resolves."""
    import langfuse.api.client as client_module

    monkeypatch.setattr(client_module, "AsyncFernLangfuse", fern_client_class, raising=False)


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

    fake_modules = _make_fake_langfuse_modules(_FakeUnauthorizedError, _FakeAccessDeniedError, _FakeApiError)
    try:
        import langfuse.types as lf_types

        monkeypatch.setattr(lf_types, "TraceContext", _TraceContext, raising=False)
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk_test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_test")
        monkeypatch.setenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
        monkeypatch.setenv("LANGFUSE_PROJECT_ID", "")
        _patch_langfuse_fern_client(monkeypatch, _DummyFernClient)
        monkeypatch.setattr("langfuse.Langfuse", _DummyLangfuse)

        result = await api_test_langfuse_connection(_make_request())

        assert result["valid"] is True
        assert "Langfuse connection successful" in result["message"]
        assert "proj_resolved" in result["message"]
        assert captured_fern_kwargs["base_url"] == "https://us.cloud.langfuse.com"
    finally:
        for k in fake_modules:
            sys.modules.pop(k, None)


@pytest.mark.asyncio
async def test_langfuse_connection_invalid_keys(monkeypatch):
    """Unauthorized errors are converted into clear validation failures."""

    class _TestUnauthorizedError(Exception):
        """Mock for langfuse UnauthorizedError - the internal module path changed in langfuse 4.x."""

        def __init__(self, message):
            self.message = message
            super().__init__(message)

    class _ErrorProjectsClient:
        async def get(self):
            raise _TestUnauthorizedError({"message": "Invalid credentials"})

    class _ErrorFernClient:
        def __init__(self, **kwargs):
            self.projects = _ErrorProjectsClient()

    fake_modules = _make_fake_langfuse_modules(_TestUnauthorizedError, _FakeAccessDeniedError, _FakeApiError)
    try:
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk_bad")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_bad")
        _patch_langfuse_fern_client(monkeypatch, _ErrorFernClient)

        result = await api_test_langfuse_connection(_make_request())

        assert result["valid"] is False
        assert "Invalid Langfuse API keys" in result["message"]
    finally:
        for k in fake_modules:
            sys.modules.pop(k, None)
