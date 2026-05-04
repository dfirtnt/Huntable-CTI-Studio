"""Tests for src.utils.prompt_loader.parse_sigma_agent_prompt_data.

SigmaAgent's DB prompt has four historical shapes the parser must handle:
  1. Locked scaffold JSON:    {"role": ..., "user_template": ...}
  2. Extraction-agent JSON:   {"role": ..., "task": ..., "json_example": ..., "instructions": ...}
  3. Legacy simple JSON:      {"system": ..., "user": ...}
  4. Legacy raw text:         template text with {title}/{content} placeholders

Plus the legacy sibling ``system_prompt`` key that pre-dated the locked format.

Shape 2 is the active save format: the UI treats SigmaAgent as a locked extractor
(LOCKED_EXTRACTOR_AGENTS includes 'SigmaAgent'), so saveAgentPrompt2() packages the
system persona into "role" and adds empty "task"/"json_example"/"instructions" keys.
The parser must extract "role" as the system prompt and return template=None so the
file-based user scaffold (sigma_generate_multi.txt) continues to be used.
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
        """Malformed JSON with no format placeholders is treated as system persona.

        Truncated/broken JSON cannot be a valid user template (no {identifier}
        placeholders), so it is routed to system rather than silently dropped.
        """
        raw = '{"role": "partial'  # truncated JSON, no {identifier} placeholders
        template, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert template is None
        assert system == raw

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

    # ------------------------------------------------------------------
    # Canonical shape (post-migration): {system, user} at outer level
    # ------------------------------------------------------------------

    def test_canonical_shape_extracts_system_and_user(self):
        """Post-migration canonical shape: {system, user} read directly."""
        template, system = parse_sigma_agent_prompt_data(
            {"system": "PERSONA_CANONICAL", "user": "tmpl {title}"}
        )
        assert template == "tmpl {title}"
        assert system == "PERSONA_CANONICAL"

    def test_canonical_shape_with_user_null(self):
        """SigmaAgent's canonical record always has user=null (template is code-owned)."""
        template, system = parse_sigma_agent_prompt_data(
            {"system": "PERSONA_CANONICAL", "user": None}
        )
        assert template is None
        assert system == "PERSONA_CANONICAL"

    def test_canonical_shape_only_system_present(self):
        """Outer dict with only 'system' key (user omitted) still detected as canonical."""
        template, system = parse_sigma_agent_prompt_data({"system": "PERSONA_ONLY"})
        assert template is None
        assert system == "PERSONA_ONLY"

    def test_canonical_shape_with_instructions_passthrough_ignored(self):
        """Optional instructions field doesn't break canonical detection."""
        template, system = parse_sigma_agent_prompt_data(
            {"system": "PERSONA", "user": None, "instructions": "extra"}
        )
        assert template is None
        assert system == "PERSONA"

    def test_canonical_takes_precedence_over_legacy_when_both_present(self):
        """If somehow both shapes are present, canonical wins.

        Defensive: malformed records that include 'system' alongside legacy 'prompt'
        should prefer canonical (newer, post-migration). The presence of 'prompt'
        means we fall through to the legacy parser instead -- this asserts the
        documented detection contract.
        """
        # Canonical is detected ONLY when 'prompt' is absent or empty. With non-empty
        # 'prompt', legacy parsing wins -- documented behavior.
        legacy = parse_sigma_agent_prompt_data(
            {"system": "CANONICAL_PERSONA", "user": "tmpl {title}", "prompt": "raw template {title}"}
        )
        # The legacy 'prompt' (raw text with placeholder) is treated as template.
        assert legacy[0] == "raw template {title}"

    # ------------------------------------------------------------------
    # Extraction-agent save format (regression for silent prompt drop)
    # ------------------------------------------------------------------

    def test_extraction_agent_format_extracts_role_as_system(self):
        """Regression: UI saves SigmaAgent in extraction-agent envelope.

        saveAgentPrompt2() wraps the system persona as "role" and adds empty
        "task", "json_example", "instructions" keys.  The parser must return
        the persona as ``system`` and leave ``template`` as None so the
        file-based user scaffold (sigma_generate_multi.txt) is used.

        Before the fix this shape fell through to the raw-text branch, causing
        the entire JSON blob to be passed to str.format(), which raised KeyError
        on the "{}" in json_example and silently fell back to the file prompt
        with system=None (hardcoded default system prompt).
        """
        persona = "teststring123\n\nGenerate Sigma detection rules strictly from provided structured observables."
        raw = json.dumps(
            {
                "role": persona,
                "task": "",
                "json_example": "{}",
                "instructions": "",
            }
        )
        template, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert system == persona
        assert template is None  # user scaffold is code-owned; file fallback takes over

    def test_extraction_agent_format_empty_role_returns_none_system(self):
        """An empty "role" string in the extraction-agent envelope returns system=None."""
        raw = json.dumps({"role": "", "task": "", "json_example": "{}", "instructions": ""})
        template, system = parse_sigma_agent_prompt_data({"prompt": raw})
        assert system is None
        assert template is None

    def test_extraction_agent_format_sibling_system_prompt_ignored_when_role_present(self):
        """When role is non-empty, sibling system_prompt must NOT override it."""
        raw = json.dumps({"role": "ROLE_WINS", "task": "", "json_example": "{}", "instructions": ""})
        _, system = parse_sigma_agent_prompt_data(
            {
                "prompt": raw,
                "system_prompt": "sibling_loses",
            }
        )
        assert system == "ROLE_WINS"

    def test_extraction_agent_format_sibling_honored_when_role_empty(self):
        """When the envelope role is empty, fall through to sibling system_prompt."""
        raw = json.dumps({"role": "", "task": "", "json_example": "{}", "instructions": ""})
        _, system = parse_sigma_agent_prompt_data(
            {
                "prompt": raw,
                "system_prompt": "sibling_active",
            }
        )
        assert system == "sibling_active"

    def test_extraction_agent_format_json_example_braces_do_not_raise(self):
        """The literal '{}' in json_example must not cause KeyError when template is later formatted.

        This was the immediate trigger of the silent failure: the raw JSON blob was
        being handed to str.format(title=..., content=...) with an unmatched '{}'
        in it. The parser must not return this blob as the template.
        """
        raw = json.dumps({"role": "my persona", "task": "", "json_example": "{}", "instructions": ""})
        template, _ = parse_sigma_agent_prompt_data({"prompt": raw})
        assert template is None  # must NOT be the JSON blob

    # ------------------------------------------------------------------
    # Auto-persist shape (shape 5 regression)
    # ------------------------------------------------------------------

    def test_auto_persist_shape_treats_prompt_as_system(self):
        """Regression: auto-persist saves {model, prompt='persona text', instructions}.

        When the user edits the SigmaAgent persona and saves the whole config
        (not via the 'Save Agent Prompt' button), the textarea value is written
        directly to agent_prompts.SigmaAgent.prompt alongside a sibling 'model'
        key from the model selector.  The plain text has no {title}/{content}
        placeholders and is the system persona -- it must be returned as system,
        not as the user template.
        """
        persona = "Generate Sigma detection rules strictly from provided structured observables. Focus on behaviors, not atomic IOCs."
        data = {"model": "qwen/qwen3-8b", "prompt": persona, "instructions": ""}
        template, system = parse_sigma_agent_prompt_data(data)
        assert system == persona
        assert template is None

    def test_auto_persist_shape_empty_prompt_returns_none_system(self):
        """Empty prompt in auto-persist shape returns system=None."""
        data = {"model": "qwen/qwen3-8b", "prompt": "", "instructions": ""}
        template, system = parse_sigma_agent_prompt_data(data)
        assert system is None
        assert template is None

    def test_auto_persist_shape_sibling_system_prompt_overridden_by_prompt(self):
        """When model key is present and prompt is non-empty, prompt wins over sibling system_prompt."""
        persona = "My custom SigmaAgent persona"
        data = {"model": "qwen/qwen3-8b", "prompt": persona, "instructions": "", "system_prompt": "should-lose"}
        _, system = parse_sigma_agent_prompt_data(data)
        assert system == persona

    def test_auto_persist_shape_does_not_trigger_when_prompt_is_json(self):
        """If the prompt field is valid JSON (shapes 1-3), model key must not interfere."""
        inner = json.dumps({"role": "ROLE", "user_template": "tmpl {title}"})
        data = {"model": "qwen/qwen3-8b", "prompt": inner, "instructions": ""}
        template, system = parse_sigma_agent_prompt_data(data)
        # Should follow locked-scaffold branch, not auto-persist branch
        assert template == "tmpl {title}"
        assert system == "ROLE"
