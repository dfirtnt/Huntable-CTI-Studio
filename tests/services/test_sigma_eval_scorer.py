"""Unit tests for src.services.sigma_eval_scorer.

Two layers:

- The pure set math (`_score_string_sets`) -- always runnable, mirrors the
  precision/recall contract used by the extractor eval scorer.
- The end-to-end `score_sigma` decomposition -- requires the `sigma_similarity`
  package (a uv workspace member, installed in CI/test env). These tests assert
  that two rules expressing the same detection in different YAML spellings score
  as a match, which is the whole point of decomposing through one extractor.
"""

import pytest

from src.services.sigma_atom_precompute import is_sigma_similarity_available
from src.services.sigma_eval_scorer import (
    SigmaEvalResult,
    _score_string_sets,
    score_sigma,
)

requires_sigma_similarity = pytest.mark.skipif(
    not is_sigma_similarity_available(),
    reason="sigma_similarity package not installed in this environment",
)


# ---------------------------------------------------------------------------
# Pure set-scoring layer (no sigma_similarity dependency)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_score_string_sets_exact_match():
    s = _score_string_sets({"a", "b"}, {"a", "b"})
    assert s.precision == 1.0
    assert s.recall == 1.0
    assert s.matched_count == 2
    assert s.missed_count == 0
    assert s.extra_count == 0


@pytest.mark.unit
def test_score_string_sets_partial():
    # expected {a,b,c,d}, actual {a,b,x}: 2 matched, 2 missed, 1 extra
    s = _score_string_sets({"a", "b", "c", "d"}, {"a", "b", "x"})
    assert s.matched_count == 2
    assert s.missed_count == 2
    assert s.extra_count == 1
    assert s.precision == 0.6667  # 2 / 3
    assert s.recall == 0.5  # 2 / 4
    assert s.matched == ["a", "b"]
    assert s.missed == ["c", "d"]
    assert s.extra == ["x"]


@pytest.mark.unit
def test_score_string_sets_empty_expected_with_extras():
    """No ground truth + rules generated -- precision must not divide by zero."""
    s = _score_string_sets(set(), {"x", "y"})
    assert s.precision == 0.0  # 0 / (0 + 2)
    assert s.recall == 0.0  # 0 / 0 -> defined as 0
    assert s.extra_count == 2


@pytest.mark.unit
def test_score_string_sets_zero_generation_against_expected():
    """Pipeline produced nothing but ground truth has atoms -> 0% recall."""
    s = _score_string_sets({"a", "b", "c"}, set())
    assert s.matched_count == 0
    assert s.missed_count == 3
    assert s.extra_count == 0
    assert s.recall == 0.0
    assert s.precision == 0.0


# ---------------------------------------------------------------------------
# End-to-end decomposition layer (requires sigma_similarity)
# ---------------------------------------------------------------------------

_RUNDLL32_PROC = {
    "logsource": {"category": "process_creation", "product": "windows"},
    "detection": {
        "selection": {"Image|endswith": "\\rundll32.exe", "CommandLine|contains": ".jpg,init"},
        "condition": "selection",
    },
}


@pytest.mark.unit
@requires_sigma_similarity
def test_score_sigma_identical_rule_full_score():
    result = score_sigma([_RUNDLL32_PROC], [_RUNDLL32_PROC])
    assert isinstance(result, SigmaEvalResult)
    assert result.expected_rule_count == 1
    assert result.actual_rule_count == 1
    assert result.logsource.precision == 1.0
    assert result.logsource.recall == 1.0
    assert result.atoms.precision == 1.0
    assert result.atoms.recall == 1.0
    assert result.expected_undecomposable == 0
    assert result.actual_undecomposable == 0


@pytest.mark.unit
@requires_sigma_similarity
def test_score_sigma_cosmetic_differences_still_match():
    """Same detection, different YAML spelling (case, backslash, field alias),
    must score as a perfect match because both sides run through one extractor."""
    expected = _RUNDLL32_PROC
    actual = {
        "logsource": {"category": "process_creation", "product": "windows"},
        "detection": {
            # different field casing + forward slash + uppercase value
            "sel": {"image|endswith": "/RUNDLL32.EXE", "commandline|contains": ".JPG,INIT"},
            "condition": "sel",
        },
    }
    result = score_sigma([expected], [actual])
    assert result.atoms.precision == 1.0
    assert result.atoms.recall == 1.0
    assert result.logsource.recall == 1.0


@pytest.mark.unit
@requires_sigma_similarity
def test_score_sigma_missing_field_lowers_recall():
    """Generated rule drops one of the two expected atoms -> recall < 1, precision == 1."""
    expected = _RUNDLL32_PROC
    actual = {
        "logsource": {"category": "process_creation", "product": "windows"},
        "detection": {
            "selection": {"Image|endswith": "\\rundll32.exe"},  # dropped CommandLine atom
            "condition": "selection",
        },
    }
    result = score_sigma([expected], [actual])
    assert result.atoms.recall == 0.5  # 1 of 2 expected atoms found
    assert result.atoms.precision == 1.0  # the one atom present is correct
    assert result.atoms.missed_count == 1


@pytest.mark.unit
@requires_sigma_similarity
def test_score_sigma_wrong_logsource():
    """Right atoms-ish but wrong telemetry class -> logsource recall 0."""
    expected = _RUNDLL32_PROC
    actual = {
        "logsource": {"category": "registry_set", "product": "windows"},
        "detection": {
            "selection": {"TargetObject|contains": "\\Run"},
            "condition": "selection",
        },
    }
    result = score_sigma([expected], [actual])
    assert result.logsource.recall == 0.0
    assert result.logsource.missed_count == 1
    assert result.logsource.extra_count == 1


@pytest.mark.unit
@requires_sigma_similarity
def test_score_sigma_empty_generation_zero_recall():
    result = score_sigma([_RUNDLL32_PROC], [])
    assert result.actual_rule_count == 0
    assert result.atoms.recall == 0.0
    assert result.atoms.missed_count == 2
    assert result.logsource.recall == 0.0


@pytest.mark.unit
@requires_sigma_similarity
def test_score_sigma_expected_count_override():
    """expected_rule_count can be tracked separately (e.g. eval_articles.yaml)."""
    result = score_sigma([_RUNDLL32_PROC], [_RUNDLL32_PROC], expected_rule_count=5)
    assert result.expected_rule_count == 5
    assert result.actual_rule_count == 1
