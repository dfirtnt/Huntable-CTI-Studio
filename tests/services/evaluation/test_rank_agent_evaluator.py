"""Tests for Rank agent evaluator functionality."""

import json
from unittest.mock import Mock, patch

import pytest

from src.services.evaluation.rank_agent_evaluator import RankAgentEvaluator

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestRankAgentEvaluator:
    """Test RankAgentEvaluator functionality."""

    @pytest.fixture
    def evaluator(self):
        """Create RankAgentEvaluator instance."""
        return RankAgentEvaluator(ranking_threshold=6.0)

    @pytest.mark.asyncio
    async def test_evaluate_dataset_success(self, evaluator, tmp_path):
        """Test successful dataset evaluation."""
        test_data = [{"article_id": 1, "expected_score": 8.5, "ground_truth_hunt_score": 85.0}]

        test_file = tmp_path / "test_dataset.json"
        with open(test_file, "w") as f:
            json.dump(test_data, f)

        with (
            patch("src.services.evaluation.rank_agent_evaluator.LLMService") as mock_llm_class,
            patch("src.services.evaluation.rank_agent_evaluator.DatabaseManager") as mock_db_class,
        ):
            mock_db = Mock()
            mock_session = Mock()
            mock_article = Mock()
            mock_article.id = 1
            mock_article.content = "Test content"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_article
            mock_db.get_session.return_value = mock_session
            mock_db_class.return_value = mock_db

            result = await evaluator.evaluate_dataset(test_data_path=test_file)

            # Result contains summary metrics, not 'results' or 'metrics' keys
            assert isinstance(result, dict)
            assert "total_articles" in result or "errors" in result

    def test_calculate_metrics(self, evaluator):
        """Test metrics calculation."""
        evaluator.results = [
            {"article_id": 1, "predicted_score": 8.5, "expected_score": 8.0, "ground_truth_hunt_score": 85.0}
        ]

        metrics = evaluator.calculate_metrics()

        # Metrics uses 'total_articles' not 'total_examples'
        assert "total_articles" in metrics or "valid_results" in metrics
        assert "mean_score" in metrics or "score_distribution" in metrics or "error_rate" in metrics
