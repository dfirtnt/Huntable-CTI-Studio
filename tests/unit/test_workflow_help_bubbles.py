"""Regression tests for workflow config help bubble content.

Verifies that the helpTexts JS object in workflow.html is consistent with the
backend implementation. These are static file checks -- no server or DB required.

Changes covered:
- Junk filter confidence description corrected (huntable, not junk)
- Model name lists and Sampling Presets blocks removed from all bubbles
- scheduledTasksExtract / scheduledTasksQA entries added
- HuntQueriesExtract header ? button added
- extractAgent sub-agent list includes ScheduledTasksExtract
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

TEMPLATE = Path("src/web/templates/workflow.html").read_text()

# Extract only the helpTexts JS object so substring checks don't match
# unrelated parts of the file (e.g. agent config selects, slider labels).
_HELP_TEXTS_MATCH = re.search(
    r"const helpTexts\s*=\s*\{(.+?)\};\s*\n\s*const help\s*=\s*helpTexts",
    TEMPLATE,
    re.DOTALL,
)
HELP_TEXTS_BLOCK = _HELP_TEXTS_MATCH.group(1) if _HELP_TEXTS_MATCH else ""


# ---------------------------------------------------------------------------
# New help entries
# ---------------------------------------------------------------------------


def test_scheduled_tasks_extract_help_key_present():
    """scheduledTasksExtract key exists in helpTexts."""
    assert "'scheduledTasksExtract'" in HELP_TEXTS_BLOCK


def test_scheduled_tasks_qa_help_key_present():
    """scheduledTasksQA key exists in helpTexts."""
    assert "'scheduledTasksQA'" in HELP_TEXTS_BLOCK


def test_hunt_queries_extract_header_has_help_button():
    """HuntQueriesExtract collapsed header row includes a showHelp() button."""
    # The button must sit between the sa-title span and the description span
    # so that it appears in the collapsed (header) view, not just when expanded.
    pattern = re.compile(
        r'<span class="sa-title">HuntQueriesExtract</span>.*?showHelp\(\'huntQueriesExtract\'\)',
        re.DOTALL,
    )
    assert pattern.search(TEMPLATE), "HuntQueriesExtract collapsed header is missing its showHelp() button"


# ---------------------------------------------------------------------------
# Junk filter description fix
# ---------------------------------------------------------------------------


def test_junk_filter_help_corrected_confidence_direction():
    """Junk filter bubble no longer describes confidence as junk likelihood."""
    assert "indicates how likely content is junk" not in HELP_TEXTS_BLOCK


def test_junk_filter_help_mentions_huntable():
    """Junk filter bubble describes confidence as huntability confidence."""
    # The corrected text says 'huntable' to describe what confidence measures.
    junk_section = re.search(
        r"'junkFilterThreshold'\s*:\s*\{(.+?)\},\s*\n\s*'rankingThreshold'",
        HELP_TEXTS_BLOCK,
        re.DOTALL,
    )
    assert junk_section, "Could not isolate junkFilterThreshold section"
    assert "huntable" in junk_section.group(1).lower()


# ---------------------------------------------------------------------------
# Model lists and Sampling Presets removed
# ---------------------------------------------------------------------------


def test_no_sampling_presets_section_in_help_bubbles():
    """No help bubble contains a Sampling Presets heading."""
    assert "Sampling Presets" not in HELP_TEXTS_BLOCK


def test_no_top_p_recommendations_in_help_bubbles():
    """No help bubble contains a Top-P range recommendation."""
    # Match "Top-P: 0.x" style ranges that were in the removed sections.
    assert not re.search(r"Top-P:</strong>\s*[\d.]+", HELP_TEXTS_BLOCK)


def test_no_primary_models_list_in_help_bubbles():
    """No help bubble contains a Primary Models (LMStudio) heading."""
    assert "Primary Models (LMStudio)" not in HELP_TEXTS_BLOCK
    assert "Primary Model (LMStudio)" not in HELP_TEXTS_BLOCK


def test_no_backup_models_list_in_help_bubbles():
    """No help bubble contains a Backup Models (LMStudio) heading."""
    assert "Backup Models (LMStudio)" not in HELP_TEXTS_BLOCK


# ---------------------------------------------------------------------------
# extractAgent sub-agent list completeness
# ---------------------------------------------------------------------------


def test_extract_agent_sub_agent_list_includes_scheduled_tasks():
    """extractAgent help lists ScheduledTasksExtract as a sub-agent."""
    extract_section = re.search(
        r"'extractAgent'\s*:\s*\{(.+?)\},\s*\n\s*'cmdlineExtract'",
        HELP_TEXTS_BLOCK,
        re.DOTALL,
    )
    assert extract_section, "Could not isolate extractAgent section"
    assert "ScheduledTasksExtract" in extract_section.group(1)
