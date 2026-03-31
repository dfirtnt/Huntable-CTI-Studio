"""Tests for RAG service functionality.

Uses mocked EmbeddingService and AsyncDatabaseManager; no real model loading.
"""

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.services.rag_service import RAGService

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestRAGService:
    """Test RAGService functionality (mocked dependencies)."""

    def test_init_does_not_create_embedding_clients(self):
        """RAGService should not instantiate embedding clients until needed."""
        with (
            patch("src.services.rag_service.get_embedding_service") as mock_get_embedding_service,
            patch("src.services.rag_service.EmbeddingService") as mock_sigma_embedding_cls,
            patch("src.services.rag_service.AsyncDatabaseManager"),
        ):
            service = RAGService()

        assert service._embedding_service is None
        assert service._sigma_embedding_service is None
        mock_get_embedding_service.assert_not_called()
        mock_sigma_embedding_cls.assert_not_called()

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = Mock()
        service.generate_embedding = AsyncMock(return_value=[0.1] * 768)
        return service

    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        manager = AsyncMock()
        manager.search_similar_annotations = AsyncMock(return_value=[])
        manager.get_article_by_id = AsyncMock(return_value=None)
        manager.search_similar_articles = AsyncMock(return_value=[])
        return manager

    @pytest.fixture
    def service(self, mock_embedding_service, mock_db_manager):
        """Create RAGService instance with mocked dependencies."""
        with (
            patch("src.services.rag_service.get_embedding_service", return_value=mock_embedding_service),
            patch("src.services.rag_service.EmbeddingService", return_value=mock_embedding_service),
            patch("src.services.rag_service.AsyncDatabaseManager", return_value=mock_db_manager),
            patch("src.services.rag_service.generate_query_embedding", return_value=[0.1] * 768),
        ):
            return RAGService()

    @pytest.fixture
    def sample_chunk(self):
        """Sample chunk data."""
        return {
            "id": 1,
            "article_id": 1,
            "selected_text": "PowerShell command execution for persistence",
            "similarity": 0.85,
            "confidence_score": 0.85,
            "annotation_type": "huntable",
        }

    @pytest.fixture
    def sample_article(self):
        """Sample article data."""
        return {
            "id": 1,
            "title": "APT29 PowerShell Persistence",
            "canonical_url": "https://example.com/article1",
            "source_name": "Threat Intel Feed",
            "published_at": "2024-01-01T12:00:00Z",
            "article_metadata": {"threat_hunting_score": 90.0},
        }

    @pytest.mark.asyncio
    async def test_embed_query(self, service):
        """Test query embedding generation."""
        query = "PowerShell persistence techniques"

        embedding = await service.embed_query(query)

        assert len(embedding) == 768
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_find_similar_chunks_success(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test successful chunk search."""
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = sample_article

        chunks = await service.find_similar_chunks(query="PowerShell persistence", top_k=10, threshold=0.7)

        assert len(chunks) == 1
        assert chunks[0]["article_title"] == sample_article["title"]
        assert chunks[0]["similarity"] == sample_chunk["similarity"]

    @pytest.mark.asyncio
    async def test_find_similar_chunks_threshold_filtering(self, service, mock_db_manager, sample_chunk):
        """Test similarity threshold filtering."""
        sample_chunk["similarity"] = 0.5  # Below threshold
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = {"title": "Test"}

        chunks = await service.find_similar_chunks(query="test", top_k=10, threshold=0.7)

        # Should still return chunks (threshold is applied in DB query)
        assert isinstance(chunks, list)

    @pytest.mark.asyncio
    async def test_find_similar_chunks_context_truncation(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test context length truncation."""
        long_text = "x" * 5000
        sample_chunk["selected_text"] = long_text
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = sample_article

        chunks = await service.find_similar_chunks(query="test", top_k=10, threshold=0.0, context_length=2000)

        assert len(chunks[0]["selected_text"]) <= 2003  # 2000 + "..."
        assert chunks[0]["selected_text"].endswith("...")

    @pytest.mark.asyncio
    async def test_find_similar_content_with_chunks(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test content search using chunks."""
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = sample_article

        results = await service.find_similar_content(query="PowerShell", top_k=10, threshold=0.7, use_chunks=True)

        assert len(results) > 0
        assert "article_id" in results[0]

    @pytest.mark.asyncio
    async def test_find_similar_content_with_articles(self, service, mock_db_manager, sample_article):
        """Test content search using article-level embeddings."""
        mock_db_manager.search_similar_articles.return_value = [sample_article]

        results = await service.find_similar_content(query="PowerShell", top_k=10, threshold=0.7, use_chunks=False)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_find_similar_content_hunt_score_filter(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test hunt score filtering."""
        sample_article["article_metadata"] = {"threat_hunting_score": 50.0}
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = sample_article

        results = await service.find_similar_content(query="test", top_k=10, threshold=0.0, min_hunt_score=60.0)

        # Should filter out articles below threshold
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_find_similar_chunks_error_handling(self, service, mock_db_manager):
        """Test error handling in chunk search."""
        mock_db_manager.search_similar_annotations.side_effect = Exception("DB error")

        chunks = await service.find_similar_chunks(query="test")

        assert chunks == []

    @pytest.mark.asyncio
    async def test_find_similar_content_deduplication(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test deduplication of results by article_id."""
        # Create multiple chunks from same article
        chunk1 = {**sample_chunk, "id": 1}
        chunk2 = {**sample_chunk, "id": 2}
        mock_db_manager.search_similar_annotations.return_value = [chunk1, chunk2]
        mock_db_manager.get_article_by_id.return_value = sample_article

        results = await service.find_similar_content(query="test", top_k=10, threshold=0.0)

        # Should deduplicate by article_id
        article_ids = [r["article_id"] for r in results]
        assert len(set(article_ids)) == len(article_ids)  # All unique

    @pytest.mark.asyncio
    async def test_find_similar_sigma_rules_passes_bracket_string_vector(self, service, mock_db_manager):
        """Sigma search binds pgvector query as a bracket string for asyncpg."""

        service.sigma_embedding_service.generate_embedding = Mock(return_value=[0.25, 0.5, 0.75])

        captured: dict[str, Any] = {}

        @asynccontextmanager
        async def fake_session():
            sess = MagicMock()

            async def _exec(_stmt, params=None):
                captured["params"] = params
                res = MagicMock()
                res.mappings.return_value = [
                    {
                        "id": 1,
                        "rule_id": "r-1",
                        "title": "Test rule",
                        "description": "d",
                        "tags": [],
                        "level": "high",
                        "status": "stable",
                        "file_path": "/x.yml",
                        "signature_sim": 0.91,
                    }
                ]
                return res

            sess.execute = AsyncMock(side_effect=_exec)
            yield sess

        mock_db_manager.get_session = fake_session

        rules = await service.find_similar_sigma_rules("malware", top_k=5, threshold=0.5)

        assert len(rules) == 1
        assert rules[0]["similarity"] == 0.91
        assert rules[0]["meets_threshold"] is True
        qv = captured["params"]["query_vector"]
        assert isinstance(qv, str)
        assert qv.startswith("[") and qv.endswith("]")
        assert "0.25" in qv

    @pytest.mark.asyncio
    async def test_find_unified_partial_errors_when_article_leg_fails(self, service):
        with (
            patch.object(service, "find_similar_content", new_callable=AsyncMock, side_effect=RuntimeError("art boom")),
            patch.object(
                service,
                "find_similar_sigma_rules",
                new_callable=AsyncMock,
                return_value=[{"id": 1, "title": "r"}],
            ),
        ):
            out = await service.find_unified_results("q", threshold=0.5)

        assert out["articles"] == []
        assert out["total_articles"] == 0
        assert len(out["rules"]) == 1
        assert "partial_errors" in out
        assert any("articles" in err for err in out["partial_errors"])

    @pytest.mark.asyncio
    async def test_find_unified_partial_errors_when_sigma_leg_fails(self, service):
        with (
            patch.object(
                service,
                "find_similar_content",
                new_callable=AsyncMock,
                return_value=[{"article_id": 9, "title": "a"}],
            ),
            patch.object(
                service,
                "find_similar_sigma_rules",
                new_callable=AsyncMock,
                side_effect=RuntimeError("sigma boom"),
            ),
        ):
            out = await service.find_unified_results("q", threshold=0.5)

        assert len(out["articles"]) == 1
        assert out["rules"] == []
        assert "partial_errors" in out
        assert any("sigma" in err for err in out["partial_errors"])
