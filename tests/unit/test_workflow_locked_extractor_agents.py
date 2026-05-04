"""Regression tests for the LOCKED_EXTRACTOR_AGENTS list in workflow.html.

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

    def test_rank_agent_still_listed_pending_separate_issue(self):
        """RankAgent has the same misclassification but is tracked in a parallel issue.

        This test pins down the current state so the SigmaAgent change doesn't
        accidentally also flip RankAgent. When the RankAgent parallel issue
        ships its UI fix, this assertion should be inverted (or this test deleted).
        """
        names = _names_in_block(LOCKED_EXTRACTOR_BLOCK)
        assert "RankAgent" in names, (
            "RankAgent classification is being changed without a corresponding RankAgent issue subtask. "
            "Coordinate with the RankAgent parent task."
        )
