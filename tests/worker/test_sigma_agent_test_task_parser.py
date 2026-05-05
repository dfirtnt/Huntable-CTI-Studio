"""Tests for test_sigma_agent_task SigmaAgent prompt parsing.

Regression: the Test SIGMA button's Celery task previously used a home-grown
parser that only checked outer-level "system"/"role" keys (which exist in
zero of the five DB shapes), silently sending system_prompt=None for every
saved configuration.  This test verifies the task now delegates to
parse_sigma_agent_prompt_data so it correctly extracts the system persona
from the auto-persist shape (the one that bit run 2426).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_config(agent_prompts: dict, agent_models: dict | None = None):
    return SimpleNamespace(
        agent_models=agent_models or {"SigmaAgent_provider": "lmstudio", "SigmaAgent": "qwen/qwen3-8b"},
        agent_prompts=agent_prompts,
        qa_enabled={},
        qa_max_retries=5,
    )


def _make_article(article_id: int = 2069):
    source = SimpleNamespace(name="TestSource")
    return SimpleNamespace(
        id=article_id,
        title="APT29 PowerShell Persistence",
        canonical_url="https://example.com/threat-report",
        content="APT29 uses PowerShell for persistence.",
        source=source,
        article_metadata={},
    )


def _run_sigma_task(agent_prompts: dict):
    """Execute test_sigma_agent_task with mocked deps; return SigmaGenerationService call kwargs."""
    article = _make_article()
    config = _make_config(agent_prompts)

    mock_service = MagicMock()
    mock_generate = AsyncMock(return_value={"rules": [], "errors": None, "metadata": {}})
    mock_service.generate_sigma_rules = mock_generate

    with (
        patch("src.worker.tasks.test_agents._get_db_session", return_value=MagicMock()),
        patch("src.worker.tasks.test_agents._load_article", return_value=article),
        patch("src.worker.tasks.test_agents._get_active_config", return_value=config),
        patch("src.worker.tasks.test_agents._filter_content", return_value="filtered content"),
        patch("src.services.sigma_generation_service.SigmaGenerationService", return_value=mock_service),
    ):
        from src.worker.tasks.test_agents import test_sigma_agent_task

        if hasattr(test_sigma_agent_task, "app"):
            test_sigma_agent_task.run(article.id)
        else:
            test_sigma_agent_task(MagicMock(), article.id)

    assert mock_generate.call_count == 1, "generate_sigma_rules was not called"
    return mock_generate.call_args


class TestSigmaAgentTaskUsesCanonicalParser:
    def test_auto_persist_shape_5_routes_persona_to_system_prompt(self):
        """Regression: shape-5 ({model, prompt='persona', instructions}) must yield system=persona, template=None.

        Before the fix, the home-grown parser took the persona text as the user template
        and left system=None, sending the article-less persona text to the LLM under the
        hardcoded default system prompt.
        """
        persona = "Generate Sigma rules strictly from observables. Focus on behaviors."
        agent_prompts = {
            "SigmaAgent": {
                "model": "qwen/qwen3-8b",
                "prompt": persona,
                "instructions": "",
            }
        }
        call = _run_sigma_task(agent_prompts)
        assert call.kwargs["sigma_system_prompt"] == persona
        assert call.kwargs["sigma_prompt_template"] is None

    def test_locked_scaffold_shape_1_extracts_role_and_user_template(self):
        """Shape 1 (locked scaffold): role -> system, user_template -> template."""
        inner = json.dumps(
            {
                "role": "PERSONA_V1",
                "user_template": "Generate for {title}: {content}",
            }
        )
        agent_prompts = {"SigmaAgent": {"prompt": inner, "instructions": ""}}
        call = _run_sigma_task(agent_prompts)
        assert call.kwargs["sigma_system_prompt"] == "PERSONA_V1"
        assert call.kwargs["sigma_prompt_template"] == "Generate for {title}: {content}"

    def test_no_model_no_placeholder_routes_persona_to_system_prompt(self):
        """Regression: live DB shape with no 'model' key and no placeholders must yield system=persona.

        The existing shape-5 test covers {model, prompt, instructions}.  The DB shape
        that triggered run-2426 had no 'model' sibling: {prompt: '<persona>', instructions: ''}.
        Without the model key the parser must still detect the absence of format placeholders
        and route the text to system, not to template.
        """
        persona = "You are a precise Sigma rule author. Focus on behavioral detection."
        agent_prompts = {
            "SigmaAgent": {
                "prompt": persona,
                "instructions": "",
            }
        }
        call = _run_sigma_task(agent_prompts)
        assert call.kwargs["sigma_system_prompt"] == persona
        assert call.kwargs["sigma_prompt_template"] is None

    def test_extraction_envelope_shape_2_extracts_role_as_system(self):
        """Shape 2 (extraction-agent envelope): role -> system, template stays None."""
        inner = json.dumps(
            {
                "role": "PERSONA_V2",
                "task": "",
                "json_example": "{}",
                "instructions": "",
            }
        )
        agent_prompts = {"SigmaAgent": {"prompt": inner, "instructions": ""}}
        call = _run_sigma_task(agent_prompts)
        assert call.kwargs["sigma_system_prompt"] == "PERSONA_V2"
        assert call.kwargs["sigma_prompt_template"] is None
