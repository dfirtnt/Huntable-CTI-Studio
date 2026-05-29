"""Regression tests confirming full deprecation of the QA Agent subsystem.

Covers:
  - Schema: AGENT_NAMES_QA is empty; no QA agents in ALL_AGENT_NAMES
  - Schema: BASE_AGENT_TO_QA is empty
  - Schema: WorkflowConfigV2 rejects any QA key (extra="forbid")
  - Migrate: _normalize_v2_strict strips ALL QA agents (including RankAgentQA)
    from Agents, QA field, and Prompts in an old config
  - Migrate: normalized config validates cleanly as WorkflowConfigV2
  - Workflow: sub_agents list is 2-tuples (name, subresult_key)
  - Default prompts: QA agents absent from AGENT_PROMPT_FILES
  - UI: workflow.html sub-agent panel has no QA result rendering
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

_ALL_QA_AGENT_NAMES = {
    "RankAgentQA",
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
    def test_agent_names_qa_is_empty(self):
        """AGENT_NAMES_QA must be empty after full QA deprecation."""
        from src.config.workflow_config_schema import AGENT_NAMES_QA

        assert AGENT_NAMES_QA == [], f"AGENT_NAMES_QA must be empty, got: {AGENT_NAMES_QA}"

    def test_base_agent_to_qa_is_empty(self):
        """BASE_AGENT_TO_QA must be empty after full QA deprecation."""
        from src.config.workflow_config_schema import BASE_AGENT_TO_QA

        assert BASE_AGENT_TO_QA == {}, f"BASE_AGENT_TO_QA must be empty, got: {BASE_AGENT_TO_QA}"

    def test_qa_agents_absent_from_all_agent_names(self):
        """No QA agent name should appear in ALL_AGENT_NAMES."""
        from src.config.workflow_config_schema import ALL_AGENT_NAMES

        for name in _ALL_QA_AGENT_NAMES:
            assert name not in ALL_AGENT_NAMES, f"{name} must not be in ALL_AGENT_NAMES"

    def test_workflow_config_v2_has_no_qa_field(self):
        """WorkflowConfigV2 with extra QA key raises ValidationError (extra='forbid')."""
        from pydantic import ValidationError

        from src.config.workflow_config_schema import WorkflowConfigV2

        raw = {
            "Version": "2.0",
            "QA": {"Enabled": {}, "MaxRetries": 1},
        }
        with pytest.raises(ValidationError):
            WorkflowConfigV2.model_validate(raw)

    def test_rank_agent_qa_rejected_as_stray_prompt(self):
        """RankAgentQA in Prompts raises ValidationError (no longer a canonical agent name)."""
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
            },
            "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
            "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
            "Prompts": {
                "RankAgent": {"prompt": "", "instructions": ""},
                "RankAgentQA": {"prompt": "", "instructions": ""},
            },
            "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
        }
        with pytest.raises(ValidationError, match="Prompts key .* is not a canonical agent name"):
            WorkflowConfigV2.model_validate(raw)


# ---------------------------------------------------------------------------
# Migration backcompat
# ---------------------------------------------------------------------------


class TestMigrateStripsAllQAAgents:
    """_normalize_v2_strict must silently strip ALL QA agents from old configs."""

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
            "HuntQueriesQA": {
                "Provider": "openai",
                "Model": "gpt-4o",
                "Temperature": 0.0,
                "TopP": 0.9,
                "Enabled": True,
            },
            "RegistryQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "ServicesQA": {"Provider": "openai", "Model": "gpt-4o", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "ScheduledTasksQA": {
                "Provider": "openai",
                "Model": "gpt-4o",
                "Temperature": 0.0,
                "TopP": 0.9,
                "Enabled": True,
            },
        },
        "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
        "QA": {
            "Enabled": {
                "RankAgent": True,
                "CmdlineExtract": True,
                "ProcTreeExtract": False,
            },
            "MaxRetries": 3,
        },
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {
            "RankAgent": {"prompt": "", "instructions": ""},
            "RankAgentQA": {"prompt": "rank_qa_prompt", "instructions": ""},
            "CmdLineQA": {"prompt": "old_qa_prompt", "instructions": ""},
            "ProcTreeQA": {"prompt": "old_qa_prompt", "instructions": ""},
        },
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }

    def _normalize(self):
        from src.config.workflow_config_migrate import _normalize_v2_strict

        return _normalize_v2_strict(self._OLD_V2)

    def test_all_qa_agents_stripped_from_agents(self):
        out = self._normalize()
        for name in _ALL_QA_AGENT_NAMES:
            assert name not in out["Agents"], f"{name} should be stripped from Agents"

    def test_rank_agent_qa_stripped_from_agents(self):
        """RankAgentQA specifically must be stripped (fully deprecated)."""
        out = self._normalize()
        assert "RankAgentQA" not in out["Agents"]

    def test_qa_field_stripped(self):
        """The top-level 'QA' field must be removed."""
        out = self._normalize()
        assert "QA" not in out, "QA field must be stripped from normalized output"

    def test_qa_prompts_stripped(self):
        out = self._normalize()
        prompts = out.get("Prompts", {})
        for name in _ALL_QA_AGENT_NAMES:
            assert name not in prompts, f"Prompts[{name}] should be stripped"

    def test_normalized_config_validates_as_v2(self):
        from src.config.workflow_config_schema import WorkflowConfigV2

        out = self._normalize()
        config = WorkflowConfigV2.model_validate(out)
        assert config.Version == "2.0"
        # Only non-QA agents remain
        for name in _ALL_QA_AGENT_NAMES:
            assert name not in config.Agents


# ---------------------------------------------------------------------------
# Default agent prompts
# ---------------------------------------------------------------------------


class TestDefaultAgentPromptsClean:
    def test_qa_agents_absent_from_agent_prompt_files(self):
        from src.utils.default_agent_prompts import AGENT_PROMPT_FILES

        for name in _ALL_QA_AGENT_NAMES:
            assert name not in AGENT_PROMPT_FILES, f"{name} must not be in AGENT_PROMPT_FILES"


# ---------------------------------------------------------------------------
# Agentic workflow sub_agents arity
# ---------------------------------------------------------------------------


class TestSubAgentsTupleArity:
    """Regression: sub_agents must be 2-tuples after QA removal.

    The previous implementation had 3-tuples (name, subresult_key, qa_name).
    Removing qa_name changed them to 2-tuples.
    """

    def test_no_three_element_unpack_on_sub_agents(self):
        """No remaining 3-element tuple unpacking on sub_agents or original_sub_agents."""
        import pathlib
        import re

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
                "sub_agents entries are 2-tuples (name, subresult_key) since QA removal."
            )

    def test_sub_agents_declaration_is_two_element_tuples(self):
        """The sub_agents list literal in agentic_workflow.py uses 2-element tuples."""
        import pathlib
        import re

        source = pathlib.Path("src/workflows/agentic_workflow.py").read_text()

        anchor = '"CmdlineExtract", "cmdline"'
        assert anchor in source, (
            'Expected sub_agents entry \'("CmdlineExtract", "cmdline")\' not found. '
            "Update this test if the sub_agents format changed."
        )
        # Verify the 3-tuple form is absent
        three_tuple_pattern = r'"CmdlineExtract",\s*"cmdline",\s*"CmdLineQA"'
        assert not re.search(three_tuple_pattern, source), (
            "Found 3-element sub_agents tuple for CmdlineExtract -- QA qa_name should be removed."
        )


# ---------------------------------------------------------------------------
# UI template: workflow.html sub-agent panel QA rendering removed
# ---------------------------------------------------------------------------


class TestWorkflowHtmlNoQARendering:
    """Regression: the sub-agent detail panel in workflow.html must not
    render QA results.

    The panel previously read ``exec.error_log.qa_results``, attached a
    ``qaName`` to every subAgent array entry, and built a ``qaHtml`` block
    showing verdict / feedback / issues. All of it is dead since the backend
    no longer writes ``qa_results`` -- removed 2026-05-22. These checks fail
    if the QA rendering is reintroduced.
    """

    @staticmethod
    def _workflow_html() -> str:
        import pathlib

        return pathlib.Path("src/web/templates/workflow.html").read_text()

    def test_no_qa_results_error_log_access(self):
        """workflow.html no longer reads error_log.qa_results."""
        html = self._workflow_html()
        assert "qa_results" not in html, "workflow.html still references error_log.qa_results"

    def test_no_qa_rendering_js_variables(self):
        """No qaHtml / qaResults / qaVerdict / qaFeedback / qaIssues JS vars remain."""
        html = self._workflow_html()
        for symbol in ("qaHtml", "qaResults", "qaVerdict", "qaFeedback", "qaIssues"):
            assert symbol not in html, f"workflow.html still references dead QA symbol: {symbol}"

    def test_no_qa_name_on_sub_agents_array(self):
        """The subAgents array entries no longer carry a qaName property."""
        html = self._workflow_html()
        assert "qaName" not in html, "workflow.html subAgents array still has a qaName property"

    def test_sub_agent_panel_still_intact(self):
        """Positive check: the sub-agent extraction panel itself survives.

        Guards against an over-eager deletion removing the whole panel along
        with the QA code.
        """
        html = self._workflow_html()
        for agent in (
            "CmdlineExtract",
            "ProcTreeExtract",
            "HuntQueriesExtract",
            "RegistryExtract",
            "ServicesExtract",
            "ScheduledTasksExtract",
        ):
            assert agent in html, f"subAgents array is missing {agent} -- panel may have been over-trimmed"
