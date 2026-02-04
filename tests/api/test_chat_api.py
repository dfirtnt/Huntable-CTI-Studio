"""API tests for RAG chat endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request


@pytest.mark.api
class TestChatHelpers:
    """Unit tests for chat route helper functions."""

    def test_extract_lexical_terms_emotet(self):
        """Extract emotet from query."""
        from src.web.routes.chat import _extract_lexical_terms

        assert _extract_lexical_terms("Emotet delivery techniques") == ["emotet"]

    def test_extract_lexical_terms_cobalt_strike(self):
        """Extract cobalt strike from query."""
        from src.web.routes.chat import _extract_lexical_terms

        assert "cobalt strike" in _extract_lexical_terms("Cobalt Strike beacon")

    def test_extract_lexical_terms_empty(self):
        """No known terms returns empty."""
        from src.web.routes.chat import _extract_lexical_terms

        assert _extract_lexical_terms("general security news") == []

    def test_filter_by_lexical_relevance_prioritizes_matches(self):
        """Articles with lexical terms are prioritized."""
        from src.web.routes.chat import _filter_by_lexical_relevance

        articles = [
            {"id": 1, "title": "Unrelated", "content": "OpenAI leak"},
            {"id": 2, "title": "Emotet delivery", "content": "emotet techniques"},
        ]
        result = _filter_by_lexical_relevance(articles, ["emotet"], max_results=5)
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_filter_by_lexical_relevance_no_terms_returns_slice(self):
        """Without terms, returns first max_results."""
        from src.web.routes.chat import _filter_by_lexical_relevance

        articles = [{"id": i, "title": f"A{i}", "content": ""} for i in range(10)]
        result = _filter_by_lexical_relevance(articles, [], max_results=3)
        assert len(result) == 3


@pytest.mark.api
class TestChatAPI:
    """Test RAG chat API endpoint."""

    @pytest.mark.asyncio
    async def test_rag_chat_requires_message(self, async_client):
        """POST /api/chat/rag requires message in body."""
        response = await async_client.post(
            "/api/chat/rag",
            json={"conversation_history": []},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_rag_chat_accepts_message_and_returns_structure(self):
        """api_rag_chat accepts message and returns response structure."""
        from src.web.routes.chat import api_rag_chat

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(
            return_value={
                "message": "Emotet delivery techniques",
                "conversation_history": [],
                "max_results": 5,
                "similarity_threshold": 0.3,
                "use_llm_generation": False,
            }
        )

        with (
            patch("src.services.rag_service.get_rag_service") as mock_get_rag,
            patch("src.database.async_manager.async_db_manager") as mock_async_db,
        ):
            mock_rag = AsyncMock()
            mock_rag.find_unified_results = AsyncMock(
                return_value={
                    "articles": [
                        {
                            "id": 1,
                            "title": "Test Article",
                            "content": "Test content",
                            "similarity": 0.5,
                            "source_name": "Test Source",
                            "canonical_url": "https://example.com",
                        }
                    ],
                    "rules": [],
                }
            )
            mock_async_db.search_articles_by_lexical_terms = AsyncMock(return_value=[])
            mock_rag.db_manager = MagicMock()
            mock_rag.db_manager.get_session = MagicMock()
            mock_rag.db_manager.get_session.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(add=MagicMock(), flush=AsyncMock(), commit=AsyncMock())
            )
            mock_rag.db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_rag.return_value = mock_rag

            result = await api_rag_chat(mock_request)
            assert "response" in result
            assert "relevant_articles" in result
            assert "total_results" in result

    @pytest.mark.asyncio
    async def test_rag_chat_lexical_terms_increase_search_limit(self):
        """Query with lexical terms (emotet) uses larger search_limit."""
        from src.web.routes.chat import api_rag_chat

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(
            return_value={
                "message": "Emotet delivery techniques",
                "conversation_history": [],
                "max_results": 5,
                "similarity_threshold": 0.3,
                "use_llm_generation": False,
            }
        )

        with (
            patch("src.services.rag_service.get_rag_service") as mock_get_rag,
            patch("src.database.async_manager.async_db_manager") as mock_async_db,
        ):
            mock_rag = AsyncMock()
            mock_rag.find_unified_results = AsyncMock(return_value={"articles": [], "rules": []})
            mock_async_db.search_articles_by_lexical_terms = AsyncMock(return_value=[])
            mock_rag.db_manager = MagicMock()
            mock_rag.db_manager.get_session = MagicMock()
            mock_rag.db_manager.get_session.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(add=MagicMock(), flush=AsyncMock(), commit=AsyncMock())
            )
            mock_rag.db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_rag.return_value = mock_rag

            await api_rag_chat(mock_request)
            call_kwargs = mock_rag.find_unified_results.call_args[1]
            assert call_kwargs["top_k_articles"] >= 50

    @pytest.mark.asyncio
    async def test_rag_chat_lexical_fallback_merges_articles(self):
        """When embedding returns few results, lexical search supplements and merges."""
        from src.web.routes.chat import api_rag_chat

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(
            return_value={
                "message": "Emotet delivery techniques",
                "conversation_history": [],
                "max_results": 5,
                "similarity_threshold": 0.3,
                "use_llm_generation": False,
            }
        )

        lexical_article = {
            "id": 42,
            "title": "Emotet delivery techniques",
            "content": "Content about emotet",
            "similarity": 0.35,
            "source_name": "Test Source",
            "canonical_url": "https://example.com/42",
        }

        with (
            patch("src.services.rag_service.get_rag_service") as mock_get_rag,
            patch("src.database.async_manager.async_db_manager") as mock_async_db,
        ):
            mock_rag = AsyncMock()
            mock_rag.find_unified_results = AsyncMock(return_value={"articles": [], "rules": []})
            mock_async_db.search_articles_by_lexical_terms = AsyncMock(return_value=[lexical_article])
            mock_rag.db_manager = MagicMock()
            mock_rag.db_manager.get_session = MagicMock()
            mock_rag.db_manager.get_session.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(add=MagicMock(), flush=AsyncMock(), commit=AsyncMock())
            )
            mock_rag.db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_get_rag.return_value = mock_rag

            result = await api_rag_chat(mock_request)
            assert "relevant_articles" in result
            assert len(result["relevant_articles"]) >= 1
            assert result["relevant_articles"][0]["id"] == 42
            mock_async_db.search_articles_by_lexical_terms.assert_called_once_with(terms=["emotet"], limit=15)
