"""Unit tests for _scan_preset_prompts_for_warnings.

Covers every branch of the import-time warning scan:
- plain-text prompts (no false positives)
- empty prompt
- invalid JSON
- structured prompt missing json_example
- json_example that is not valid JSON
- json_example missing required traceability fields
- simple extractor missing 'value'
- rich extractor with domain fields (value absence is not flagged)
- clean pass-through
"""

from __future__ import annotations

import json

import pytest

from src.web.routes.workflow_config import _scan_preset_prompts_for_warnings

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(prompt: str) -> dict:
    return {"prompt": prompt}


def _rich_example(**extra_fields) -> str:
    """json_example with all three required traceability fields plus extras."""
    item = {
        "source_evidence": "The malware creates a scheduled task",
        "extraction_justification": "Explicit task name mentioned in article",
        "confidence_score": 0.95,
        **extra_fields,
    }
    return json.dumps({"items": [item]})


# ---------------------------------------------------------------------------
# No warnings expected
# ---------------------------------------------------------------------------


class TestCleanCases:
    def test_plain_text_prompt_no_warning(self):
        """Plain-text (non-JSON) prompts must not be flagged -- they have no structured contract."""
        prompts = {
            "HuntabilityScore": _make_entry("You are a strict cyber threat-intelligence analyst. Score 1-10."),
            "SigmaAgent": _make_entry("Generate Sigma detection rules strictly from provided structured observables."),
        }
        assert _scan_preset_prompts_for_warnings(prompts) == []

    def test_empty_agent_prompts_dict(self):
        assert _scan_preset_prompts_for_warnings({}) == []

    def test_non_dict_entry_skipped(self):
        """If an entry is not a dict (malformed preset), it is silently skipped."""
        assert _scan_preset_prompts_for_warnings({"BadAgent": "raw string"}) == []

    def test_rich_extractor_no_warning(self):
        """Extractor with domain-specific fields + all traceability fields: no warning."""
        prompt = json.dumps(
            {
                "role": "You are a cmdline extractor.",
                "task": "Extract cmdlines.",
                "instructions": "Extract only verbatim cmdlines.",
                "json_example": _rich_example(task_name="GoogleUpdateTask", task_path="\\Tasks\\Google"),
            }
        )
        warnings = _scan_preset_prompts_for_warnings({"ScheduledTasksExtract": _make_entry(prompt)})
        assert warnings == []

    def test_simple_extractor_with_value_no_warning(self):
        """Simple extractor (only traceability fields + value): clean."""
        item = {
            "value": "some extracted string",
            "source_evidence": "found in article",
            "extraction_justification": "explicit mention",
            "confidence_score": 0.9,
        }
        prompt = json.dumps(
            {
                "role": "extractor",
                "task": "extract",
                "instructions": "do it",
                "json_example": json.dumps({"items": [item]}),
            }
        )
        warnings = _scan_preset_prompts_for_warnings({"CmdlineExtract": _make_entry(prompt)})
        assert warnings == []

    def test_non_extractor_agent_missing_json_example_no_warning(self):
        """A structured prompt for a non-extractor agent (no *Extract suffix) without
        json_example should not warn -- the contract only applies to extractors."""
        prompt = json.dumps({"role": "ranker", "task": "rank", "instructions": "rank items"})
        warnings = _scan_preset_prompts_for_warnings({"RankAgent": _make_entry(prompt)})
        assert warnings == []


# ---------------------------------------------------------------------------
# Warnings expected
# ---------------------------------------------------------------------------


