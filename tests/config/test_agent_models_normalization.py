"""normalize_agent_models_to_flat: nested WorkflowConfigV2 -> flat LLMService keys.

Regression: nested format silently routed all LLM calls to LMStudio because every
flat-key lookup missed and `_canonicalize_provider("")` defaulted to "lmstudio".
"""

import pytest

from src.config.workflow_config_schema import (
    agent_models_is_nested,
    normalize_agent_models_to_flat,
)


class TestAgentModelsNormalization:
    def test_flat_input_returns_equivalent(self):
        flat = {
            "RankAgent": "gpt-4o",
            "RankAgent_provider": "openai",
            "RankAgent_temperature": 0.2,
            "CmdlineExtract_model": "gpt-4o-mini",
            "CmdlineExtract_provider": "openai",
        }
        out = normalize_agent_models_to_flat(flat)
        assert out == flat
        # Idempotent
        assert normalize_agent_models_to_flat(out) == out

    def test_nested_sub_agent_flattens(self):
        nested = {
            "CmdlineExtract": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "top_p": 0.95,
            }
        }
        out = normalize_agent_models_to_flat(nested)
        assert out == {
            "CmdlineExtract_provider": "openai",
            "CmdlineExtract_model": "gpt-4o-mini",
            "CmdlineExtract_temperature": 0.1,
            "CmdlineExtract_top_p": 0.95,
        }

    def test_nested_main_agent_uses_bare_model_key(self):
        # Main agents (Rank/Extract/Sigma) use the bare name as the model key,
        # matching WorkflowConfigV2.flatten_for_llm_service.
        nested = {"RankAgent": {"provider": "anthropic", "model": "claude-sonnet-4-5"}}
        out = normalize_agent_models_to_flat(nested)
        assert out == {"RankAgent_provider": "anthropic", "RankAgent": "claude-sonnet-4-5"}

    def test_nested_with_pascalcase_keys(self):
        # WorkflowConfigV2 uses PascalCase; accept those too.
        nested = {"ExtractAgent": {"Provider": "openai", "Model": "gpt-4o"}}
        out = normalize_agent_models_to_flat(nested)
        assert out == {"ExtractAgent_provider": "openai", "ExtractAgent": "gpt-4o"}

    def test_mixed_flat_and_nested(self):
        mixed = {
            "RankAgent": {"provider": "openai", "model": "gpt-4o"},
            "ExtractAgent_provider": "anthropic",
            "ExtractAgent": "claude-sonnet-4-5",
            "OSDetectionAgent_embedding": "ibm-research/CTI-BERT",
        }
        out = normalize_agent_models_to_flat(mixed)
        assert out["RankAgent_provider"] == "openai"
        assert out["RankAgent"] == "gpt-4o"
        assert out["ExtractAgent_provider"] == "anthropic"
        assert out["ExtractAgent"] == "claude-sonnet-4-5"
        assert out["OSDetectionAgent_embedding"] == "ibm-research/CTI-BERT"

    def test_empty_or_none_returns_empty(self):
        assert normalize_agent_models_to_flat(None) == {}
        assert normalize_agent_models_to_flat({}) == {}

    def test_non_agent_dict_values_preserved(self):
        # A dict that's not keyed by a known agent name shouldn't be unwrapped --
        # this avoids munging future scalar/dict additions like OS selection lists.
        data = {"OSDetectionAgent_selected_os": ["Windows", "Linux"]}
        out = normalize_agent_models_to_flat(data)
        assert out == data

    @pytest.mark.parametrize(
        "agent",
        [
            "CmdlineExtract",
            "ProcTreeExtract",
            "HuntQueriesExtract",
            "RegistryExtract",
            "ServicesExtract",
            "ScheduledTasksExtract",
        ],
    )
    def test_all_sub_agents_supported(self, agent):
        nested = {agent: {"provider": "openai", "model": "gpt-4o-mini"}}
        out = normalize_agent_models_to_flat(nested)
        assert out == {f"{agent}_provider": "openai", f"{agent}_model": "gpt-4o-mini"}


class TestAgentModelsIsNested:
    def test_flat_returns_false(self):
        assert not agent_models_is_nested({"CmdlineExtract_model": "x", "CmdlineExtract_provider": "openai"})

    def test_nested_returns_true(self):
        assert agent_models_is_nested({"CmdlineExtract": {"provider": "openai", "model": "x"}})

    def test_empty_returns_false(self):
        assert not agent_models_is_nested(None)
        assert not agent_models_is_nested({})

    def test_unknown_dict_key_returns_false(self):
        # A dict value under an unknown key (e.g. a future container) is not nested-agent format.
        assert not agent_models_is_nested({"SomeFutureKey": {"a": 1}})


class TestFlattenForLlmServiceParity:
    """Ensure normalize_agent_models_to_flat output matches WorkflowConfigV2.flatten_for_llm_service
    for the same logical config -- so the normalizer is a true equivalent, not just a near-match.
    """

    def test_matches_flatten_for_llm_service(self):
        from src.config.workflow_config_schema import (
            AgentConfig,
            EmbeddingsConfig,
            ExecutionConfig,
            ExtractAgentSettingsModel,
            MetadataConfig,
            PromptConfig,
            WorkflowConfigV2,
        )

        cfg = WorkflowConfigV2(
            Version="2.0",
            Metadata=MetadataConfig(),
            Agents={
                "RankAgent": AgentConfig(Provider="openai", Model="gpt-4o", Temperature=0.2, TopP=0.9, Enabled=True),
                "CmdlineExtract": AgentConfig(
                    Provider="anthropic", Model="claude-sonnet-4-5", Temperature=0.0, TopP=0.95, Enabled=True
                ),
            },
            Embeddings=EmbeddingsConfig(),
            Prompts={
                "RankAgent": PromptConfig(prompt="x", instructions="x"),
                "CmdlineExtract": PromptConfig(prompt="x", instructions="x"),
            },
            Execution=ExecutionConfig(ExtractAgentSettings=ExtractAgentSettingsModel(DisabledAgents=[])),
        )
        flat_from_method = cfg.flatten_for_llm_service()

        nested = {
            "RankAgent": {"provider": "openai", "model": "gpt-4o", "temperature": 0.2, "top_p": 0.9},
            "CmdlineExtract": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5",
                "temperature": 0.0,
                "top_p": 0.95,
            },
        }
        normalized = normalize_agent_models_to_flat(nested)

        # Every key the normalizer emits should match flatten_for_llm_service.
        for key, value in normalized.items():
            assert key in flat_from_method, f"{key} missing from flatten_for_llm_service output"
            assert flat_from_method[key] == value, f"{key}: {value!r} != {flat_from_method[key]!r}"
