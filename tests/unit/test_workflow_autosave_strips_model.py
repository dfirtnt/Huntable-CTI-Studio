"""Regression: performAutoSave must strip the 'model' sibling from agent_prompts.

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
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

TEMPLATE = Path("src/web/templates/workflow.html").read_text()

# Locate the performAutoSave function body so the strip block must live inside it.
_FN_MATCH = re.search(
    r"async function performAutoSave\(\)\s*\{(.+?)\n\}",
    TEMPLATE,
    re.DOTALL,
)
PERFORM_AUTOSAVE_BODY = _FN_MATCH.group(1) if _FN_MATCH else ""


class TestAutoSaveStripsModelFromAgentPrompts:
    def test_performAutoSave_function_present(self):
        assert _FN_MATCH, "performAutoSave function not found in workflow.html"

    def test_strip_block_deletes_model_key(self):
        """The strip block must call `delete promptsCopy[key].model` (or equivalent)."""
        assert "delete promptsCopy[key].model" in PERFORM_AUTOSAVE_BODY, (
            "performAutoSave must strip the 'model' sibling from each agent_prompts entry "
            "before sending the autosave payload."
        )

    def test_strip_block_skips_extract_agent_settings(self):
        """ExtractAgentSettings is a settings container, not a prompt -- must be exempted."""
        assert "ExtractAgentSettings" in PERFORM_AUTOSAVE_BODY, (
            "Strip loop must reference ExtractAgentSettings explicitly (skip exemption)."
        )
        # The exemption uses a continue / equality check
        assert re.search(
            r"ExtractAgentSettings.*continue|continue.*ExtractAgentSettings",
            PERFORM_AUTOSAVE_BODY,
            re.DOTALL,
        ), "ExtractAgentSettings exemption must use a 'continue' guard."

    def test_strip_runs_before_payload_send(self):
        """The strip block must execute BEFORE the agent_prompts payload is constructed."""
        strip_idx = PERFORM_AUTOSAVE_BODY.find("delete promptsCopy[key].model")
        payload_idx = PERFORM_AUTOSAVE_BODY.find("agent_prompts: promptsCopy")
        assert strip_idx >= 0 and payload_idx >= 0, "Strip block or payload assembly missing"
        assert strip_idx < payload_idx, (
            "Strip block must run BEFORE the autosave payload is built; "
            "otherwise the unstripped object goes to the API."
        )
