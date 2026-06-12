"""
Unit tests verifying that generate_sigma_node emits a sigma_repair_attempts
Langfuse score after sigma generation completes.

Uses the same run_workflow harness pattern as test_sigma_min_confidence_threshold.py,
patching score_langfuse_trace and get_active_trace_id at the agentic_workflow
module level so no real Langfuse client is needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_mock_article(content: str = "ransomware intrusion technique") -> Mock:
    article = Mock()
    article.id = 1
    article.title = "Threat Report"
    article.content = content
    article.canonical_url = "https://example.com/1"
    article.article_metadata = {}
    article.source = Mock()
    article.source.name = "ThreatFeed"
    return article


def _make_mock_config(junk_filter_threshold: float = 0.8) -> Mock:
    cfg = Mock()
    cfg.id = 1
    cfg.junk_filter_threshold = junk_filter_threshold
    cfg.min_hunt_score = 97.0
    cfg.ranking_threshold = 6.0
    cfg.similarity_threshold = 0.5
    cfg.sigma_fallback_enabled = True
    cfg.rank_agent_enabled = True
    cfg.cmdline_attention_preprocessor_enabled = True
    cfg.agent_models = {}
    cfg.agent_prompts = {}
    return cfg


def _make_mock_execution(config: Mock) -> Mock:
    execution = Mock()
    execution._sa_instance_state = Mock()
    execution.id = 100
    execution.article_id = 1
    execution.status = "pending"
    execution.started_at = None
    execution.completed_at = None
    execution.current_step = None
    execution.error_log = {}
    execution.extraction_result = None
    execution.config_snapshot = {
        "skip_rank_agent": True,
        "skip_os_detection": True,
        "agent_prompts": {},
        "agent_models": {},
        "cmdline_attention_preprocessor_enabled": True,
    }
    return execution


def _make_mock_db_session(article: Mock, execution: Mock) -> Mock:
    from src.database.models import AgenticWorkflowExecutionTable, ArticleTable

    session = Mock()
    session.commit = Mock()
    session.refresh = Mock()
    session.add = Mock()

    def query_side_effect(model):
        q = Mock()
        if model is ArticleTable:
            q.filter.return_value.first.return_value = article
        elif model is AgenticWorkflowExecutionTable:
            chain = q.filter.return_value
            chain.first.return_value = execution
            chain.order_by.return_value.first.return_value = execution
        else:
            q.filter.return_value.order_by.return_value.first.return_value = None
        return q

    session.query.side_effect = query_side_effect
    return session


def _run_workflow_with_sigma_result(generation_result: dict, active_trace_id: str | None = "trace-test-777"):
    """Run run_workflow with all heavy nodes mocked, returning what score_langfuse_trace captured."""
    from src.workflows.agentic_workflow import run_workflow

    article = _make_mock_article()
    config = _make_mock_config()
    execution = _make_mock_execution(config)
    db_session = _make_mock_db_session(article, execution)

    filter_result = Mock()
    filter_result.filtered_content = article.content
    filter_result.removed_chunks = []
    filter_result.is_huntable = True
    filter_result.confidence = 0.9

    mock_sigma_service = Mock()
    mock_sigma_service.generate_sigma_rules = AsyncMock(return_value=generation_result)

    score_calls = []

    import asyncio

    with (
        patch("src.workflows.agentic_workflow.ContentFilter") as mock_cf_cls,
        patch("src.workflows.agentic_workflow.WorkflowTriggerService") as mock_trigger_cls,
        patch("src.workflows.agentic_workflow.LLMService") as mock_llm_cls,
        patch("src.workflows.agentic_workflow.auto_load_workflow_models"),
        patch("src.workflows.agentic_workflow.trace_workflow_execution") as mock_trace,
        patch("src.workflows.agentic_workflow.flag_modified"),
        patch(
            "src.services.sigma_generation_service.SigmaGenerationService",
            return_value=mock_sigma_service,
        ),
        patch("src.workflows.agentic_workflow.get_active_trace_id", return_value=active_trace_id),
        patch(
            "src.workflows.agentic_workflow.score_langfuse_trace", side_effect=lambda **kw: score_calls.append(kw)
        ) as mock_score,
    ):
        mock_cf_cls.return_value.filter_content.return_value = filter_result

        mock_trigger = Mock()
        mock_trigger.get_active_config.return_value = config
        mock_trigger_cls.return_value = mock_trigger

        mock_llm = Mock()
        mock_llm.run_extraction_agent = AsyncMock(return_value={"items": [], "count": 0, "cmdline_items": []})
        mock_llm.check_model_context_length = AsyncMock(
            return_value={"context_length": 8000, "is_sufficient": True, "threshold": 4096}
        )
        mock_llm_cls.return_value = mock_llm

        mock_trace.return_value.__enter__ = Mock(return_value=None)
        mock_trace.return_value.__exit__ = Mock(return_value=False)

        asyncio.get_event_loop().run_until_complete(run_workflow(article_id=1, db_session=db_session, execution_id=100))

    return score_calls, mock_score


class TestSigmaRepairScoreEmitted:
    """generate_sigma_node emits score_langfuse_trace with sigma_repair_attempts."""

    def test_score_emitted_with_total_attempts(self):
        """When sigma generation returns total_attempts=3 and a trace is active, the score is emitted."""
        generation_result = {
            "rules": [{"title": "Test Rule", "yaml": "title: Test"}],
            "errors": None,
            "metadata": {"total_attempts": 3, "valid_rules": 1, "validation_results": [], "conversation_log": []},
        }

        score_calls, _ = _run_workflow_with_sigma_result(generation_result, active_trace_id="trace-test-777")

        assert len(score_calls) == 1
        call = score_calls[0]
        assert call["trace_id"] == "trace-test-777"
        assert call["name"] == "sigma_repair_attempts"
        assert call["value"] == 3.0

    def test_score_not_emitted_when_no_active_trace(self):
        """When get_active_trace_id returns None, score_langfuse_trace is not called."""
        generation_result = {
            "rules": [{"title": "Test Rule", "yaml": "title: Test"}],
            "errors": None,
            "metadata": {"total_attempts": 2, "valid_rules": 1, "validation_results": [], "conversation_log": []},
        }

        score_calls, _ = _run_workflow_with_sigma_result(generation_result, active_trace_id=None)

        assert score_calls == []

    def test_score_not_emitted_when_metadata_missing_total_attempts(self):
        """When metadata has no total_attempts key, no score is emitted."""
        generation_result = {
            "rules": [{"title": "Test Rule", "yaml": "title: Test"}],
            "errors": None,
            "metadata": {},
        }

        score_calls, _ = _run_workflow_with_sigma_result(generation_result, active_trace_id="trace-xyz")

        assert score_calls == []
