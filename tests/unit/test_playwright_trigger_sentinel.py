"""Guard: Playwright specs must trigger the workflow modal with a non-existent (sentinel)
article ID, never a real one.

Background: the "Enter key triggers primary button" test in
``tests/playwright/modal_stack_and_enter.spec.ts`` submits the trigger-workflow
modal against the LIVE server (which reads the prod DB). With a real article ID
this runs the full agentic workflow and mints a spurious ``agentic_workflow_executions``
row on every Playwright run -- the reason article 68 "Intelligence Center" kept
reappearing in ``/workflow#executions`` long after the API-smoke variant of this bug
(``tests/api/test_endpoints.py::test_workflow_trigger_smoke``) was sentinel-fixed on
2026-05-24. A sentinel ID (>= 999999) makes the trigger return 404 so no execution is
created, while the modal still shows its message so the keybinding assertion holds.

These are static-text checks -- no browser/DB needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PLAYWRIGHT_DIR = Path("tests/playwright")

# Any article ID below this is treated as a real, seedable row (pollution risk).
SENTINEL_MIN = 999999


def _specs_filling_trigger_article() -> list[Path]:
    return [p for p in PLAYWRIGHT_DIR.glob("*.spec.ts") if "#triggerArticleId" in p.read_text()]


def test_a_spec_actually_exercises_the_trigger_modal():
    """Sanity: the guarded pattern still exists (test stays meaningful)."""
    specs = _specs_filling_trigger_article()
    assert specs, "No Playwright spec fills #triggerArticleId — update this guard if the test moved."


@pytest.mark.parametrize("spec", _specs_filling_trigger_article(), ids=lambda p: p.name)
def test_trigger_article_id_default_is_sentinel(spec: Path):
    """The TEST_ARTICLE_ID fallback used to fill #triggerArticleId must be a non-existent ID."""
    text = spec.read_text()
    m = re.search(r"TEST_ARTICLE_ID\s*=\s*process\.env\.TEST_ARTICLE_ID\s*\|\|\s*'(\d+)'", text)
    assert m, (
        f"{spec.name} fills #triggerArticleId but has no "
        "`TEST_ARTICLE_ID = process.env.TEST_ARTICLE_ID || '<id>'` default to audit."
    )
    article_id = int(m.group(1))
    assert article_id >= SENTINEL_MIN, (
        f"{spec.name}: TEST_ARTICLE_ID default {article_id} is a real, seedable article ID. "
        f"Triggering it runs the full workflow against the prod DB and pollutes "
        f"/workflow#executions. Use a sentinel >= {SENTINEL_MIN} (e.g. 999999)."
    )
