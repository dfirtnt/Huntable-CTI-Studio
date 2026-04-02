"""Verify that 500-level HTTP error responses do not leak internal exception details.

These tests ensure that when route handlers catch unexpected exceptions, they
return generic error messages instead of raw str(exc) which could expose DB
paths, connection strings, or stack trace fragments.
"""

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_embeddings_stats_500_hides_exception_detail(monkeypatch):
    from src.web.routes import embeddings as mod

    monkeypatch.setattr(
        mod,
        "_get_embedding_coverage_stats",
        AsyncMock(side_effect=RuntimeError("psycopg2.OperationalError: connection refused at /var/run/postgres")),
    )

    with pytest.raises(Exception) as exc_info:
        await mod.api_embedding_stats()

    detail = getattr(exc_info.value, "detail", str(exc_info.value))
    assert "psycopg2" not in detail
    assert "postgres" not in detail
    assert detail == "Internal server error"


@pytest.mark.asyncio
async def test_articles_list_500_hides_exception_detail(monkeypatch):
    from src.web.routes import articles as mod

    monkeypatch.setattr(
        mod.async_db_manager,
        "list_articles",
        AsyncMock(side_effect=RuntimeError("FATAL: database 'cti' does not exist")),
    )

    with pytest.raises(Exception) as exc_info:
        await mod.api_articles_list()

    detail = getattr(exc_info.value, "detail", str(exc_info.value))
    assert "FATAL" not in detail
    assert "cti" not in detail
    assert detail == "Internal server error"


@pytest.mark.asyncio
async def test_sources_get_500_hides_exception_detail(monkeypatch):
    from src.web.routes import sources as mod

    monkeypatch.setattr(
        mod.async_db_manager,
        "get_source",
        AsyncMock(side_effect=RuntimeError("SSL SYSCALL error: EOF detected")),
    )

    with pytest.raises(Exception) as exc_info:
        await mod.api_get_source(source_id=1)

    detail = getattr(exc_info.value, "detail", str(exc_info.value))
    assert "SSL" not in detail
    assert "EOF" not in detail
    assert detail == "Internal server error"


@pytest.mark.asyncio
async def test_search_500_hides_exception_detail(monkeypatch):
    from src.web.routes import search as mod

    monkeypatch.setattr(
        mod.async_db_manager,
        "list_articles",
        AsyncMock(side_effect=RuntimeError("pg_trgm index scan failed")),
    )

    with pytest.raises(Exception) as exc_info:
        await mod.api_search_articles(q="test")

    detail = getattr(exc_info.value, "detail", str(exc_info.value))
    assert "pg_trgm" not in detail
    assert detail == "Internal server error"


@pytest.mark.asyncio
async def test_health_check_hides_exception_detail(monkeypatch):
    from src.web.routes import health as mod

    monkeypatch.setattr(
        mod.async_db_manager,
        "get_database_stats",
        AsyncMock(side_effect=RuntimeError("connection pool exhausted, max=20")),
    )

    result = await mod.api_health_check()

    assert result.get("error") == "Health check failed"
    assert "pool" not in str(result)
    assert "max=20" not in str(result)


@pytest.mark.asyncio
async def test_dashboard_metrics_500_hides_exception_detail(monkeypatch):
    from src.web.routes import metrics as mod

    monkeypatch.setattr(
        mod.async_db_manager,
        "list_sources",
        AsyncMock(side_effect=RuntimeError("relation 'sources' does not exist")),
    )

    result = await mod.api_metrics_health()

    assert result.get("status") == "critical"
    assert "relation" not in str(result)
    assert result.get("uptime") == 0.0
