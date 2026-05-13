"""Regression tests for the LOCKED_EXTRACTOR_AGENTS list and sub-agent rendering array in workflow.html.

The list controls which agents the prompt-edit UI treats as extraction agents
and packages with the {role, task, json_example, instructions} envelope when
saving.  SigmaAgent must NOT be in this list -- it doesn't use those fields,
and the UI mis-classification was the root cause of shape-2 records appearing
in agent_prompts.SigmaAgent (parent issue: SigmaAgent prompt-storage cleanup).

These are static-text checks -- no DOM or browser needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

TEMPLATE = Path("src/web/templates/workflow.html").read_text()

# Extract the LOCKED_EXTRACTOR_AGENTS array literal so substring checks don't
# spuriously match unrelated mentions of the agent names elsewhere in the file.
_LIST_MATCH = re.search(
    r"const LOCKED_EXTRACTOR_AGENTS\s*=\s*\[(.+?)\]\s*;",
    TEMPLATE,
    re.DOTALL,
)
LOCKED_EXTRACTOR_BLOCK = _LIST_MATCH.group(1) if _LIST_MATCH else ""


def _names_in_block(block: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", block))


class TestLockedExtractorAgents:
    def test_list_is_present(self):
        assert _LIST_MATCH, "LOCKED_EXTRACTOR_AGENTS array literal not found in workflow.html"

    def test_sigma_agent_is_excluded(self):
        """Regression: SigmaAgent must NOT be in LOCKED_EXTRACTOR_AGENTS.

        It doesn't use extraction-agent fields (task/json_example/instructions);
        listing it caused the UI to save with the wrong envelope (shape-2),
        which parse_sigma_agent_prompt_data then had to special-case.
        """
        names = _names_in_block(LOCKED_EXTRACTOR_BLOCK)
        assert "SigmaAgent" not in names, (
            f"SigmaAgent must not be in LOCKED_EXTRACTOR_AGENTS. Found: {sorted(names)}"
        )

    def test_actual_extraction_agents_remain(self):
        """The genuine extraction agents -- which DO use task/json_example -- must stay listed."""
        names = _names_in_block(LOCKED_EXTRACTOR_BLOCK)
        required = {
            "CmdlineExtract",
            "ProcTreeExtract",
            "HuntQueriesExtract",
            "RegistryExtract",
            "ServicesExtract",
            "ScheduledTasksExtract",
        }
        missing = required - names
        assert not missing, f"Missing genuine extraction agents from list: {sorted(missing)}"

    def test_rank_agent_is_excluded(self):
        """Regression: RankAgent must NOT be in LOCKED_EXTRACTOR_AGENTS.

        Same rationale as SigmaAgent: RankAgent doesn't use extraction-agent
        fields. Its readers go through `_parse_rank_prompt` which expects
        {system, user} or raw text with {title}/{content} placeholders.
        Listing RankAgent here would cause the UI to save with the wrong
        envelope and silently drop the user's persona.
        """
        names = _names_in_block(LOCKED_EXTRACTOR_BLOCK)
        assert "RankAgent" not in names, (
            f"RankAgent must not be in LOCKED_EXTRACTOR_AGENTS. Found: {sorted(names)}"
        )


# ---------------------------------------------------------------------------
# Sub-agents rendering array (the JS object array that drives card generation)
# ---------------------------------------------------------------------------
# This is a SEPARATE array from LOCKED_EXTRACTOR_AGENTS.  It lives inside the
# `if (exec.extraction_result?.subresults)` block in workflow.html and controls
# which per-agent cards are rendered in the execution-detail modal.
#
# Regression note: ScheduledTasksExtract was wired everywhere else but was
# accidentally omitted from this array (it was added to workflow_executions.html
# but not to the parallel copy in workflow.html), causing the card to silently
# disappear from the /workflow#executions execution-detail view.
# ---------------------------------------------------------------------------

# The rendering array starts immediately after the subresults guard block.
_RENDER_SECTION = TEMPLATE[TEMPLATE.find("if (exec.extraction_result?.subresults)"):]
_RENDER_ARRAY_MATCH = re.search(
    r"const subAgents\s*=\s*\[(\s*\{.+?)\s*\]\s*;",
    _RENDER_SECTION,
    re.DOTALL,
)
_RENDER_ARRAY_BLOCK = _RENDER_ARRAY_MATCH.group(1) if _RENDER_ARRAY_MATCH else ""

# Expected entries: (subresults_key, agent_name)
_EXPECTED_RENDER_ENTRIES = [
    ("cmdline", "CmdlineExtract"),
    ("process_lineage", "ProcTreeExtract"),
    ("hunt_queries", "HuntQueriesExtract"),
    ("registry_artifacts", "RegistryExtract"),
    ("windows_services", "ServicesExtract"),
    ("scheduled_tasks", "ScheduledTasksExtract"),
]


class TestSubAgentsRenderingArray:
    """Guard the rendering array that drives execution-detail sub-agent cards."""

    def test_array_is_present(self):
        assert _RENDER_ARRAY_MATCH, (
            "Sub-agents object rendering array not found inside the "
            "exec.extraction_result?.subresults block of workflow.html"
        )

    def test_exactly_six_entries(self):
        count = len(re.findall(r"\{\s*key:", _RENDER_ARRAY_BLOCK))
        assert count == 6, (
            f"Expected 6 sub-agent rendering entries, found {count}. "
            "Update this count when adding a new extractor."
        )

    @pytest.mark.parametrize("key,agent_name", _EXPECTED_RENDER_ENTRIES)
    def test_entry_present(self, key, agent_name):
        """Every extractor must have both a subresults key and an agent name in the array."""
        assert f"key: '{key}'" in _RENDER_ARRAY_BLOCK, (
            f"Rendering array is missing subresults key '{key}'. "
            f"The {agent_name} card will not render in the execution detail modal."
        )
        assert f"name: '{agent_name}'" in _RENDER_ARRAY_BLOCK, (
            f"Rendering array is missing agent name '{agent_name}'. "
            f"The card for key '{key}' will not render correctly."
        )

    def test_scheduled_tasks_is_last(self):
        """ScheduledTasksExtract must be order 6 (last) -- it was added after the other five."""
        assert "order: 6" in _RENDER_ARRAY_BLOCK, (
            "ScheduledTasksExtract must have order: 6 in the rendering array."
        )
