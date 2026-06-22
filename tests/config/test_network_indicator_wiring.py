"""Full-stack wiring tests for the NetworkIndicatorExtract sub-agent (literal, no QA)."""

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.config.workflow_config_loader import (
    AGENTS_ORDER_UI,
    EXTRACT_AGENTS,
)
from src.config.workflow_config_migrate import migrate_v1_to_v2
from src.config.workflow_config_schema import (
    AGENT_NAMES_SUB,
    ALL_AGENT_NAMES,
    WorkflowConfigV2,
)
from src.utils.subagent_utils import AGENT_TO_SUBAGENT, normalize_subagent_name

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parent.parent.parent


def _make_v2():
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "NetworkIndicatorExtract": {
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0.0,
            "TopP": 0.9,
            "Enabled": True,
        },
    }
    prompts = {k: {"prompt": "", "instructions": ""} for k in agents}
    return {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "", "Description": ""},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
        },
        "Agents": agents,
        "Embeddings": {"Sigma": "ibm-research/CTI-BERT"},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": prompts,
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }


class TestSchemaConstants:
    def test_in_agent_names_sub(self):
        assert "NetworkIndicatorExtract" in AGENT_NAMES_SUB

    def test_in_all_agent_names(self):
        assert "NetworkIndicatorExtract" in ALL_AGENT_NAMES


class TestSchemaValidation:
    def test_valid_v2(self):
        config = WorkflowConfigV2.model_validate(_make_v2())
        assert "NetworkIndicatorExtract" in config.Agents

    def test_missing_prompt_rejected(self):
        raw = _make_v2()
        del raw["Prompts"]["NetworkIndicatorExtract"]
        with pytest.raises(ValidationError, match="Missing prompt block for agent NetworkIndicatorExtract"):
            WorkflowConfigV2.model_validate(raw)

    def test_flatten_keys(self):
        flat = WorkflowConfigV2.model_validate(_make_v2()).flatten_for_llm_service()
        assert flat["NetworkIndicatorExtract_model"] == "gpt-4"
        assert flat["NetworkIndicatorExtract_provider"] == "openai"


class TestLoaderConstants:
    def test_in_extract_agents(self):
        assert "NetworkIndicatorExtract" in EXTRACT_AGENTS

    def test_in_agents_order_ui(self):
        assert "NetworkIndicatorExtract" in AGENTS_ORDER_UI


class TestMigration:
    def test_v1_migrates(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                "RankAgent_provider": "openai",
                "RankAgent": "gpt-4",
                "ExtractAgent": "gpt-4",
                "SigmaAgent": "gpt-4",
                "NetworkIndicatorExtract_provider": "anthropic",
                "NetworkIndicatorExtract_model": "claude-sonnet-4-5",
                "NetworkIndicatorExtract_temperature": 0.2,
                "NetworkIndicatorExtract_top_p": 0.95,
            },
            "agent_prompts": {n: {"prompt": "", "instructions": ""} for n in ALL_AGENT_NAMES},
        }
        config = WorkflowConfigV2.model_validate(migrate_v1_to_v2(raw))
        assert config.Agents["NetworkIndicatorExtract"].Model == "claude-sonnet-4-5"
        assert config.Agents["NetworkIndicatorExtract"].Provider == "anthropic"


class TestSubagentUtils:
    def test_agent_to_subagent(self):
        assert AGENT_TO_SUBAGENT["networkindicatorextract"] == "network_indicators"

    @pytest.mark.parametrize(
        "alias",
        [
            "network_indicators",
            "networkindicators",
            "network-indicators",
            "networkindicatorextract",
            "network",
            "NetworkIndicatorExtract",
            "NETWORK_INDICATORS",
        ],
    )
    def test_normalize_aliases(self, alias):
        assert normalize_subagent_name(alias) == "network_indicators"

    def test_unknown_returns_none(self):
        assert normalize_subagent_name("not_a_subagent") is None