class TestWarningCases:
    def test_empty_prompt_warns(self):
        warnings = _scan_preset_prompts_for_warnings({"SomeAgent": _make_entry("")})
        assert len(warnings) == 1
        assert "system prompt is empty" in warnings[0]
        assert "SomeAgent" in warnings[0]

    def test_whitespace_only_prompt_warns(self):
        warnings = _scan_preset_prompts_for_warnings({"SomeAgent": _make_entry("   \n  ")})
        assert len(warnings) == 1
        assert "system prompt is empty" in warnings[0]

    def test_invalid_json_prompt_warns(self):
        warnings = _scan_preset_prompts_for_warnings({"CmdlineExtract": _make_entry('{"role": "x", "task": BROKEN}')})
        assert len(warnings) == 1
        assert "invalid JSON" in warnings[0]

    def test_extractor_missing_json_example_warns(self):
        prompt = json.dumps({"role": "extractor", "task": "extract", "instructions": "do it"})
        warnings = _scan_preset_prompts_for_warnings({"CmdlineExtract": _make_entry(prompt)})
        assert len(warnings) == 1
        assert "missing 'json_example'" in warnings[0]
        assert "CmdlineExtract" in warnings[0]

    def test_extractor_agent_exact_name_warns(self):
        """The 'ExtractAgent' exact name also triggers the json_example check."""
        prompt = json.dumps({"role": "orchestrator", "task": "dispatch", "instructions": "route"})
        warnings = _scan_preset_prompts_for_warnings({"ExtractAgent": _make_entry(prompt)})
        assert any("missing 'json_example'" in w for w in warnings)

    def test_invalid_json_example_string_warns(self):
        prompt = json.dumps(
            {
                "role": "extractor",
                "task": "extract",
                "instructions": "do it",
                "json_example": "{not valid json}",
            }
        )
        warnings = _scan_preset_prompts_for_warnings({"CmdlineExtract": _make_entry(prompt)})
        assert len(warnings) == 1
        assert "json_example is not valid JSON" in warnings[0]

    def test_missing_required_traceability_fields_warns(self):
        """If source_evidence/extraction_justification/confidence_score are absent, warn."""
        item = {"value": "x"}  # only value, none of the three required fields
        prompt = json.dumps(
            {
                "role": "extractor",
                "task": "extract",
                "instructions": "do it",
                "json_example": json.dumps({"items": [item]}),
            }
        )
        warnings = _scan_preset_prompts_for_warnings({"CmdlineExtract": _make_entry(prompt)})
        assert len(warnings) == 1
        assert "missing required traceability fields" in warnings[0]
        assert "source_evidence" in warnings[0]
        assert "extraction_justification" in warnings[0]
        assert "confidence_score" in warnings[0]

    def test_simple_extractor_missing_value_warns(self):
        """Items that only have traceability fields but no domain fields must have 'value'."""
        item = {
            "source_evidence": "found",
            "extraction_justification": "explicit",
            "confidence_score": 0.8,
            # no 'value', no domain-specific fields
        }
        prompt = json.dumps(
            {
                "role": "extractor",
                "task": "extract",
                "instructions": "do it",
                "json_example": json.dumps({"items": [item]}),
            }
        )
        warnings = _scan_preset_prompts_for_warnings({"CmdlineExtract": _make_entry(prompt)})
        assert len(warnings) == 1
        assert "missing 'value' field" in warnings[0]

    def test_rich_extractor_missing_value_no_warning(self):
        """Rich extractors with domain fields do NOT need 'value' -- no false positive."""
        prompt = json.dumps(
            {
                "role": "extractor",
                "task": "extract",
                "instructions": "do it",
                "json_example": _rich_example(task_name="GoogleUpdate"),
            }
        )
        warnings = _scan_preset_prompts_for_warnings({"ScheduledTasksExtract": _make_entry(prompt)})
        assert warnings == []

    def test_multiple_agents_collect_all_warnings(self):
        """All issues across all agents are collected, not just the first."""
        prompts = {
            "AgentA": _make_entry(""),
            "AgentB": _make_entry('{"broken": json}'),
            "HuntabilityScore": _make_entry("plain text prompt, should be clean"),
        }
        warnings = _scan_preset_prompts_for_warnings(prompts)
        assert len(warnings) == 2
        agents_warned = {w.split(":")[0] for w in warnings}
        assert "AgentA" in agents_warned
        assert "AgentB" in agents_warned
        assert "HuntabilityScore" not in agents_warned
