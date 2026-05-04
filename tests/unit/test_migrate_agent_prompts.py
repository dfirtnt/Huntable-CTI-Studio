"""Tests for scripts/migrate_agent_prompts.py normalization logic.

These exercise the pure shape-converter (`_normalize_record`) and the
canonical-shape detector (`_is_canonical`) for SigmaAgent and RankAgent.
No DB or filesystem -- the migration script's main loop is tested separately
when run with --apply against real data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add repo root so the script module is importable as `scripts.migrate_agent_prompts`.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.migrate_agent_prompts import _is_canonical, _normalize_record  # noqa: E402

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# SigmaAgent normalization
# ---------------------------------------------------------------------------


class TestNormalizeSigmaAgent:
    """SigmaAgent always converges on {system, user=None}."""

    def test_locked_scaffold_extracts_role_drops_template(self):
        raw = {
            "prompt": json.dumps({"role": "PERSONA_V1", "user_template": "tmpl {title}"}),
            "instructions": "",
        }
        result = _normalize_record("SigmaAgent", raw)
        assert result == {"system": "PERSONA_V1", "user": None}

    def test_extraction_envelope_extracts_role_drops_task_etc(self):
        raw = {
            "prompt": json.dumps(
                {
                    "role": "PERSONA_V2",
                    "task": "",
                    "json_example": "{}",
                    "instructions": "from inner",
                }
            ),
            "instructions": "outer instructions",
        }
        result = _normalize_record("SigmaAgent", raw)
        assert result == {
            "system": "PERSONA_V2",
            "user": None,
            "instructions": "outer instructions",
        }

    def test_legacy_simple_extracts_system_drops_user_for_sigma(self):
        """SigmaAgent's user is code-owned even if the legacy record had one."""
        raw = {
            "prompt": json.dumps({"system": "PERSONA_V3", "user": "old user template"}),
            "instructions": "",
        }
        result = _normalize_record("SigmaAgent", raw)
        assert result == {"system": "PERSONA_V3", "user": None}

    def test_raw_text_with_placeholders_routes_to_user_then_drops(self):
        """Even if the raw text is template-like, SigmaAgent's user is forced None."""
        raw = {"prompt": "Generate Sigma for {title}: {content}", "instructions": ""}
        result = _normalize_record("SigmaAgent", raw)
        # System stays None because the persona was never set; user dropped per SigmaAgent rule
        assert result == {"system": None, "user": None}

    def test_raw_text_persona_routes_to_system(self):
        """Auto-persist shape: plain persona text with no placeholders."""
        persona = "Generate Sigma rules strictly from observables. Focus on behaviors."
        raw = {"prompt": persona, "instructions": "", "model": "qwen/qwen3-8b"}
        result = _normalize_record("SigmaAgent", raw)
        assert result == {"system": persona, "user": None}

    def test_sibling_system_prompt_falls_through(self):
        raw = {"prompt": "", "system_prompt": "PERSONA_FROM_SIBLING"}
        result = _normalize_record("SigmaAgent", raw)
        assert result == {"system": "PERSONA_FROM_SIBLING", "user": None}

    def test_empty_record_returns_none(self):
        """Both None and {} are treated as no data -- return None so caller skips writing."""
        assert _normalize_record("SigmaAgent", None) is None
        assert _normalize_record("SigmaAgent", {}) is None

    def test_instructions_preserved_when_nonempty(self):
        raw = {
            "prompt": json.dumps({"role": "X", "user_template": "t {title}"}),
            "instructions": "important instructions",
        }
        result = _normalize_record("SigmaAgent", raw)
        assert result["instructions"] == "important instructions"

    def test_instructions_dropped_when_empty(self):
        raw = {
            "prompt": json.dumps({"role": "X", "user_template": "t {title}"}),
            "instructions": "",
        }
        result = _normalize_record("SigmaAgent", raw)
        assert "instructions" not in result


# ---------------------------------------------------------------------------
# RankAgent normalization
# ---------------------------------------------------------------------------


class TestNormalizeRankAgent:
    """RankAgent preserves both system and user when both are recoverable."""

    def test_locked_scaffold_preserves_user_template(self):
        raw = {
            "prompt": json.dumps(
                {"role": "RANK_PERSONA", "user_template": "Score: {title} {content}"}
            ),
            "instructions": "",
        }
        result = _normalize_record("RankAgent", raw)
        assert result == {"system": "RANK_PERSONA", "user": "Score: {title} {content}"}

    def test_legacy_simple_preserves_both(self):
        raw = {
            "prompt": json.dumps({"system": "RANK_PERSONA", "user": "Score {title}"}),
            "instructions": "",
        }
        result = _normalize_record("RankAgent", raw)
        assert result == {"system": "RANK_PERSONA", "user": "Score {title}"}

    def test_raw_text_template_routes_to_user(self):
        raw = {
            "prompt": "Rank this article:\nTitle: {title}\nContent: {content}",
            "instructions": "",
        }
        result = _normalize_record("RankAgent", raw)
        assert result["user"] == "Rank this article:\nTitle: {title}\nContent: {content}"
        assert result["system"] is None

    def test_raw_text_persona_routes_to_system(self):
        """Shape-5 from the live DB: persona text without placeholders."""
        persona = "You are a strict CTI ranking analyst. Score 1-10."
        raw = {"prompt": persona, "instructions": "", "model": "qwen/qwen3-8b"}
        result = _normalize_record("RankAgent", raw)
        assert result == {"system": persona, "user": None}

    def test_extraction_envelope_extracts_role_drops_task(self):
        """If RankAgent was ever saved with the extraction envelope, recover the role."""
        raw = {
            "prompt": json.dumps(
                {"role": "RANK_PERSONA", "task": "", "json_example": "{}", "instructions": ""}
            ),
            "instructions": "",
        }
        result = _normalize_record("RankAgent", raw)
        assert result == {"system": "RANK_PERSONA", "user": None}


# ---------------------------------------------------------------------------
# _is_canonical
# ---------------------------------------------------------------------------


class TestIsCanonical:
    def test_minimal_canonical_form(self):
        assert _is_canonical({"system": "x", "user": None})
        assert _is_canonical({"system": None, "user": "tmpl {title}"})
        assert _is_canonical({"system": "x", "user": None, "instructions": "y"})

    def test_missing_system_or_user_is_not_canonical(self):
        assert not _is_canonical({"system": "x"})
        assert not _is_canonical({"user": "tmpl"})

    def test_extraneous_keys_disqualify(self):
        assert not _is_canonical({"system": "x", "user": None, "model": "qwen/qwen3-8b"})
        assert not _is_canonical({"prompt": "...", "instructions": ""})

    def test_empty_dict_or_none_not_canonical(self):
        assert not _is_canonical({})
        assert not _is_canonical(None)

    def test_legacy_shapes_not_canonical(self):
        # Shape 5 (auto-persist)
        assert not _is_canonical({"prompt": "...", "model": "x", "instructions": ""})
        # Shape 4 (raw text)
        assert not _is_canonical({"prompt": "raw text", "instructions": ""})
