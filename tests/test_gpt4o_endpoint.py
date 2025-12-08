"""Tests for GPT-4o optimized endpoint functionality."""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException
from datetime import datetime

# Import the endpoint function
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.web.gpt4o_optimized_endpoint import api_gpt4o_rank_optimized
from src.models.article import Article


class TestGPT4oOptimizedEndpoint:
    """Test GPT-4o optimized endpoint functionality."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app for testing."""
        app = FastAPI()
        app.post("/api/articles/{article_id}/gpt4o-rank-optimized")(api_gpt4o_rank_optimized)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def sample_article(self):
        """Create sample article for testing."""
        return Article(
            id=1,
            source_id=1,
            canonical_url="https://example.com/article",
            title="Test Threat Intelligence Article",
            published_at=datetime.utcnow(),
            content="This is a test article about PowerShell malware techniques.",
            summary="Test summary",
            authors=["Test Author"],
            tags=["malware", "powershell"],
            article_metadata={},
            content_hash="test_hash",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    @pytest.fixture
    def sample_source(self):
        """Create sample source for testing."""
        return Mock(
            id=1,
            name="Test Source",
            url="https://example.com"
        )

    @pytest.fixture
    def mock_request_body(self):
        """Create mock request body."""
        return {
            "url": "https://example.com/article",
            "api_key": "test-api-key",
            "use_filtering": True,
            "min_confidence": 0.7
        }

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_success(self, sample_article, sample_source, mock_request_body):
        """Test successful GPT-4o ranking with optimization."""
        # Mock dependencies
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            with patch('src.web.gpt4o_optimized_endpoint.optimize_article_content') as mock_optimize:
                with patch('src.web.gpt4o_optimized_endpoint.httpx.AsyncClient') as mock_client:
                    # Setup mocks
                    mock_db.get_article.return_value = sample_article
                    mock_db.get_source.return_value = sample_source
                    mock_db.update_article.return_value = None
                    
                    mock_optimize.return_value = {
                        'success': True,
                        'filtered_content': 'Filtered content',
                        'cost_savings': 0.05,
                        'tokens_saved': 1000,
                        'chunks_removed': 2
                    }
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        'choices': [{'message': {'content': 'SIGMA HUNTABILITY SCORE: 8'}}]
                    }
                    
                    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                    
                    # Create mock request
                    mock_request = Mock()
                    mock_request.json.return_value = mock_request_body
                    
                    # Call the endpoint
                    result = await api_gpt4o_rank_optimized(1, mock_request)
        
        # Verify results
        assert result['success'] is True
        assert result['article_id'] == 1
        assert 'analysis' in result
        assert 'timestamp' in result
        assert result['optimization']['enabled'] is True
        assert result['optimization']['cost_savings'] == 0.05
        assert result['optimization']['tokens_saved'] == 1000
        assert result['optimization']['chunks_removed'] == 2

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_without_filtering(self, sample_article, sample_source):
        """Test GPT-4o ranking without content filtering."""
        mock_request_body = {
            "url": "https://example.com/article",
            "api_key": "test-api-key",
            "use_filtering": False
        }
        
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            with patch('src.web.gpt4o_optimized_endpoint.httpx.AsyncClient') as mock_client:
                # Setup mocks
                mock_db.get_article.return_value = sample_article
                mock_db.get_source.return_value = sample_source
                mock_db.update_article.return_value = None
                
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'choices': [{'message': {'content': 'SIGMA HUNTABILITY SCORE: 7'}}]
                }
                
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                
                # Create mock request
                mock_request = Mock()
                mock_request.json.return_value = mock_request_body
                
                # Call the endpoint
                result = await api_gpt4o_rank_optimized(1, mock_request)
        
        # Verify results
        assert result['success'] is True
        assert result['optimization']['enabled'] is False
        assert result['optimization']['cost_savings'] == 0.0
        assert result['optimization']['tokens_saved'] == 0
        assert result['optimization']['chunks_removed'] == 0

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_article_not_found(self, mock_request_body):
        """Test GPT-4o ranking when article is not found."""
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            mock_db.get_article.return_value = None
            
            mock_request = Mock()
            mock_request.json.return_value = mock_request_body
            
            with pytest.raises(HTTPException) as exc_info:
                await api_gpt4o_rank_optimized(999, mock_request)
            
            assert exc_info.value.status_code == 404
            assert "Article not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_missing_api_key(self, sample_article):
        """Test GPT-4o ranking with missing API key."""
        mock_request_body = {
            "url": "https://example.com/article",
            "use_filtering": True
        }
        
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            mock_db.get_article.return_value = sample_article
            
            mock_request = Mock()
            mock_request.json.return_value = mock_request_body
            
            with pytest.raises(HTTPException) as exc_info:
                await api_gpt4o_rank_optimized(1, mock_request)
            
            assert exc_info.value.status_code == 400
            assert "OpenAI API key is required" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_missing_content(self, sample_article):
        """Test GPT-4o ranking with missing article content."""
        sample_article.content = None
        mock_request_body = {
            "url": "https://example.com/article",
            "api_key": "test-api-key",
            "use_filtering": True
        }
        
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            mock_db.get_article.return_value = sample_article
            
            mock_request = Mock()
            mock_request.json.return_value = mock_request_body
            
            with pytest.raises(HTTPException) as exc_info:
                await api_gpt4o_rank_optimized(1, mock_request)
            
            assert exc_info.value.status_code == 400
            assert "Article content is required" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_optimization_failure(self, sample_article, sample_source, mock_request_body):
        """Test GPT-4o ranking when optimization fails."""
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            with patch('src.web.gpt4o_optimized_endpoint.optimize_article_content') as mock_optimize:
                with patch('src.web.gpt4o_optimized_endpoint.httpx.AsyncClient') as mock_client:
                    # Setup mocks
                    mock_db.get_article.return_value = sample_article
                    mock_db.get_source.return_value = sample_source
                    mock_db.update_article.return_value = None
                    
                    mock_optimize.return_value = {
                        'success': False,
                        'error': 'Optimization failed'
                    }
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        'choices': [{'message': {'content': 'SIGMA HUNTABILITY SCORE: 6'}}]
                    }
                    
                    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                    
                    # Create mock request
                    mock_request = Mock()
                    mock_request.json.return_value = mock_request_body
                    
                    # Call the endpoint
                    result = await api_gpt4o_rank_optimized(1, mock_request)
        
        # Verify results - should fallback to original content
        assert result['success'] is True
        assert result['optimization']['enabled'] is True
        assert result['optimization']['cost_savings'] == 0.0
        assert result['optimization']['tokens_saved'] == 0
        assert result['optimization']['chunks_removed'] == 0

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_openai_api_error(self, sample_article, sample_source, mock_request_body):
        """Test GPT-4o ranking when OpenAI API returns error."""
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            with patch('src.web.gpt4o_optimized_endpoint.optimize_article_content') as mock_optimize:
                with patch('src.web.gpt4o_optimized_endpoint.httpx.AsyncClient') as mock_client:
                    # Setup mocks
                    mock_db.get_article.return_value = sample_article
                    mock_db.get_source.return_value = sample_source
                    
                    mock_optimize.return_value = {
                        'success': True,
                        'filtered_content': 'Filtered content',
                        'cost_savings': 0.05,
                        'tokens_saved': 1000,
                        'chunks_removed': 2
                    }
                    
                    mock_response = Mock()
                    mock_response.status_code = 401
                    mock_response.text = "Unauthorized"
                    
                    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                    
                    # Create mock request
                    mock_request = Mock()
                    mock_request.json.return_value = mock_request_body
                    
                    with pytest.raises(HTTPException) as exc_info:
                        await api_gpt4o_rank_optimized(1, mock_request)
                    
                    assert exc_info.value.status_code == 500
                    assert "OpenAI API error" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_content_truncation(self, sample_article, sample_source, mock_request_body):
        """Test GPT-4o ranking with content truncation."""
        # Create very long content
        sample_article.content = "x" * 500000  # 500KB content
        
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            with patch('src.web.gpt4o_optimized_endpoint.optimize_article_content') as mock_optimize:
                with patch('src.web.gpt4o_optimized_endpoint.httpx.AsyncClient') as mock_client:
                    # Setup mocks
                    mock_db.get_article.return_value = sample_article
                    mock_db.get_source.return_value = sample_source
                    mock_db.update_article.return_value = None
                    
                    mock_optimize.return_value = {
                        'success': True,
                        'filtered_content': 'x' * 500000,  # Still long
                        'cost_savings': 0.1,
                        'tokens_saved': 5000,
                        'chunks_removed': 10
                    }
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        'choices': [{'message': {'content': 'SIGMA HUNTABILITY SCORE: 9'}}]
                    }
                    
                    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                    
                    # Create mock request
                    mock_request = Mock()
                    mock_request.json.return_value = mock_request_body
                    
                    # Call the endpoint
                    result = await api_gpt4o_rank_optimized(1, mock_request)
        
        # Verify results
        assert result['success'] is True
        # Content should be truncated in the prompt
        assert len(result['analysis']) > 0

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_metadata_update(self, sample_article, sample_source, mock_request_body):
        """Test that article metadata is updated with analysis results."""
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            with patch('src.web.gpt4o_optimized_endpoint.optimize_article_content') as mock_optimize:
                with patch('src.web.gpt4o_optimized_endpoint.httpx.AsyncClient') as mock_client:
                    # Setup mocks
                    mock_db.get_article.return_value = sample_article
                    mock_db.get_source.return_value = sample_source
                    mock_update = Mock()
                    mock_db.update_article.return_value = mock_update
                    
                    mock_optimize.return_value = {
                        'success': True,
                        'filtered_content': 'Filtered content',
                        'cost_savings': 0.05,
                        'tokens_saved': 1000,
                        'chunks_removed': 2
                    }
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        'choices': [{'message': {'content': 'SIGMA HUNTABILITY SCORE: 8'}}]
                    }
                    
                    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                    
                    # Create mock request
                    mock_request = Mock()
                    mock_request.json.return_value = mock_request_body
                    
                    # Call the endpoint
                    result = await api_gpt4o_rank_optimized(1, mock_request)
        
        # Verify metadata update was called
        mock_db.update_article.assert_called_once()
        call_args = mock_db.update_article.call_args
        assert call_args[0][0] == 1  # article_id
        update_data = call_args[0][1]
        assert 'gpt4o_ranking' in update_data.metadata
        assert update_data.metadata['gpt4o_ranking']['model'] == 'gpt-4o'
        assert update_data.metadata['gpt4o_ranking']['optimization_enabled'] is True

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_custom_confidence(self, sample_article, sample_source):
        """Test GPT-4o ranking with custom confidence threshold."""
        mock_request_body = {
            "url": "https://example.com/article",
            "api_key": "test-api-key",
            "use_filtering": True,
            "min_confidence": 0.9
        }
        
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            with patch('src.web.gpt4o_optimized_endpoint.optimize_article_content') as mock_optimize:
                with patch('src.web.gpt4o_optimized_endpoint.httpx.AsyncClient') as mock_client:
                    # Setup mocks
                    mock_db.get_article.return_value = sample_article
                    mock_db.get_source.return_value = sample_source
                    mock_db.update_article.return_value = None
                    
                    mock_optimize.return_value = {
                        'success': True,
                        'filtered_content': 'Filtered content',
                        'cost_savings': 0.08,
                        'tokens_saved': 1500,
                        'chunks_removed': 3
                    }
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        'choices': [{'message': {'content': 'SIGMA HUNTABILITY SCORE: 9'}}]
                    }
                    
                    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                    
                    # Create mock request
                    mock_request = Mock()
                    mock_request.json.return_value = mock_request_body
                    
                    # Call the endpoint
                    result = await api_gpt4o_rank_optimized(1, mock_request)
        
        # Verify custom confidence was used
        assert result['success'] is True
        assert result['optimization']['min_confidence'] == 0.9
        mock_optimize.assert_called_once_with(sample_article.content, 0.9)

    @pytest.mark.asyncio
    async def test_api_gpt4o_rank_optimized_exception_handling(self, sample_article, mock_request_body):
        """Test GPT-4o ranking exception handling."""
        with patch('src.web.gpt4o_optimized_endpoint.async_db_manager') as mock_db:
            mock_db.get_article.side_effect = Exception("Database error")
            
            mock_request = Mock()
            mock_request.json.return_value = mock_request_body
            
            with pytest.raises(HTTPException) as exc_info:
                await api_gpt4o_rank_optimized(1, mock_request)
            
            assert exc_info.value.status_code == 500
            assert "Database error" in str(exc_info.value.detail)
