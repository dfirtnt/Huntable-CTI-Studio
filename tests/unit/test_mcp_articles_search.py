"""Unit tests for search_articles and search_articles_by_keywords MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.articles import register

pytestmark = pytest.mark.unit


def _make_tools(rag_mock, db_mock):
    mcp = FastMCP("test-articles-search")
    register(mcp, rag_mock, db_mock)
    return {t.name: t for t in mcp._tool_manager.list_tools()}


def _article_result(article_id=42, title="APT28 Lateral Movement", source_name="Bleeping Computer"):
    return {
        "id": article_id,
        "title": title,
        "source_name": source_name,
        "similarity": 0.82,
        "hunt_score": 75,
        "canonical_url": f"https://example.com/{article_id}",
        "published_at": "2026-01-15T10:00:00",
        "content": "Analysis of lateral movement via WMI and scheduled tasks.",
    }


# ---- search_articles --------------------------------------------------------


class TestSearchArticles:
    @pytest.mark.asyncio
    async def test_returns_formatted_list_on_results(self):
        rag = AsyncMock()
        rag.find_similar_content.return_value = [_article_result()]
        fn = _make_tools(rag, AsyncMock())["search_articles"].fn

        result = await fn(query="lateral movement")

        assert "APT28 Lateral Movement" in result
        assert "Bleeping Computer" in result
        assert "0.82" in result
        assert "75" in result

    @pytest.mark.asyncio
    async def test_returns_no_results_message_when_empty(self):
        rag = AsyncMock()
        rag.find_similar_content.return_value = []
        fn = _make_tools(rag, AsyncMock())["search_articles"].fn

        result = await fn(query="obscure threat actor xyz")

        assert "No articles found" in result

    @pytest.mark.asyncio
    async def test_result_count_in_header(self):
        rag = AsyncMock()
        rag.find_similar_content.return_value = [
            _article_result(article_id=i + 1, title=f"Article {i + 1}") for i in range(3)
        ]
        fn = _make_tools(rag, AsyncMock())["search_articles"].fn

        result = await fn(query="test")

        assert "Found 3 articles" in result

    @pytest.mark.asyncio
    async def test_article_id_shown_from_plain_id_field(self):
        rag = AsyncMock()
        rag.find_similar_content.return_value = [_article_result(article_id=99)]
        fn = _make_tools(rag, AsyncMock())["search_articles"].fn

        result = await fn(query="test")

        assert "Article ID:** 99" in result

    @pytest.mark.asyncio
    async def test_article_id_prefers_article_id_over_id_for_chunk_rows(self):
        """Chunk rows carry article_id (article pk) separate from id (chunk pk)."""
        rag = AsyncMock()
        rag.find_similar_content.return_value = [
            {
                "id": 1001,
                "article_id": 42,
                "title": "Chunk Article",
                "source_name": "Source A",
                "similarity": 0.7,
                "hunt_score": None,
                "canonical_url": "https://example.com/42",
                "published_at": "2026-01-01",
                "content": "content",
            }
        ]
        fn = _make_tools(rag, AsyncMock())["search_articles"].fn

        result = await fn(query="test")

        assert "Article ID:** 42" in result

    @pytest.mark.asyncio
    async def test_source_name_filter_resolves_to_source_id(self):
        rag = AsyncMock()
        rag.find_similar_content.return_value = []

        db = AsyncMock()
        src = MagicMock()
        src.name = "Bleeping Computer"
        src.id = 7
        db.list_sources.return_value = [src]

        fn = _make_tools(rag, db)["search_articles"].fn
        await fn(query="malware", source_name="bleeping")

        call_kwargs = rag.find_similar_content.call_args.kwargs
        assert call_kwargs["source_id"] == 7

    @pytest.mark.asyncio
    async def test_unmatched_source_name_passes_none_source_id(self):
        rag = AsyncMock()
        rag.find_similar_content.return_value = []

        db = AsyncMock()
        src = MagicMock()
        src.name = "Bleeping Computer"
        src.id = 7
        db.list_sources.return_value = [src]

        fn = _make_tools(rag, db)["search_articles"].fn
        await fn(query="malware", source_name="nonexistent_source_xyz")

        call_kwargs = rag.find_similar_content.call_args.kwargs
        assert call_kwargs["source_id"] is None

    @pytest.mark.asyncio
    async def test_no_source_name_skips_db_list_sources(self):
        rag = AsyncMock()
        rag.find_similar_content.return_value = []
        db = AsyncMock()

        fn = _make_tools(rag, db)["search_articles"].fn
        await fn(query="malware")

        db.list_sources.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_error_string_on_exception(self):
        rag = AsyncMock()
        rag.find_similar_content.side_effect = RuntimeError("RAG unavailable")
        fn = _make_tools(rag, AsyncMock())["search_articles"].fn

        result = await fn(query="test")

        assert "Error searching articles" in result


# ---- search_articles_by_keywords --------------------------------------------


class TestSearchArticlesByKeywords:
    @pytest.mark.asyncio
    async def test_returns_formatted_list_on_results(self):
        db = AsyncMock()
        db.search_articles_by_lexical_terms.return_value = [
            {
                "id": 55,
                "title": "Cobalt Strike C2 Detection",
                "source_name": "SecurityWeek",
                "canonical_url": "https://example.com/55",
                "published_at": "2026-02-01",
                "content": "Analysis of Cobalt Strike beacon traffic.",
            }
        ]
        fn = _make_tools(AsyncMock(), db)["search_articles_by_keywords"].fn

        result = await fn(keywords=["cobalt strike"])

        assert "Cobalt Strike C2 Detection" in result
        assert "SecurityWeek" in result
        assert "Article ID:** 55" in result

    @pytest.mark.asyncio
    async def test_returns_no_match_message_when_empty(self):
        db = AsyncMock()
        db.search_articles_by_lexical_terms.return_value = []
        fn = _make_tools(AsyncMock(), db)["search_articles_by_keywords"].fn

        result = await fn(keywords=["zzz_nonexistent_term"])

        assert "No articles found matching keywords" in result
        assert "zzz_nonexistent_term" in result

    @pytest.mark.asyncio
    async def test_keywords_shown_in_result_header(self):
        db = AsyncMock()
        db.search_articles_by_lexical_terms.return_value = [
            {
                "id": 1,
                "title": "T",
                "source_name": "S",
                "canonical_url": "https://example.com",
                "published_at": "2026-01-01",
                "content": "",
            }
        ]
        fn = _make_tools(AsyncMock(), db)["search_articles_by_keywords"].fn

        result = await fn(keywords=["ransomware", "healthcare"])

        assert "ransomware" in result
        assert "healthcare" in result

    @pytest.mark.asyncio
    async def test_passes_limit_to_db(self):
        db = AsyncMock()
        db.search_articles_by_lexical_terms.return_value = []
        fn = _make_tools(AsyncMock(), db)["search_articles_by_keywords"].fn

        await fn(keywords=["malware"], limit=5)

        db.search_articles_by_lexical_terms.assert_awaited_once_with(terms=["malware"], limit=5)

    @pytest.mark.asyncio
    async def test_returns_error_string_on_exception(self):
        db = AsyncMock()
        db.search_articles_by_lexical_terms.side_effect = RuntimeError("DB timeout")
        fn = _make_tools(AsyncMock(), db)["search_articles_by_keywords"].fn

        result = await fn(keywords=["test"])

        assert "Error searching by keywords" in result
