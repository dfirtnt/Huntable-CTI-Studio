"""Contract test keeping the prompt-warning badges in step with the agent roster.

The browser tests in ``tests/ui/test_workflow_comprehensive_ui.py`` prove that a
badge fires, clears, and agrees with the Validate button. They cannot prove the
property that actually matters over time: that EVERY prompt-bearing agent is
covered. Each of those tests names today's seven extractors explicitly, so an
eighth sub-agent would leave them all green while its prompt silently went
unvalidated -- the exact "broken for two days behind a button" failure the badges
exist to prevent, reintroduced one agent at a time.

That is not a hypothetical: this repository ships a ``create-huntable-agent``
skill whose job is to add an extraction sub-agent across schemas, config,
services, routes, UI and presets. This test pins the three lists it would have to
touch against each other:

  * ``_PROMPT_BADGE_STEPS``  (prompt-editor.js) -- who gets validated on load
  * ``EXTRACT_SUB_AGENTS``   (workflow.html)    -- who the validator treats as an
    extractor, which decides both the envelope checks and the empty-prompt
    exemption
  * the ``subAgents`` roster in ``renderAgentPrompts`` (config.js) -- who gets a
    prompt panel rendered at all

and against the badge anchors in the template, so a missing ``<span>`` is a test
failure rather than a badge that never appears.

Static parsing is deliberate: this must fail in a fast unit run, without a
browser or a live app, at the moment the roster changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_EDITOR_JS = REPO_ROOT / "src" / "web" / "static" / "js" / "workflow" / "prompt-editor.js"
CONFIG_JS = REPO_ROOT / "src" / "web" / "static" / "js" / "workflow" / "config.js"
WORKFLOW_HTML = REPO_ROOT / "src" / "web" / "templates" / "workflow.html"

_BADGE_STEPS_BLOCK = re.compile(r"var _PROMPT_BADGE_STEPS = \[(.*?)\n\];", re.S)
_STEP_ENTRY = re.compile(r"\{\s*step:\s*'([^']+)',\s*agents:\s*\[(.*?)\]\s*\}", re.S)
_QUOTED = re.compile(r"'([^']+)'")
_EXTRACT_SUB_AGENTS = re.compile(r"const EXTRACT_SUB_AGENTS = \[(.*?)\];", re.S)
_SUBAGENT_ROSTER = re.compile(r"\{\s*name:\s*'([^']+)',\s*container:\s*'([^']+)'")
_BADGE_ANCHOR = re.compile(r'id="([a-z0-9]+)-prompt-warn-badge"')


def _badge_steps() -> dict[str, list[str]]:
    """{step id -> agent names} as declared in prompt-editor.js."""
    block = _BADGE_STEPS_BLOCK.search(PROMPT_EDITOR_JS.read_text(encoding="utf-8"))
    assert block, "_PROMPT_BADGE_STEPS not found -- the badge roster moved or was renamed"
    return {step: _QUOTED.findall(agents) for step, agents in _STEP_ENTRY.findall(block.group(1))}


def _extract_sub_agents() -> list[str]:
    match = _EXTRACT_SUB_AGENTS.search(WORKFLOW_HTML.read_text(encoding="utf-8"))
    assert match, "EXTRACT_SUB_AGENTS not found in workflow.html"
    return _QUOTED.findall(match.group(1))


def _rendered_prompt_agents() -> list[str]:
    return [name for name, _container in _SUBAGENT_ROSTER.findall(CONFIG_JS.read_text(encoding="utf-8"))]


def _badge_anchor_ids() -> set[str]:
    return set(_BADGE_ANCHOR.findall(WORKFLOW_HTML.read_text(encoding="utf-8")))


def test_parsers_are_not_vacuous():
    """A broken regex must fail loudly instead of proving empty sets equal.

    Every assertion below compares parsed collections, so a pattern that silently
    matched nothing would make the whole file pass while checking nothing.
    """
    steps = _badge_steps()
    assert set(steps) == {"s2", "s3", "s4"}, steps
    assert len(_extract_sub_agents()) >= 7
    assert len(_rendered_prompt_agents()) >= 7
    assert len(_badge_anchor_ids()) >= 10


def test_every_extraction_sub_agent_is_badged():
    """A new extractor must be added to the badge roster, not silently skipped."""
    badged = set(_badge_steps()["s3"])
    declared = set(_extract_sub_agents())

    missing = sorted(declared - badged)
    assert not missing, (
        f"extraction sub-agents are never validated on load: {missing}. "
        "Add them to _PROMPT_BADGE_STEPS['s3'] in prompt-editor.js."
    )

    unknown = sorted(badged - declared)
    assert not unknown, (
        f"badge roster names agents that are not extraction sub-agents: {unknown}. "
        "They would skip the envelope checks and wrongly receive the empty-prompt exemption."
    )


def test_every_agent_with_a_prompt_panel_is_badged():
    """Owning an editable prompt panel and being validated must not diverge."""
    badged = {agent for agents in _badge_steps().values() for agent in agents}
    rendered = set(_rendered_prompt_agents()) | {"RankAgent", "SigmaAgent"}

    missing = sorted(rendered - badged)
    assert not missing, f"agents render an editable prompt but are never validated on load: {missing}"


def test_every_badged_agent_has_a_badge_anchor_in_the_template():
    """The JS writes into ids that must actually exist, or the badge is a no-op."""
    anchors = _badge_anchor_ids()
    expected = {
        agent.lower().replace(" ", "-")
        for agents in _badge_steps().values()
        for agent in agents
        if agent not in {"RankAgent", "SigmaAgent"}
    } | set(_badge_steps())

    missing = sorted(expected - anchors)
    assert not missing, (
        f"no <span id='...-prompt-warn-badge'> for: {missing}. "
        "refreshPromptWarningBadges would compute a verdict and drop it on the floor."
    )


def test_no_orphaned_badge_anchors():
    """An anchor nothing writes to is dead markup that reads as 'no issues'."""
    anchors = _badge_anchor_ids()
    claimed = {
        agent.lower().replace(" ", "-")
        for agents in _badge_steps().values()
        for agent in agents
        if agent not in {"RankAgent", "SigmaAgent"}
    } | set(_badge_steps())

    orphans = sorted(anchors - claimed)
    assert not orphans, (
        f"badge anchors nothing ever writes to: {orphans}. "
        "A permanently empty badge is indistinguishable from a clean prompt."
    )
