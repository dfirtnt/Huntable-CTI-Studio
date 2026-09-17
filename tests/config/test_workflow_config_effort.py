"""Optional per-agent Effort in the v2 config contract.

Effort is the only per-agent knob that may be absent: None means "provider default",
which is what every shipped preset and every pre-existing DB row carries. The flat key
is ``{Agent}_effort`` and is emitted only when set so untouched configs flatten as before.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.workflow_config_loader import export_preset_as_canonical_v2, load_workflow_config
from src.config.workflow_config_migrate import migrate_v1_to_v2
from src.config.workflow_config_schema import (
    VALID_EFFORT_LEVELS,
    AgentConfig,
    WorkflowConfigV2,
    normalize_agent_models_to_flat,
)

pytestmark = pytest.mark.unit

_QUICKSTART_DIR = Path(__file__).resolve().parents[2] / "config" / "presets" / "AgentConfigs" / "quickstart"


def _agent(**overrides):
    base = {"Provider": "openai", "Model": "gpt-5.6-luna", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}
    base.update(overrides)
    return base


def _config(agent: dict) -> WorkflowConfigV2:
    return WorkflowConfigV2.model_validate(
        {
            "Version": "2.0",
            "Agents": {"RankAgent": agent},
            "Prompts": {"RankAgent": {"prompt": "", "instructions": ""}},
        }
    )


class TestAgentConfigEffort:
    def test_absent_means_provider_default(self):
        assert AgentConfig(**_agent()).Effort is None

    def test_none_and_blank_normalize_to_none(self):
        assert AgentConfig(**_agent(Effort=None)).Effort is None
        assert AgentConfig(**_agent(Effort="")).Effort is None
        assert AgentConfig(**_agent(Effort="   ")).Effort is None

    @pytest.mark.parametrize("level", VALID_EFFORT_LEVELS)
    def test_every_documented_tier_is_accepted(self, level):
        assert AgentConfig(**_agent(Effort=level)).Effort == level

    def test_value_is_normalized_to_lowercase(self):
        assert AgentConfig(**_agent(Effort=" XHigh ")).Effort == "xhigh"

    def test_live_provider_tier_names_are_accepted_by_shape(self):
        # Codex has shipped tiers outside the documented vocabulary; the contract pins
        # the token shape and leaves membership to the resolved model.
        assert AgentConfig(**_agent(Provider="codex", Effort="ultra")).Effort == "ultra"

    @pytest.mark.parametrize("bad", ["very high", "hi!", "9", 5, 1.5, True, ["high"]])
    def test_invalid_values_are_rejected_with_a_clear_error(self, bad):
        with pytest.raises(ValidationError, match="Effort"):
            AgentConfig(**_agent(Effort=bad))


class TestFlatKeyRoundTrip:
    def test_flatten_emits_effort_only_when_set(self):
        assert "RankAgent_effort" not in _config(_agent()).flatten_for_llm_service()
        flat = _config(_agent(Effort="high")).flatten_for_llm_service()
        assert flat["RankAgent_effort"] == "high"

    def test_legacy_response_dict_carries_effort(self):
        legacy = _config(_agent(Effort="low")).to_legacy_response_dict()
        assert legacy["agent_models"]["RankAgent_effort"] == "low"

    def test_nested_to_flat_normalization(self):
        flat = normalize_agent_models_to_flat(
            {
                "CmdlineExtract": {"provider": "anthropic", "model": "claude-opus-5", "effort": "xhigh"},
                "SigmaAgent": {"Provider": "openai", "Model": "gpt-5.6-luna", "Effort": "max"},
                "RankAgent": {"provider": "openai", "model": "gpt-4o"},
            }
        )
        assert flat["CmdlineExtract_effort"] == "xhigh"
        assert flat["SigmaAgent_effort"] == "max"
        assert "RankAgent_effort" not in flat
        # Idempotent on already-flat input
        assert normalize_agent_models_to_flat(flat) == flat

    def test_migrator_lifts_flat_effort_into_the_agent_block(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                "RankAgent_provider": "openai",
                "RankAgent": "gpt-5.6-luna",
                "RankAgent_effort": " High ",
                "SigmaAgent_provider": "openai",
                "SigmaAgent": "gpt-5.6-luna",
                "SigmaAgent_effort": "",
            },
        }
        migrated = migrate_v1_to_v2(raw)
        assert migrated["Agents"]["RankAgent"]["Effort"] == "high"
        assert "Effort" not in migrated["Agents"]["SigmaAgent"]


class TestPresetsNeedNoEdit:
    @pytest.mark.parametrize("preset_path", sorted(_QUICKSTART_DIR.glob("*.json")), ids=lambda p: p.name)
    def test_every_quickstart_preset_still_validates(self, preset_path: Path):
        config = load_workflow_config(json.loads(preset_path.read_text()))
        assert isinstance(config, WorkflowConfigV2)
        assert all(agent.Effort is None for agent in config.Agents.values())
        assert not any(key.endswith("_effort") for key in config.flatten_for_llm_service())


class TestUiOrderedPresetRoundTrip:
    """The UI-ordered export/import shape must carry Effort.

    This is the "Export to file" / hand-authored-preset path
    (`export_preset_as_canonical_v2` -> `ui_ordered_to_v2`). It re-picks each agent's
    fields by name rather than passing the block through, so an optional field is
    dropped unless it is carried deliberately -- which is exactly what happened on the
    first cut of this feature: a config with a chosen tier exported without it and came
    back as "provider default", silently, with no error or log line.
    """

    def _v2_dict(self) -> dict:
        preset = json.loads((_QUICKSTART_DIR / "Quickstart-openai-gpt-4o.json").read_text())
        return load_workflow_config(preset).model_dump(mode="json")

    def test_effort_survives_export_then_import(self):
        raw = self._v2_dict()
        for agent in ("RankAgent", "ExtractAgent", "SigmaAgent", "CmdlineExtract"):
            raw["Agents"][agent]["Effort"] = "high"

        exported = export_preset_as_canonical_v2(raw)
        restored = load_workflow_config(exported)

        for agent in ("RankAgent", "ExtractAgent", "SigmaAgent", "CmdlineExtract"):
            assert exported[agent]["Effort"] == "high", agent
            assert restored.Agents[agent].Effort == "high", agent

    def test_agent_without_effort_exports_no_key(self):
        raw = self._v2_dict()
        raw["Agents"]["RankAgent"]["Effort"] = "low"

        exported = export_preset_as_canonical_v2(raw)

        assert "Effort" not in exported["ServicesExtract"]
        assert load_workflow_config(exported).Agents["ServicesExtract"].Effort is None

    def test_preset_that_never_set_effort_exports_the_pre_field_shape(self):
        """No committed preset gains an Effort key just because the field now exists."""
        preset = json.loads((_QUICKSTART_DIR / "Quickstart-openai-gpt-4o.json").read_text())
        exported = export_preset_as_canonical_v2(preset)
        assert not [k for k, v in exported.items() if isinstance(v, dict) and "Effort" in v]

    def test_re_export_is_identical(self):
        raw = self._v2_dict()
        raw["Agents"]["SigmaAgent"]["Effort"] = "xhigh"
        exported = export_preset_as_canonical_v2(raw)
        assert export_preset_as_canonical_v2(exported) == exported

    def test_hand_authored_ui_ordered_effort_is_honored_on_import(self):
        preset = json.loads((_QUICKSTART_DIR / "Quickstart-openai-gpt-4o.json").read_text())
        preset["SigmaAgent"]["Effort"] = " MAX "
        assert load_workflow_config(preset).Agents["SigmaAgent"].Effort == "max"
