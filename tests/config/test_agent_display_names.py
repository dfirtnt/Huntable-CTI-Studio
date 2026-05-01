"""Tests for AGENT_DISPLAY_NAMES coverage and consistency.

Contract invariants (from handoff report):
  * Every agent in ALL_AGENT_NAMES must have a display name.
  * No orphan keys in AGENT_DISPLAY_NAMES (only real agents + the OSDetectionAgent special case).
  * Display names must be non-empty strings.
"""

import pytest

from src.config.workflow_config_schema import (
    AGENT_DISPLAY_NAMES,
    AGENT_NAMES_MAIN,
    AGENT_NAMES_QA,
    AGENT_NAMES_SUB,
    ALL_AGENT_NAMES,
)

pytestmark = pytest.mark.unit

# Legacy keys kept for display/backward-compat; NOT in ALL_AGENT_NAMES but allowed in AGENT_DISPLAY_NAMES.
_ALLOWED_EXTRAS = {"OSDetectionAgent", "QAAgent"}


def test_display_names_cover_all_agents():
    """Every agent in ALL_AGENT_NAMES must have a display name."""
    missing = [name for name in ALL_AGENT_NAMES if name not in AGENT_DISPLAY_NAMES]
    assert not missing, f"Missing display names for: {missing}"


def test_display_names_no_orphan_keys():
    """No key in AGENT_DISPLAY_NAMES should be unknown (not in ALL_AGENT_NAMES or allowed extras)."""
    known = set(ALL_AGENT_NAMES) | _ALLOWED_EXTRAS
    orphans = [key for key in AGENT_DISPLAY_NAMES if key not in known]
    assert not orphans, f"Orphan display name keys: {orphans}"


def test_display_names_are_non_empty_strings():
    """Every display name must be a non-empty, non-whitespace string."""
    bad = [k for k, v in AGENT_DISPLAY_NAMES.items() if not isinstance(v, str) or not v.strip()]
    assert not bad, f"Blank or non-string display names for: {bad}"


def test_cmdline_qa_canonical_key_has_display_name():
    """CmdLineQA (canonical casing) must have a display name; CmdlineQA must not."""
    assert "CmdLineQA" in AGENT_DISPLAY_NAMES, "Canonical CmdLineQA missing from AGENT_DISPLAY_NAMES"
    assert "CmdlineQA" not in AGENT_DISPLAY_NAMES, "Legacy CmdlineQA must not appear in AGENT_DISPLAY_NAMES"


def test_main_agents_all_covered():
    for name in AGENT_NAMES_MAIN:
        assert name in AGENT_DISPLAY_NAMES, f"Main agent {name!r} missing from AGENT_DISPLAY_NAMES"


def test_sub_agents_all_covered():
    for name in AGENT_NAMES_SUB:
        assert name in AGENT_DISPLAY_NAMES, f"Sub-agent {name!r} missing from AGENT_DISPLAY_NAMES"


def test_qa_agents_all_covered():
    for name in AGENT_NAMES_QA:
        assert name in AGENT_DISPLAY_NAMES, f"QA agent {name!r} missing from AGENT_DISPLAY_NAMES"


def test_display_names_dict_is_not_empty():
    assert len(AGENT_DISPLAY_NAMES) > 0


def test_display_names_count_at_least_all_agents():
    """Dict must have at least as many entries as ALL_AGENT_NAMES (plus optional extras)."""
    assert len(AGENT_DISPLAY_NAMES) >= len(ALL_AGENT_NAMES)
