"""Unit tests for src.services.sigma_eval_service.

Covers ground-truth loading, the pure scoring-to-column mapping (build_eval_values),
and the mocked-DB persistence path (score_and_persist_execution).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.sigma_atom_precompute import is_sigma_similarity_available
from src.services.sigma_eval_service import (
    build_eval_values,
    is_sigma_eval_execution,
    load_sigma_ground_truth,
    score_and_persist_execution,
)

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


@pytest.mark.unit
def test_load_ground_truth_skips_non_dict_entries(tmp_path):
    f = tmp_path / "ground_truth.json"
    f.write_text(json.dumps(["not-a-dict", {"url": "https://x.test/b", "expected_rules": [_RUNDLL32]}]))
    gt = load_sigma_ground_truth(f)
    assert list(gt) == ["https://x.test/b"]


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


# ---------------------------------------------------------------------------
# is_sigma_eval_execution / score_and_persist_execution (mocked DB)
# ---------------------------------------------------------------------------


def _eval_query_returning(eval_record):
    query = MagicMock()
    filtered = MagicMock()
    filtered.first.return_value = eval_record
    query.filter.return_value = filtered
    return query


@pytest.mark.unit
@pytest.mark.parametrize(
    "snapshot,expected",
    [
        ({"sigma_eval": True}, True),
        ({"sigma_eval": False}, False),
        ({}, False),
        (None, False),
    ],
)
def test_is_sigma_eval_execution(snapshot, expected):
    execution = SimpleNamespace(config_snapshot=snapshot)
    assert is_sigma_eval_execution(execution) is expected


@pytest.mark.unit
def test_score_and_persist_non_sigma_eval_is_noop():
    execution = SimpleNamespace(id=1, config_snapshot={}, sigma_rules=[])
    db_session = MagicMock()
    assert score_and_persist_execution(execution, db_session) is None
    db_session.query.assert_not_called()


@pytest.mark.unit
def test_score_and_persist_missing_eval_row_returns_none():
    execution = SimpleNamespace(id=7, config_snapshot={"sigma_eval": True}, sigma_rules=[])
    db_session = MagicMock()
    db_session.query.return_value = _eval_query_returning(None)
    assert score_and_persist_execution(execution, db_session) is None
    db_session.commit.assert_not_called()


@pytest.mark.unit
@requires_sigma_similarity
def test_score_and_persist_scores_and_commits():
    eval_record = SimpleNamespace(
        id=99,
        article_url="https://x.test/a",
        expected_rule_count=1,
        expected_rules=[_RUNDLL32],
        status="pending",
        completed_at=None,
    )
    execution = SimpleNamespace(
        id=7,
        config_snapshot={"sigma_eval": True},
        sigma_rules=[_RUNDLL32],
    )
    db_session = MagicMock()
    db_session.query.return_value = _eval_query_returning(eval_record)

    with patch(
        "src.services.sigma_eval_service.load_sigma_ground_truth",
        return_value={"https://x.test/a": {"expected_rule_count": 1, "expected_rules": [_RUNDLL32]}},
    ):
        result = score_and_persist_execution(execution, db_session)

    assert result is eval_record
    assert eval_record.status == "completed"
    assert eval_record.completed_at is not None
    assert eval_record.actual_rule_count == 1
    db_session.commit.assert_called_once()


@pytest.mark.unit
@requires_sigma_similarity
def test_score_and_persist_falls_back_to_row_expected_rules():
    eval_record = SimpleNamespace(
        id=99,
        article_url="https://unknown.test/a",
        expected_rule_count=1,
        expected_rules=[_RUNDLL32],
        status="pending",
        completed_at=None,
    )
    execution = SimpleNamespace(
        id=7,
        config_snapshot={"sigma_eval": True},
        sigma_rules=[_RUNDLL32],
    )
    db_session = MagicMock()
    db_session.query.return_value = _eval_query_returning(eval_record)

    with patch("src.services.sigma_eval_service.load_sigma_ground_truth", return_value={}):
        result = score_and_persist_execution(execution, db_session)

    assert result is eval_record
    assert eval_record.status == "completed"
    assert eval_record.atom_recall == 1.0


@pytest.mark.unit
def test_score_and_persist_marks_failed_on_scoring_error():
    eval_record = SimpleNamespace(
        id=99,
        article_url="https://x.test/a",
        expected_rule_count=1,
        expected_rules=[],
        status="pending",
        completed_at=None,
    )
    execution = SimpleNamespace(
        id=7,
        config_snapshot={"sigma_eval": True},
        sigma_rules="not-a-list",
    )
    db_session = MagicMock()
    db_session.query.return_value = _eval_query_returning(eval_record)

    with patch(
        "src.services.sigma_eval_service.build_eval_values",
        side_effect=RuntimeError("scoring blew up"),
    ):
        result = score_and_persist_execution(execution, db_session)

    assert result is None
    assert eval_record.status == "failed"
    db_session.rollback.assert_called_once()
    db_session.commit.assert_called_once()
