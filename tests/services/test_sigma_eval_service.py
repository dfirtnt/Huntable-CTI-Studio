"""Unit tests for src.services.sigma_eval_service (DB-free parts).

Covers ground-truth loading and the pure scoring-to-column mapping
(build_eval_values). The DB persistence path (score_and_persist_execution) is
exercised by integration tests; here we lock down the file loading and the
contract that build_eval_values returns exactly the SigmaEvaluationTable columns.
"""

import json

import pytest

from src.services.sigma_atom_precompute import is_sigma_similarity_available
from src.services.sigma_eval_service import build_eval_values, load_sigma_ground_truth

requires_sigma_similarity = pytest.mark.skipif(
    not is_sigma_similarity_available(),
    reason="sigma_similarity package not installed in this environment",
)

_RUNDLL32 = {
    "logsource": {"category": "process_creation", "product": "windows"},
    "detection": {
        "selection": {"Image|endswith": "\\rundll32.exe", "CommandLine|contains": ".jpg,init"},
        "condition": "selection",
    },
}


# ---------------------------------------------------------------------------
# load_sigma_ground_truth
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_real_ground_truth_keyed_by_url():
    """The committed fixture loads and is keyed by URL with the right shape."""
    gt = load_sigma_ground_truth()
    assert gt, "expected non-empty committed sigma ground truth"
    for url, entry in gt.items():
        assert url.startswith("http")
        assert isinstance(entry["expected_rule_count"], int)
        assert isinstance(entry["expected_rules"], list)
        # underscore-prefixed annotation keys must not leak into the entry
        assert "_note" not in entry


@pytest.mark.unit
def test_load_ground_truth_missing_file_returns_empty(tmp_path):
    assert load_sigma_ground_truth(tmp_path / "does_not_exist.json") == {}


@pytest.mark.unit
def test_load_ground_truth_malformed_returns_empty(tmp_path):
    bad = tmp_path / "ground_truth.json"
    bad.write_text("{ this is not valid json ]")
    assert load_sigma_ground_truth(bad) == {}


@pytest.mark.unit
def test_load_ground_truth_defaults_count_from_rules(tmp_path):
    f = tmp_path / "ground_truth.json"
    f.write_text(json.dumps([{"url": "https://x.test/a", "expected_rules": [_RUNDLL32, _RUNDLL32]}]))
    gt = load_sigma_ground_truth(f)
    assert gt["https://x.test/a"]["expected_rule_count"] == 2


# ---------------------------------------------------------------------------
# build_eval_values
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_eval_values_returns_model_columns():
    """Every key must be a real SigmaEvaluationTable column so setattr works."""
    from src.database.models import SigmaEvaluationTable

    values = build_eval_values([], {"expected_rule_count": 0, "expected_rules": []})
    model_columns = {c.name for c in SigmaEvaluationTable.__table__.columns}
    assert set(values).issubset(model_columns), set(values) - model_columns


@pytest.mark.unit
@requires_sigma_similarity
def test_build_eval_values_perfect_match():
    gt = {"expected_rule_count": 1, "expected_rules": [_RUNDLL32]}
    values = build_eval_values([_RUNDLL32], gt)
    assert values["expected_rule_count"] == 1
    assert values["actual_rule_count"] == 1
    assert values["atom_precision"] == 1.0
    assert values["atom_recall"] == 1.0
    assert values["logsource_recall"] == 1.0
    assert values["missed_atoms"] == []


@pytest.mark.unit
@requires_sigma_similarity
def test_build_eval_values_empty_generation():
    gt = {"expected_rule_count": 1, "expected_rules": [_RUNDLL32]}
    values = build_eval_values([], gt)
    assert values["actual_rule_count"] == 0
    assert values["atom_recall"] == 0.0
    assert len(values["missed_atoms"]) == 2  # both expected atoms missed
    assert values["matched_atoms"] == []