class TestPromptFile:
    def test_exists_valid_and_value_field(self):
        path = _REPO / "src" / "prompts" / "NetworkIndicatorExtract"
        assert path.exists()
        data = json.loads(path.read_text())
        ex = data["json_example"]
        parsed = json.loads(ex) if isinstance(ex, str) else ex
        assert "network_indicators" in parsed
        assert parsed["network_indicators"][0]["value"], "simple extractor items must carry a non-empty value"


class TestDefaultAgentPrompts:
    def test_in_agent_prompt_files(self):
        from src.utils.default_agent_prompts import AGENT_PROMPT_FILES

        assert "NetworkIndicatorExtract" in AGENT_PROMPT_FILES


_LLM_SERVICE_PATH = _REPO / "src" / "services" / "llm_service.py"


class TestLLMServiceNormalization:
    """NetworkIndicatorExtract is wired into llm_service.py's normalization path.

    Source-presence checks, matching the sibling convention (see
    test_scheduledtasks_wiring.py::TestLLMServiceNormalizationKeys): the inline
    normalization ladder is not a standalone callable, so wiring tests assert presence
    here while the rename *behavior* is exercised by integration/e2e tests that run real
    extraction. The branch is a verbatim mirror of the working sibling branches.
    """

    def test_normalization_branch_present(self):
        source = _LLM_SERVICE_PATH.read_text()
        assert 'elif "network_indicators" in last_result' in source, (
            "llm_service.py missing the network_indicators -> items normalization branch"
        )

    def test_simple_extractor_and_array_key_present(self):
        source = _LLM_SERVICE_PATH.read_text()
        # value-carrying simple extractor (agent name) + recognized LLM array key
        assert '"NetworkIndicatorExtract"' in source
        assert '"network_indicators"' in source


class TestWorkflowHelpers:
    def test_extract_actual_count(self):
        from src.workflows.agentic_workflow import _extract_actual_count

        subresults = {
            "network_indicators": {
                "items": [
                    {"value": "evil[.]com", "indicator_type": "domain"},
                    {"value": "8.8.8[.]8", "indicator_type": "ip"},
                ],
                "count": 2,
            }
        }
        assert _extract_actual_count("network_indicators", subresults, execution_id=1) == 2

    def test_extract_actual_items_reads_value(self):
        from src.workflows.agentic_workflow import _extract_actual_items

        subresults = {
            "network_indicators": {
                "items": [{"value": "evil[.]com", "indicator_type": "domain"}],
                "count": 1,
            }
        }
        items = _extract_actual_items("network_indicators", subresults)
        assert items == ["evil[.]com"]


class TestPresetFiles:
    """NetworkIndicatorExtract must be present in every quickstart preset with valid config."""

    _QUICKSTART_DIR = _REPO / "config" / "presets" / "AgentConfigs" / "quickstart"
    _PRESETS = sorted(_QUICKSTART_DIR.glob("*.json"))

    @pytest.mark.parametrize("preset_path", _PRESETS, ids=lambda p: p.stem)
    def test_nie_present(self, preset_path):
        data = json.loads(preset_path.read_text())
        assert "NetworkIndicatorExtract" in data, f"{preset_path.name}: NetworkIndicatorExtract section missing"

    @pytest.mark.parametrize("preset_path", _PRESETS, ids=lambda p: p.stem)
    def test_nie_model_non_empty(self, preset_path):
        data = json.loads(preset_path.read_text())
        section = data.get("NetworkIndicatorExtract", {})
        assert section.get("Model", ""), f"{preset_path.name}: NetworkIndicatorExtract.Model is empty"

    @pytest.mark.parametrize("preset_path", _PRESETS, ids=lambda p: p.stem)
    def test_nie_prompt_non_empty(self, preset_path):
        data = json.loads(preset_path.read_text())
        section = data.get("NetworkIndicatorExtract", {})
        prompt = section.get("Prompt", {})
        assert prompt.get("prompt", ""), f"{preset_path.name}: NetworkIndicatorExtract.Prompt.prompt is empty"

    @pytest.mark.parametrize("preset_path", _PRESETS, ids=lambda p: p.stem)
    def test_nie_no_qa(self, preset_path):
        data = json.loads(preset_path.read_text())
        section = data.get("NetworkIndicatorExtract", {})
        assert "QAEnabled" not in section and "QA" not in section, (
            f"{preset_path.name}: NetworkIndicatorExtract must not have QA keys"
        )


