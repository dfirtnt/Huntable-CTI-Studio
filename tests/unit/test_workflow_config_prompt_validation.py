"""Unit tests for the Save-time prompt validation scanners.

Regression context: an active config lost every extractor prompt, so all 7 sub-agents
logged "prompt not found in workflow config, skipping", extraction produced zero
observables, and the workflow still reported ``status: completed`` with no error. The
existing preset scanner could not see the loss because it only inspects prompt entries
that are present -- a dropped key is invisible to it.
"""

import pytest

from src.config.workflow_config_schema import AGENT_NAMES_SUB
from src.web.routes.workflow_config import (
    _scan_missing_extractor_prompts,
    _scan_preset_prompts_for_warnings,
)

pytestmark = pytest.mark.unit


def _prompt(body: str = '{"json_example": {"items": [{"value": "x", "source_excerpt": "y"}]}}') -> dict:
    return {"prompt": body, "instructions": ""}


class TestScanMissingExtractorPrompts:
    def test_reports_every_enabled_extractor_with_no_prompt_entry(self):
        """The exact shape of the config that produced a silent zero-rule run."""
        agent_prompts = {"ExtractAgentSettings": {"disabled_agents": []}}

        warnings = _scan_missing_extractor_prompts(agent_prompts)

        assert len(warnings) == len(AGENT_NAMES_SUB)
        for agent_name in AGENT_NAMES_SUB:
            assert any(agent_name in w for w in warnings), f"{agent_name} not reported"
        assert all("will be skipped at runtime" in w for w in warnings)

    def test_empty_and_whitespace_prompts_count_as_missing(self):
        agent_prompts = {
            "ExtractAgentSettings": {"disabled_agents": []},
            "CmdlineExtract": {"prompt": ""},
            "ProcTreeExtract": {"prompt": "   \n  "},
        }

        warnings = _scan_missing_extractor_prompts(agent_prompts)

        assert any("CmdlineExtract" in w for w in warnings)
        assert any("ProcTreeExtract" in w for w in warnings)

    def test_disabled_extractors_are_not_reported(self):
        agent_prompts = {"ExtractAgentSettings": {"disabled_agents": list(AGENT_NAMES_SUB)}}

        assert _scan_missing_extractor_prompts(agent_prompts) == []

    def test_legacy_disabled_sub_agents_key_is_honored(self):
        agent_prompts = {"ExtractAgentSettings": {"disabled_sub_agents": list(AGENT_NAMES_SUB)}}

        assert _scan_missing_extractor_prompts(agent_prompts) == []

    def test_fully_populated_config_is_clean(self):
        agent_prompts = {"ExtractAgentSettings": {"disabled_agents": []}}
        for agent_name in AGENT_NAMES_SUB:
            agent_prompts[agent_name] = _prompt()

        assert _scan_missing_extractor_prompts(agent_prompts) == []

    def test_missing_extract_settings_treats_all_extractors_as_enabled(self):
        assert len(_scan_missing_extractor_prompts({})) == len(AGENT_NAMES_SUB)

    def test_non_dict_extract_settings_does_not_crash(self):
        assert len(_scan_missing_extractor_prompts({"ExtractAgentSettings": "nope"})) == len(AGENT_NAMES_SUB)


class TestScannersAreComplementary:
    def test_present_scanner_alone_misses_a_dropped_extractor(self):
        """Documents why the missing-prompt scanner had to be added."""
        agent_prompts = {"ExtractAgentSettings": {"disabled_agents": []}}

        assert _scan_preset_prompts_for_warnings(agent_prompts) == []
        assert _scan_missing_extractor_prompts(agent_prompts) != []

    def test_present_scanner_still_catches_an_empty_body(self):
        agent_prompts = {"SigmaAgent": {"prompt": ""}}

        assert any("empty" in w for w in _scan_preset_prompts_for_warnings(agent_prompts))
