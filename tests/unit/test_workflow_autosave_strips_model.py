"""Regression: workflow save paths must not persist a model sibling in prompts.

Shape-5 (agent_prompts.X = {"model": ..., "prompt": "...", "instructions": ...})
was generated because the in-memory `agentPrompts[X]` object held a `model`
field for UI display, and `performAutoSave` sent the whole structure to
the API verbatim.  `model` selection is canonical in `agent_models.X` --
duplicating it inside `agent_prompts.X` creates a shape that
parse_sigma_agent_prompt_data and the rank/sigma readers must work around.

These are static-text checks against workflow.html -- no DOM/browser needed.
"""

from __future__ import annotations

import re

import pytest

from tests.utils.workflow_html_source import read_workflow_src

pytestmark = pytest.mark.unit

TEMPLATE = read_workflow_src()

# Locate the autosave and explicit-save bodies independently.
_AUTOSAVE_MATCH = re.search(r"async function performAutoSave\(\)\s*\{(.+?)\n\}", TEMPLATE, re.DOTALL)
PERFORM_AUTOSAVE_BODY = _AUTOSAVE_MATCH.group(1) if _AUTOSAVE_MATCH else ""
_SAVE_START = TEMPLATE.find("workflowConfigForm.addEventListener('submit'")
_SAVE_END = re.search(r"^\}", TEMPLATE[_SAVE_START:], re.MULTILINE) if _SAVE_START >= 0 else None
SAVE_HANDLER_BODY = TEMPLATE[_SAVE_START : _SAVE_START + _SAVE_END.end()] if _SAVE_END else ""


class TestAutoSaveSendsNoPromptRecords:
    def test_performAutoSave_function_present(self):
        assert _AUTOSAVE_MATCH, "performAutoSave function not found in workflow.html"

    def test_autosave_payload_is_extract_agent_settings_only(self):
        match = re.search(r"const promptsCopy\s*=\s*\{([^}]*)\}", PERFORM_AUTOSAVE_BODY)
        assert match is not None, "performAutoSave no longer builds promptsCopy as an object literal"
        assert re.findall(r"(\w+)\s*:", match.group(1)) == ["ExtractAgentSettings"]

    def test_autosave_sends_that_payload(self):
        assert "agent_prompts: promptsCopy" in PERFORM_AUTOSAVE_BODY


class TestExplicitSaveStripsModelFromAgentPrompts:
    def test_save_handler_present(self):
        assert SAVE_HANDLER_BODY, "#workflowConfigForm submit handler not found in workflow.html"
        assert "formData.agent_prompts" in SAVE_HANDLER_BODY

    def test_strip_block_deletes_model_key(self):
        """The strip block must call `delete promptsCopy[key].model` (or equivalent)."""
        assert "delete promptsCopy[key].model" in SAVE_HANDLER_BODY, (
            "the explicit Save handler must strip the model sibling from each agent prompt before sending."
        )

    def test_strip_block_skips_extract_agent_settings(self):
        """ExtractAgentSettings is a settings container, not a prompt -- must be exempted."""
        assert re.search(
            r"ExtractAgentSettings.*continue|continue.*ExtractAgentSettings",
            SAVE_HANDLER_BODY,
            re.DOTALL,
        ), "ExtractAgentSettings exemption must use a 'continue' guard."

    def test_strip_runs_before_payload_send(self):
        """The strip block must execute before the explicit Save payload is built."""
        strip_idx = SAVE_HANDLER_BODY.find("delete promptsCopy[key].model")
        payload_idx = SAVE_HANDLER_BODY.find("formData.agent_prompts = ")
        assert strip_idx >= 0 and payload_idx >= 0, "Strip block or payload assembly missing"
        assert strip_idx < payload_idx, (
            "strip block must execute before the payload is built; otherwise the unstripped object goes to the API."
        )
