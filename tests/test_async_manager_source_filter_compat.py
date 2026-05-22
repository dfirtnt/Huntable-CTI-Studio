"""Regression tests for source filter compatibility in AsyncDatabaseManager."""

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.database.async_manager import AsyncDatabaseManager


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def unique(self):
        return self

    def scalars(self):
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _query):
        return _FakeExecuteResult(self._rows)


def _build_fake_source(identifier: str, name: str, active: bool):
    return SimpleNamespace(
        id=1,
        identifier=identifier,
        name=name,
        url="https://example.com",
        rss_url="https://example.com/feed.xml",
        check_frequency=3600,
        lookback_days=180,
        active=active,
        config={},
        last_check=None,
        last_success=None,
        consecutive_failures=0,
        total_articles=0,
        average_response_time=0.0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _make_manager(rows):
    mgr = AsyncDatabaseManager.__new__(AsyncDatabaseManager)

    @asynccontextmanager
    async def _fake_get_session():
        yield _FakeSession(rows)

    mgr.get_session = _fake_get_session
    mgr._db_source_to_model = lambda row: row
    return mgr


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_sources_accepts_minimal_source_filter_shape():
    """Minimal SourceFilter (active + identifier) should not require legacy fields."""
    rows = [_build_fake_source("alpha", "Alpha", True)]
    mgr = _make_manager(rows)

    # Mirrors current SourceFilter shape: active + identifier
    filter_like = SimpleNamespace(active=True, identifier="alp")
    result = await mgr.list_sources(filter_params=filter_like)

    assert len(result) == 1
    assert result[0].identifier == "alpha"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_sources_accepts_legacy_alias_fields():
    """Legacy callers with identifier_contains/name_contains should still work."""
    rows = [_build_fake_source("beta", "Beta Source", True)]
    mgr = _make_manager(rows)

    # Legacy shape compatibility
    filter_like = SimpleNamespace(active=True, identifier_contains="bet", name_contains="Beta")
    result = await mgr.list_sources(filter_params=filter_like)

    assert len(result) == 1
    assert result[0].name == "Beta Source"


class _ErrorSession:
    """Session that always raises on execute — simulates a transient DB error."""

    async def execute(self, _query):
        raise RuntimeError("simulated DB connection error")


def _make_error_manager():
    """Manager whose session raises on every execute call."""
    mgr = AsyncDatabaseManager.__new__(AsyncDatabaseManager)

    @asynccontextmanager
    async def _fake_get_session():
        yield _ErrorSession()

    mgr.get_session = _fake_get_session
    mgr._db_source_to_model = lambda row: row
    return mgr


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_sources_propagates_db_error():
    """DB errors must propagate — list_sources must NOT silently return [].

    Regression for the bug that caused duplicate sources: when list_sources()
    swallowed exceptions and returned [], _sync_to_db treated every YAML source
    as new and created duplicates in a single batch.
    """
    mgr = _make_error_manager()

    with pytest.raises(RuntimeError, match="simulated DB connection error"):
        await mgr.list_sources()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_sources_no_filter_returns_all_sources():
    """list_sources() with no filter returns all rows from the session."""
    rows = [
        _build_fake_source("alpha", "Alpha", True),
        _build_fake_source("beta", "Beta", False),
    ]
    mgr = _make_manager(rows)

    result = await mgr.list_sources()

    assert len(result) == 2
    identifiers = {r.identifier for r in result}
    assert identifiers == {"alpha", "beta"}
