"""Tests for EvalBundleService."""

from unittest.mock import Mock, patch

import pytest

from src.database.models import AgenticWorkflowExecutionTable, ArticleTable, SubagentEvaluationTable
from src.services.eval_bundle_service import EvalBundleService

pytestmark = pytest.mark.unit


class TestEvalBundleIllegalState:
    """Test illegal state detection: messages==[] AND status==completed."""

    def test_empty_messages_completed_status_sets_infra_failed(self):
        """Bundle with messages=[] and status=completed must have infra_failed=True."""
        db_session = Mock()

        # Mock execution with completed status and empty messages in conversation_log
        execution = Mock()
        execution.id = 1
        execution.article_id = 1
        execution.status = "completed"
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [],  # Empty — illegal when completed
                        "result": {"cmdline_items": [], "count": 0},
                    }
                ]
            }
        }
        execution.config_snapshot = {}
        execution.started_at = None
        execution.completed_at = None
        execution.current_step = None
        execution.retry_count = 0
        execution.error_message = None
        execution.extraction_result = {}

        subagent_eval = Mock()
        subagent_eval.expected_count = 4
        subagent_eval.actual_count = 0
        subagent_eval.score = -4
        subagent_eval.status = "completed"

        # Mock article
        article = Mock()
        article.content = "Test article content"
        article.id = 1
        article.title = "Test"
        article.canonical_url = None
        article.published_at = None
        article.word_count = 100
        article.discovered_at = None
        article.article_metadata = {}
        article.source = None

        def mock_query(model):
            q = Mock()
            f = Mock()
            if model == AgenticWorkflowExecutionTable:
                f.first.return_value = execution
            elif model == ArticleTable:
                f.first.return_value = article
            elif model == SubagentEvaluationTable:
                f.first.return_value = subagent_eval
            else:
                f.first.return_value = None
            q.filter.return_value = f
            return q

        db_session.query = mock_query

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract")

        assert "ILLEGAL_STATE_MESSAGES_EMPTY_BUT_COMPLETED" in bundle["integrity"]["warnings"]
        assert bundle.get("infra_failed") is True
        assert bundle["execution_context"]["infra_failed"] is True
        assert bundle["execution_context"]["infra_failed_reason"] == "messages empty but execution marked completed"
        assert "EVAL_SCORE_SUPPRESSED_DUE_TO_INFRA_FAILURE" in bundle["integrity"]["warnings"]
        assert "evaluation_score" not in bundle["workflow"]
        assert bundle["workflow"].get("evaluation_status") == "failed"

    def test_valid_messages_completed_status_does_not_set_infra_failed(self):
        """Bundle with valid messages and status=completed must NOT have infra_failed (negative case)."""
        db_session = Mock()

        execution = Mock()
        execution.id = 1
        execution.article_id = 1
        execution.status = "completed"
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [
                            {"role": "system", "content": "You are an extractor."},
                            {"role": "user", "content": "Content:\n" + "x" * 600},
                        ],
                        "result": {"cmdline_items": ["cmd1"], "count": 1},
                    }
                ]
            }
        }
        execution.config_snapshot = {}
        execution.started_at = None
        execution.completed_at = None
        execution.current_step = None
        execution.retry_count = 0
        execution.error_message = None
        execution.extraction_result = {}

        article = Mock()
        article.content = "Test article content"
        article.id = 1
        article.title = "Test"
        article.canonical_url = None
        article.published_at = None
        article.word_count = 100
        article.discovered_at = None
        article.article_metadata = {}
        article.source = None

        def mock_query(model):
            q = Mock()
            f = Mock()
            if model == AgenticWorkflowExecutionTable:
                f.first.return_value = execution
            elif model == ArticleTable:
                f.first.return_value = article
            else:
                f.first.return_value = None
            q.filter.return_value = f
            return q

        db_session.query = mock_query

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract")

        assert "ILLEGAL_STATE_MESSAGES_EMPTY_BUT_COMPLETED" not in bundle["integrity"]["warnings"]
        assert bundle.get("infra_failed") is not True
        assert bundle["execution_context"].get("infra_failed") is not True

    def test_empty_messages_failed_status_does_not_set_infra_failed(self):
        """Bundle with messages=[] but status!=completed must NOT set infra_failed."""
        db_session = Mock()

        execution = Mock()
        execution.id = 1
        execution.article_id = 1
        execution.status = "failed"
        execution.error_log = {
            "extract_agent": {
                "conversation_log": [
                    {
                        "agent": "CmdlineExtract",
                        "messages": [],
                        "result": {"error": "Something failed"},
                    }
                ]
            }
        }
        execution.config_snapshot = {}
        execution.started_at = None
        execution.completed_at = None
        execution.current_step = None
        execution.retry_count = 0
        execution.error_message = "Failed"
        execution.extraction_result = {}

        article = Mock()
        article.content = "Test article content"
        article.id = 1
        article.title = "Test"
        article.canonical_url = None
        article.published_at = None
        article.word_count = 100
        article.discovered_at = None
        article.article_metadata = {}
        article.source = None

        def mock_query(model):
            q = Mock()
            f = Mock()
            if model == AgenticWorkflowExecutionTable:
                f.first.return_value = execution
            elif model == ArticleTable:
                f.first.return_value = article
            else:
                f.first.return_value = None
            q.filter.return_value = f
            return q

        db_session.query = mock_query

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name="CmdlineExtract")

        assert "ILLEGAL_STATE_MESSAGES_EMPTY_BUT_COMPLETED" not in bundle["integrity"]["warnings"]
        assert bundle.get("infra_failed") is not True
        assert bundle["execution_context"].get("infra_failed") is not True
