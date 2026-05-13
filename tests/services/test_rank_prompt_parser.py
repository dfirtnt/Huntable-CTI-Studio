"""Tests for _parse_rank_prompt — RankAgent prompt-shape resolver.

RankAgent's prompt is stored in agent_prompts.RankAgent in the same multi-shape
mess that bit SigmaAgent.  _parse_rank_prompt resolves the user-message
template and optional system override across shapes 1, 3, and raw text.

KNOWN LIMITATION: shape-5 (auto-persist plain persona text without placeholders)
is NOT detected here -- it returns the persona as the user template and the
caller's .format() drops the article.  These tests pin down the supported
shapes and document the shape-5 hole; the actual fix lives in the UI write
side (subtasks 1+2 of the SigmaAgent simplification issue).
"""

from __future__ import annotations

import json

import pytest

from src.services.llm_service import PreprocessInvariantError, _parse_rank_prompt

pytestmark = pytest.mark.unit


class TestParseRankPromptSupportedShapes:
    def test_locked_scaffold_extracts_user_template_and_role(self):
        """Shape 1 ({role, user_template}): user_template -> template, role -> system."""
        raw = json.dumps(
            {
                "role": "You are a CTI ranking analyst.",
                "user_template": "Rank: {title} | {content}",
            }
        )
        template, system = _parse_rank_prompt(raw)
        assert template == "Rank: {title} | {content}"
        assert system == "You are a CTI ranking analyst."

    def test_legacy_simple_extracts_user_and_system(self):
        """Shape 3 ({system, user}): user -> template, system -> system."""
        raw = json.dumps(
            {
                "system": "Score 1-10.",
                "user": "Article: {title}\n{content}",
            }
        )
        template, system = _parse_rank_prompt(raw)
        assert template == "Article: {title}\n{content}"
        assert system == "Score 1-10."

    def test_generic_prompt_key_extracts_as_template(self):
        """Generic JSON {prompt, system}: prompt -> template, system -> system."""
        raw = json.dumps({"prompt": "Rank {title}", "system": "You are an analyst."})
        template, system = _parse_rank_prompt(raw)
        assert template == "Rank {title}"
        assert system == "You are an analyst."

    def test_raw_text_template_passthrough(self):
        """Plain text with placeholders is returned verbatim, no system override."""
        raw = "Rank this article:\nTitle: {title}\nContent: {content}\n"
        template, system = _parse_rank_prompt(raw)
        assert template == raw
        assert system is None


class TestParseRankPromptEdgeCases:
    def test_json_with_empty_system_raises(self):
        """JSON-shape prompt without a system/role must abort -- silent empty system is unsafe."""
        raw = json.dumps({"user": "tmpl {title}"})
        with pytest.raises(PreprocessInvariantError):
            _parse_rank_prompt(raw)

    def test_json_with_only_system_returns_system_as_template(self):
        """When only system is set in JSON, system text becomes the template (legacy fallback)."""
        raw = json.dumps({"system": "Just a system prompt, no user."})
        template, system = _parse_rank_prompt(raw)
        assert template == "Just a system prompt, no user."
        assert system == "Just a system prompt, no user."

    def test_invalid_json_treated_as_raw_text(self):
        """Malformed JSON falls back to raw-text passthrough."""
        raw = '{"role": "partial'  # truncated JSON
        template, system = _parse_rank_prompt(raw)
        assert template == raw
        assert system is None

    def test_role_alias_for_system(self):
        """role key is honored as a system override alias."""
        raw = json.dumps({"role": "Analyst persona", "user_template": "tmpl {title}"})
        _, system = _parse_rank_prompt(raw)
        assert system == "Analyst persona"


class TestParseRankPromptDocumentedLimitations:
    """Documents the behavior of the inner _parse_rank_prompt for shape-5 (auto-persist).

    Shape 5 produced plain persona text with no placeholders, stored at
    agent_prompts.RankAgent.prompt with a sibling "model" key.  At the
    _parse_rank_prompt layer there is no way to distinguish persona from
    template, so the text is returned as the template -- and downstream
    .format() becomes a no-op, silently dropping the article.

    Status (2026-05-04):
    - UI fix landed (LOCKED_CANONICAL_AGENTS): RankAgent user scaffold is
      now locked; new saves always use the canonical {system, user} shape.
    - parse_rank_agent_prompt_data (the public API) already handles shape-5
      correctly via a disambiguation check (no-placeholder text -> system).
      See TestParseRankAgentPromptDataCanonical.test_legacy_raw_text_persona_routes_to_system.
    - _parse_rank_prompt (this class) retains the documented behavior because
      it is an internal helper; all callers go through parse_rank_agent_prompt_data.
    - DB migration of existing shape-5 records: deferred (separate task).
    """

    def test_shape5_persona_text_misroutes_as_template(self):
        """Inner _parse_rank_prompt: persona text without placeholders becomes template.
        The outer parse_rank_agent_prompt_data wrapper disambiguates this correctly."""
        persona = "You are a strict CTI analyst. Score 1-10 for huntability."
        template, system = _parse_rank_prompt(persona)
        # _parse_rank_prompt behavior: persona is the template, no system override.
        # parse_rank_agent_prompt_data adds a disambiguation step that corrects this.
        assert template == persona
        assert system is None
        assert "{title}" not in template, "Sanity: shape-5 persona has no placeholders"


