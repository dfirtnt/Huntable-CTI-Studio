"""
Unit tests for observable model evaluator.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.services.observable_evaluation.evaluator import ObservableModelEvaluator
from src.database.models import ArticleAnnotationTable, ArticleTable


class TestObservableModelEvaluator:
    """Tests for ObservableModelEvaluator."""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = Mock()
        return session
    
    @pytest.fixture
    def evaluator(self):
        """Create an evaluator instance."""
        return ObservableModelEvaluator(
            model_name="CMD",
            model_version="20240101_120000",
            observable_type="CMD",
            overlap_threshold=0.5,
        )
    
    @pytest.fixture
    def mock_annotations(self):
        """Create mock annotations."""
        ann1 = Mock(spec=ArticleAnnotationTable)
        ann1.id = 1
        ann1.article_id = 100
        ann1.selected_text = "cmd.exe /c whoami"
        ann1.start_position = 0
        ann1.end_position = 17
        
        ann2 = Mock(spec=ArticleAnnotationTable)
        ann2.id = 2
        ann2.article_id = 100
        ann2.selected_text = "powershell -enc base64"
        ann2.start_position = 20
        ann2.end_position = 42
        
        return [ann1, ann2]
    
    @pytest.fixture
    def mock_article(self):
        """Create a mock article."""
        article = Mock(spec=ArticleTable)
        article.id = 100
        article.content = "The attacker ran cmd.exe /c whoami and then powershell -enc base64 to evade detection."
        return article
    
    def test_empty_metrics_eval(self, evaluator):
        """Test that empty metrics are returned for eval when no annotations."""
        metrics = evaluator._empty_metrics("eval")
        assert metrics["usage"] == "eval"
        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0
        assert metrics["f1_score"] == 0.0
        assert metrics["sample_count"] == 0
    
    def test_empty_metrics_gold(self, evaluator):
        """Test that empty metrics are returned for gold when no annotations."""
        metrics = evaluator._empty_metrics("gold")
        assert metrics["usage"] == "gold"
        assert metrics["exact_match_rate"] == 0.0
        assert metrics["zero_fp_pass_rate"] == 0.0
        assert metrics["sample_count"] == 0
    
    @patch('src.services.observable_evaluation.evaluator.ObservableModelInference')
    def test_load_annotations(self, mock_inference_class, evaluator, mock_session, mock_annotations):
        """Test that annotations are loaded correctly."""
        # Mock the query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_annotations
        mock_session.execute.return_value = mock_result
        
        annotations = evaluator._load_annotations(mock_session, "eval")
        
        assert len(annotations) == 2
        assert annotations[0].article_id == 100
        mock_session.execute.assert_called_once()
    
    @patch('src.services.observable_evaluation.evaluator.ObservableModelInference')
    def test_compute_eval_metrics_basic(self, mock_inference_class, evaluator, mock_session, mock_annotations, mock_article):
        """Test basic eval metrics computation."""
        # Setup mocks
        mock_inference = Mock()
        mock_inference.extract.return_value = [
            {"start": 0, "end": 17, "text": "cmd.exe /c whoami", "label": "CMD"},
            {"start": 20, "end": 42, "text": "powershell -enc base64", "label": "CMD"},
        ]
        mock_inference.load_model.return_value = True
        evaluator.inference_service = mock_inference
        
        mock_session.get.return_value = mock_article
        
        article_annotations = {100: mock_annotations}
        
        metrics = evaluator._compute_eval_metrics(mock_session, article_annotations)
        
        assert metrics["usage"] == "eval"
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1_score" in metrics
        assert "token_overlap_f1" in metrics
        assert metrics["sample_count"] > 0
    
    @patch('src.services.observable_evaluation.evaluator.ObservableModelInference')
    def test_compute_gold_metrics_basic(self, mock_inference_class, evaluator, mock_session, mock_annotations, mock_article):
        """Test basic gold metrics computation."""
        # Setup mocks
        mock_inference = Mock()
        mock_inference.extract.return_value = [
            {"start": 0, "end": 17, "text": "cmd.exe /c whoami", "label": "CMD"},
        ]
        mock_inference.load_model.return_value = True
        evaluator.inference_service = mock_inference
        
        mock_session.get.return_value = mock_article
        
        article_annotations = {100: [mock_annotations[0]]}  # Only first annotation
        
        metrics = evaluator._compute_gold_metrics(mock_session, article_annotations)
        
        assert metrics["usage"] == "gold"
        assert "exact_match_rate" in metrics
        assert "zero_fp_pass_rate" in metrics
        assert "over_extraction_rate" in metrics
        assert "under_extraction_rate" in metrics
        assert "hallucination_rate" in metrics
        assert metrics["sample_count"] > 0
    
    def test_invalid_usage(self, evaluator, mock_session):
        """Test that invalid usage raises ValueError."""
        with pytest.raises(ValueError, match="Invalid usage"):
            evaluator.evaluate(mock_session, "invalid", None)


