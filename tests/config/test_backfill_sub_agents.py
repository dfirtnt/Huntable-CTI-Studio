"""Tests for _backfill_ui_ordered_sub_agents in workflow_config_loader.

Validates that presets saved before a sub-agent existed import cleanly
by having their missing sections injected with disabled defaults before
strict validation fires.

Parametrized across all sub-agents covered by _OPTIONAL_SUB_AGENT_SECTIONS:
RegistryExtract, ServicesExtract, ScheduledTasksExtract.
"""

import copy

import pytest

from src.config.workflow_config_loader import (
    _OPTIONAL_SUB_AGENT_SECTIONS,
    _backfill_ui_ordered_sub_agents,
    validate_ui_ordered_preset_strict,
)

pytestmark = pytest.mark.unit


# Sub-agents that have backfill defaults; each must support the full backfill contract.
BACKFILL_AGENTS = ["RegistryExtract", "ServicesExtract", "ScheduledTasksExtract"]


def _base_agent_block():
    return {
        "Enabled": True,
        "Provider": "openai",
        "Model": "gpt-4",
        "Temperature": 0,
        "TopP": 0.9,
        "Prompt": {"prompt": "", "instructions": ""},
        "QAEnabled": False,
        "QA": {"Provider": "", "Model": "", "Temperature": 0.1, "TopP": 0.9},
        "QAPrompt": {"prompt": "", "instructions": ""},
    }


def _make_preset_without(agent_name: str) -> dict:
    """Build a UI-ordered preset that mimics one saved before `agent_name` existed.

    All other sub-agents covered by backfill are present; the named one is omitted.
    """
    base = _base_agent_block()
    preset = {
        "Version": "2.0",
        "Metadata": {},
        "JunkFilter": {"JunkFilterThreshold": 0.8},
        "QASettings": {"MaxRetries": 3},
        "Thresholds": {"MinHuntScore": 97.0},
        "OSDetection": {
            "Embedding": "bert",
            "FallbackEnabled": False,
            "Fallback": {},
            "SelectedOs": ["Windows"],
            "Prompt": {},
        },
        "RankAgent": {**base, "RankingThreshold": 6.0},
        "ExtractAgent": {
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0,
            "TopP": 0.9,
            "Prompt": {},
        },
        "CmdlineExtract": {**base, "AttentionPreprocessor": True},
        "ProcTreeExtract": dict(base),
        "HuntQueriesExtract": dict(base),
        "RegistryExtract": dict(base),
        "ServicesExtract": dict(base),
        "ScheduledTasksExtract": dict(base),
        "SigmaAgent": {
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0,
            "TopP": 0.9,
            "SimilarityThreshold": 0.5,
            "UseFullArticleContent": False,
            "Prompt": {},
        },
    }
    del preset[agent_name]
    return preset


# ===========================================================================
# Core backfill behavior
# ===========================================================================


class TestBackfillMissingSections:
    """_backfill_ui_ordered_sub_agents injects disabled defaults for absent sections."""

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_missing_section_is_injected(self, agent_name):
        preset = _make_preset_without(agent_name)
        assert agent_name not in preset

        result = _backfill_ui_ordered_sub_agents(preset)
        assert agent_name in result

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_injected_section_is_disabled(self, agent_name):
        preset = _make_preset_without(agent_name)
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result[agent_name]["Enabled"] is False

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_injected_section_has_all_required_keys(self, agent_name):
        preset = _make_preset_without(agent_name)
        result = _backfill_ui_ordered_sub_agents(preset)
        section = result[agent_name]
        required = ["Enabled", "Provider", "Model", "Temperature", "TopP", "Prompt", "QAEnabled", "QA", "QAPrompt"]
        for key in required:
            assert key in section, f"{agent_name} missing required key: {key}"

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_injected_section_matches_default_block(self, agent_name):
        """Values match the _OPTIONAL_SUB_AGENT_SECTIONS default exactly."""
        preset = _make_preset_without(agent_name)
        result = _backfill_ui_ordered_sub_agents(preset)
        expected = dict(_OPTIONAL_SUB_AGENT_SECTIONS)[agent_name]
        assert result[agent_name] == expected

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_injected_qa_is_disabled(self, agent_name):
        preset = _make_preset_without(agent_name)
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result[agent_name]["QAEnabled"] is False

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_injected_provider_is_empty_string(self, agent_name):
        """Empty provider means the agent inherits ExtractAgent's provider at runtime."""
        preset = _make_preset_without(agent_name)
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result[agent_name]["Provider"] == ""
        assert result[agent_name]["Model"] == ""


# ===========================================================================
# Existing sections not overwritten
# ===========================================================================


class TestBackfillPreservesExisting:
    """Sections already present are not touched."""

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_existing_section_not_overwritten(self, agent_name):
        preset = _make_preset_without(agent_name)
        preset[agent_name] = {
            "Enabled": True,
            "Provider": "anthropic",
            "Model": "claude-sonnet-4-5",
            "Temperature": 0.2,
            "TopP": 0.95,
            "Prompt": {"prompt": "custom", "instructions": "custom"},
            "QAEnabled": True,
            "QA": {"Provider": "anthropic", "Model": "claude-sonnet-4-5", "Temperature": 0.1, "TopP": 0.9},
            "QAPrompt": {"prompt": "qa", "instructions": "qa"},
        }
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result[agent_name]["Provider"] == "anthropic"
        assert result[agent_name]["Model"] == "claude-sonnet-4-5"
        assert result[agent_name]["Enabled"] is True

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_other_sections_untouched(self, agent_name):
        preset = _make_preset_without(agent_name)
        original_cmdline = copy.deepcopy(preset["CmdlineExtract"])
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result["CmdlineExtract"] == original_cmdline


# ===========================================================================
# No mutation of caller's dict
# ===========================================================================


class TestBackfillImmutability:
    """Function returns a new dict, doesn't mutate the input."""

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_original_dict_not_mutated(self, agent_name):
        preset = _make_preset_without(agent_name)
        original_keys = set(preset.keys())
        _backfill_ui_ordered_sub_agents(preset)
        assert set(preset.keys()) == original_keys
        assert agent_name not in preset


# ===========================================================================
# Integration with strict validation
# ===========================================================================


class TestBackfillBeforeValidation:
    """After backfill, strict validation passes on old presets."""

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_old_preset_passes_strict_validation_after_backfill(self, agent_name):
        preset = _make_preset_without(agent_name)
        backfilled = _backfill_ui_ordered_sub_agents(preset)
        # Should not raise
        validate_ui_ordered_preset_strict(backfilled)

    @pytest.mark.parametrize("agent_name", BACKFILL_AGENTS)
    def test_old_preset_fails_strict_validation_without_backfill(self, agent_name):
        preset = _make_preset_without(agent_name)
        with pytest.raises(ValueError, match=f"missing or null.*{agent_name}"):
            validate_ui_ordered_preset_strict(preset)
