"""Unit tests for the todo-001 backfill heuristic predicate.

`_is_empty_scores` is the predicate that decided which legacy rows the live
backfill relabeled (`pending`+`0.0`+empty similarity_scores -> `needs_review`).
A wrong predicate = a wrong one-shot data migration, so the exact input
representations seen in the DB (JSONB -> Python list, or rendered text
'[]' / 'null') are pinned here as regression tests.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_001_inconclusive_needs_review.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("backfill_001_mod", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __main__ guard prevents the backfill from running
    return mod


backfill_mod = _load_module()
_is_empty_scores = backfill_mod._is_empty_scores


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        None,  # NULL similarity_scores
        [],  # JSONB [] -> Python list
        (),  # defensive: tuple
        {},  # defensive: dict
        "",  # rendered empty text
        "   ",  # whitespace-only text
        "[]",  # rendered empty JSON array (the common DB form)
        "null",  # rendered JSON null
        "  []  ",  # padded
    ],
)
def test_empty_signatures_are_relabel_candidates(value):
    """These are the legacy *inconclusive* signature -> must be selected."""
    assert _is_empty_scores(value) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        [{"rule_id": "abc", "similarity": 0.42}],  # genuinely-scored: HAS stored matches
        [1],
        {"a": 1},
        '[{"rule_id":"abc"}]',  # non-empty rendered JSON
        "[ ]",  # not the exact DB form -> conservatively excluded
        0,  # numeric, not "empty scores"
        0.0,
    ],
)
def test_nonempty_or_scored_rows_are_excluded(value):
    """CRITICAL: a row with stored matches must NEVER be relabeled by the
    backfill -- it is genuinely scored, not inconclusive. This is the guard
    that kept the live migration from corrupting the 48 scored-0.0 rows."""
    assert _is_empty_scores(value) is False
