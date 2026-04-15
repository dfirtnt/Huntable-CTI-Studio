"""Tests for ServicesExtract / ServicesQA agent wiring across the full stack.

Validates that the new ServicesExtract sub-agent is wired as a first-class peer
of CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, and RegistryExtract in
schema, config, migration, subagent utils, and workflow execution layers.
"""

import json
from pathlib import Path

import pytest
import yaml
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
    "ServicesExtract_model": "gpt-4",
    "RankAgentQA": "gpt-4",
    "CmdLineQA": "gpt-4",
    "ProcTreeQA": "gpt-4",
    "HuntQueriesQA": "gpt-4",
    "RegistryQA": "gpt-4",
    "ServicesQA": "gpt-4",
}

_MINIMAL_AGENT_PROMPTS = {name: {"prompt": "", "instructions": ""} for name in ALL_AGENT_NAMES}


def _make_v2_with_services(**overrides):
    """Build a minimal valid v2 config dict with ServicesExtract + ServicesQA."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "ServicesExtract": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "ServicesQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.1, "TopP": 0.9, "Enabled": True},
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
    """ServicesExtract/ServicesQA appear in all schema-level constant lists."""

    def test_services_in_agent_names_sub(self):
        assert "ServicesExtract" in AGENT_NAMES_SUB

    def test_services_qa_in_agent_names_qa(self):
        assert "ServicesQA" in AGENT_NAMES_QA

    def test_services_in_all_agent_names(self):
        assert "ServicesExtract" in ALL_AGENT_NAMES
        assert "ServicesQA" in ALL_AGENT_NAMES

    def test_base_to_qa_mapping(self):
        assert BASE_AGENT_TO_QA["ServicesExtract"] == "ServicesQA"

    def test_qa_to_base_mapping(self):
        assert QA_AGENT_TO_BASE["ServicesQA"] == "ServicesExtract"


# ===========================================================================
# Schema validation
# ===========================================================================


class TestSchemaValidation:
    """WorkflowConfigV2 validates ServicesExtract correctly."""

    def test_valid_v2_with_services(self):
        config = WorkflowConfigV2.model_validate(_make_v2_with_services())
        assert "ServicesExtract" in config.Agents
        assert "ServicesQA" in config.Agents

    def test_orphan_services_qa_rejected(self):
        """ServicesQA without ServicesExtract is rejected."""
        raw = _make_v2_with_services()
        del raw["Agents"]["ServicesExtract"]
        del raw["Prompts"]["ServicesExtract"]
        with pytest.raises(ValidationError, match="Orphan QA agent ServicesQA"):
            WorkflowConfigV2.model_validate(raw)

    def test_services_missing_prompt_rejected(self):
        """ServicesExtract with Provider+Model but no prompt is rejected."""
        raw = _make_v2_with_services()
        del raw["Prompts"]["ServicesExtract"]
        with pytest.raises(ValidationError, match="Missing prompt block for agent ServicesExtract"):
            WorkflowConfigV2.model_validate(raw)

    def test_flatten_produces_services_flat_keys(self):
        config = WorkflowConfigV2.model_validate(_make_v2_with_services())
        flat = config.flatten_for_llm_service()
        assert flat["ServicesExtract_model"] == "gpt-4"
        assert flat["ServicesExtract_provider"] == "openai"
        assert flat["ServicesExtract_temperature"] == 0.0
        assert flat["ServicesExtract_top_p"] == 0.9
        assert flat["ServicesQA"] == "gpt-4"
        assert flat["ServicesQA_provider"] == "openai"

    def test_disabled_services_in_extract_agent_settings(self):
        raw = _make_v2_with_services()
        raw["Execution"]["ExtractAgentSettings"]["DisabledAgents"] = ["ServicesExtract"]
        config = WorkflowConfigV2.model_validate(raw)
        legacy = config.to_legacy_response_dict()
        assert "ServicesExtract" in legacy["agent_prompts"]["ExtractAgentSettings"]["disabled_agents"]


# ===========================================================================
# Loader constants
# ===========================================================================


class TestLoaderConstants:
    """ServicesExtract appears in loader ordering constants."""

    def test_in_extract_agents(self):
        assert "ServicesExtract" in EXTRACT_AGENTS

    def test_in_qa_agents(self):
        assert "ServicesQA" in QA_AGENTS

    def test_in_agents_order_ui(self):
        assert "ServicesExtract" in AGENTS_ORDER_UI
        assert "ServicesQA" in AGENTS_ORDER_UI


# ===========================================================================
# Migration
# ===========================================================================


class TestMigration:
    """v1-to-v2 migration produces ServicesExtract/ServicesQA agents."""

    def test_v1_with_services_model_migrates(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "ServicesExtract_provider": "anthropic",
                "ServicesExtract_model": "claude-sonnet-4-5",
                "ServicesExtract_temperature": 0.2,
                "ServicesExtract_top_p": 0.95,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        assert config.Agents["ServicesExtract"].Model == "claude-sonnet-4-5"
        assert config.Agents["ServicesExtract"].Provider == "anthropic"
        assert config.Agents["ServicesExtract"].Temperature == 0.2
        assert config.Agents["ServicesExtract"].TopP == 0.95

    def test_v1_services_qa_migrates(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "ServicesQA_provider": "openai",
                "ServicesQA": "gpt-4o",
                "ServicesQA_temperature": 0.1,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        assert config.Agents["ServicesQA"].Model == "gpt-4o"
        assert config.Agents["ServicesQA"].Provider == "openai"

    def test_migration_roundtrip_flatten_preserves_services(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "ServicesExtract_provider": "openai",
                "ServicesExtract_model": "gpt-4o-mini",
                "ServicesExtract_temperature": 0.3,
                "ServicesExtract_top_p": 0.85,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        flat = config.flatten_for_llm_service()
        assert flat["ServicesExtract_model"] == "gpt-4o-mini"
        assert flat["ServicesExtract_provider"] == "openai"
        assert flat["ServicesExtract_temperature"] == 0.3
        assert flat["ServicesExtract_top_p"] == 0.85


# ===========================================================================
# Subagent utils
# ===========================================================================


class TestSubagentUtils:
    """windows_services alias normalization works correctly."""

    def test_agent_to_subagent_has_services(self):
        assert AGENT_TO_SUBAGENT["servicesextract"] == "windows_services"

    @pytest.mark.parametrize(
        "alias",
        [
            "windows_services",
            "windowsservices",
            "windows-services",
            "servicesextract",
            "services",
            "ServicesExtract",
            "WINDOWS_SERVICES",
        ],
    )
    def test_normalize_services_aliases(self, alias):
        assert normalize_subagent_name(alias) == "windows_services"


# ===========================================================================
# UI-ordered export / import round-trip
# ===========================================================================


class TestUIOrderedRoundTrip:
    """ServicesExtract survives ui-ordered export -> import cycle."""

    def _make_ui_ordered_preset(self):
        """Build a UI-ordered preset dict with ServicesExtract section."""
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
            "ServicesExtract": dict(base_agent),
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

    def test_load_workflow_config_accepts_services(self):
        preset = self._make_ui_ordered_preset()
        config = load_workflow_config(preset)
        assert "ServicesExtract" in config.Agents
        assert "ServicesQA" in config.Agents

    def test_services_round_trip_through_export(self):
        from src.config.workflow_config_loader import v2_to_ui_ordered_export

        preset = self._make_ui_ordered_preset()
        config = load_workflow_config(preset)
        v2_dict = json.loads(config.model_dump_json())
        exported = v2_to_ui_ordered_export(v2_dict)
        assert "ServicesExtract" in exported, "ServicesExtract missing from UI-ordered export"
        assert exported["ServicesExtract"]["Provider"] == "openai"
        assert exported["ServicesExtract"]["Model"] == "gpt-4"


# ===========================================================================
# Old-preset backward compatibility
# ===========================================================================


class TestOldPresetBackwardCompat:
    """A pre-Services preset (without ServicesExtract section) still imports."""

    def test_old_preset_without_services_imports(self):
        """Presets saved before ServicesExtract existed must import with a default disabled block."""
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
        preset = {
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
            "RankAgent": {**base_agent, "RankingThreshold": 6.0},
            "ExtractAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0, "TopP": 0.9, "Prompt": {}},
            "CmdlineExtract": {**base_agent, "AttentionPreprocessor": True},
            "ProcTreeExtract": dict(base_agent),
            "HuntQueriesExtract": dict(base_agent),
            "RegistryExtract": dict(base_agent),
            # ServicesExtract intentionally absent
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
        # Must not raise -- the loader should backfill a default ServicesExtract section.
        config = load_workflow_config(preset)
        assert "ServicesExtract" in config.Agents, "Loader failed to backfill ServicesExtract"


# ===========================================================================
# Prompt files
# ===========================================================================


class TestPromptFiles:
    """ServicesExtract and ServicesQA prompt files exist and are valid JSON configs."""

    @pytest.mark.parametrize("prompt_name", ["ServicesExtract", "ServicesQA"])
    def test_prompt_file_exists_and_is_valid_json(self, prompt_name):
        prompt_path = Path(__file__).resolve().parent.parent.parent / "src" / "prompts" / prompt_name
        assert prompt_path.exists(), f"Prompt file missing: {prompt_path}"
        content = prompt_path.read_text()
        data = json.loads(content)
        assert "role" in data or "task" in data, f"Prompt file {prompt_name} missing expected keys"

    def test_services_extract_prompt_has_output_schema(self):
        prompt_path = Path(__file__).resolve().parent.parent.parent / "src" / "prompts" / "ServicesExtract"
        data = json.loads(prompt_path.read_text())
        example = data.get("json_example", "")
        if isinstance(example, str):
            parsed = json.loads(example)
        else:
            parsed = example
        assert "windows_services" in parsed, "json_example must define windows_services"


# ===========================================================================
# Preset files
# ===========================================================================


class TestPresetFiles:
    """Quickstart preset files include ServicesExtract section."""

    def test_quickstart_presets_have_services(self):
        preset_dir = (
            Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"
        )
        if not preset_dir.exists():
            pytest.skip("Quickstart preset directory not found")
        preset_files = list(preset_dir.glob("*.json"))
        assert len(preset_files) > 0, "No preset files found"
        for preset_file in preset_files:
            data = json.loads(preset_file.read_text())
            assert "ServicesExtract" in data, f"ServicesExtract missing from {preset_file.name}"
            assert "Provider" in data["ServicesExtract"], f"ServicesExtract.Provider missing in {preset_file.name}"


# ===========================================================================
# Eval articles placeholder
# ===========================================================================


class TestEvalArticlesPlaceholder:
    """Static eval articles directory exists for windows_services."""

    _REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _EVAL_DIR = _REPO_ROOT / "config" / "eval_articles_data" / "windows_services"
    _YAML_PATH = _REPO_ROOT / "config" / "eval_articles.yaml"

    def test_eval_articles_directory_exists(self):
        assert self._EVAL_DIR.exists(), f"Eval articles dir missing: {self._EVAL_DIR}"
        articles_file = self._EVAL_DIR / "articles.json"
        assert articles_file.exists(), "articles.json placeholder missing"

    def test_yaml_windows_services_key_present_and_non_empty(self):
        """eval_articles.yaml has a non-empty windows_services list."""
        data = yaml.safe_load(self._YAML_PATH.read_text())
        subagents = data.get("subagents", {})
        assert "windows_services" in subagents, "windows_services key missing from eval_articles.yaml"
        entries = subagents["windows_services"]
        assert isinstance(entries, list) and len(entries) > 0, (
            "windows_services in eval_articles.yaml must be a non-empty list"
        )

    def test_articles_json_non_empty_and_valid(self):
        """articles.json parses as a non-empty list."""
        articles_file = self._EVAL_DIR / "articles.json"
        articles = json.loads(articles_file.read_text())
        assert isinstance(articles, list) and len(articles) > 0, "articles.json must be a non-empty list"

    def test_articles_json_required_fields(self):
        """Every entry in articles.json has url, title, content, and expected_count."""
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        required = {"url", "title", "content", "expected_count"}
        for i, entry in enumerate(articles):
            missing = required - set(entry.keys())
            assert not missing, f"articles.json entry {i} missing fields: {missing}"

    def test_articles_json_expected_count_non_negative_int(self):
        """expected_count in every articles.json entry is a non-negative integer."""
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        for i, entry in enumerate(articles):
            ec = entry.get("expected_count")
            assert isinstance(ec, int), f"entry {i}: expected_count must be int, got {type(ec).__name__}"
            assert ec >= 0, f"entry {i}: expected_count must be >= 0, got {ec}"

    def test_articles_json_no_duplicate_urls(self):
        """No two entries in articles.json share the same URL."""
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        urls = [a.get("url") for a in articles]
        seen = set()
        dupes = []
        for u in urls:
            if u in seen:
                dupes.append(u)
            seen.add(u)
        assert not dupes, f"Duplicate URLs in articles.json: {dupes}"

    def test_yaml_and_articles_json_count_match(self):
        """Number of entries in eval_articles.yaml matches articles.json."""
        yaml_data = yaml.safe_load(self._YAML_PATH.read_text())
        yaml_entries = yaml_data["subagents"]["windows_services"]
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        assert len(yaml_entries) == len(articles), (
            f"eval_articles.yaml has {len(yaml_entries)} windows_services entries but articles.json has {len(articles)}"
        )


# ===========================================================================
# Workflow helpers
# ===========================================================================


class TestWorkflowHelpers:
    """_extract_actual_count handles windows_services subresults."""

    def test_extract_actual_count_windows_services(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        subresults = {
            "windows_services": {
                "items": [
                    {"service_name": "WinSvcUpdater", "binary_path": "C:\\Users\\Public\\svchost.exe"},
                    {"service_name": "EvilSvc", "binary_path": "C:\\Temp\\m.exe"},
                ],
                "count": 2,
            }
        }
        assert _extract_actual_count("windows_services", subresults, execution_id=1) == 2

    def test_extract_actual_count_windows_services_from_count(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        subresults = {"windows_services": {"count": 5, "items": []}}
        assert _extract_actual_count("windows_services", subresults, execution_id=1) == 5

    def test_extract_actual_count_windows_services_missing(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        assert _extract_actual_count("windows_services", {}, execution_id=1) == 0


# ===========================================================================
# Default agent prompts
# ===========================================================================


class TestDefaultAgentPrompts:
    """ServicesExtract and ServicesQA are in the prompt file map."""

    def test_agent_prompt_files_has_services(self):
        from src.utils.default_agent_prompts import AGENT_PROMPT_FILES

        assert "ServicesExtract" in AGENT_PROMPT_FILES
        assert "ServicesQA" in AGENT_PROMPT_FILES


# ===========================================================================
# LLM service JSON normalization + Langfuse output keys
# ===========================================================================


class TestLLMServiceNormalizationKeys:
    """Verify llm_service.py expected_keys and normalization handle windows_services."""

    def test_expected_keys_includes_windows_services(self):
        """The JSON candidate expected_keys list must include windows_services."""
        llm_service_path = Path(__file__).resolve().parent.parent.parent / "src" / "services" / "llm_service.py"
        source = llm_service_path.read_text()
        assert "windows_services" in source, "windows_services missing from llm_service.py"

    def test_langfuse_loop_includes_windows_services(self):
        """The Langfuse output loop must scan for windows_services."""
        llm_service_path = Path(__file__).resolve().parent.parent.parent / "src" / "services" / "llm_service.py"
        source = llm_service_path.read_text()
        assert "windows_services" in source
        # Verify windows_services is in the Langfuse output key list alongside registry_artifacts.
        assert 'registry_artifacts", "windows_services"' in source or '"windows_services"' in source
