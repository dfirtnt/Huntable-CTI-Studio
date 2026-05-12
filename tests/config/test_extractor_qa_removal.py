"""Regression tests for the removal of per-extractor QA agents.

Covers:
  - Schema: AGENT_NAMES_QA contains only RankAgentQA; extractor QA names absent
  - Schema: BASE_AGENT_TO_QA maps only RankAgent -> RankAgentQA
  - Schema: WorkflowConfigV2 rejects CmdLineQA as an orphan agent
  - Migrate: _normalize_v2_strict strips all extractor QA agents from Agents,
    QA.Enabled, and Prompts in an old config
  - Migrate: normalized config validates cleanly as WorkflowConfigV2
  - Workflow: sub_agents list is 2-tuples (name, subresult_key) -- 3-tuple
    regression from the extractor QA removal
  - Default prompts: extractor QA agents absent from AGENT_PROMPT_FILES
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

_EXTRACTOR_QA_AGENTS = {
    "CmdLineQA",
    "CmdlineQA",
    "ProcTreeQA",
    "HuntQueriesQA",
    "RegistryQA",
    "ServicesQA",
    "ScheduledTasksQA",
}


# ---------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------


class TestSchemaQAContract:
    def test_agent_names_qa_contains_only_rank_agent_qa(self):
        from src.config.workflow_config_schema import AGENT_NAMES_QA

        assert AGENT_NAMES_QA == ["RankAgentQA"]

    def test_extractor_qa_agents_absent_from_agent_names_qa(self):
        from src.config.workflow_config_schema import AGENT_NAMES_QA

        for name in _EXTRACTOR_QA_AGENTS:
            assert name not in AGENT_NAMES_QA, f"{name} must not be in AGENT_NAMES_QA"

    def test_base_agent_to_qa_only_rank(self):
        from src.config.workflow_config_schema import BASE_AGENT_TO_QA

        assert BASE_AGENT_TO_QA == {"RankAgent": "RankAgentQA"}

    def test_extractor_qa_absent_from_all_agent_names(self):
        from src.config.workflow_config_schema import ALL_AGENT_NAMES

        for name in _EXTRACTOR_QA_AGENTS:
            assert name not in ALL_AGENT_NAMES, f"{name} must not be in ALL_AGENT_NAMES"

    def test_cmdline_qa_rejected_as_orphan(self):
        """CmdLineQA in Agents raises ValidationError (orphan QA -- base 'CmdLine' does not exist)."""
        from pydantic import ValidationError

        from src.config.workflow_config_schema import WorkflowConfigV2

        raw = {
            "Version": "2.0",
            "Metadata": {"CreatedAt": "", "Description": ""},
            "Thresholds": {
                "MinHuntScore": 97.0,
                "RankingThreshold": 6.0,
                "SimilarityThreshold": 0.5,
                "JunkFilterThreshold": 0.8,
            },
            "Agents": {
                "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
                "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
                "CmdLineQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            },
            "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
            "QA": {"Enabled": {}, "MaxRetries": 5},
            "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
            "Prompts": {
                "RankAgent": {"prompt": "", "instructions": ""},
                "RankAgentQA": {"prompt": "", "instructions": ""},
                "CmdLineQA": {"prompt": "", "instructions": ""},
            },
            "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
        }
        # Validation raises because CmdLineQA is no longer a canonical agent name
        # (caught at Prompts key validation or orphan QA check depending on ordering)
        with pytest.raises(ValidationError):
            WorkflowConfigV2.model_validate(raw)


# ---------------------------------------------------------------------------
# Migration backcompat
# ---------------------------------------------------------------------------


class TestMigrateStripsExtractorQAAgents:
    """_normalize_v2_strict must silently strip all extractor QA agents from old configs."""

    _OLD_V2 = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "", "Description": ""},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "RankAgentQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "CmdLineQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "ProcTreeQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "HuntQueriesQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "RegistryQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "ServicesQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "ScheduledTasksQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        },
        "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
        "QA": {
            "Enabled": {
                "CmdlineExtract": True,
                "ProcTreeExtract": False,
                "HuntQueriesExtract": True,
                "RegistryExtract": False,
                "ServicesExtract": False,
                "ScheduledTasksExtract": False,
            },
            "MaxRetries": 3,
        },
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {
            "RankAgent": {"prompt": "", "instructions": ""},
            "RankAgentQA": {"prompt": "", "instructions": ""},
            "CmdLineQA": {"prompt": "old_qa_prompt", "instructions": ""},
            "ProcTreeQA": {"prompt": "old_qa_prompt", "instructions": ""},
        },
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }

    def _normalize(self):
        from src.config.workflow_config_migrate import _normalize_v2_strict

        return _normalize_v2_strict(self._OLD_V2)

    def test_extractor_qa_stripped_from_agents(self):
        out = self._normalize()
        for name in _EXTRACTOR_QA_AGENTS:
            assert name not in out["Agents"], f"{name} should be stripped from Agents"

    def test_rank_agent_qa_preserved(self):
        out = self._normalize()
        assert "RankAgentQA" in out["Agents"]

    def test_extractor_qa_enabled_flags_stripped(self):
        out = self._normalize()
        enabled = out.get("QA", {}).get("Enabled", {})
        for extractor in ("CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract",
                          "RegistryExtract", "ServicesExtract", "ScheduledTasksExtract"):
            assert extractor not in enabled, f"QA.Enabled[{extractor}] should be stripped"

    def test_extractor_qa_prompts_stripped(self):
        out = self._normalize()
        prompts = out.get("Prompts", {})
        for name in _EXTRACTOR_QA_AGENTS:
            assert name not in prompts, f"Prompts[{name}] should be stripped"

    def test_normalized_config_validates_as_v2(self):
        from src.config.workflow_config_schema import WorkflowConfigV2

        out = self._normalize()
        config = WorkflowConfigV2.model_validate(out)
        assert config.Version == "2.0"


# ---------------------------------------------------------------------------
# Default agent prompts
# ---------------------------------------------------------------------------


class TestDefaultAgentPromptsClean:
    def test_extractor_qa_absent_from_agent_prompt_files(self):
        from src.utils.default_agent_prompts import AGENT_PROMPT_FILES

        for name in _EXTRACTOR_QA_AGENTS:
            assert name not in AGENT_PROMPT_FILES, f"{name} must not be in AGENT_PROMPT_FILES"


# ---------------------------------------------------------------------------
# Agentic workflow sub_agents arity
# ---------------------------------------------------------------------------


class TestSubAgentsTupleArity:
    """Regression: sub_agents must be 2-tuples after extractor QA removal.

    The previous implementation had 3-tuples (name, subresult_key, qa_name).
    Removing qa_name changed them to 2-tuples, but several log lines and a
    loop in the eval-filtering path still unpacked 3 elements, which would
    crash every subagent eval run. This test catches any regression.
    """

    def test_no_three_element_unpack_on_sub_agents(self):
        """No remaining 3-element tuple unpacking on sub_agents or original_sub_agents."""
        import re
        import pathlib

        source = pathlib.Path("src/workflows/agentic_workflow.py").read_text()

        bad_patterns = [
            r"for\s+\w+,\s*\w+,\s*_\s+in\s+sub_agents",
            r"for\s+\w+,\s*_,\s*_\s+in\s+sub_agents",
            r"for\s+\w+,\s*\w+,\s*_\s+in\s+original_sub_agents",
            r"for\s+\w+,\s*_,\s*_\s+in\s+original_sub_agents",
        ]
        for pattern in bad_patterns:
            matches = re.findall(pattern, source)
            assert not matches, (
                f"Found 3-element tuple unpack on sub_agents: {matches}. "
                "sub_agents entries are 2-tuples (name, subresult_key) since extractor QA removal."
            )

    def test_sub_agents_declaration_is_two_element_tuples(self):
        """The sub_agents list literal in agentic_workflow.py uses 2-element tuples."""
        import re
        import pathlib

        source = pathlib.Path("src/workflows/agentic_workflow.py").read_text()

        # Find the tuple entries in the sub_agents list: ("Name", "key")
        # A 3-tuple would have 2 commas: ("Name", "key", "QAName")
        # Extract all tuple-like strings from the sub_agents block.
        anchor = '"CmdlineExtract", "cmdline"'
        assert anchor in source, (
            "Expected sub_agents entry '(\"CmdlineExtract\", \"cmdline\")' not found. "
            "Update this test if the sub_agents format changed."
        )
        # Verify the 3-tuple form is absent
        three_tuple_pattern = r'"CmdlineExtract",\s*"cmdline",\s*"CmdLineQA"'
        assert not re.search(three_tuple_pattern, source), (
            "Found 3-element sub_agents tuple for CmdlineExtract -- extractor QA qa_name should be removed."
        )
