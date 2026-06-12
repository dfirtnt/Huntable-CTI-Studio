"""Contract tests for the read-only extractor-prompt display in workflow.html.

Standard Extractor Contract prompts (CmdlineExtract, ProcTreeExtract, ...) store
the raw config JSON in ``promptParts.system`` so Save round-trips it verbatim.
Rendering that raw JSON in the read-only "System Prompt" view produced a wall of
text -- newlines inside the role/instructions strings are escaped (``\\n``) and the
``whitespace-pre-wrap`` display only breaks on real newlines.

The fix renders the already-parsed ``templateData`` fields (Role / Task / JSON
Example / Instructions, which carry real newlines) in the read-only view, while
leaving the edit ``<textarea>`` and the save round-trip on the raw JSON untouched.

These are static-text checks against the template source -- no DOM/browser needed,
consistent with the repo note that :8001 is Docker-served from the MAIN tree.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

TEMPLATE = Path("src/web/templates/workflow.html").read_text()

# renderSinglePrompt body: from its definition up to the next top-level function.
_RENDER_SINGLE_MATCH = re.search(
    r"function renderSinglePrompt\(.+?(?=function getOrCreatePromptData)",
    TEMPLATE,
    re.DOTALL,
)
RENDER_SINGLE_BODY = _RENDER_SINGLE_MATCH.group(0) if _RENDER_SINGLE_MATCH else ""

# renderExtractorConfigFields helper body.
_HELPER_MATCH = re.search(
    r"function renderExtractorConfigFields\(.+?(?=function renderSinglePrompt)",
    TEMPLATE,
    re.DOTALL,
)
HELPER_BODY = _HELPER_MATCH.group(0) if _HELPER_MATCH else ""


class TestReadableExtractorDisplayWiring:
    def test_render_single_prompt_found(self):
        assert _RENDER_SINGLE_MATCH, "renderSinglePrompt function not found in workflow.html"

    def test_helper_function_present(self):
        """The readable-field renderer must exist."""
        assert _HELPER_MATCH, "renderExtractorConfigFields helper not found in workflow.html"

    def test_helper_renders_all_four_contract_fields(self):
        """Role / Task / JSON Example / Instructions must all be surfaced (no info regression)."""
        for field in ("role", "task", "json_example", "instructions"):
            assert f"td.{field}" in HELPER_BODY, f"renderExtractorConfigFields must render templateData.{field}"
        for label in ("Role", "Task", "JSON Example", "Instructions"):
            assert f"'{label}'" in HELPER_BODY, f"Readable display is missing the '{label}' label"

    def test_helper_escapes_values(self):
        """Field values must be HTML-escaped (they are user-editable prompt text)."""
        assert "escapeHtml(String(value))" in HELPER_BODY

    def test_helper_preserves_newlines(self):
        """The readable blocks must use whitespace-pre-wrap so the parsed newlines break."""
        assert "whitespace-pre-wrap" in HELPER_BODY


class TestReadableDisplayBranchGate:
    def test_gate_requires_template_format_and_json_config(self):
        """The readable branch must fire only for view mode + isTemplateFormat + raw-JSON system.

        Gating on a system value that starts with '{' is what keeps Sigma and other
        plain-text / {system,user} agents on the original renderer (no regression).
        """
        assert "showReadableExtractorConfig" in RENDER_SINGLE_BODY
        gate = re.search(
            r"const showReadableExtractorConfig\s*=\s*(.+?);",
            RENDER_SINGLE_BODY,
            re.DOTALL,
        )
        assert gate, "showReadableExtractorConfig assignment not found"
        expr = gate.group(1)
        assert "!isEditing" in expr, "Readable display must be view-only (not while editing)"
        assert "isTemplateFormat" in expr, "Readable display must require isTemplateFormat"
        assert "systemIsConfigJson" in expr, "Readable display must require a raw-JSON-config system"

    def test_systemiconfigjson_checks_leading_brace(self):
        """systemIsConfigJson distinguishes raw config JSON from parsed persona text."""
        assert re.search(
            r"const systemIsConfigJson\s*=.*?startsWith\('\{'\)",
            RENDER_SINGLE_BODY,
            re.DOTALL,
        ), "systemIsConfigJson must test promptParts.system.trim().startsWith('{')"

    def test_readable_branch_invokes_helper(self):
        """The view-mode HTML must call the field renderer when the gate is on."""
        assert "renderExtractorConfigFields(templateData)" in RENDER_SINGLE_BODY

    def test_display_branch_uses_systemDisplayHtml(self):
        """The non-editing System Prompt slot must render via systemDisplayHtml."""
        assert "` : systemDisplayHtml}" in RENDER_SINGLE_BODY, (
            "The read-only System Prompt branch must interpolate systemDisplayHtml"
        )


class TestEditAndSavePathUnchanged:
    """The edit textarea and save round-trip must stay on the raw JSON (regression guard)."""

    def test_edit_textarea_still_emits_raw_system(self):
        """Editing must still show the full raw config in the textarea (round-trips on Save)."""
        assert "${escapeHtml(promptParts.system)}</textarea>" in RENDER_SINGLE_BODY, (
            "Edit textarea must still bind the raw promptParts.system so Save round-trips the JSON"
        )

    def test_fallback_branch_still_renders_raw_system_for_non_extractors(self):
        """Non-extractor / plain-text agents keep the original raw-system display branch."""
        assert "${escapeHtml(promptParts.system || '(empty)')}" in RENDER_SINGLE_BODY, (
            "The non-readable display path (Sigma, {system,user}, plain text) must be preserved"
        )
