"""Tests for _backfill_ui_ordered_sub_agents in workflow_config_loader.

Validates that presets saved before a sub-agent existed import cleanly
by having their missing sections injected with disabled defaults before
strict validation fires.
"""

import copy

import pytest

from src.config.workflow_config_loader import (
    _OPTIONAL_SUB_AGENT_SECTIONS,
    _backfill_ui_ordered_sub_agents,
    validate_ui_ordered_preset_strict,
)

pytestmark = pytest.mark.unit


def _make_preset_without_registry():
    """Build a UI-ordered preset that mimics one saved before RegistryExtract existed."""
    base = {
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
    return {
        "Version": "2.0",
        "Metadata": {},
        "JunkFilter": {"JunkFilterThreshold": 0.8},
        "QASettings": {"MaxRetries": 3},
        "Thresholds": {"MinHuntScore": 97.0, "AutoTriggerHuntScoreThreshold": 60.0},
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
        # NOTE: RegistryExtract intentionally absent — simulates old preset
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


# ===========================================================================
# Core backfill behavior
# ===========================================================================


class TestBackfillMissingSections:
    """_backfill_ui_ordered_sub_agents injects disabled defaults for absent sections."""

    def test_missing_registry_extract_is_injected(self):
        preset = _make_preset_without_registry()
        assert "RegistryExtract" not in preset

        result = _backfill_ui_ordered_sub_agents(preset)
        assert "RegistryExtract" in result

    def test_injected_section_is_disabled(self):
        preset = _make_preset_without_registry()
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result["RegistryExtract"]["Enabled"] is False

    def test_injected_section_has_all_required_keys(self):
        preset = _make_preset_without_registry()
        result = _backfill_ui_ordered_sub_agents(preset)
        section = result["RegistryExtract"]
        required = ["Enabled", "Provider", "Model", "Temperature", "TopP", "Prompt", "QAEnabled", "QA", "QAPrompt"]
        for key in required:
            assert key in section, f"Missing required key: {key}"

    def test_injected_section_matches_default_block(self):
        """Values match the _OPTIONAL_SUB_AGENT_SECTIONS default exactly."""
        preset = _make_preset_without_registry()
        result = _backfill_ui_ordered_sub_agents(preset)
        expected = dict(_OPTIONAL_SUB_AGENT_SECTIONS)["RegistryExtract"]
        assert result["RegistryExtract"] == expected

    def test_injected_qa_is_disabled(self):
        preset = _make_preset_without_registry()
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result["RegistryExtract"]["QAEnabled"] is False

    def test_injected_provider_is_empty_string(self):
        """Empty provider means the agent inherits ExtractAgent's provider at runtime."""
        preset = _make_preset_without_registry()
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result["RegistryExtract"]["Provider"] == ""
        assert result["RegistryExtract"]["Model"] == ""


# ===========================================================================
# Existing sections not overwritten
# ===========================================================================


class TestBackfillPreservesExisting:
    """Sections already present are not touched."""

    def test_existing_registry_extract_not_overwritten(self):
        preset = _make_preset_without_registry()
        preset["RegistryExtract"] = {
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
        assert result["RegistryExtract"]["Provider"] == "anthropic"
        assert result["RegistryExtract"]["Model"] == "claude-sonnet-4-5"
        assert result["RegistryExtract"]["Enabled"] is True

    def test_other_sections_untouched(self):
        preset = _make_preset_without_registry()
        original_cmdline = copy.deepcopy(preset["CmdlineExtract"])
        result = _backfill_ui_ordered_sub_agents(preset)
        assert result["CmdlineExtract"] == original_cmdline


# ===========================================================================
# No mutation of caller's dict
# ===========================================================================


class TestBackfillImmutability:
    """Function returns a new dict, doesn't mutate the input."""

    def test_original_dict_not_mutated(self):
        preset = _make_preset_without_registry()
        original_keys = set(preset.keys())
        _backfill_ui_ordered_sub_agents(preset)
        assert set(preset.keys()) == original_keys
        assert "RegistryExtract" not in preset


# ===========================================================================
# Integration with strict validation
# ===========================================================================


class TestBackfillBeforeValidation:
    """After backfill, strict validation passes on old presets."""

    def test_old_preset_passes_strict_validation_after_backfill(self):
        preset = _make_preset_without_registry()
        backfilled = _backfill_ui_ordered_sub_agents(preset)
        # Should not raise
        validate_ui_ordered_preset_strict(backfilled)

    def test_old_preset_fails_strict_validation_without_backfill(self):
        preset = _make_preset_without_registry()
        with pytest.raises(ValueError, match="missing or null.*RegistryExtract"):
            validate_ui_ordered_preset_strict(preset)
