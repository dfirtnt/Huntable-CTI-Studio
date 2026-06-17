"""Full-stack wiring tests for the NetworkIndicatorExtract sub-agent (literal, no QA)."""

import json
from pathlib import Path

import pytest
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
        "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
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
