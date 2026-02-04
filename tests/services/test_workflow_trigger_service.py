"""Tests for workflow trigger service functionality."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.database.models import AgenticWorkflowConfigTable, AgenticWorkflowExecutionTable, ArticleTable
from src.services.workflow_trigger_service import WorkflowTriggerService

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestWorkflowTriggerService:
    """Test WorkflowTriggerService functionality."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = Mock()
        session.query = Mock()
        session.add = Mock()
        session.commit = Mock()
        session.refresh = Mock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create WorkflowTriggerService instance."""
        return WorkflowTriggerService(mock_db_session)

    @pytest.fixture
    def sample_article(self):
        """Create sample article with high hunt score."""
        article = Mock(spec=ArticleTable)
        article.id = 1
        article.title = "High Threat Article"
        article.article_metadata = {"threat_hunting_score": 95.0}
        return article

    @pytest.fixture
    def sample_config(self):
        """Create sample workflow config."""
        config = Mock(spec=AgenticWorkflowConfigTable)
        config.id = 1
        config.version = 1
        config.is_active = True
        config.min_hunt_score = 97.0
        config.ranking_threshold = 6.0
        config.similarity_threshold = 0.5
        config.junk_filter_threshold = 0.8
        config.auto_trigger_hunt_score_threshold = 60.0
        config.agent_models = {}
        config.qa_enabled = {}
        config.rank_agent_enabled = True
        return config

    def test_get_active_config_exists(self, service, mock_db_session, sample_config):
        """Test getting existing active config."""
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.first.return_value = sample_config
        mock_db_session.query.return_value = mock_query

        config = service.get_active_config()

        assert config == sample_config

    def test_get_active_config_create_default(self, service, mock_db_session):
        """Test creating default config when none exists."""
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        config = service.get_active_config()

        # Should create default config
        assert config is not None
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_should_trigger_workflow_high_score(self, service, mock_db_session, sample_article, sample_config):
        """Test workflow trigger for article with high hunt score."""
        # Mock config query
        mock_config_query = Mock()
        mock_config_query.filter.return_value.order_by.return_value.first.return_value = sample_config
        mock_db_session.query.return_value = mock_config_query

        # Mock execution query (no existing execution)
        mock_exec_query = Mock()
        mock_exec_query.filter.return_value.first.return_value = None

        def query_side_effect(model):
            if model == AgenticWorkflowConfigTable:
                return mock_config_query
            if model == AgenticWorkflowExecutionTable:
                return mock_exec_query
            return Mock()

        mock_db_session.query.side_effect = query_side_effect

        should_trigger = service.should_trigger_workflow(sample_article)

        assert should_trigger is True

    def test_should_trigger_workflow_low_score(self, service, mock_db_session, sample_article, sample_config):
        """Test workflow trigger for article with low hunt score."""
        sample_article.article_metadata = {"threat_hunting_score": 50.0}

        mock_config_query = Mock()
        mock_config_query.filter.return_value.order_by.return_value.first.return_value = sample_config
        mock_db_session.query.return_value = mock_config_query

        should_trigger = service.should_trigger_workflow(sample_article)

        assert should_trigger is False

    def test_should_trigger_workflow_existing_execution(self, service, mock_db_session, sample_article, sample_config):
        """Test workflow trigger when execution already exists."""
        existing_execution = Mock(spec=AgenticWorkflowExecutionTable)
        existing_execution.id = 1
        existing_execution.status = "running"
        existing_execution.created_at = datetime.now()
        existing_execution.started_at = datetime.now()

        mock_config_query = Mock()
        mock_config_query.filter.return_value.order_by.return_value.first.return_value = sample_config

        mock_exec_query = Mock()
        mock_exec_query.filter.return_value.first.return_value = existing_execution

        def query_side_effect(model):
            if model == AgenticWorkflowConfigTable:
                return mock_config_query
            if model == AgenticWorkflowExecutionTable:
                return mock_exec_query
            return Mock()

        mock_db_session.query.side_effect = query_side_effect

        should_trigger = service.should_trigger_workflow(sample_article)

        assert should_trigger is False

    def test_should_trigger_workflow_stuck_execution(self, service, mock_db_session, sample_article, sample_config):
        """Test workflow trigger with stuck pending execution."""
        stuck_execution = Mock(spec=AgenticWorkflowExecutionTable)
        stuck_execution.id = 1
        stuck_execution.status = "pending"
        stuck_execution.created_at = datetime.now() - timedelta(minutes=10)
        stuck_execution.started_at = None
        stuck_execution.error_message = None

        mock_config_query = Mock()
        mock_config_query.filter.return_value.order_by.return_value.first.return_value = sample_config

        mock_exec_query = Mock()
        mock_exec_query.filter.return_value.first.return_value = stuck_execution

        def query_side_effect(model):
            if model == AgenticWorkflowConfigTable:
                return mock_config_query
            if model == AgenticWorkflowExecutionTable:
                return mock_exec_query
            return Mock()

        mock_db_session.query.side_effect = query_side_effect

        should_trigger = service.should_trigger_workflow(sample_article)

        # Should mark stuck execution as failed and allow new trigger
        assert stuck_execution.status == "failed"
        assert should_trigger is True

    def test_trigger_workflow_success(self, service, mock_db_session, sample_article, sample_config):
        """Test successful workflow triggering."""
        # Mock article query
        mock_article_query = Mock()
        mock_article_query.filter.return_value.first.return_value = sample_article

        # Mock config query
        mock_config_query = Mock()
        mock_config_query.filter.return_value.order_by.return_value.first.return_value = sample_config

        # Mock execution query (no existing)
        mock_exec_query = Mock()
        mock_exec_query.filter.return_value.first.return_value = None

        def query_side_effect(model):
            if model == ArticleTable:
                return mock_article_query
            if model == AgenticWorkflowConfigTable:
                return mock_config_query
            if model == AgenticWorkflowExecutionTable:
                return mock_exec_query
            return Mock()

        mock_db_session.query.side_effect = query_side_effect

        with patch("src.services.workflow_trigger_service.trigger_agentic_workflow") as mock_trigger:
            mock_trigger.delay = Mock()

            result = service.trigger_workflow(article_id=1)

            assert result is True
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called()
            mock_trigger.delay.assert_called_once_with(1)

    def test_trigger_workflow_article_not_found(self, service, mock_db_session):
        """Test workflow trigger when article doesn't exist."""
        mock_article_query = Mock()
        mock_article_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_article_query

        result = service.trigger_workflow(article_id=999)

        assert result is False

    def test_trigger_workflow_should_not_trigger(self, service, mock_db_session, sample_article, sample_config):
        """Test workflow trigger when should_trigger returns False."""
        sample_article.article_metadata = {"threat_hunting_score": 50.0}

        mock_article_query = Mock()
        mock_article_query.filter.return_value.first.return_value = sample_article

        mock_config_query = Mock()
        mock_config_query.filter.return_value.order_by.return_value.first.return_value = sample_config

        mock_exec_query = Mock()
        mock_exec_query.filter.return_value.first.return_value = None

        def query_side_effect(model):
            if model == ArticleTable:
                return mock_article_query
            if model == AgenticWorkflowConfigTable:
                return mock_config_query
            if model == AgenticWorkflowExecutionTable:
                return mock_exec_query
            return Mock()

        mock_db_session.query.side_effect = query_side_effect

        result = service.trigger_workflow(article_id=1)

        assert result is False

    def test_get_active_config_error_handling(self, service, mock_db_session):
        """Test error handling in get_active_config."""
        mock_db_session.query.side_effect = Exception("Database error")

        config = service.get_active_config()

        assert config is None

    def test_should_trigger_workflow_no_config(self, service, mock_db_session, sample_article):
        """Test should_trigger when no config exists."""
        mock_config_query = Mock()
        mock_config_query.filter.return_value.order_by.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_config_query

        should_trigger = service.should_trigger_workflow(sample_article)

        assert should_trigger is False

    def test_should_trigger_workflow_no_metadata(self, service, mock_db_session, sample_article, sample_config):
        """Test should_trigger when article has no metadata."""
        sample_article.article_metadata = None

        mock_config_query = Mock()
        mock_config_query.filter.return_value.order_by.return_value.first.return_value = sample_config

        mock_exec_query = Mock()
        mock_exec_query.filter.return_value.first.return_value = None

        def query_side_effect(model):
            if model == AgenticWorkflowConfigTable:
                return mock_config_query
            if model == AgenticWorkflowExecutionTable:
                return mock_exec_query
            return Mock()

        mock_db_session.query.side_effect = query_side_effect

        should_trigger = service.should_trigger_workflow(sample_article)

        assert should_trigger is False
