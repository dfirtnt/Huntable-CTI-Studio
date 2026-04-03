"""Tests for RegistryExtract / RegistryQA agent wiring across the full stack.

Validates that the new RegistryExtract sub-agent is wired as a first-class peer
of CmdlineExtract, ProcTreeExtract, and HuntQueriesExtract in schema, config,
migration, subagent utils, and workflow execution layers.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.workflow_config_loader import (
    AGENTS_ORDER_UI,
    EXTRACT_AGENTS,
    QA_AGENTS,
    load_workflow_config,
)
from src.config.workflow_config_migrate import migrate_v1_to_v2
from src.config.workflow_config_schema import (
    AGENT_NAMES_QA,
    AGENT_NAMES_SUB,
    ALL_AGENT_NAMES,
    BASE_AGENT_TO_QA,
    QA_AGENT_TO_BASE,
    WorkflowConfigV2,
)
from src.utils.subagent_utils import (
    AGENT_TO_SUBAGENT,
    normalize_subagent_name,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_AGENT_MODELS = {
    "RankAgent_provider": "openai",
    "RankAgent": "gpt-4",
    "ExtractAgent": "gpt-4",
    "SigmaAgent": "gpt-4",
    "CmdlineExtract_model": "gpt-4",
    "ProcTreeExtract_model": "gpt-4",
    "HuntQueriesExtract_model": "gpt-4",
    "RegistryExtract_model": "gpt-4",
    "RankAgentQA": "gpt-4",
    "CmdLineQA": "gpt-4",
    "ProcTreeQA": "gpt-4",
    "HuntQueriesQA": "gpt-4",
    "RegistryQA": "gpt-4",
}

_MINIMAL_AGENT_PROMPTS = {name: {"prompt": "", "instructions": ""} for name in ALL_AGENT_NAMES}


def _make_v2_with_registry(**overrides):
    """Build a minimal valid v2 config dict with RegistryExtract + RegistryQA."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "RegistryExtract": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "RegistryQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.1, "TopP": 0.9, "Enabled": True},
    }
    prompts = {k: {"prompt": "", "instructions": ""} for k in agents}
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "", "Description": ""},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
            "AutoTriggerHuntScoreThreshold": 60.0,
        },
        "Agents": agents,
        "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": prompts,
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    raw.update(overrides)
    return raw


# ===========================================================================
# Schema constants
# ===========================================================================


class TestSchemaConstants:
    """RegistryExtract/RegistryQA appear in all schema-level constant lists."""

    def test_registry_in_agent_names_sub(self):
        assert "RegistryExtract" in AGENT_NAMES_SUB

    def test_registry_qa_in_agent_names_qa(self):
        assert "RegistryQA" in AGENT_NAMES_QA

    def test_registry_in_all_agent_names(self):
        assert "RegistryExtract" in ALL_AGENT_NAMES
        assert "RegistryQA" in ALL_AGENT_NAMES

    def test_base_to_qa_mapping(self):
        assert BASE_AGENT_TO_QA["RegistryExtract"] == "RegistryQA"

    def test_qa_to_base_mapping(self):
        assert QA_AGENT_TO_BASE["RegistryQA"] == "RegistryExtract"


# ===========================================================================
# Schema validation
# ===========================================================================


class TestSchemaValidation:
    """WorkflowConfigV2 validates RegistryExtract correctly."""

    def test_valid_v2_with_registry(self):
        config = WorkflowConfigV2.model_validate(_make_v2_with_registry())
        assert "RegistryExtract" in config.Agents
        assert "RegistryQA" in config.Agents

    def test_orphan_registry_qa_rejected(self):
        """RegistryQA without RegistryExtract is rejected."""
        raw = _make_v2_with_registry()
        del raw["Agents"]["RegistryExtract"]
        del raw["Prompts"]["RegistryExtract"]
        with pytest.raises(ValidationError, match="Orphan QA agent RegistryQA"):
            WorkflowConfigV2.model_validate(raw)

    def test_registry_missing_prompt_rejected(self):
        """RegistryExtract with Provider+Model but no prompt is rejected."""
        raw = _make_v2_with_registry()
        del raw["Prompts"]["RegistryExtract"]
        with pytest.raises(ValidationError, match="Missing prompt block for agent RegistryExtract"):
            WorkflowConfigV2.model_validate(raw)

    def test_flatten_produces_registry_flat_keys(self):
        config = WorkflowConfigV2.model_validate(_make_v2_with_registry())
        flat = config.flatten_for_llm_service()
        assert flat["RegistryExtract_model"] == "gpt-4"
        assert flat["RegistryExtract_provider"] == "openai"
        assert flat["RegistryExtract_temperature"] == 0.0
        assert flat["RegistryExtract_top_p"] == 0.9
        assert flat["RegistryQA"] == "gpt-4"
        assert flat["RegistryQA_provider"] == "openai"

    def test_disabled_registry_in_extract_agent_settings(self):
        raw = _make_v2_with_registry()
        raw["Execution"]["ExtractAgentSettings"]["DisabledAgents"] = ["RegistryExtract"]
        config = WorkflowConfigV2.model_validate(raw)
        legacy = config.to_legacy_response_dict()
        assert "RegistryExtract" in legacy["agent_prompts"]["ExtractAgentSettings"]["disabled_agents"]


