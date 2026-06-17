"""Full-stack wiring tests for the NetworkIndicatorExtract sub-agent (literal, no QA)."""

import ast
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


def _extract_network_indicators_branch_body() -> list[ast.stmt]:
    """Pull the real `elif "network_indicators" in last_result:` branch body out of
    the live llm_service.py source via AST.

    The normalization ladder is inline (not a standalone callable), so we locate the
    actual branch in the shipped source and return its statements. This drives the
    real code rather than a hand-copied reproduction. Returns [] when the branch is
    absent (the RED state before the impl edit)."""
    tree = ast.parse(_LLM_SERVICE_PATH.read_text())

    def _tests_network_indicators(test: ast.expr) -> bool:
        # Matches: "network_indicators" in last_result
        return (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Constant)
            and test.left.value == "network_indicators"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.In)
            and isinstance(test.comparators[0], ast.Name)
            and test.comparators[0].id == "last_result"
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _tests_network_indicators(node.test):
            return node.body
    return []


class TestLLMServiceNormalization:
    """Real-behavior proof that llm_service.py normalizes the LLM `network_indicators`
    array to `items` (retaining the generic `value` field) for NetworkIndicatorExtract.

    The normalizer is inline inside a large async method (not callable in isolation),
    so we lift the actual branch body from the source via AST and execute it against a
    real result dict. This is a behavior assertion on the shipped code -- not a source
    substring check, and not a hand-rolled copy of the logic."""

    def test_network_indicators_branch_exists(self):
        assert _extract_network_indicators_branch_body(), (
            'llm_service.py has no `elif "network_indicators" in last_result:` normalization branch'
        )

    def test_branch_renames_array_to_items_and_keeps_value(self):
        body = _extract_network_indicators_branch_body()
        assert body, "network_indicators normalization branch missing from llm_service.py"

        # Execute the real branch statements against a representative LLM result.
        last_result = {
            "network_indicators": [
                {
                    "value": "evil[.]com",
                    "indicator_type": "domain",
                    "source_evidence": "beacons to evil[.]com",
                    "confidence_score": 0.9,
                }
            ],
            "count": 1,
        }

        class _Logger:
            def info(self, *_a, **_k):
                pass

            def warning(self, *_a, **_k):
                pass

        namespace = {
            "last_result": last_result,
            "agent_name": "NetworkIndicatorExtract",
            "logger": _Logger(),
            "len": len,
            "list": list,
        }
        module = ast.Module(body=body, type_ignores=[])
        exec(compile(module, str(_LLM_SERVICE_PATH), "exec"), namespace)  # noqa: S102

        last_result = namespace["last_result"]
        assert "network_indicators" not in last_result, "array was not renamed away"
        assert "items" in last_result, "array was not normalized to `items`"
        assert last_result["items"][0]["value"] == "evil[.]com", "generic value field lost"
