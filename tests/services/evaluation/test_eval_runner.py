"""Tests for evaluation runner functionality."""

import pytest
from unittest.mock import Mock, patch
from uuid import uuid4
from typing import Dict, Any

from src.services.evaluation.eval_runner import EvalRunner
from src.database.models import EvalRunTable, EvalPresetSnapshotTable

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
