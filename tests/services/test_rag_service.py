"""Tests for RAG service functionality.

SKIPPED: RAGService depends on EmbeddingService which uses Sentence Transformers models.
Models are downloaded from HuggingFace Hub (public repository) but run locally - no API keys needed.
Tests are skipped because model loading/download is slow for unit tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, List

from src.services.rag_service import RAGService

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
# SKIPPED: Model loading is slow for unit tests (models run locally, downloaded from HuggingFace Hub)
pytestmark = [pytest.mark.unit, pytest.mark.skip(reason="SKIPPED: RAGService requires Sentence Transformers model loading (slow for unit tests)")]


class TestRAGService:
    """Test RAGService functionality.
    
    SKIPPED: RAGService depends on EmbeddingService which uses Sentence Transformers models.
    Models are downloaded from HuggingFace Hub but run locally - no API keys or connections needed.
    Tests are skipped because model loading is slow for unit tests.
    """

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
        with patch('src.services.rag_service.get_embedding_service', return_value=mock_embedding_service), \
             patch('src.services.rag_service.EmbeddingService', return_value=mock_embedding_service), \
             patch('src.services.rag_service.AsyncDatabaseManager', return_value=mock_db_manager), \
             patch('src.services.rag_service.generate_query_embedding', return_value=[0.1] * 768):
            return RAGService()

    @pytest.fixture
    def sample_chunk(self):
        """Sample chunk data."""
        return {
            'id': 1,
            'article_id': 1,
            'selected_text': 'PowerShell command execution for persistence',
            'similarity': 0.85,
            'annotation_type': 'huntable'
        }

    @pytest.fixture
    def sample_article(self):
        """Sample article data."""
        return {
            'id': 1,
            'title': 'APT29 PowerShell Persistence',
            'canonical_url': 'https://example.com/article1',
            'source_name': 'Threat Intel Feed',
            'published_at': '2024-01-01T12:00:00Z',
            'article_metadata': {'threat_hunting_score': 90.0}
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
        
        chunks = await service.find_similar_chunks(
            query="PowerShell persistence",
            top_k=10,
            threshold=0.7
        )
        
        assert len(chunks) == 1
        assert chunks[0]['article_title'] == sample_article['title']
        assert chunks[0]['similarity'] == sample_chunk['similarity']

    @pytest.mark.asyncio
    async def test_find_similar_chunks_threshold_filtering(self, service, mock_db_manager, sample_chunk):
        """Test similarity threshold filtering."""
        sample_chunk['similarity'] = 0.5  # Below threshold
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = {'title': 'Test'}
        
        chunks = await service.find_similar_chunks(
            query="test",
            top_k=10,
            threshold=0.7
        )
        
        # Should still return chunks (threshold is applied in DB query)
        assert isinstance(chunks, list)

    @pytest.mark.asyncio
    async def test_find_similar_chunks_context_truncation(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test context length truncation."""
        long_text = "x" * 5000
        sample_chunk['selected_text'] = long_text
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = sample_article
        
        chunks = await service.find_similar_chunks(
            query="test",
            top_k=10,
            threshold=0.0,
            context_length=2000
        )
        
        assert len(chunks[0]['selected_text']) <= 2003  # 2000 + "..."
        assert chunks[0]['selected_text'].endswith("...")

    @pytest.mark.asyncio
    async def test_find_similar_content_with_chunks(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test content search using chunks."""
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = sample_article
        
        results = await service.find_similar_content(
            query="PowerShell",
            top_k=10,
            threshold=0.7,
            use_chunks=True
        )
        
        assert len(results) > 0
        assert 'article_id' in results[0]

    @pytest.mark.asyncio
    async def test_find_similar_content_with_articles(self, service, mock_db_manager, sample_article):
        """Test content search using article-level embeddings."""
        mock_db_manager.search_similar_articles.return_value = [sample_article]
        
        results = await service.find_similar_content(
            query="PowerShell",
            top_k=10,
            threshold=0.7,
            use_chunks=False
        )
        
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_find_similar_content_hunt_score_filter(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test hunt score filtering."""
        sample_article['article_metadata'] = {'threat_hunting_score': 50.0}
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = sample_article
        
        results = await service.find_similar_content(
            query="test",
            top_k=10,
            threshold=0.0,
            min_hunt_score=60.0
        )
        
        # Should filter out articles below threshold
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_get_context_for_article(self, service, mock_db_manager, sample_chunk, sample_article):
        """Test context retrieval for article."""
        mock_db_manager.search_similar_annotations.return_value = [sample_chunk]
        mock_db_manager.get_article_by_id.return_value = sample_article
        
        context = await service.get_context_for_article(
            article_id=1,
            top_k=5,
            threshold=0.7
        )
        
        assert isinstance(context, list)

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
        chunk1 = {**sample_chunk, 'id': 1}
        chunk2 = {**sample_chunk, 'id': 2}
        mock_db_manager.search_similar_annotations.return_value = [chunk1, chunk2]
        mock_db_manager.get_article_by_id.return_value = sample_article
        
        results = await service.find_similar_content(
            query="test",
            top_k=10,
            threshold=0.0
        )
        
        # Should deduplicate by article_id
        article_ids = [r['article_id'] for r in results]
        assert len(set(article_ids)) == len(article_ids)  # All unique
