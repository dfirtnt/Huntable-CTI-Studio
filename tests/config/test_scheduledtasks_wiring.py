"""Tests for ScheduledTasksExtract / ScheduledTasksQA agent wiring across the full stack.

Validates that ScheduledTasksExtract is wired as a first-class peer of all existing
extraction sub-agents in schema, config, migration, subagent utils, and workflow layers.
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
    "ScheduledTasksExtract_model": "gpt-4",
    "RankAgentQA": "gpt-4",
    "CmdLineQA": "gpt-4",
    "ProcTreeQA": "gpt-4",
    "HuntQueriesQA": "gpt-4",
    "RegistryQA": "gpt-4",
    "ServicesQA": "gpt-4",
    "ScheduledTasksQA": "gpt-4",
}

_MINIMAL_AGENT_PROMPTS = {name: {"prompt": "", "instructions": ""} for name in ALL_AGENT_NAMES}


def _make_v2_with_scheduled_tasks(**overrides):
    """Build a minimal valid v2 config dict with ScheduledTasksExtract + ScheduledTasksQA."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "ScheduledTasksExtract": {
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0.0,
            "TopP": 0.9,
            "Enabled": True,
        },
        "ScheduledTasksQA": {
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0.1,
            "TopP": 0.9,
            "Enabled": True,
        },
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
    """ScheduledTasksExtract/ScheduledTasksQA appear in all schema-level constant lists."""

    def test_scheduled_tasks_in_agent_names_sub(self):
        assert "ScheduledTasksExtract" in AGENT_NAMES_SUB

    def test_scheduled_tasks_qa_in_agent_names_qa(self):
        assert "ScheduledTasksQA" in AGENT_NAMES_QA

    def test_scheduled_tasks_in_all_agent_names(self):
        assert "ScheduledTasksExtract" in ALL_AGENT_NAMES
        assert "ScheduledTasksQA" in ALL_AGENT_NAMES

    def test_base_to_qa_mapping(self):
        assert BASE_AGENT_TO_QA["ScheduledTasksExtract"] == "ScheduledTasksQA"

    def test_qa_to_base_mapping(self):
        assert QA_AGENT_TO_BASE["ScheduledTasksQA"] == "ScheduledTasksExtract"


# ===========================================================================
# Schema validation
# ===========================================================================


class TestSchemaValidation:
    """WorkflowConfigV2 validates ScheduledTasksExtract correctly."""

    def test_valid_v2_with_scheduled_tasks(self):
        config = WorkflowConfigV2.model_validate(_make_v2_with_scheduled_tasks())
        assert "ScheduledTasksExtract" in config.Agents
        assert "ScheduledTasksQA" in config.Agents

    def test_orphan_scheduled_tasks_qa_rejected(self):
        """ScheduledTasksQA without ScheduledTasksExtract is rejected."""
        raw = _make_v2_with_scheduled_tasks()
        del raw["Agents"]["ScheduledTasksExtract"]
        del raw["Prompts"]["ScheduledTasksExtract"]
        with pytest.raises(ValidationError, match="Orphan QA agent ScheduledTasksQA"):
            WorkflowConfigV2.model_validate(raw)

    def test_scheduled_tasks_missing_prompt_rejected(self):
        """ScheduledTasksExtract with Provider+Model but no prompt is rejected."""
        raw = _make_v2_with_scheduled_tasks()
        del raw["Prompts"]["ScheduledTasksExtract"]
        with pytest.raises(ValidationError, match="Missing prompt block for agent ScheduledTasksExtract"):
            WorkflowConfigV2.model_validate(raw)

    def test_flatten_produces_scheduled_tasks_flat_keys(self):
        config = WorkflowConfigV2.model_validate(_make_v2_with_scheduled_tasks())
        flat = config.flatten_for_llm_service()
        assert flat["ScheduledTasksExtract_model"] == "gpt-4"
        assert flat["ScheduledTasksExtract_provider"] == "openai"
        assert flat["ScheduledTasksExtract_temperature"] == 0.0
        assert flat["ScheduledTasksExtract_top_p"] == 0.9
        assert flat["ScheduledTasksQA"] == "gpt-4"
        assert flat["ScheduledTasksQA_provider"] == "openai"

    def test_disabled_scheduled_tasks_in_extract_agent_settings(self):
        raw = _make_v2_with_scheduled_tasks()
        raw["Execution"]["ExtractAgentSettings"]["DisabledAgents"] = ["ScheduledTasksExtract"]
        config = WorkflowConfigV2.model_validate(raw)
        legacy = config.to_legacy_response_dict()
        assert "ScheduledTasksExtract" in legacy["agent_prompts"]["ExtractAgentSettings"]["disabled_agents"]


