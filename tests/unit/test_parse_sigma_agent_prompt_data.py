"""Tests for src.utils.prompt_loader.parse_sigma_agent_prompt_data.

SigmaAgent's DB prompt has three historical shapes the parser must handle:
  1. Locked scaffold JSON: {"role": ..., "user_template": ...}
  2. Legacy simple JSON:   {"system": ..., "user": ...}
  3. Legacy raw text:      template text with {title}/{content} placeholders

Plus the legacy sibling ``system_prompt`` key that pre-dated the locked format.
"""

import json

import pytest

from src.utils.prompt_loader import parse_sigma_agent_prompt_data

pytestmark = pytest.mark.unit


class TestParseSigmaAgentPromptData:
    def test_locked_scaffold_json_extracts_template_and_role(self):
        """Locked scaffold format: user_template -> template, role -> system."""
        raw = json.dumps(
            {
                "role": "You are a SIGMA rule generator.",
                "user_template": "Generate Sigma rules from {title} at {url}: {content}",
            }
        )
        template, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert template == "Generate Sigma rules from {title} at {url}: {content}"
        assert system == "You are a SIGMA rule generator."

    def test_locked_scaffold_prefers_role_over_system(self):
        """When both role and system keys are present, role wins (locked-scaffold contract)."""
        raw = json.dumps(
            {
                "role": "LOCKED_ROLE",
                "system": "LEGACY_SYSTEM",
                "user_template": "template {title}",
            }
        )
        _, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert system == "LOCKED_ROLE"

    def test_locked_scaffold_falls_back_to_system_when_role_missing(self):
        """If the locked JSON has no role, fall back to the system key."""
        raw = json.dumps(
            {
                "system": "SYSTEM_ONLY",
                "user_template": "template {title}",
            }
        )
        _, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert system == "SYSTEM_ONLY"

    def test_legacy_system_user_json_extracts_user_as_template(self):
        """Legacy {system, user} JSON: user -> template, system -> system."""
        raw = json.dumps(
            {
                "system": "You are a SIGMA expert.",
                "user": "Old-style template with {title} and {content}",
            }
        )
        template, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert template == "Old-style template with {title} and {content}"
        assert system == "You are a SIGMA expert."

    def test_legacy_raw_text_prompt_is_template(self):
        """Bootstrap raw-text prompt is used verbatim as the template."""
        raw = "Generate Sigma detection rules from threat intelligence.\nTitle: {title}\nContent: {content}\n"
        template, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert template == raw
        assert system is None

    def test_invalid_json_treated_as_raw_text(self):
        """Malformed JSON is treated as raw text (not a silent error)."""
        raw = '{"role": "partial'  # truncated JSON
        template, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert template == raw
        assert system is None

    def test_legacy_sibling_system_prompt_key_honored_when_no_json_system(self):
        """Legacy sibling key ``system_prompt`` is used when the inner JSON has no system.

        Before locking, SigmaAgent stored the persona in a sibling ``system_prompt`` key
        and the template in ``prompt``. The helper keeps that path working.
        """
        template, system = parse_sigma_agent_prompt_data(
            {
                "prompt": "Raw template {title}",
                "system_prompt": "Persona from sibling key",
            }
        )
        assert template == "Raw template {title}"
        assert system == "Persona from sibling key"

    def test_locked_scaffold_role_wins_over_sibling_system_prompt(self):
        """When the locked JSON has role, the sibling system_prompt is NOT used."""
        raw = json.dumps({"role": "ROLE_WINS", "user_template": "t {title}"})
        _, system = parse_sigma_agent_prompt_data(
            {
                "prompt": raw,
                "system_prompt": "sibling_loses",
            }
        )
        assert system == "ROLE_WINS"

    def test_empty_prompt_data_returns_none(self):
        """Empty or missing input returns (None, None) gracefully."""
        assert parse_sigma_agent_prompt_data(None) == (None, None)
        assert parse_sigma_agent_prompt_data({}) == (None, None)
        assert parse_sigma_agent_prompt_data({"prompt": ""}) == (None, None)

    def test_non_string_prompt_returns_none_template(self):
        """If ``prompt`` is not a string, the template is None but sibling system_prompt still works."""
        template, system = parse_sigma_agent_prompt_data(
            {
                "prompt": 12345,  # not a string
                "system_prompt": "sibling",
            }
        )
        assert template is None
        assert system == "sibling"