# ===========================================================================
# Eval articles data
# ===========================================================================


class TestEvalArticlesData:
    """Static eval articles directory and YAML contract for network_indicators."""

    _REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _EVAL_DIR = _REPO_ROOT / "config" / "eval_articles_data" / "network_indicators"
    _YAML_PATH = _REPO_ROOT / "config" / "eval_articles.yaml"

    def test_eval_articles_directory_exists(self):
        assert self._EVAL_DIR.exists(), f"Eval articles dir missing: {self._EVAL_DIR}"

    def test_articles_json_exists(self):
        articles_file = self._EVAL_DIR / "articles.json"
        assert articles_file.exists(), "articles.json missing"

    def test_yaml_network_indicators_key_present_and_non_empty(self):
        data = yaml.safe_load(self._YAML_PATH.read_text())
        subagents = data.get("subagents", {})
        assert "network_indicators" in subagents, "network_indicators key missing from eval_articles.yaml"
        entries = subagents["network_indicators"]
        assert isinstance(entries, list) and len(entries) > 0, (
            "network_indicators in eval_articles.yaml must be a non-empty list"
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
            assert isinstance(entry["url"], str) and entry["url"].startswith(("http://", "https://")), (
                f"entry {i}: url must be an http(s) URL"
            )
            assert isinstance(entry["title"], str) and entry["title"].strip(), f"entry {i}: title must be non-empty"
            assert isinstance(entry["content"], str) and entry["content"].strip(), (
                f"entry {i}: content must be non-empty"
            )

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
        yaml_entries = yaml_data["subagents"]["network_indicators"]
        articles = json.loads((self._EVAL_DIR / "articles.json").read_text())
        assert len(yaml_entries) == len(articles), (
            f"eval_articles.yaml has {len(yaml_entries)} network_indicators entries "
            f"but articles.json has {len(articles)}"
        )

    def test_yaml_urls_present_in_articles_json(self):
        yaml_data = yaml.safe_load(self._YAML_PATH.read_text())
        yaml_urls = {e["url"] for e in yaml_data["subagents"]["network_indicators"] if e.get("url")}
        json_urls = {a["url"] for a in json.loads((self._EVAL_DIR / "articles.json").read_text()) if a.get("url")}
        missing = yaml_urls - json_urls
        assert not missing, (
            f"URLs in eval_articles.yaml (network_indicators) missing from articles.json: {sorted(missing)}"
        )

    def test_articles_json_urls_present_in_yaml(self):
        yaml_data = yaml.safe_load(self._YAML_PATH.read_text())
        yaml_urls = {e["url"] for e in yaml_data["subagents"]["network_indicators"] if e.get("url")}
        json_urls = {a["url"] for a in json.loads((self._EVAL_DIR / "articles.json").read_text()) if a.get("url")}
        extra = json_urls - yaml_urls
        assert not extra, f"URLs in articles.json missing from eval_articles.yaml (network_indicators): {sorted(extra)}"

    def test_yaml_and_articles_json_expected_counts_match_by_url(self):
        yaml_data = yaml.safe_load(self._YAML_PATH.read_text())
        yaml_counts = {
            e["url"]: e["expected_count"] for e in yaml_data["subagents"]["network_indicators"] if e.get("url")
        }
        json_counts = {
            a["url"]: a["expected_count"]
            for a in json.loads((self._EVAL_DIR / "articles.json").read_text())
            if a.get("url")
        }
        mismatches = {
            url: {"yaml": yaml_counts[url], "articles_json": json_counts[url]}
            for url in sorted(yaml_counts.keys() & json_counts.keys())
            if yaml_counts[url] != json_counts[url]
        }
        assert not mismatches, f"network_indicators expected_count mismatch by URL: {mismatches}"
