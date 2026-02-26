"""Tests for agentic workflow PreprocessInvariantError handling."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.database.models import AgenticWorkflowConfigTable, AgenticWorkflowExecutionTable, ArticleTable
from src.services.llm_service import PreprocessInvariantError
from src.workflows.agentic_workflow import run_workflow

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_article():
    """Mock article with content."""
    article = Mock(spec=ArticleTable)
    article.id = 1
    article.title = "Test Article"
    article.content = "x" * 600 + "\nContent:\nThe attacker ran powershell -enc."
    article.canonical_url = "https://example.com/1"
    article.article_metadata = {}
    return article


@pytest.fixture
def mock_config():
    """Mock workflow config with CmdlineExtract prompt."""
    config = Mock(spec=AgenticWorkflowConfigTable)
    config.id = 1
    config.version = 1
    config.agent_models = {"CmdlineExtract_model": "gpt-4", "CmdlineExtract_provider": "openai"}
    config.agent_prompts = {
        "CmdlineExtract": {
            "prompt": json.dumps(
                {
                    "role": "You are an extractor.",
                    "user_template": (
                        "Title: {title}\nURL: {url}\nContent:\n{content}\nTask: Extract\n"
                        "JSON: {}\nInstructions: Output JSON"
                    ),
                    "task": "Extract",
                    "instructions": "Output JSON",
                    "json_example": "{}",
                }
            ),
            "instructions": "Output JSON",
        }
    }
    config.qa_enabled = {}
    config.qa_max_retries = 5
    return config


@pytest.fixture
def mock_execution(mock_config):
    """Mock execution with config snapshot that skips rank and sigma."""
    execution = Mock(spec=AgenticWorkflowExecutionTable)
    execution._sa_instance_state = Mock()  # SQLAlchemy internal, avoid attribute errors
    execution.error_log = {}  # Must be dict for subscript access
    execution.id = 100
    execution.article_id = 1
    execution.status = "pending"
    execution.config_snapshot = {
        "skip_rank_agent": True,
        "eval_run": True,
        "skip_os_detection": True,
        "subagent_eval": "cmdline",  # Required for infra failure to set result["success"]=False
        "agent_prompts": mock_config.agent_prompts,
        "agent_models": mock_config.agent_models,
        "qa_enabled": {},
        "cmdline_attention_preprocessor_enabled": True,
    }
    execution.started_at = None
    execution.current_step = None
    execution.error_log = None
    execution.extraction_result = None
    return execution


@pytest.fixture
def mock_db_session(mock_article, mock_execution):
    """Mock DB session returning article and execution."""
    session = Mock()
    session.commit = Mock()
    session.refresh = Mock()
    session.add = Mock()

    def query_side_effect(model):
        q = Mock()
        if model == ArticleTable:
            q.filter.return_value.first.return_value = mock_article
        elif model == AgenticWorkflowExecutionTable:
            chain = q.filter.return_value
            chain.first.return_value = mock_execution
            chain.order_by.return_value.first.return_value = mock_execution
        else:
            q.filter.return_value.order_by.return_value.first.return_value = None
        return q

    session.query.side_effect = query_side_effect
    return session


@pytest.mark.asyncio
async def test_preprocess_invariant_error_stores_infra_failed_in_subresults(
    mock_db_session, mock_article, mock_execution, mock_config
):
    """When CmdlineExtract raises PreprocessInvariantError, subresults[cmdline] has infra_failed."""
    preprocess_error = PreprocessInvariantError(
        "newline count mismatch",
        debug_artifacts={"agent_name": "CmdlineExtract", "orig_newline_count": 2},
    )

    async def raise_for_cmdline(*args, **kwargs):
        if kwargs.get("agent_name") == "CmdlineExtract":
            raise preprocess_error
        return {"items": [], "count": 0, "cmdline_items": []}

    filter_result = Mock()
    filter_result.filtered_content = mock_article.content
    filter_result.removed_chunks = []
    filter_result.is_huntable = True
    filter_result.confidence = 0.9

    with (
        patch("src.workflows.agentic_workflow.ContentFilter") as mock_cf_cls,
        patch("src.workflows.agentic_workflow.WorkflowTriggerService") as mock_trigger_cls,
        patch("sqlalchemy.orm.attributes.flag_modified"),  # Avoid SQLAlchemy inspect on Mock
    ):
        mock_cf_cls.return_value.filter_content.return_value = filter_result
        mock_trigger = Mock()
        mock_trigger.get_active_config.return_value = mock_config
        mock_trigger_cls.return_value = mock_trigger

        with patch("src.workflows.agentic_workflow.auto_load_workflow_models") as mock_load:
            mock_load.return_value = {"models_loaded": [], "models_failed": [], "lmstudio_cli_available": False}

        with patch("src.workflows.agentic_workflow.trace_workflow_execution") as mock_trace:
            mock_trace.return_value.__enter__ = Mock(return_value=None)
            mock_trace.return_value.__exit__ = Mock(return_value=False)

        with patch("src.workflows.agentic_workflow.LLMService") as mock_llm_cls:
            mock_llm = Mock()
            mock_llm.run_extraction_agent = AsyncMock(side_effect=raise_for_cmdline)
            mock_llm.check_model_context_length = AsyncMock(
                return_value={"context_length": 8000, "is_sufficient": True, "threshold": 4096}
            )
            mock_llm_cls.return_value = mock_llm

            result = await run_workflow(article_id=1, db_session=mock_db_session, execution_id=100)

    assert result is not None
    assert result["success"] is False
    # extraction_result is stored on execution, not in return dict
    extraction_result = mock_execution.extraction_result
    assert extraction_result is not None
    subresults = extraction_result.get("subresults", {})
    cmdline_result = subresults.get("cmdline")
    assert cmdline_result is not None
    raw = cmdline_result.get("raw", {})
    assert raw.get("infra_failed") is True
    assert "infra_debug_artifacts" in raw
    assert raw["infra_debug_artifacts"].get("agent_name") == "CmdlineExtract"
    assert extraction_result.get("infra_failed") is True
    assert mock_execution.status == "failed"
    assert "Eval infra failure" in (mock_execution.error_message or "")
