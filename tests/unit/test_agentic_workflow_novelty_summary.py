"""RED: novelty-summary must distinguish an *inconclusive* comparator result
(candidates evaluated, zero behavioral matches) from a *scored* low/zero result.

Regression guard for todo 001 (C1+C2): the deterministic novelty comparator
collapsed "evaluated N candidates, found 0 behavioral matches" into the same
``max_similarity=0.0`` as a genuinely-scored low result. That made 86% of the
review queue look like confident "novel" (0.0%) and silently disabled novelty
suppression. ``summarize_rule_novelty`` is the single source of truth that keeps
the two cases distinct: inconclusive => ``max_similarity=None`` (unscored).
"""

import pytest

from src.workflows.agentic_workflow import summarize_rule_novelty


@pytest.mark.unit
def test_inconclusive_comparator_is_unscored_not_zero():
    """1175 candidates evaluated, 0 behavioral matches -> NOT a confident 0.0."""
    r = summarize_rule_novelty(
        {"matches": [], "total_candidates_evaluated": 1175, "behavioral_matches_found": 0},
        0.5,
    )
    assert r["max_similarity"] is None
    assert r["comparator_inconclusive"] is True
    assert r["total_candidates_evaluated"] == 1175
    assert r["behavioral_matches_found"] == 0


@pytest.mark.unit
def test_real_matches_preserve_max_score():
    """Real behavioral matches -> max similarity is the true max, not inconclusive."""
    r = summarize_rule_novelty(
        {
            "matches": [{"similarity": 0.42}, {"similarity": 0.81}],
            "total_candidates_evaluated": 1175,
            "behavioral_matches_found": 2,
        },
        0.5,
    )
    assert r["max_similarity"] == 0.81
    assert r["comparator_inconclusive"] is False


@pytest.mark.unit
def test_below_threshold_real_score_stays_scored():
    """A genuine low score must NOT be reclassified as inconclusive (over-correction guard)."""
    r = summarize_rule_novelty(
        {
            "matches": [{"similarity": 0.12}],
            "total_candidates_evaluated": 1175,
            "behavioral_matches_found": 1,
        },
        0.5,
    )
    assert r["max_similarity"] == 0.12
    assert r["comparator_inconclusive"] is False


@pytest.mark.unit
def test_empty_corpus_zero_candidates_stays_zero():
    """total==0 means "nothing to compare" -> keep current 0.0 semantics, NOT inconclusive."""
    r = summarize_rule_novelty(
        {"matches": [], "total_candidates_evaluated": 0, "behavioral_matches_found": 0},
        0.5,
    )
    assert r["max_similarity"] == 0.0
    assert r["comparator_inconclusive"] is False


@pytest.mark.unit
def test_missing_keys_default_to_safe_zero():
    """Robustness: a result dict missing every key must not raise; behaves as
    "nothing compared" (0.0, not inconclusive)."""
    r = summarize_rule_novelty({}, 0.5)
    assert r["max_similarity"] == 0.0
    assert r["comparator_inconclusive"] is False
    assert r["total_candidates_evaluated"] == 0
    assert r["behavioral_matches_found"] == 0


@pytest.mark.unit
def test_explicit_none_values_are_coerced():
    """The except-fallback of assess_rule_novelty can yield None-ish
    fields; `int(... or 0)` / `or []` must coerce, not raise."""
    r = summarize_rule_novelty(
        {"matches": None, "total_candidates_evaluated": None, "behavioral_matches_found": None},
        0.5,
    )
    assert r["max_similarity"] == 0.0
    assert r["comparator_inconclusive"] is False
    assert r["total_candidates_evaluated"] == 0
    assert r["behavioral_matches_found"] == 0


@pytest.mark.unit
def test_matches_without_similarity_key_default_zero():
    """A match dict missing 'similarity' must not raise; contributes 0.0."""
    r = summarize_rule_novelty(
        {"matches": [{}], "total_candidates_evaluated": 5, "behavioral_matches_found": 1},
        0.5,
    )
    assert r["max_similarity"] == 0.0
    assert r["comparator_inconclusive"] is False


@pytest.mark.unit
def test_behavioral_count_is_authority_over_match_list():
    """CONTRACT: inconclusivity is decided by behavioral_matches_found==0 (with
    candidates>0), NOT by len(matches). A contradictory result (candidates>0,
    behavioral==0, but a stray match present) is still inconclusive -> None.
    Guards the gate against trusting a populated-but-meaningless match list."""
    r = summarize_rule_novelty(
        {
            "matches": [{"similarity": 0.9}],
            "total_candidates_evaluated": 10,
            "behavioral_matches_found": 0,
        },
        0.5,
    )
    assert r["max_similarity"] is None
    assert r["comparator_inconclusive"] is True
