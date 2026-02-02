"""Tests for evaluation runner functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4
from typing import Dict, Any

from src.services.evaluation.eval_runner import EvalRunner
from src.database.models import EvalRunTable, EvalPresetSnapshotTable
from src.services.llm_service import PreprocessInvariantError

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestEvalRunner:
    """Test EvalRunner functionality."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = Mock()
        session.query = Mock()
        return session

    @pytest.fixture
    def runner(self, mock_db_session):
        """Create EvalRunner instance."""
        return EvalRunner(mock_db_session)

    @pytest.fixture
    def sample_eval_run(self):
        """Create sample eval run."""
        run = Mock(spec=EvalRunTable)
        run.id = uuid4()
        run.status = 'pending'
        run.total_items = 0
        run.started_at = None
        return run

    @pytest.fixture
    def sample_snapshot(self):
        """Create sample snapshot."""
        snapshot = Mock(spec=EvalPresetSnapshotTable)
        snapshot.id = uuid4()
        snapshot.snapshot_data = {
            'agent_models': {},
            'agent_prompts': {}
        }
        return snapshot

    def test_run_evaluation_success(self, runner, mock_db_session, sample_eval_run, sample_snapshot):
        """Test successful evaluation run."""
        mock_eval_query = Mock()
        mock_eval_query.filter.return_value.first.return_value = sample_eval_run
        
        mock_snapshot_query = Mock()
        mock_snapshot_query.filter.return_value.first.return_value = sample_snapshot
        
        def query_side_effect(model):
            if model == EvalRunTable:
                return mock_eval_query
            elif model == EvalPresetSnapshotTable:
                return mock_snapshot_query
            return Mock()
        
        mock_db_session.query.side_effect = query_side_effect
        
        with patch('src.services.evaluation.eval_runner.get_langfuse_client') as mock_langfuse:
            mock_client = Mock()
            mock_dataset = Mock()
            mock_dataset.items = []
            mock_client.get_dataset.return_value = mock_dataset
            mock_langfuse.return_value = mock_client
            
            result = runner.run_evaluation(
                eval_run_id=sample_eval_run.id,
                snapshot_id=sample_snapshot.id,
                dataset_name="test-dataset"
            )
            
            assert result is not None

    def test_run_evaluation_eval_run_not_found(self, runner, mock_db_session):
        """Test evaluation run when eval run not found."""
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query
        
        with pytest.raises(ValueError, match="Eval run.*not found"):
            runner.run_evaluation(
                eval_run_id=uuid4(),
                snapshot_id=uuid4(),
                dataset_name="test-dataset"
            )

    def test_run_evaluation_snapshot_not_found(self, runner, mock_db_session, sample_eval_run):
        """Test evaluation run when snapshot not found."""
        mock_eval_query = Mock()
        mock_eval_query.filter.return_value.first.return_value = sample_eval_run
        
        mock_snapshot_query = Mock()
        mock_snapshot_query.filter.return_value.first.return_value = None
        
        def query_side_effect(model):
            if model == EvalRunTable:
                return mock_eval_query
            elif model == EvalPresetSnapshotTable:
                return mock_snapshot_query
            return Mock()
        
        mock_db_session.query.side_effect = query_side_effect
        
        with pytest.raises(ValueError, match="Snapshot.*not found"):
            runner.run_evaluation(
                eval_run_id=sample_eval_run.id,
                snapshot_id=uuid4(),
                dataset_name="test-dataset"
            )

    def test_preprocess_invariant_error_classified_as_infra_failed(self, runner, mock_db_session):
        """When PreprocessInvariantError is raised, run is classified as infra_failed, not model failure."""
        debug_artifacts = {
            "agent_name": "CmdlineExtract",
            "content_sha256": "abc123",
            "attention_preprocessor_enabled": True,
        }
        preprocess_error = PreprocessInvariantError(
            "user message content length (0) below minimum (500)",
            debug_artifacts=debug_artifacts,
        )

        sample_eval_run = Mock(spec=EvalRunTable)
        sample_eval_run.id = uuid4()
        sample_eval_run.status = "running"
        sample_eval_run.total_items = 1
        sample_eval_run.completed_items = 0
        sample_eval_run.started_at = None
        sample_eval_run.completed_at = None

        sample_snapshot = Mock(spec=EvalPresetSnapshotTable)
        sample_snapshot.id = uuid4()
        sample_snapshot.snapshot_data = {
            "agent_models": {"CmdlineExtract_provider": "openai", "CmdlineExtract_model": "gpt-4o"},
            "agent_prompts": {
                "CmdlineExtract": {
                    "prompt": "{}",
                    "instructions": "Extract commands.",
                    "model": "gpt-4o",
                }
            },
            "qa_enabled": {},
        }

        mock_dataset_item = Mock()
        mock_dataset_item.id = "article_200"
        mock_dataset_item.input = {
            "article_text": "x" * 1000,
            "article_title": "Test",
            "article_url": "https://example.com",
        }
        mock_dataset_item.expected_output = {"expected_count": 2}

        mock_dataset = Mock()
        mock_dataset.items = [mock_dataset_item]

        def query_side_effect(model):
            if model == EvalRunTable:
                q = Mock()
                q.filter.return_value.first.return_value = sample_eval_run
                return q
            if model == EvalPresetSnapshotTable:
                q = Mock()
                q.filter.return_value.first.return_value = sample_snapshot
                return q
            return Mock()

        mock_db_session.query.side_effect = query_side_effect
        mock_db_session.commit = Mock()

        mock_trace = MagicMock()

        with patch("src.services.evaluation.eval_runner.get_langfuse_client") as mock_langfuse:
            mock_client = Mock()
            mock_client.get_dataset.return_value = mock_dataset
            mock_langfuse.return_value = mock_client

            with patch.object(
                runner, "_run_extraction", side_effect=preprocess_error
            ):
                with patch.object(
                    runner.langfuse_client, "log_trace_scores"
                ) as mock_log_scores:
                    with patch.object(
                        runner.langfuse_client, "create_trace", return_value=mock_trace
                    ):
                        with patch.object(
                            runner.langfuse_client,
                            "create_experiment",
                            return_value={"id": "exp-1", "name": "test-exp"},
                        ):
                            runner.run_evaluation(
                                eval_run_id=sample_eval_run.id,
                                snapshot_id=sample_snapshot.id,
                                dataset_name="test-dataset",
                            )

                    mock_log_scores.assert_called()
                    call_kwargs = mock_log_scores.call_args[1]
                    assert call_kwargs.get("infra_failed") is True
                    assert call_kwargs.get("execution_error") is False
                    assert "infra_debug_artifacts" in call_kwargs
                    assert call_kwargs["infra_debug_artifacts"] == debug_artifacts
