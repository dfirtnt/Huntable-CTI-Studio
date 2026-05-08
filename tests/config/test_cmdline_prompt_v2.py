"""Regression tests for CmdlineExtract prompt v2 fixes (eval 3802).

Three failure modes addressed:
1. Context overflow (7/10 articles) -- instructions trimmed; dynamic overhead calc in llm_service
2. Hallucination from json_example -- synthetic placeholder values; anti-hallucination note added
3. Wrapper stripping failures -- explicit rule stating value field = post-wrapper content only

These are data-contract tests: they read the prompt file and assert structural invariants.
No LLM calls are made.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPT_PATH = REPO_ROOT / "src" / "prompts" / "CmdlineExtract"

# Commands that appeared verbatim in eval 3802 hallucinations.
# These were example values in the old json_example and leaked into real extraction output.
HALLUCINATION_TRIGGERS = [
    "ipconfig /all & whoami",
    "powershell.exe -NoP -W Hidden",
]

# Original instruction length before this fix (6419 chars).
# New version must be strictly shorter.
ORIGINAL_INSTRUCTIONS_LENGTH = 6419


def _load() -> dict:
    assert PROMPT_PATH.exists(), f"Prompt file missing: {PROMPT_PATH}"
    return json.loads(PROMPT_PATH.read_text(encoding="utf-8"))


def _example_parsed() -> dict:
    data = _load()
    raw = data["json_example"]
    return json.loads(raw) if isinstance(raw, str) else raw


class TestHallucinationMitigation:
    """json_example must use synthetic values; instructions must warn against extracting from it."""

    def test_json_example_not_hallucination_prone(self):
        """json_example must not contain the specific commands that triggered hallucinations in eval 3802."""
        example_str = json.dumps(_example_parsed())
        for trigger in HALLUCINATION_TRIGGERS:
            assert trigger not in example_str, (
                f"json_example contains '{trigger}' which caused hallucinations in eval run 3802. "
                "Replace with clearly synthetic placeholder command strings that are "
                "unlikely to appear verbatim in real CTI articles."
            )

    def test_instructions_warn_against_json_example_extraction(self):
        """instructions must contain an anti-hallucination note about json_example being template-only."""
        instructions = _load()["instructions"]
        has_note = "SYNTHETIC PLACEHOLDERS" in instructions or "FORMAT TEMPLATE" in instructions
        assert has_note, (
            "instructions must warn that json_example values are synthetic/template-only "
            "and must not be extracted. Eval 3802 showed the model copying example commands "
            "into output as if they were extracted from the article."
        )


class TestWrapperStripping:
    """Wrapper stripping rule must explicitly specify what goes in the value field after stripping."""

    def test_wrapper_handling_specifies_value_field(self):
        """WRAPPER HANDLING section must state that value = post-wrapper content only."""
        instructions = _load()["instructions"]
        # Rule 5 added in this fix: post-wrapper substring goes in value field
        has_rule = (
            "post-wrapper substring as the value field" in instructions
            or "Never include the wrapper prefix in the value field" in instructions
            or ("post-wrapper" in instructions and "value" in instructions and "wrapper" in instructions.lower())
        )
        assert has_rule, (
            "WRAPPER HANDLING must explicitly state that the value field contains the "
            "post-wrapper substring only. Eval 3802 showed inconsistent wrapper stripping "
            "because the prompt never said what to put in value after stripping."
        )


class TestContextOverhead:
    """Prompt must be shorter than the original to reduce LM Studio context overflow risk."""

    def test_final_validation_checklist_removed(self):
        """FINAL VALIDATION CHECKLIST is redundant with VALID COMMAND CRITERIA and must be removed."""
        instructions = _load()["instructions"]
        assert "FINAL VALIDATION CHECKLIST" not in instructions, (
            "FINAL VALIDATION CHECKLIST must be removed -- it duplicates VALID COMMAND CRITERIA "
            "A-E entirely, adding ~629 chars of redundant context. Eval 3802: 7/10 articles failed "
            "due to context overflow on Qwen3-8B with an 8192-token context window."
        )

    def test_instructions_shorter_than_original(self):
        """instructions must be shorter than the original 6419-char version."""
        instructions = _load()["instructions"]
        assert len(instructions) < ORIGINAL_INSTRUCTIONS_LENGTH, (
            f"instructions ({len(instructions)} chars) must be shorter than original "
            f"({ORIGINAL_INSTRUCTIONS_LENGTH} chars). Context overflow was the primary "
            "failure mode in eval 3802."
        )

    def test_architecture_context_still_present(self):
        """ARCHITECTURE CONTEXT must not be removed entirely -- agents need scope boundaries."""
        instructions = _load()["instructions"]
        assert "ARCHITECTURE CONTEXT" in instructions, (
            "ARCHITECTURE CONTEXT section must remain. Removing it would cause agents to "
            "absorb adjacent artifact types owned by sibling agents."
        )
