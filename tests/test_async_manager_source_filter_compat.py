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
