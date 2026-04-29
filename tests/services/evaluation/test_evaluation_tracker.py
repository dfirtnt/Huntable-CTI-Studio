"""Tests for EvaluationTracker and _compare_metrics."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.services.evaluation.evaluation_tracker import EvaluationTracker, _compare_metrics

pytestmark = pytest.mark.unit


class TestCompareMetrics:
    """Unit tests for the _compare_metrics helper."""

    def test_improvement_detected(self):
        result = _compare_metrics({"accuracy": 0.7}, {"accuracy": 0.9})
        assert "accuracy" in result["improvements"]
        assert result["improvements"]["accuracy"]["diff"] == pytest.approx(0.2)
        assert result["improvements"]["accuracy"]["baseline"] == 0.7
        assert result["improvements"]["accuracy"]["current"] == 0.9

    def test_degradation_detected(self):
        result = _compare_metrics({"accuracy": 0.9}, {"accuracy": 0.7})
        assert "accuracy" in result["degradations"]
        assert result["degradations"]["accuracy"]["diff"] == pytest.approx(-0.2)

    def test_unchanged_within_epsilon(self):
        result = _compare_metrics({"accuracy": 0.9}, {"accuracy": 0.9})
        assert "accuracy" in result["unchanged"]
        assert "accuracy" not in result["improvements"]
        assert "accuracy" not in result["degradations"]

    def test_sub_epsilon_diff_is_unchanged(self):
        result = _compare_metrics({"val": 1.0}, {"val": 1.0009})
        assert "val" in result["unchanged"]

    def test_nested_dict_dot_notation(self):
        baseline = {"scores": {"f1": 0.6, "precision": 0.7}}
        current = {"scores": {"f1": 0.8, "precision": 0.65}}
        result = _compare_metrics(baseline, current)
        assert "scores.f1" in result["improvements"]
        assert "scores.precision" in result["degradations"]

    def test_pct_change_zero_baseline(self):
        result = _compare_metrics({"val": 0.0}, {"val": 1.0})
        entry = result["improvements"]["val"]
        assert entry["pct_change"] == 0  # no divide-by-zero

    def test_non_numeric_values_ignored(self):
        result = _compare_metrics({"label": "v1", "score": 0.5}, {"label": "v2", "score": 0.6})
        assert "label" not in result["improvements"]
        assert "label" not in result["degradations"]
        assert "label" not in result["unchanged"]
        assert "score" in result["improvements"]

    def test_empty_dicts_return_empty_buckets(self):
        result = _compare_metrics({}, {})
        assert result["improvements"] == {}
        assert result["degradations"] == {}
        assert result["unchanged"] == {}

    def test_none_inputs_handled(self):
        result = _compare_metrics(None, None)
        assert result["improvements"] == {}
        assert result["degradations"] == {}

    def test_baseline_and_current_preserved_in_output(self):
        b = {"accuracy": 0.8}
        c = {"accuracy": 0.9}
        result = _compare_metrics(b, c)
        assert result["baseline"] is b
        assert result["current"] is c

    def test_key_only_in_current_skipped(self):
        # b_val is None for a key that only exists in current, so no bucket entry
        result = _compare_metrics({}, {"new_metric": 0.5})
        assert "new_metric" not in result["improvements"]
        assert "new_metric" not in result["degradations"]
        assert "new_metric" not in result["unchanged"]


def _make_record(id, agent_name, metrics, evaluation_type="baseline", model_version=None):
    rec = MagicMock()
    rec.id = id
    rec.agent_name = agent_name
    rec.metrics = metrics
    rec.evaluation_type = evaluation_type
    rec.model_version = model_version
    rec.created_at = datetime(2025, 1, 1)
    return rec


class TestEvaluationTrackerCompareEvaluations:
    """Tests for EvaluationTracker.compare_evaluations() with mocked DB."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    def test_compare_returns_structured_result(self, mock_db):
        baseline = _make_record(1, "ExtractAgent", {"accuracy": 0.7})
        current = _make_record(2, "ExtractAgent", {"accuracy": 0.9})
        mock_db.query.return_value.filter.return_value.first.side_effect = [baseline, current]

        tracker = EvaluationTracker(mock_db)
        result = tracker.compare_evaluations(1, 2)

        assert result["baseline"]["id"] == 1
        assert result["current"]["id"] == 2
        assert "comparison" in result
        assert "improvements" in result["comparison"]
        assert "accuracy" in result["comparison"]["improvements"]

    def test_compare_raises_on_missing_record(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.side_effect = [None, None]
        tracker = EvaluationTracker(mock_db)
        with pytest.raises(ValueError, match="not found"):
            tracker.compare_evaluations(1, 2)

    def test_compare_raises_on_agent_name_mismatch(self, mock_db):
        baseline = _make_record(1, "ExtractAgent", {})
        current = _make_record(2, "RankAgent", {})
        mock_db.query.return_value.filter.return_value.first.side_effect = [baseline, current]

        tracker = EvaluationTracker(mock_db)
        with pytest.raises(ValueError, match="different agents"):
            tracker.compare_evaluations(1, 2)

    def test_compare_degradation_in_result(self, mock_db):
        baseline = _make_record(1, "SigmaAgent", {"f1": 0.9})
        current = _make_record(2, "SigmaAgent", {"f1": 0.7})
        mock_db.query.return_value.filter.return_value.first.side_effect = [baseline, current]

        tracker = EvaluationTracker(mock_db)
        result = tracker.compare_evaluations(1, 2)
        assert "f1" in result["comparison"]["degradations"]
