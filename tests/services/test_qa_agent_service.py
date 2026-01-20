"""Tests for QA agent service functionality."""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from src.services.qa_agent_service import QAAgentService
from src.database.models import ArticleTable

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestQAAgentService:
    """Test QAAgentService functionality."""

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service."""
        service = Mock()
        service.request_chat = AsyncMock(return_value={
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'summary': 'Output is compliant and accurate',
                        'issues': [],
                        'verdict': 'pass'
                    })
                }
            }]
        })
        return service

    @pytest.fixture
    def service(self, mock_llm_service):
        """Create QAAgentService instance."""
        return QAAgentService(mock_llm_service)

    @pytest.fixture
    def sample_article(self):
        """Create sample article."""
        article = Mock(spec=ArticleTable)
        article.id = 1
        article.title = "Test Article"
        article.content = "This is test article content about threat intelligence."
        article.article_metadata = {}
        return article

    @pytest.fixture
    def sample_agent_output(self):
        """Sample agent output."""
        return {
            'rank': 8.5,
            'reasoning': 'High threat intelligence value',
            'indicators': ['PowerShell', 'persistence']
        }

    @pytest.mark.asyncio
    async def test_evaluate_agent_output_success(self, service, sample_article, sample_agent_output, mock_llm_service):
        """Test successful agent output evaluation."""
        result = await service.evaluate_agent_output(
            article=sample_article,
            agent_prompt="Rank this article",
            agent_output=sample_agent_output,
            agent_name="RankAgent"
        )
        
        assert 'summary' in result
        assert 'issues' in result
        assert 'verdict' in result
        assert result['verdict'] == 'pass'

    @pytest.mark.asyncio
    async def test_evaluate_agent_output_with_issues(self, service, sample_article, sample_agent_output, mock_llm_service):
        """Test evaluation with detected issues."""
        mock_llm_service.request_chat.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'summary': 'Output has formatting issues',
                        'issues': [
                            {
                                'type': 'formatting',
                                'description': 'Missing required field',
                                'location': 'rank',
                                'severity': 'medium'
                            }
                        ],
                        'verdict': 'needs_revision'
                    })
                }
            }]
        }
        
        result = await service.evaluate_agent_output(
            article=sample_article,
            agent_prompt="Rank this article",
            agent_output=sample_agent_output,
            agent_name="RankAgent"
        )
        
        assert result['verdict'] == 'needs_revision'
        assert len(result['issues']) > 0

    @pytest.mark.asyncio
    async def test_evaluate_agent_output_critical_failure(self, service, sample_article, sample_agent_output, mock_llm_service):
        """Test evaluation with critical failure."""
        mock_llm_service.request_chat.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'summary': 'Output is completely incorrect',
                        'issues': [
                            {
                                'type': 'factuality',
                                'description': 'Output contradicts article content',
                                'location': 'reasoning',
                                'severity': 'high'
                            }
                        ],
                        'verdict': 'critical_failure'
                    })
                }
            }]
        }
        
        result = await service.evaluate_agent_output(
            article=sample_article,
            agent_prompt="Rank this article",
            agent_output=sample_agent_output,
            agent_name="RankAgent"
        )
        
        assert result['verdict'] == 'critical_failure'
        assert any(issue['severity'] == 'high' for issue in result['issues'])

    @pytest.mark.asyncio
    async def test_evaluate_agent_output_with_config(self, service, sample_article, sample_agent_output, mock_llm_service):
        """Test evaluation with custom QA prompt from config."""
        config_obj = Mock()
        config_obj.agent_prompts = {
            "QAAgent": {
                "prompt": json.dumps({
                    "role": "QA Evaluator",
                    "objective": "Evaluate agent outputs",
                    "evaluation_criteria": ["accuracy", "completeness"]
                })
            }
        }
        
        result = await service.evaluate_agent_output(
            article=sample_article,
            agent_prompt="Rank this article",
            agent_output=sample_agent_output,
            agent_name="RankAgent",
            config_obj=config_obj
        )
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_evaluate_agent_output_content_truncation(self, service, sample_article, sample_agent_output, mock_llm_service):
        """Test content truncation for long articles."""
        sample_article.content = "x" * 20000  # Very long content
        
        result = await service.evaluate_agent_output(
            article=sample_article,
            agent_prompt="Rank this article",
            agent_output=sample_agent_output,
            agent_name="RankAgent"
        )
        
        # Should handle truncation gracefully
        assert result is not None

    @pytest.mark.asyncio
    async def test_evaluate_agent_output_error_handling(self, service, sample_article, sample_agent_output, mock_llm_service):
        """Test error handling in evaluation."""
        mock_llm_service.request_chat.side_effect = Exception("LLM error")
        
        with pytest.raises(Exception):
            await service.evaluate_agent_output(
                article=sample_article,
                agent_prompt="Rank this article",
                agent_output=sample_agent_output,
                agent_name="RankAgent"
            )

    @pytest.mark.asyncio
    async def test_evaluate_agent_output_json_parsing(self, service, sample_article, sample_agent_output, mock_llm_service):
        """Test JSON parsing from LLM response."""
        # LLM response wrapped in markdown
        mock_llm_service.request_chat.return_value = {
            'choices': [{
                'message': {
                    'content': '```json\n{"summary": "Good", "issues": [], "verdict": "pass"}\n```'
                }
            }]
        }
        
        result = await service.evaluate_agent_output(
            article=sample_article,
            agent_prompt="Rank this article",
            agent_output=sample_agent_output,
            agent_name="RankAgent"
        )
        
        assert result['verdict'] == 'pass'