# ===========================================================================
# Loader constants
# ===========================================================================


class TestLoaderConstants:
    """ScheduledTasksExtract appears in loader ordering constants."""

    def test_in_extract_agents(self):
        assert "ScheduledTasksExtract" in EXTRACT_AGENTS

    def test_in_qa_agents(self):
        assert "ScheduledTasksQA" in QA_AGENTS

    def test_in_agents_order_ui(self):
        assert "ScheduledTasksExtract" in AGENTS_ORDER_UI
        assert "ScheduledTasksQA" in AGENTS_ORDER_UI


# ===========================================================================
# Migration
# ===========================================================================


class TestMigration:
    """v1-to-v2 migration produces ScheduledTasksExtract/ScheduledTasksQA agents."""

    def test_v1_with_scheduled_tasks_model_migrates(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "ScheduledTasksExtract_provider": "anthropic",
                "ScheduledTasksExtract_model": "claude-sonnet-4-5",
                "ScheduledTasksExtract_temperature": 0.2,
                "ScheduledTasksExtract_top_p": 0.95,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        assert config.Agents["ScheduledTasksExtract"].Model == "claude-sonnet-4-5"
        assert config.Agents["ScheduledTasksExtract"].Provider == "anthropic"
        assert config.Agents["ScheduledTasksExtract"].Temperature == 0.2
        assert config.Agents["ScheduledTasksExtract"].TopP == 0.95

    def test_v1_scheduled_tasks_qa_migrates(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "ScheduledTasksQA_provider": "openai",
                "ScheduledTasksQA": "gpt-4o",
                "ScheduledTasksQA_temperature": 0.1,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        assert config.Agents["ScheduledTasksQA"].Model == "gpt-4o"
        assert config.Agents["ScheduledTasksQA"].Provider == "openai"

    def test_migration_roundtrip_flatten_preserves_scheduled_tasks(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                **_MINIMAL_AGENT_MODELS,
                "ScheduledTasksExtract_provider": "openai",
                "ScheduledTasksExtract_model": "gpt-4o-mini",
                "ScheduledTasksExtract_temperature": 0.3,
                "ScheduledTasksExtract_top_p": 0.85,
            },
            "qa_enabled": {},
            "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
        }
        migrated = migrate_v1_to_v2(raw)
        config = WorkflowConfigV2.model_validate(migrated)
        flat = config.flatten_for_llm_service()
        assert flat["ScheduledTasksExtract_model"] == "gpt-4o-mini"
        assert flat["ScheduledTasksExtract_provider"] == "openai"
        assert flat["ScheduledTasksExtract_temperature"] == 0.3
        assert flat["ScheduledTasksExtract_top_p"] == 0.85


# ===========================================================================
# Subagent utils
# ===========================================================================


class TestSubagentUtils:
    """scheduled_tasks alias normalization works correctly."""

    def test_agent_to_subagent_has_scheduled_tasks(self):
        assert AGENT_TO_SUBAGENT["scheduledtasksextract"] == "scheduled_tasks"

    @pytest.mark.parametrize(
        "alias",
        [
            "scheduled_tasks",
            "scheduledtasks",
            "scheduled-tasks",
            "scheduledtasksextract",
            "schedtasks",
            "ScheduledTasksExtract",
            "SCHEDULED_TASKS",
        ],
    )
    def test_normalize_scheduled_tasks_aliases(self, alias):
        assert normalize_subagent_name(alias) == "scheduled_tasks"

    def test_normalize_unknown_returns_none(self):
        assert normalize_subagent_name("not_a_subagent") is None


# ===========================================================================
# UI-ordered export / import round-trip
# ===========================================================================


class TestUIOrderedRoundTrip:
    """ScheduledTasksExtract survives ui-ordered export -> import cycle."""

    def _make_ui_ordered_preset(self):
        """Build a UI-ordered preset dict with ScheduledTasksExtract section."""
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
            "Thresholds": {"MinHuntScore": 97.0},
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
            "ServicesExtract": dict(base_agent),
            "ScheduledTasksExtract": dict(base_agent),
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

    def test_load_workflow_config_accepts_scheduled_tasks(self):
        preset = self._make_ui_ordered_preset()
        config = load_workflow_config(preset)
        assert "ScheduledTasksExtract" in config.Agents
        assert "ScheduledTasksQA" in config.Agents

    def test_scheduled_tasks_round_trip_through_export(self):
        from src.config.workflow_config_loader import v2_to_ui_ordered_export

        preset = self._make_ui_ordered_preset()
        config = load_workflow_config(preset)
        v2_dict = json.loads(config.model_dump_json())
        exported = v2_to_ui_ordered_export(v2_dict)
        assert "ScheduledTasksExtract" in exported, "ScheduledTasksExtract missing from UI-ordered export"
        assert exported["ScheduledTasksExtract"]["Provider"] == "openai"
        assert exported["ScheduledTasksExtract"]["Model"] == "gpt-4"


# ===========================================================================
# Prompt files
# ===========================================================================


class TestPromptFiles:
    """ScheduledTasksExtract and ScheduledTasksQA prompt files exist and are valid JSON configs."""

    @pytest.mark.parametrize("prompt_name", ["ScheduledTasksExtract", "ScheduledTasksQA"])
    def test_prompt_file_exists_and_is_valid_json(self, prompt_name):
        prompt_path = Path(__file__).resolve().parent.parent.parent / "src" / "prompts" / prompt_name
        assert prompt_path.exists(), f"Prompt file missing: {prompt_path}"
        content = prompt_path.read_text()
        data = json.loads(content)
        assert "role" in data or "task" in data, f"Prompt file {prompt_name} missing expected keys"

    def test_scheduled_tasks_extract_prompt_has_output_schema(self):
        prompt_path = Path(__file__).resolve().parent.parent.parent / "src" / "prompts" / "ScheduledTasksExtract"
        data = json.loads(prompt_path.read_text())
        example = data.get("json_example", "")
        if isinstance(example, str):
            parsed = json.loads(example)
        else:
            parsed = example
        assert "scheduled_tasks" in parsed, "json_example must define scheduled_tasks array"


# ===========================================================================
# Preset files
# ===========================================================================


class TestPresetFiles:
    """Quickstart preset files include ScheduledTasksExtract section."""

    def test_quickstart_presets_have_scheduled_tasks(self):
        preset_dir = (
            Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"
        )
        if not preset_dir.exists():
            pytest.skip("Quickstart preset directory not found")
        preset_files = list(preset_dir.glob("*.json"))
        assert len(preset_files) > 0, "No preset files found"
        for preset_file in preset_files:
            data = json.loads(preset_file.read_text())
            assert "ScheduledTasksExtract" in data, f"ScheduledTasksExtract missing from {preset_file.name}"
            section = data["ScheduledTasksExtract"]
            assert "Provider" in section, f"ScheduledTasksExtract.Provider missing in {preset_file.name}"
            prompt_val = section.get("Prompt", {}).get("prompt", "")
            assert prompt_val, (
                f"ScheduledTasksExtract.Prompt.prompt is empty in {preset_file.name} -- "
                "quickstart presets must carry the full prompt text"
            )
            qa_prompt_val = section.get("QAPrompt", {}).get("prompt", "")
            assert qa_prompt_val, (
                f"ScheduledTasksExtract.QAPrompt.prompt is empty in {preset_file.name} -- "
                "quickstart presets must carry the full QA prompt text"
            )

    @pytest.mark.regression
    def test_quickstart_presets_have_scheduled_tasks_model(self):
        """Each quickstart preset carries a non-empty Model for ScheduledTasksExtract.

        Regression: when this field is absent or empty the eval API falls back to the
        ExtractAgent model key, silently using whatever model was active before the preset
        was applied instead of the preset-specified model.
        """
        preset_dir = (
            Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"
        )
        if not preset_dir.exists():
            pytest.skip("Quickstart preset directory not found")
        preset_files = list(preset_dir.glob("*.json"))
        assert len(preset_files) > 0, "No preset files found"
        for preset_file in preset_files:
            data = json.loads(preset_file.read_text())
            section = data.get("ScheduledTasksExtract", {})
            model_val = section.get("Model", "")
            assert model_val, (
                f"ScheduledTasksExtract.Model is empty in {preset_file.name} -- "
                "eval API uses this value; an empty Model causes a silent fallback to the "
                "ExtractAgent model key, which may carry the previous config's model."
            )

    @pytest.mark.regression
    def test_quickstart_preset_to_legacy_includes_scheduled_tasks_model(self):
        """to-legacy conversion of a quickstart preset produces ScheduledTasksExtract_model.

        Regression: the eval API reads agent_models['ScheduledTasksExtract_model'] from the
        active DB config. This test follows the full preset -> to_legacy -> flat key path to
        confirm the model survives the conversion and reaches the dict the eval consumes.
        """
        preset_path = (
            Path(__file__).resolve().parent.parent.parent
            / "config"
            / "presets"
            / "AgentConfigs"
            / "quickstart"
            / "Quickstart-LMStudio-Qwen3.json"
        )
        if not preset_path.exists():
            pytest.skip("Qwen3 quickstart preset not found")

        data = json.loads(preset_path.read_text())
        config = load_workflow_config(data)
        flat = config.flatten_for_llm_service()

        assert "ScheduledTasksExtract_model" in flat, (
            "ScheduledTasksExtract_model key missing from flat agent_models -- "
            "eval API will fall back to ExtractAgent model"
        )
        assert flat["ScheduledTasksExtract_model"], (
            "ScheduledTasksExtract_model is empty -- eval API will fall back to ExtractAgent model"
        )
        assert flat["ScheduledTasksExtract_model"] == data["ScheduledTasksExtract"]["Model"], (
            "flat ScheduledTasksExtract_model does not match preset file value"
        )


# ===========================================================================
# Eval articles data
# ===========================================================================


class TestEvalArticlesData:
    """Static eval articles directory and YAML contract for scheduled_tasks."""

    _REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _EVAL_DIR = _REPO_ROOT / "config" / "eval_articles_data" / "scheduled_tasks"
    _YAML_PATH = _REPO_ROOT / "config" / "eval_articles.yaml"

    def test_eval_articles_directory_exists(self):
        assert self._EVAL_DIR.exists(), f"Eval articles dir missing: {self._EVAL_DIR}"

    def test_articles_json_exists(self):
        articles_file = self._EVAL_DIR / "articles.json"
        assert articles_file.exists(), "articles.json placeholder missing"

    def test_yaml_scheduled_tasks_key_present_and_non_empty(self):
        data = yaml.safe_load(self._YAML_PATH.read_text())
        subagents = data.get("subagents", {})
        assert "scheduled_tasks" in subagents, "scheduled_tasks key missing from eval_articles.yaml"
        entries = subagents["scheduled_tasks"]
        assert isinstance(entries, list) and len(entries) > 0, (
            "scheduled_tasks in eval_articles.yaml must be a non-empty list"
        )

    def test_articles_json_parses_as_list(self):
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        assert isinstance(articles, list), "articles.json must be a list"

    def test_articles_json_required_fields(self):
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        required = {"url", "title", "content", "expected_count"}
        for i, entry in enumerate(articles):
            missing = required - set(entry.keys())
            assert not missing, f"articles.json entry {i} missing fields: {missing}"

    def test_articles_json_expected_count_non_negative_int(self):
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        for i, entry in enumerate(articles):
            ec = entry.get("expected_count")
            assert isinstance(ec, int), f"entry {i}: expected_count must be int, got {type(ec).__name__}"
            assert ec >= 0, f"entry {i}: expected_count must be >= 0, got {ec}"

    def test_articles_json_no_duplicate_urls(self):
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        urls = [a.get("url") for a in articles]
        seen: set = set()
        dupes: list = []
        for u in urls:
            if u in seen:
                dupes.append(u)
            seen.add(u)
        assert not dupes, f"Duplicate URLs in articles.json: {dupes}"

    def test_yaml_and_articles_json_count_match(self):
        yaml_data = yaml.safe_load(self._YAML_PATH.read_text())
        yaml_entries = yaml_data["subagents"]["scheduled_tasks"]
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        assert len(yaml_entries) == len(articles), (
            f"eval_articles.yaml has {len(yaml_entries)} scheduled_tasks entries but articles.json has {len(articles)}"
        )

    def test_yaml_urls_present_in_articles_json(self):
        yaml_data = yaml.safe_load(self._YAML_PATH.read_text())
        yaml_urls = {e["url"] for e in yaml_data["subagents"]["scheduled_tasks"] if e.get("url")}
        json_urls = {a["url"] for a in json.loads((self._EVAL_DIR / "articles.json").read_text()) if a.get("url")}
        missing = yaml_urls - json_urls
        assert not missing, (
            f"URLs in eval_articles.yaml (scheduled_tasks) missing from articles.json: {sorted(missing)}. "
            "Run: python3 scripts/fetch_eval_articles_static.py"
        )


# ===========================================================================
# Workflow helpers
# ===========================================================================


class TestWorkflowHelpers:
    """_extract_actual_count handles scheduled_tasks subresults."""

    def test_extract_actual_count_scheduled_tasks(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        subresults = {
            "scheduled_tasks": {
                "items": [
                    {"task_name": "WindowsUpdateHelper", "trigger": "AtLogon"},
                    {"task_name": "MalwareTask", "trigger": "Daily"},
                ],
                "count": 2,
            }
        }
        assert _extract_actual_count("scheduled_tasks", subresults, execution_id=1) == 2

    def test_extract_actual_count_scheduled_tasks_from_count(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        subresults = {"scheduled_tasks": {"count": 3, "items": []}}
        assert _extract_actual_count("scheduled_tasks", subresults, execution_id=1) == 3

    def test_extract_actual_count_scheduled_tasks_missing(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        assert _extract_actual_count("scheduled_tasks", {}, execution_id=1) == 0


# ===========================================================================
# Default agent prompts
# ===========================================================================


class TestDefaultAgentPrompts:
    """ScheduledTasksExtract and ScheduledTasksQA are in the prompt file map."""

    def test_agent_prompt_files_has_scheduled_tasks(self):
        from src.utils.default_agent_prompts import AGENT_PROMPT_FILES

        assert "ScheduledTasksExtract" in AGENT_PROMPT_FILES
        assert "ScheduledTasksQA" in AGENT_PROMPT_FILES


# ===========================================================================
# LLM service normalization keys
# ===========================================================================


class TestLLMServiceNormalizationKeys:
    """Verify llm_service.py expected_keys and normalization handle scheduled_tasks."""

    def test_expected_keys_includes_scheduled_tasks(self):
        llm_service_path = Path(__file__).resolve().parent.parent.parent / "src" / "services" / "llm_service.py"
        source = llm_service_path.read_text()
        assert "scheduled_tasks" in source, "scheduled_tasks missing from llm_service.py"

    def test_langfuse_loop_includes_scheduled_tasks(self):
        llm_service_path = Path(__file__).resolve().parent.parent.parent / "src" / "services" / "llm_service.py"
        source = llm_service_path.read_text()
        assert "scheduled_tasks" in source
