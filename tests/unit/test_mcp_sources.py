"""Unit tests for list_sources and get_stats MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.sources import register

pytestmark = pytest.mark.unit


def _make_tools(db_mock):
    mcp = FastMCP("test-sources")
    register(mcp, db_mock)
    return {t.name: t for t in mcp._tool_manager.list_tools()}


def _make_source(name="SANS ISC", id=1, url="https://isc.sans.edu", rss_url=None,
                 total_articles=120, active=True, last_check=None,
                 consecutive_failures=0, average_response_time=1.4):
    src = MagicMock()
    src.name = name
    src.id = id
    src.url = url
    src.rss_url = rss_url
    src.total_articles = total_articles
    src.active = active
    src.last_check = last_check
    src.consecutive_failures = consecutive_failures
    src.average_response_time = average_response_time
    return src


def _make_article_stats(total=500, embedded=450, coverage=90.0, pending=50):
    return {
        "total_articles": total,
        "embedded_count": embedded,
        "embedding_coverage_percent": coverage,
        "pending_embeddings": pending,
    }


def _make_sigma_stats(total=2000, embedded=1800, coverage=90.0, pending=200):
    return {
        "total_sigma_rules": total,
        "sigma_rules_with_rag_embedding": embedded,
        "sigma_embedding_coverage_percent": coverage,
        "sigma_rules_pending_rag_embedding": pending,
    }


# ---- list_sources -----------------------------------------------------------


class TestListSources:
    @pytest.mark.asyncio
    async def test_returns_formatted_source_list(self):
        src = _make_source(name="Bleeping Computer", id=3, url="https://bleepingcomputer.com",
                           total_articles=800, active=True, consecutive_failures=0,
                           average_response_time=0.8)
        db = AsyncMock()
        db.list_sources.return_value = [src]
        fn = _make_tools(db)["list_sources"].fn

        result = await fn()

        assert "Bleeping Computer" in result
        assert "ID: 3" in result
        assert "https://bleepingcomputer.com" in result
        assert "800" in result

    @pytest.mark.asyncio
    async def test_returns_no_sources_when_empty(self):
        db = AsyncMock()
        db.list_sources.return_value = []
        fn = _make_tools(db)["list_sources"].fn

        result = await fn()

        assert "No sources found" in result

    @pytest.mark.asyncio
    async def test_active_only_true_passes_filter(self):
        db = AsyncMock()
        db.list_sources.return_value = []
        fn = _make_tools(db)["list_sources"].fn

        await fn(active_only=True)

        db.list_sources.assert_awaited_once()
        call_kwargs = db.list_sources.call_args.kwargs
        # filter_params should be a SourceFilter with active=True (not None)
        assert call_kwargs["filter_params"] is not None

    @pytest.mark.asyncio
    async def test_active_only_false_passes_none_filter(self):
        db = AsyncMock()
        db.list_sources.return_value = []
        fn = _make_tools(db)["list_sources"].fn

        await fn(active_only=False)

        call_kwargs = db.list_sources.call_args.kwargs
        assert call_kwargs["filter_params"] is None

    @pytest.mark.asyncio
    async def test_last_check_never_when_none(self):
        src = _make_source(last_check=None)
        db = AsyncMock()
        db.list_sources.return_value = [src]
        fn = _make_tools(db)["list_sources"].fn

        result = await fn()

        assert "never" in result

    @pytest.mark.asyncio
    async def test_last_check_isoformat_when_set(self):
        last_check = MagicMock()
        last_check.isoformat.return_value = "2026-05-01T12:00:00"
        src = _make_source(last_check=last_check)
        db = AsyncMock()
        db.list_sources.return_value = [src]
        fn = _make_tools(db)["list_sources"].fn

        result = await fn()

        assert "2026-05-01T12:00:00" in result

    @pytest.mark.asyncio
    async def test_returns_error_string_on_exception(self):
        db = AsyncMock()
        db.list_sources.side_effect = RuntimeError("Connection refused")
        fn = _make_tools(db)["list_sources"].fn

        result = await fn()

        assert "Error listing sources" in result

    @pytest.mark.asyncio
    async def test_header_shows_active_label_when_active_only(self):
        db = AsyncMock()
        db.list_sources.return_value = []
        fn = _make_tools(db)["list_sources"].fn

        result = await fn(active_only=True)
        # "No sources found." returned, but we test the active_only=False path in another test
        # For non-empty: header contains "Active sources"
        src = _make_source()
        db.list_sources.return_value = [src]
        result = await fn(active_only=True)

        assert "Active sources" in result


# ---- get_stats --------------------------------------------------------------


class TestGetStats:
    @pytest.mark.asyncio
    async def test_renders_all_three_sections(self):
        db = AsyncMock()
        db.get_article_embedding_stats.return_value = _make_article_stats()
        db.get_sigma_rule_embedding_stats.return_value = _make_sigma_stats()
        src = _make_source(active=True)
        db.list_sources.return_value = [src]
        fn = _make_tools(db)["get_stats"].fn

        result = await fn()

        assert "Articles:" in result
        assert "Sigma rules:" in result
        assert "Sources:" in result

    @pytest.mark.asyncio
    async def test_article_stats_numbers_appear(self):
        db = AsyncMock()
        db.get_article_embedding_stats.return_value = _make_article_stats(total=1234, embedded=1100, coverage=89.1)
        db.get_sigma_rule_embedding_stats.return_value = _make_sigma_stats()
        db.list_sources.return_value = []
        fn = _make_tools(db)["get_stats"].fn

        result = await fn()

        assert "1234" in result
        assert "1100" in result
        assert "89.1" in result

    @pytest.mark.asyncio
    async def test_sigma_no_rows_shows_index_hint(self):
        db = AsyncMock()
        db.get_article_embedding_stats.return_value = _make_article_stats()
        db.get_sigma_rule_embedding_stats.return_value = _make_sigma_stats(total=0, embedded=0, coverage=0.0, pending=0)
        db.list_sources.return_value = []
        fn = _make_tools(db)["get_stats"].fn

        result = await fn()

        assert "sigma index" in result.lower() or "SIGMA RAG" in result

    @pytest.mark.asyncio
    async def test_sigma_no_embeddings_shows_index_embeddings_hint(self):
        db = AsyncMock()
        db.get_article_embedding_stats.return_value = _make_article_stats()
        db.get_sigma_rule_embedding_stats.return_value = _make_sigma_stats(total=100, embedded=0, coverage=0.0, pending=100)
        db.list_sources.return_value = []
        fn = _make_tools(db)["get_stats"].fn

        result = await fn()

        assert "index-embeddings" in result

    @pytest.mark.asyncio
    async def test_sources_count_shows_active_and_total(self):
        db = AsyncMock()
        db.get_article_embedding_stats.return_value = _make_article_stats()
        db.get_sigma_rule_embedding_stats.return_value = _make_sigma_stats()
        active_src = _make_source(active=True)
        inactive_src = _make_source(name="Inactive Feed", active=False)
        db.list_sources.return_value = [active_src, inactive_src]
        fn = _make_tools(db)["get_stats"].fn

        result = await fn()

        assert "1 active" in result
        assert "2 total" in result

    @pytest.mark.asyncio
    async def test_article_stats_failure_shows_unavailable(self):
        db = AsyncMock()
        db.get_article_embedding_stats.side_effect = RuntimeError("stats table missing")
        db.get_sigma_rule_embedding_stats.return_value = _make_sigma_stats()
        db.list_sources.return_value = []
        fn = _make_tools(db)["get_stats"].fn

        result = await fn()

        assert "unavailable" in result
        # Other sections still render
        assert "Sigma rules:" in result

    @pytest.mark.asyncio
    async def test_sigma_stats_failure_shows_unavailable(self):
        db = AsyncMock()
        db.get_article_embedding_stats.return_value = _make_article_stats()
        db.get_sigma_rule_embedding_stats.side_effect = RuntimeError("pg_vector missing")
        db.list_sources.return_value = []
        fn = _make_tools(db)["get_stats"].fn

        result = await fn()

        assert "unavailable" in result
        assert "Articles:" in result

    @pytest.mark.asyncio
    async def test_all_sections_fail_still_returns_non_empty(self):
        db = AsyncMock()
        db.get_article_embedding_stats.side_effect = RuntimeError("DB down")
        db.get_sigma_rule_embedding_stats.side_effect = RuntimeError("DB down")
        db.list_sources.side_effect = RuntimeError("DB down")
        fn = _make_tools(db)["get_stats"].fn

        result = await fn()

        assert result.strip()
