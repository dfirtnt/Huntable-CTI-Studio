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
        assert "SigmaAgent" not in names, f"SigmaAgent must not be in LOCKED_EXTRACTOR_AGENTS. Found: {sorted(names)}"

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
        assert "RankAgent" not in names, f"RankAgent must not be in LOCKED_EXTRACTOR_AGENTS. Found: {sorted(names)}"


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
_RENDER_SECTION = TEMPLATE[TEMPLATE.find("if (exec.extraction_result?.subresults)") :]
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
            f"Expected 6 sub-agent rendering entries, found {count}. Update this count when adding a new extractor."
        )

    @pytest.mark.parametrize("key,agent_name", _EXPECTED_RENDER_ENTRIES)
    def test_entry_present(self, key, agent_name):
        """Every extractor must have both a subresults key and an agent name in the array."""
        assert f"key: '{key}'" in _RENDER_ARRAY_BLOCK, (
            f"Rendering array is missing subresults key '{key}'. "
            f"The {agent_name} card will not render in the execution detail modal."
        )
        assert f"name: '{agent_name}'" in _RENDER_ARRAY_BLOCK, (
            f"Rendering array is missing agent name '{agent_name}'. The card for key '{key}' will not render correctly."
        )

    def test_scheduled_tasks_is_last(self):
        """ScheduledTasksExtract must be order 6 (last) -- it was added after the other five."""
        assert "order: 6" in _RENDER_ARRAY_BLOCK, "ScheduledTasksExtract must have order: 6 in the rendering array."


# ---------------------------------------------------------------------------
# LOCKED_CANONICAL_AGENTS: SigmaAgent and RankAgent
# ---------------------------------------------------------------------------
# These agents use the {system, user} canonical save format (not the extractor
# JSON envelope). Their user-template slot holds the generation prompt that
# gets filled with article data at runtime. renderSinglePrompt shows this
# template in the amber "locked scaffold" section so users can see the loaded
# prompt after importing a quickstart preset.
# ---------------------------------------------------------------------------

_CANONICAL_MATCH = re.search(
    r"const LOCKED_CANONICAL_AGENTS\s*=\s*\[(.+?)\]\s*;",
    TEMPLATE,
    re.DOTALL,
)
LOCKED_CANONICAL_BLOCK = _CANONICAL_MATCH.group(1) if _CANONICAL_MATCH else ""

# Extract renderSinglePrompt body (up to, not including, renderQAPrompt).
_RENDER_SINGLE_MATCH = re.search(
    r"function renderSinglePrompt\(.+?(?=function renderQAPrompt)",
    TEMPLATE,
    re.DOTALL,
)
RENDER_SINGLE_BODY = _RENDER_SINGLE_MATCH.group(0) if _RENDER_SINGLE_MATCH else ""


class TestLockedCanonicalAgents:
    """Guards the LOCKED_CANONICAL_AGENTS list and the active-template rendering added in
    commit 9b8617d7 ('feat(ui): show active generation template for locked canonical prompts').

    Background: quickstart presets store SigmaAgent/RankAgent prompts in the legacy
    {prompt: "..."} shape.  parsePromptParts() routes text-with-placeholders into
    promptParts.user (not system), so the System Prompt field shows '(empty)'.
    The fix renders promptParts.user in the amber locked-scaffold section so users
    see the loaded generation template after import.
    """

    def test_locked_canonical_agents_list_present(self):
        """LOCKED_CANONICAL_AGENTS array literal must exist in workflow.html."""
        assert _CANONICAL_MATCH, "LOCKED_CANONICAL_AGENTS array literal not found in workflow.html"

    def test_locked_canonical_agents_contains_sigma_and_rank(self):
        """Both SigmaAgent and RankAgent must be in LOCKED_CANONICAL_AGENTS."""
        names = _names_in_block(LOCKED_CANONICAL_BLOCK)
        assert "SigmaAgent" in names, "SigmaAgent missing from LOCKED_CANONICAL_AGENTS"
        assert "RankAgent" in names, "RankAgent missing from LOCKED_CANONICAL_AGENTS"

    def test_locked_canonical_agents_has_exactly_two_entries(self):
        """Exactly SigmaAgent and RankAgent — no accidental additions.

        If a third canonical agent is intentionally added, update this assertion
        and verify it also gets the active-template display in renderSinglePrompt.
        """
        names = _names_in_block(LOCKED_CANONICAL_BLOCK)
        assert len(names) == 2, (
            f"Expected exactly 2 LOCKED_CANONICAL_AGENTS, got {len(names)}: {sorted(names)}. "
            "Update this test and verify the new agent gets active-template display treatment."
        )

    def test_render_single_prompt_function_found(self):
        """renderSinglePrompt function must be locatable in workflow.html."""
        assert _RENDER_SINGLE_MATCH, "renderSinglePrompt function not found in workflow.html"

    def test_active_generation_template_label_present_in_render_single(self):
        """The 'Active generation template:' label must be in renderSinglePrompt.

        Regression: if this label is removed, users importing a quickstart preset
        will see a blank prompt in the Generate SIGMA / Rank Agent panels.
        """
        assert "Active generation template:" in RENDER_SINGLE_BODY, (
            "renderSinglePrompt no longer contains 'Active generation template:'. "
            "Quickstart preset users will see a blank prompt panel after import."
        )

    def test_active_generation_template_uses_escape_html(self):
        """Prompt content must be rendered via escapeHtml() to prevent XSS.

        The user template can contain arbitrary text from the preset file.
        Direct interpolation without escaping would be an XSS vector.
        """
        idx = RENDER_SINGLE_BODY.find("Active generation template:")
        assert idx != -1, "Cannot locate 'Active generation template:' in renderSinglePrompt"
        # Inspect the 500 chars immediately following the label
        nearby = RENDER_SINGLE_BODY[idx : idx + 500]
        assert "escapeHtml(promptParts.user)" in nearby, (
            "The active-template div must use escapeHtml(promptParts.user). "
            "Raw interpolation of promptParts.user is an XSS risk."
        )

    def test_active_generation_template_guarded_by_locked_scaffold(self):
        """The canonical-template display must be nested inside the isLockedScaffoldAgent branch.

        If it escapes that guard it would render for regular (non-locked) agents
        that happen to have non-empty promptParts.user, polluting their UI.
        """
        locked_pos = RENDER_SINGLE_BODY.find("isLockedScaffoldAgent ?")
        canonical_pos = RENDER_SINGLE_BODY.find("isLockedCanonicalPrompt(agentName) && promptParts.user")
        assert locked_pos != -1, "isLockedScaffoldAgent ternary not found in renderSinglePrompt"
        assert canonical_pos != -1, (
            "isLockedCanonicalPrompt(agentName) && promptParts.user condition not found in renderSinglePrompt"
        )
        assert locked_pos < canonical_pos, (
            "The isLockedCanonicalPrompt condition must appear AFTER the isLockedScaffoldAgent "
            "guard (i.e. nested inside it). "
            "Current order would render the template outside the locked-scaffold branch."
        )
