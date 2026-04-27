"""Tests for test_sub_agent_task provider/model resolution.

Validates that the Test button's Celery task reads per-agent provider,
model, temperature, and top_p from the saved config and passes them
to run_extraction_agent() — not falling back to ExtractAgent's defaults.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_config(agent_models: dict, agent_prompts: dict | None = None, qa_enabled: dict | None = None):
    """Build a mock config object matching ActiveWorkflowConfig shape."""
    return SimpleNamespace(
        agent_models=agent_models,
        agent_prompts=agent_prompts or {"RegistryExtract": {"prompt": "", "instructions": ""}},
        qa_enabled=qa_enabled or {},
        qa_max_retries=5,
    )


def _make_article(article_id: int = 1916, title: str = "Test Article", url: str = "https://example.com"):
    """Build a mock article."""
    source = SimpleNamespace(name="TestSource")
    return SimpleNamespace(
        id=article_id,
        title=title,
        canonical_url=url,
        content="Test content with registry keys.",
        source=source,
        article_metadata={"threat_hunting_score": 50},
    )


def _run_task(agent_name: str, agent_models: dict, qa_enabled: dict | None = None, agent_prompts: dict | None = None):
    """Execute test_sub_agent_task with mocked dependencies, return the kwargs passed to run_extraction_agent."""
    article = _make_article()
    config = _make_config(agent_models, agent_prompts=agent_prompts, qa_enabled=qa_enabled)

    mock_llm_service = MagicMock()
    mock_run = AsyncMock(return_value={"items": [], "count": 0})
    mock_llm_service.run_extraction_agent = mock_run

    with (
        patch("src.worker.tasks.test_agents._get_db_session", return_value=MagicMock()),
        patch("src.worker.tasks.test_agents._load_article", return_value=article),
        patch("src.worker.tasks.test_agents._get_active_config", return_value=config),
        patch("src.worker.tasks.test_agents._filter_content", return_value="filtered content"),
        patch("src.services.llm_service.LLMService", return_value=mock_llm_service),
    ):
        from src.worker.tasks.test_agents import test_sub_agent_task

        # tests/worker/conftest.py mocks celery with a passthrough `task`
        # decorator ONLY if the real `celery` package hasn't been imported
        # yet. In full-suite runs, earlier tests import real Celery, so
        # `test_sub_agent_task` is a real Task instance. For a real bound
        # Task, `.run` is already a bound method (self auto-injected) and
        # expects `(agent_name, article_id, ...)`. For the mocked passthrough,
        # `test_sub_agent_task` is the raw function needing a manual `self`.
        if hasattr(test_sub_agent_task, "app"):  # real Celery Task instance
            result = test_sub_agent_task.run(agent_name, 1916)
        else:  # passthrough-mocked: raw function with `self` first param
            result = test_sub_agent_task(MagicMock(), agent_name, 1916)

    assert mock_run.call_count == 1
    return mock_run.call_args


# ===========================================================================
# Provider resolution
# ===========================================================================


class TestProviderResolution:
    """Per-agent provider is read from agent_models and passed explicitly."""

    def test_openai_provider_passed_to_extraction(self):
        call = _run_task(
            "RegistryExtract",
            {
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4o",
            },
        )
        assert call.kwargs["provider"] == "openai"

    def test_anthropic_provider_passed(self):
        call = _run_task(
            "CmdlineExtract",
            {
                "CmdlineExtract_provider": "anthropic",
                "CmdlineExtract_model": "claude-sonnet-4-5",
            },
        )
        assert call.kwargs["provider"] == "anthropic"

    def test_lmstudio_provider_passed(self):
        call = _run_task(
            "ProcTreeExtract",
            {
                "ProcTreeExtract_provider": "lmstudio",
                "ProcTreeExtract_model": "qwen3-14b",
            },
        )
        assert call.kwargs["provider"] == "lmstudio"

    def test_missing_provider_passes_empty_or_none(self):
        """When agent_models has no provider key, provider is empty string → treated as None."""
        call = _run_task("RegistryExtract", {"RegistryExtract_model": "gpt-4"})
        # Empty string is passed, which run_extraction_agent treats as None (fallback)
        assert call.kwargs["provider"] == "" or call.kwargs["provider"] is None


# ===========================================================================
# Model resolution
# ===========================================================================


class TestModelResolution:
    """Per-agent model is read from agent_models and passed explicitly."""

    def test_model_name_passed(self):
        call = _run_task(
            "RegistryExtract",
            {
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4o-mini",
            },
        )
        assert call.kwargs["model_name"] == "gpt-4o-mini"

    def test_missing_model_passes_empty_or_none(self):
        call = _run_task("RegistryExtract", {"RegistryExtract_provider": "openai"})
        assert call.kwargs["model_name"] == "" or call.kwargs["model_name"] is None


# ===========================================================================
# Temperature & top_p resolution
# ===========================================================================


class TestTemperatureTopP:
    """Temperature and top_p are resolved and converted to correct types."""

    def test_temperature_passed_as_float(self):
        call = _run_task(
            "RegistryExtract",
            {
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4",
                "RegistryExtract_temperature": 0.5,
            },
        )
        assert call.kwargs["temperature"] == 0.5
        assert isinstance(call.kwargs["temperature"], float)

    def test_temperature_string_converted_to_float(self):
        """Config may store temperature as string from JSON."""
        call = _run_task(
            "RegistryExtract",
            {
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4",
                "RegistryExtract_temperature": "0.7",
            },
        )
        assert call.kwargs["temperature"] == 0.7

    def test_missing_temperature_defaults_to_zero(self):
        call = _run_task(
            "RegistryExtract",
            {
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4",
            },
        )
        assert call.kwargs["temperature"] == 0.0

    def test_top_p_passed_as_float(self):
        call = _run_task(
            "RegistryExtract",
            {
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4",
                "RegistryExtract_top_p": 0.95,
            },
        )
        assert call.kwargs["top_p"] == 0.95
        assert isinstance(call.kwargs["top_p"], float)

    def test_missing_top_p_is_none(self):
        """Missing top_p should be None, not 0.0 — lets the LLM service use its default."""
        call = _run_task(
            "RegistryExtract",
            {
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4",
            },
        )
        assert call.kwargs["top_p"] is None


# ===========================================================================
# QA model override
# ===========================================================================


class TestQAModelOverride:
    """QA model override is resolved from BASE_AGENT_TO_QA mapping."""

    def test_qa_model_override_from_config(self):
        call = _run_task(
            "RegistryExtract",
            agent_models={
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4",
                "RegistryQA": "gpt-4o-mini",
            },
            qa_enabled={"RegistryExtract": True},
            agent_prompts={
                "RegistryExtract": {"prompt": "", "instructions": ""},
                "RegistryExtract_QA": {"prompt": "", "instructions": ""},
            },
        )
        assert call.kwargs["qa_model_override"] == "gpt-4o-mini"

    def test_no_qa_model_when_not_in_config(self):
        call = _run_task(
            "RegistryExtract",
            {
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4",
            },
        )
        assert call.kwargs["qa_model_override"] is None


# ===========================================================================
# Cross-agent: same logic works for all sub-agents
# ===========================================================================


class TestCrossAgentResolution:
    """Provider resolution works uniformly across all sub-agent types."""

    @pytest.mark.parametrize(
        "agent_name",
        [
            "CmdlineExtract",
            "ProcTreeExtract",
            "HuntQueriesExtract",
            "RegistryExtract",
            "ServicesExtract",
            "ScheduledTasksExtract",
        ],
    )
    def test_each_subagent_gets_own_provider(self, agent_name):
        call = _run_task(
            agent_name,
            {
                f"{agent_name}_provider": "anthropic",
                f"{agent_name}_model": "claude-sonnet-4-5",
                f"{agent_name}_temperature": 0.3,
                f"{agent_name}_top_p": 0.85,
            },
        )
        assert call.kwargs["provider"] == "anthropic"
        assert call.kwargs["model_name"] == "claude-sonnet-4-5"
        assert call.kwargs["temperature"] == 0.3
        assert call.kwargs["top_p"] == 0.85


# ===========================================================================
# Empty agent_models
# ===========================================================================


class TestEmptyConfig:
    """Graceful handling when agent_models is empty or None."""

    def test_empty_agent_models_no_crash(self):
        call = _run_task("RegistryExtract", {})
        # Should not crash; provider/model are empty/None
        assert call.kwargs["provider"] == "" or call.kwargs["provider"] is None
        assert call.kwargs["temperature"] == 0.0
        assert call.kwargs["top_p"] is None
