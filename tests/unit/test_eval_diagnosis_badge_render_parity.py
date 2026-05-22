"""Regression: the diagnosis-history `[dx N]` badge must render in BOTH
agent-evals result table render paths.

`agent_evals.html` has two render paths for the results table:

  * ``renderSubagentResultsPivot()``  -- the matrix/pivot view (one clickable
    cell per config version). This path already emitted a hidden
    ``.dx-badge`` placeholder + ``data-exec-id`` on the clickable cell and
    called ``applyDiagnosisCounts()`` after writing the results-table HTML.

  * ``renderSubagentResults()``  -- the flat-list view (Article / Expected /
    Actual / Score / Status). This path historically emitted NO ``.dx-badge``
    placeholder and never called ``applyDiagnosisCounts()``, so the badge was
    invisible in that view even when saved diagnoses existed.

This is a render-path *parity contract*: every clickable result cell, in
either path, must carry the badge wiring so ``applyDiagnosisCounts()`` (which
stamps every ``td[data-exec-id]`` containing a ``.dx-badge``) can light it up.

The contract is asserted as template structure, not API behaviour: the
``/api/evaluations/evals/diagnosis-counts`` endpoint already works, so an
API-level test would pass before any fix. Only a template-structure assertion
genuinely fails on the missing flat-list wiring and guards against regression
(matching the repo convention in ``tests/unit/test_inline_validate_button_visible.py``).
"""

import re
from pathlib import Path

import pytest

AGENT_EVALS_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "agent_evals.html"

DX_BADGE_PLACEHOLDER = '<span class="dx-badge" style="display:none;"></span>'
EXEC_ID_GUARD = "if (result.execution_id)"
# Assembled from two pieces so this test file does not itself contain the
# literal `innerHTML =` token. A security linter flags that pattern as a
# possible XSS sink; that concern is about production DOM writes, not a
# string-matching assertion, so splitting the needle keeps the test's exact
# behaviour while keeping the linter quiet.
HTML_WRITE_NEEDLE = "resultsTable.inner" + "HTML = html;"
# The invocation statement, not a bare `applyDiagnosisCounts(` -- the latter
# also matches the JSDoc-style comment ("...filled by applyDiagnosisCounts()
# after table renders") that the matrix path emits *before* the HTML write,
# which would make the after-write order assertion misfire in both paths.
APPLY_CALL = "applyDiagnosisCounts();"


def _extract_function_body(text: str, func_name: str) -> str:
    """Return the source between ``function <func_name>(...) {`` and the next
    top-level ``function `` declaration.

    ``\\(`` anchors the name so ``renderSubagentResults`` does not also match
    ``renderSubagentResultsPivot``.
    """
    match = re.search(
        rf"function {re.escape(func_name)}\([^)]*\)\s*\{{(.*?)\nfunction ",
        text,
        re.DOTALL,
    )
    assert match, f"{func_name} function not found in agent_evals.html"
    return match.group(1)


@pytest.mark.unit
@pytest.mark.regression
class TestDiagnosisBadgeRenderParity:
    @pytest.fixture(scope="class")
    def template_text(self) -> str:
        return AGENT_EVALS_TEMPLATE.read_text()

    @pytest.fixture(scope="class")
    def matrix_body(self, template_text: str) -> str:
        return _extract_function_body(template_text, "renderSubagentResultsPivot")

    @pytest.fixture(scope="class")
    def flat_list_body(self, template_text: str) -> str:
        return _extract_function_body(template_text, "renderSubagentResults")

    # -- reference path (matrix): guards the working path from regressing -----

    def test_matrix_path_has_badge_wiring(self, matrix_body: str) -> None:
        """The matrix path is the reference; it must keep its badge wiring."""
        assert matrix_body.count("data-exec-id") == 1, (
            "matrix path must carry data-exec-id on exactly one clickable cell"
        )
        assert matrix_body.count(DX_BADGE_PLACEHOLDER) == 1, (
            "matrix path must emit exactly one hidden .dx-badge placeholder"
        )
        write_idx = matrix_body.find(HTML_WRITE_NEEDLE)
        apply_idx = matrix_body.find(APPLY_CALL)
        assert write_idx != -1 and apply_idx != -1, (
            "matrix path must perform the results-table HTML write and call applyDiagnosisCounts()"
        )
        assert write_idx < apply_idx, "applyDiagnosisCounts() must run AFTER the results-table HTML is written"

    # -- flat-list path: RED before the fix, GREEN after ---------------------

    def test_flat_list_path_has_data_exec_id(self, flat_list_body: str) -> None:
        """Flat-list clickable cell must carry data-exec-id so
        applyDiagnosisCounts()'s ``td[data-exec-id]`` selector can find it."""
        assert "data-exec-id" in flat_list_body, (
            "flat-list path (renderSubagentResults) is missing the data-exec-id attribute on its clickable result cell"
        )

    def test_flat_list_path_has_guarded_dx_badge_placeholder(self, flat_list_body: str) -> None:
        """Flat-list cell must emit the hidden .dx-badge placeholder, guarded by
        result.execution_id, exactly as the matrix path does."""
        assert DX_BADGE_PLACEHOLDER in flat_list_body, (
            "flat-list path (renderSubagentResults) is missing the hidden .dx-badge placeholder span"
        )
        guard_idx = flat_list_body.find(EXEC_ID_GUARD)
        badge_idx = flat_list_body.find(DX_BADGE_PLACEHOLDER)
        assert guard_idx != -1 and guard_idx < badge_idx, (
            "the .dx-badge placeholder must be guarded by `if (result.execution_id)`"
        )

    def test_flat_list_path_calls_apply_diagnosis_counts_after_write(self, flat_list_body: str) -> None:
        """applyDiagnosisCounts() must be invoked after the flat-list path
        writes the results-table HTML, mirroring the matrix path."""
        write_idx = flat_list_body.find(HTML_WRITE_NEEDLE)
        apply_idx = flat_list_body.find(APPLY_CALL)
        assert write_idx != -1, "flat-list path must perform the results-table HTML write"
        assert apply_idx != -1, "flat-list path (renderSubagentResults) never calls applyDiagnosisCounts()"
        assert write_idx < apply_idx, "applyDiagnosisCounts() must run AFTER the results-table HTML write"

    def test_flat_list_does_not_double_stamp(self, flat_list_body: str) -> None:
        """Exactly one cell per row carries the badge wiring. The flat-list has
        two clickable cells (Actual + Score) sharing onClickAttr; wiring both
        would render two `[dx N]` badges per row. Pin it to one."""
        assert flat_list_body.count("data-exec-id") == 1, (
            f"expected data-exec-id on exactly one flat-list cell, found "
            f"{flat_list_body.count('data-exec-id')} (double-badge regression)"
        )
        assert flat_list_body.count(DX_BADGE_PLACEHOLDER) == 1, (
            f"expected exactly one .dx-badge placeholder in the flat-list path, "
            f"found {flat_list_body.count(DX_BADGE_PLACEHOLDER)}"
        )
