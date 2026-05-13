"""Tests covering eval bundle gaps identified in post-refactor audit.

Gap 1: Eval bundle fixtures for ProcTreeExtract, ServicesExtract, ScheduledTasksExtract
        (CmdlineExtract-only coverage existed prior to this file)
"""

from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Gap 1: Eval bundle fixtures for structured extractors
# Verify that EvalBundleService.generate_bundle produces valid bundles for
# ProcTreeExtract, ServicesExtract, and ScheduledTasksExtract (not just CmdlineExtract).
# ---------------------------------------------------------------------------


def _make_mock_execution(agent_name, items_key, items):
    """Build a mock execution with a conversation_log for the given agent."""
    execution = Mock()
    execution.id = 1
    execution.article_id = 1
    execution.status = "completed"
    execution.error_log = {
        "extract_agent": {
            "conversation_log": [
                {
                    "agent": agent_name,
                    "messages": [
                        {"role": "system", "content": "You are an extractor."},
                        {"role": "user", "content": "Content:\n" + "x" * 600},
                    ],
                    "result": {items_key: items, "count": len(items)},
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
    return execution


def _make_mock_article():
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
    return article


def _mock_query_factory(execution, article):
    from src.database.models import AgenticWorkflowExecutionTable, ArticleTable

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

    return mock_query


class TestEvalBundleStructuredExtractors:
    """Eval bundle generation works for the 3 structured extractors, not just CmdlineExtract."""

    @pytest.mark.parametrize(
        ("agent_name", "items_key", "sample_item"),
        [
            ("ProcTreeExtract", "items", {"parent": "cmd.exe", "child": "evil.exe"}),
            ("ServicesExtract", "items", {"service_name": "EvilSvc", "binary_path": "C:\\evil.exe"}),
            ("ScheduledTasksExtract", "items", {"task_name": "EvilTask", "task_path": "\\EvilTask"}),
        ],
    )
    def test_generate_bundle_for_structured_extractor(self, agent_name, items_key, sample_item):
        from src.services.eval_bundle_service import EvalBundleService

        execution = _make_mock_execution(agent_name, items_key, [sample_item])
        article = _make_mock_article()
        db_session = Mock()
        db_session.query = _mock_query_factory(execution, article)

        with patch("src.services.eval_bundle_service.is_langfuse_enabled", return_value=False):
            service = EvalBundleService(db_session)
            bundle = service.generate_bundle(execution_id=1, agent_name=agent_name)

        assert bundle is not None
        # Bundle should have core structure (execution_context, llm_call, integrity)
        assert "execution_context" in bundle
        assert "integrity" in bundle
        assert bundle.get("infra_failed") is not True


