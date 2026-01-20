"""Tests for LLM service functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

from src.services.llm_service import LLMService

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestLLMService:
    """Test LLMService functionality."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance with mocked dependencies."""
        with patch('src.services.llm_service.DatabaseManager') as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
            return LLMService()

    @pytest.fixture
    def service_with_config(self):
        """Create LLMService with config models."""
        config_models = {
            "RankAgent": "test-rank-model",
            "ExtractAgent": "test-extract-model",
            "SigmaAgent": "test-sigma-model"
        }
        with patch('src.services.llm_service.DatabaseManager') as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
            return LLMService(config_models=config_models)

    def test_canonicalize_provider_openai(self, service):
        """Test provider canonicalization for OpenAI."""
        assert service._canonicalize_provider("openai") == "openai"
        assert service._canonicalize_provider("chatgpt") == "openai"
        assert service._canonicalize_provider("gpt-4o") == "openai"

    def test_canonicalize_provider_anthropic(self, service):
        """Test provider canonicalization for Anthropic."""
        assert service._canonicalize_provider("anthropic") == "anthropic"
        assert service._canonicalize_provider("claude") == "anthropic"

    def test_canonicalize_provider_lmstudio(self, service):
        """Test provider canonicalization for LMStudio."""
        assert service._canonicalize_provider("lmstudio") == "lmstudio"
        assert service._canonicalize_provider("local") == "lmstudio"
        assert service._canonicalize_provider(None) == "lmstudio"

    def test_resolve_agent_model_from_config(self, service_with_config):
        """Test model resolution from config."""
        assert service_with_config.model_rank == "test-rank-model"
        assert service_with_config.model_extract == "test-extract-model"
        assert service_with_config.model_sigma == "test-sigma-model"

    def test_convert_messages_for_model_mistral(self, service):
        """Test message conversion for Mistral models."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"}
        ]
        
        converted = service._convert_messages_for_model(messages, "mistral-7b-instruct")
        
        # Should convert system to user message
        assert len(converted) == 1
        assert converted[0]["role"] == "user"

    def test_convert_messages_for_model_qwen(self, service):
        """Test message conversion for Qwen models (supports system role)."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"}
        ]
        
        converted = service._convert_messages_for_model(messages, "qwen-7b-instruct")
        
        # Should keep system role
        assert len(converted) == 2
        assert converted[0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_request_chat_success(self, service):
        """Test successful chat request."""
        mock_response = {
            'choices': [{
                'message': {
                    'content': 'Test response'
                }
            }],
            'usage': {
                'prompt_tokens': 10,
                'completion_tokens': 5,
                'total_tokens': 15
            }
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=Mock(status_code=200, json=lambda: mock_response))
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await service.request_chat(
                provider='lmstudio',
                model_name='test-model',
                messages=[{"role": "user", "content": "Hello"}]
            )
            
            assert result['choices'][0]['message']['content'] == 'Test response'

    @pytest.mark.asyncio
    async def test_request_chat_retry_on_failure(self, service):
        """Test retry logic on chat request failure."""
        mock_response = {
            'choices': [{
                'message': {
                    'content': 'Success after retry'
                }
            }]
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            # First call fails, second succeeds
            mock_client.post = AsyncMock(side_effect=[
                Exception("Connection error"),
                Mock(status_code=200, json=lambda: mock_response)
            ])
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await service.request_chat(
                provider='lmstudio',
                model_name='test-model',
                messages=[{"role": "user", "content": "Hello"}],
                max_retries=2
            )
            
            assert result['choices'][0]['message']['content'] == 'Success after retry'

    @pytest.mark.asyncio
    async def test_request_chat_error_handling(self, service):
        """Test error handling in chat request."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("API error"))
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            with pytest.raises(Exception):
                await service.request_chat(
                    provider='lmstudio',
                    model_name='test-model',
                    messages=[{"role": "user", "content": "Hello"}],
                    max_retries=1
                )

    def test_truncate_content(self, service):
        """Test content truncation for context limits."""
        long_content = "x" * 10000
        
        truncated = service._truncate_content(
            long_content,
            max_context_tokens=1000,
            max_output_tokens=100
        )
        
        assert len(truncated) < len(long_content)
        assert "[Content truncated" in truncated

    def test_estimate_tokens(self, service):
        """Test token estimation."""
        text = "x" * 400  # ~100 tokens at 4 chars/token
        
        tokens = service._estimate_tokens(text)
        
        assert tokens == 100

    def test_get_top_p_for_agent(self, service_with_config):
        """Test getting top_p for specific agent."""
        top_p = service_with_config.get_top_p_for_agent("RankAgent")
        
        assert isinstance(top_p, float)
        assert 0.0 <= top_p <= 1.0

    def test_compute_rank_ground_truth(self, service):
        """Test ground truth rank computation."""
        result = service.compute_rank_ground_truth(hunt_score=85.0, ml_score=90.0)
        
        assert 'ground_truth_rank' in result
        assert result['ground_truth_rank'] is not None
        assert 1.0 <= result['ground_truth_rank'] <= 10.0

    def test_compute_rank_ground_truth_none_scores(self, service):
        """Test ground truth rank with None scores."""
        result = service.compute_rank_ground_truth(hunt_score=None, ml_score=None)
        
        assert result['ground_truth_rank'] is None

    @pytest.mark.asyncio
    async def test_check_model_context_length(self, service):
        """Test model context length checking."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock(status_code=200, json=lambda: {"data": [{"id": "test-model", "context_length": 32768}]})
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(return_value=Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": "test"}}]}))
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await service.check_model_context_length(model_name="test-model", threshold=16384)
            
            assert 'context_length' in result
            assert 'is_sufficient' in result
            assert result['is_sufficient'] is True