# ===========================================================================
# Loader constants
# ===========================================================================


class TestLoaderConstants:
    """RegistryExtract appears in loader ordering constants."""

    def test_in_extract_agents(self):
        assert "RegistryExtract" in EXTRACT_AGENTS

    def test_in_qa_agents(self):
        assert "RegistryQA" in QA_AGENTS

    def test_in_agents_order_ui(self):
        assert "RegistryExtract" in AGENTS_ORDER_UI
        assert "RegistryQA" in AGENTS_ORDER_UI


# ===========================================================================
# Migration
# ===========================================================================


class TestMigration:
    """v1-to-v2 migration produces RegistryExtract/RegistryQA agents."""

    def test_v1_with_registry_model_migrates(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "RegistryExtract_provider": "anthropic",
                "RegistryExtract_model": "claude-sonnet-4-5",
                "RegistryExtract_temperature": 0.2,
                "RegistryExtract_top_p": 0.95,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        assert config.Agents["RegistryExtract"].Model == "claude-sonnet-4-5"
        assert config.Agents["RegistryExtract"].Provider == "anthropic"
        assert config.Agents["RegistryExtract"].Temperature == 0.2
        assert config.Agents["RegistryExtract"].TopP == 0.95

    def test_v1_registry_qa_migrates(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "RegistryQA_provider": "openai",
                "RegistryQA": "gpt-4o",
                "RegistryQA_temperature": 0.1,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        assert config.Agents["RegistryQA"].Model == "gpt-4o"
        assert config.Agents["RegistryQA"].Provider == "openai"

    def test_migration_roundtrip_flatten_preserves_registry(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "RegistryExtract_provider": "openai",
                "RegistryExtract_model": "gpt-4o-mini",
                "RegistryExtract_temperature": 0.3,
                "RegistryExtract_top_p": 0.85,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        flat = config.flatten_for_llm_service()
        assert flat["RegistryExtract_model"] == "gpt-4o-mini"
        assert flat["RegistryExtract_provider"] == "openai"
        assert flat["RegistryExtract_temperature"] == 0.3
        assert flat["RegistryExtract_top_p"] == 0.85


# ===========================================================================
# Subagent utils
# ===========================================================================


class TestSubagentUtils:
    """registry_artifacts alias normalization works correctly."""

    def test_agent_to_subagent_has_registry(self):
        assert AGENT_TO_SUBAGENT["registryextract"] == "registry_artifacts"

    @pytest.mark.parametrize(
        "alias",
        [
            "registry_artifacts",
            "registryartifacts",
            "registry-artifacts",
            "registryextract",
            "registry",
            "RegistryExtract",
            "REGISTRY_ARTIFACTS",
        ],
    )
    def test_normalize_registry_aliases(self, alias):
        assert normalize_subagent_name(alias) == "registry_artifacts"

    def test_normalize_unknown_returns_none(self):
        assert normalize_subagent_name("not_a_subagent") is None


# ===========================================================================
# UI-ordered export / import round-trip
# ===========================================================================


class TestUIOrderedRoundTrip:
    """RegistryExtract survives ui-ordered export → import cycle."""

    def _make_ui_ordered_preset(self):
        """Build a UI-ordered preset dict with RegistryExtract section."""
        base_agent = {
            "Enabled": True,
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0,
            "TopP": 0.9,
            "Prompt": {},
            "QAEnabled": False,
            "QA": {},
            "QAPrompt": {},
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
            "RankAgent": {
                **base_agent,
                "RankingThreshold": 6.0,
            },
            "ExtractAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0, "TopP": 0.9, "Prompt": {}},
            "CmdlineExtract": {**base_agent, "AttentionPreprocessor": True},
            "ProcTreeExtract": dict(base_agent),
            "HuntQueriesExtract": dict(base_agent),
            "RegistryExtract": dict(base_agent),
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

    def test_load_workflow_config_accepts_registry(self):
        preset = self._make_ui_ordered_preset()
        config = load_workflow_config(preset)
        assert "RegistryExtract" in config.Agents
        assert "RegistryQA" in config.Agents

    def test_registry_round_trip_through_export(self):
        from src.config.workflow_config_loader import v2_to_ui_ordered_export

        preset = self._make_ui_ordered_preset()
        config = load_workflow_config(preset)
        # v2_to_ui_ordered_export expects a raw v2 dict
        v2_dict = json.loads(config.model_dump_json())
        exported = v2_to_ui_ordered_export(v2_dict)
        assert "RegistryExtract" in exported, "RegistryExtract missing from UI-ordered export"
        assert exported["RegistryExtract"]["Provider"] == "openai"
        assert exported["RegistryExtract"]["Model"] == "gpt-4"


# ===========================================================================
# Prompt files
# ===========================================================================


class TestPromptFiles:
    """RegistryExtract and RegistryQA prompt files exist and are valid JSON configs."""

    @pytest.mark.parametrize("prompt_name", ["RegistryExtract", "RegistryQA"])
    def test_prompt_file_exists_and_is_valid_json(self, prompt_name):
        prompt_path = Path(__file__).resolve().parent.parent.parent / "src" / "prompts" / prompt_name
        assert prompt_path.exists(), f"Prompt file missing: {prompt_path}"
        content = prompt_path.read_text()
        data = json.loads(content)
        assert "role" in data or "task" in data, f"Prompt file {prompt_name} missing expected keys"

    def test_registry_extract_prompt_has_output_schema(self):
        prompt_path = Path(__file__).resolve().parent.parent.parent / "src" / "prompts" / "RegistryExtract"
        data = json.loads(prompt_path.read_text())
        # The json_example should define registry_artifacts array
        example = data.get("json_example", "")
        if isinstance(example, str):
            parsed = json.loads(example)
        else:
            parsed = example
        assert "registry_artifacts" in parsed, "json_example must define registry_artifacts"


# ===========================================================================
# Preset files
# ===========================================================================


class TestPresetFiles:
    """Quickstart preset files include RegistryExtract section."""

    def test_quickstart_presets_have_registry(self):
        preset_dir = (
            Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"
        )
        if not preset_dir.exists():
            pytest.skip("Quickstart preset directory not found")
        preset_files = list(preset_dir.glob("*.json"))
        assert len(preset_files) > 0, "No preset files found"
        for preset_file in preset_files:
            data = json.loads(preset_file.read_text())
            assert "RegistryExtract" in data, f"RegistryExtract missing from {preset_file.name}"
            assert "Provider" in data["RegistryExtract"], f"RegistryExtract.Provider missing in {preset_file.name}"


# ===========================================================================
# Eval articles placeholder
# ===========================================================================


class TestEvalArticlesPlaceholder:
    """Static eval articles directory exists for registry_artifacts."""

    def test_eval_articles_directory_exists(self):
        eval_dir = (
            Path(__file__).resolve().parent.parent.parent / "config" / "eval_articles_data" / "registry_artifacts"
        )
        assert eval_dir.exists(), f"Eval articles dir missing: {eval_dir}"
        articles_file = eval_dir / "articles.json"
        assert articles_file.exists(), "articles.json placeholder missing"


# ===========================================================================
# Workflow helpers
# ===========================================================================


class TestWorkflowHelpers:
    """_extract_actual_count handles registry_artifacts subresults."""

    def test_extract_actual_count_registry_artifacts(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        subresults = {
            "registry_artifacts": {
                "items": [
                    {"registry_hive": "HKEY_LOCAL_MACHINE", "registry_key_path": "SOFTWARE\\Test"},
                    {"registry_hive": "HKEY_CURRENT_USER", "registry_key_path": "SOFTWARE\\Other"},
                ],
                "count": 2,
            }
        }
        assert _extract_actual_count("registry_artifacts", subresults, execution_id=1) == 2

    def test_extract_actual_count_registry_artifacts_from_count(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        subresults = {"registry_artifacts": {"count": 5, "items": []}}
        assert _extract_actual_count("registry_artifacts", subresults, execution_id=1) == 5

    def test_extract_actual_count_registry_artifacts_missing(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        assert _extract_actual_count("registry_artifacts", {}, execution_id=1) == 0


# ===========================================================================
# Default agent prompts
# ===========================================================================


class TestDefaultAgentPrompts:
    """RegistryExtract and RegistryQA are in the prompt file map."""

    def test_agent_prompt_files_has_registry(self):
        from src.utils.default_agent_prompts import AGENT_PROMPT_FILES

        assert "RegistryExtract" in AGENT_PROMPT_FILES
        assert "RegistryQA" in AGENT_PROMPT_FILES
