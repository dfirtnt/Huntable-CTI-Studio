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
    assert cmdline_result.get("error_type") == "PreprocessInvariantError"
    assert "error_details" in cmdline_result
    assert cmdline_result["error_details"].get("exception_type") == "PreprocessInvariantError"
    assert cmdline_result["error_details"].get("agent_name") == "CmdlineExtract"


@pytest.mark.asyncio
async def test_extraction_result_subresult_promotes_error_to_top_level(
    mock_db_session, mock_article, mock_execution, mock_config
):
    """When run_extraction_agent returns result with error/error_details/error_type, subresult has them at top level."""
    agent_result_with_error = {
        "items": [],
        "count": 0,
        "cmdline_items": [],
        "error": "API error: temperature not supported",
        "error_type": "HTTPStatusError",
        "error_details": {
            "message": "API error: temperature not supported",
            "exception_type": "HTTPStatusError",
            "attempt": 1,
            "agent_name": "CmdlineExtract",
        },
    }

    async def return_error_for_cmdline(*args, **kwargs):
        if kwargs.get("agent_name") == "CmdlineExtract":
            return agent_result_with_error
        return {"items": [], "count": 0, "cmdline_items": []}

    filter_result = Mock()
    filter_result.filtered_content = mock_article.content
    filter_result.removed_chunks = []
    filter_result.is_huntable = True
    filter_result.confidence = 0.9

    with (
        patch("src.workflows.agentic_workflow.ContentFilter") as mock_cf_cls,
        patch("src.workflows.agentic_workflow.WorkflowTriggerService") as mock_trigger_cls,
        patch("sqlalchemy.orm.attributes.flag_modified"),
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
            mock_llm.run_extraction_agent = AsyncMock(side_effect=return_error_for_cmdline)
            mock_llm.check_model_context_length = AsyncMock(
                return_value={"context_length": 8000, "is_sufficient": True, "threshold": 4096}
            )
            mock_llm_cls.return_value = mock_llm

            await run_workflow(article_id=1, db_session=mock_db_session, execution_id=100)

    extraction_result = mock_execution.extraction_result
    assert extraction_result is not None
    subresults = extraction_result.get("subresults", {})
    cmdline_result = subresults.get("cmdline")
    assert cmdline_result is not None
    assert cmdline_result.get("error") == "API error: temperature not supported"
    assert cmdline_result.get("error_type") == "HTTPStatusError"
    assert cmdline_result.get("error_details") == agent_result_with_error["error_details"]
    assert cmdline_result.get("raw") == agent_result_with_error


@pytest.mark.asyncio
async def test_lmstudio_health_gate_aborts_when_unreachable(mock_db_session, mock_article, mock_execution):
    """When LMStudio provider is selected but the server is unreachable, run_workflow returns failure early."""
    lmstudio_config = Mock(spec=AgenticWorkflowConfigTable)
    lmstudio_config.id = 1
    lmstudio_config.version = 1
    lmstudio_config.agent_models = {
        "ExtractAgent_provider": "lmstudio",
        "ExtractAgent": "gemma-3-1b",
    }
    lmstudio_config.agent_prompts = {}
    lmstudio_config.qa_enabled = {}
    lmstudio_config.qa_max_retries = 5
    lmstudio_config.rank_agent_enabled = True
    lmstudio_config.cmdline_attention_preprocessor_enabled = True

    mock_execution.config_snapshot = {
        "skip_rank_agent": True,
        "eval_run": True,
        "skip_os_detection": True,
        "agent_models": lmstudio_config.agent_models,
        "agent_prompts": {},
        "qa_enabled": {},
        "cmdline_attention_preprocessor_enabled": True,
    }

    with (
        patch("src.workflows.agentic_workflow.WorkflowTriggerService") as mock_trigger_cls,
        patch("src.workflows.agentic_workflow._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
    ):
        mock_trigger = Mock()
        mock_trigger.get_active_config.return_value = lmstudio_config
        mock_trigger_cls.return_value = mock_trigger

        result = await run_workflow(article_id=1, db_session=mock_db_session, execution_id=100)

    assert result["success"] is False
    assert "lmstudio" in result["error"].lower() or "reachable" in result["error"].lower()
    assert mock_execution.status == "failed"


@pytest.mark.asyncio
async def test_lmstudio_health_gate_not_called_for_openai_config(
    mock_db_session, mock_article, mock_execution, mock_config
):
    """When all providers are openai, _probe_lmstudio must not be called.

    Guards against the gate accidentally probing non-local providers, which would add
    latency and spurious failures to every OpenAI/Anthropic workflow run.
    """
    # mock_config.agent_models has CmdlineExtract_provider=openai; the gate checks
    # RankAgent_provider / ExtractAgent_provider / SigmaAgent_provider — none are lmstudio.
    with (
        patch("src.workflows.agentic_workflow.WorkflowTriggerService") as mock_trigger_cls,
        patch("src.workflows.agentic_workflow._probe_lmstudio", new=AsyncMock()) as mock_probe,
        patch("src.workflows.agentic_workflow.auto_load_workflow_models"),
        patch("src.workflows.agentic_workflow.trace_workflow_execution"),
        patch("src.workflows.agentic_workflow.LLMService"),
        patch("src.workflows.agentic_workflow.ContentFilter"),
        patch("sqlalchemy.orm.attributes.flag_modified"),
    ):
        mock_trigger = Mock()
        mock_trigger.get_active_config.return_value = mock_config
        mock_trigger_cls.return_value = mock_trigger

        await run_workflow(article_id=1, db_session=mock_db_session, execution_id=100)

    mock_probe.assert_not_awaited()