# ---------------------------------------------------------------------------
# parse_rank_agent_prompt_data: outer-dict-aware helper (canonical + legacy)
# ---------------------------------------------------------------------------


class TestParseRankAgentPromptDataCanonical:
    """Tests for the outer-dict-aware helper that mirrors parse_sigma_agent_prompt_data."""

    def test_canonical_shape_extracts_system_and_user(self):
        """Post-migration: {system, user} at outer level read directly."""
        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        template, system = parse_rank_agent_prompt_data({"system": "RANK_PERSONA", "user": "Score: {title}"})
        assert template == "Score: {title}"
        assert system == "RANK_PERSONA"

    def test_canonical_shape_with_user_null(self):
        """RankAgent canonical record with user=null falls back to file scaffold (template=None)."""
        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        template, system = parse_rank_agent_prompt_data({"system": "RANK_PERSONA", "user": None})
        assert template is None
        assert system == "RANK_PERSONA"

    def test_canonical_only_system_present(self):
        """Outer dict with just 'system' is canonical."""
        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        template, system = parse_rank_agent_prompt_data({"system": "PERSONA_ONLY"})
        assert template is None
        assert system == "PERSONA_ONLY"

    def test_legacy_prompt_field_routes_through_parse_rank_prompt(self):
        """Legacy {prompt: <json>} still works via _parse_rank_prompt."""
        import json

        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        raw = {
            "prompt": json.dumps({"role": "LEGACY_PERSONA", "user_template": "tmpl {title}"}),
            "instructions": "",
        }
        template, system = parse_rank_agent_prompt_data(raw)
        assert template == "tmpl {title}"
        assert system == "LEGACY_PERSONA"

    def test_legacy_raw_text_persona_routes_to_system(self):
        """Legacy raw-text persona without placeholders becomes system."""
        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        persona = "You are a strict CTI analyst. Score 1-10."
        raw = {"prompt": persona, "instructions": "", "model": "qwen/qwen3-8b"}
        template, system = parse_rank_agent_prompt_data(raw)
        assert template is None
        assert system == persona

    def test_legacy_raw_text_template_routes_to_user(self):
        """Legacy raw text WITH placeholders is treated as the user template."""
        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        raw = {"prompt": "Rank: {title} {content}", "instructions": ""}
        template, system = parse_rank_agent_prompt_data(raw)
        assert template == "Rank: {title} {content}"
        assert system is None

    def test_canonical_shape_user_empty_string_treated_as_null(self):
        """Locked-scaffold saves send user='' (empty string); that must yield template=None.

        saveAgentPrompt2 sends user='' when the user scaffold is locked
        (LOCKED_CANONICAL_AGENTS). The parser must not forward '' as a template or
        the file-based rank_article.txt scaffold would be skipped.
        """
        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        template, system = parse_rank_agent_prompt_data({"system": "RANK_PERSONA", "user": ""})
        assert template is None
        assert system == "RANK_PERSONA"

    def test_canonical_shape_user_non_placeholder_text_passes_through(self):
        """Plain text in the user field is returned as template verbatim.
        The UI lock (LOCKED_CANONICAL_AGENTS) prevents this from happening in practice;
        this test documents the contract so a future bypass is immediately visible."""
        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        template, system = parse_rank_agent_prompt_data(
            {"system": "RANK_PERSONA", "user": "plain text no placeholders"}
        )
        assert template == "plain text no placeholders"
        assert system == "RANK_PERSONA"

    def test_empty_record_returns_none_pair(self):
        from src.utils.prompt_loader import parse_rank_agent_prompt_data

        assert parse_rank_agent_prompt_data(None) == (None, None)
        assert parse_rank_agent_prompt_data({}) == (None, None)
        assert parse_rank_agent_prompt_data({"prompt": ""}) == (None, None)
