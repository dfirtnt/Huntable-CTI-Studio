"""Tests for Extract agent evaluator functionality."""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
from typing import Dict, Any

from src.services.evaluation.extract_agent_evaluator import ExtractAgentEvaluator

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestExtractAgentEvaluator:
    """Test ExtractAgentEvaluator functionality."""

    @pytest.fixture
    def evaluator(self):
        """Create ExtractAgentEvaluator instance."""
        return ExtractAgentEvaluator()

    @pytest.fixture
    def sample_extraction_result(self):
        """Sample extraction result."""
        return {
            'command_lines': ['powershell.exe -Command "schtasks /create"'],
            'observables': {
                'ip_addresses': ['192.168.1.1'],
                'domains': ['example.com'],
                'file_paths': ['C:\\Windows\\System32']
            },
            'processes': ['powershell.exe'],
            'registry_keys': []
        }

    @pytest.mark.asyncio
    async def test_evaluate_dataset_success(self, evaluator, tmp_path, sample_extraction_result):
        """Test successful dataset evaluation."""
        test_data = [
            {
                'article_id': 1,
                'expected_extraction': sample_extraction_result
            }
        ]
        
        test_file = tmp_path / "test_dataset.json"
        with open(test_file, 'w') as f:
            json.dump(test_data, f)
        
        with patch('src.services.evaluation.extract_agent_evaluator.LLMService') as mock_llm_class, \
             patch('src.services.evaluation.extract_agent_evaluator.ContentFilter') as mock_filter_class, \
             patch('src.services.evaluation.extract_agent_evaluator.DatabaseManager') as mock_db_class:
            
            mock_db = Mock()
            mock_session = Mock()
            mock_article = Mock()
            mock_article.id = 1
            mock_article.content = "Test content"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_article
            mock_db.get_session.return_value = mock_session
            mock_db_class.return_value = mock_db
            
            result = await evaluator.evaluate_dataset(test_data_path=test_file)
            
            assert 'results' in result or 'metrics' in result

    def test_calculate_metrics(self, evaluator, sample_extraction_result):
        """Test metrics calculation."""
        evaluator.results = [
            {
                'article_id': 1,
                'extraction_result': sample_extraction_result,
                'expected_extraction': sample_extraction_result,
                'json_valid': True,
                'field_completeness': 1.0
            }
        ]
        
        metrics = evaluator.calculate_metrics()
        
        assert 'total_examples' in metrics
        assert 'json_validity_rate' in metrics or 'valid_json_rate' in metrics
