"""
Unit tests for MLModelVersionManager methods not covered by rollback tests.

Covers:
- save_model_version()
- get_latest_version()
- get_all_versions()
- get_versions_paginated()
- compare_versions()
- save_evaluation_metrics()
- update_comparison_results()
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.utils.model_versioning import MLModelVersionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_manager(session_mock=None):
    """Return a db_manager whose get_session() acts as an async context manager."""
    if session_mock is None:
        session_mock = AsyncMock()
        session_mock.execute = AsyncMock()
        session_mock.commit = AsyncMock()
        session_mock.add = Mock()
        session_mock.refresh = AsyncMock()
        session_mock.flush = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session_mock)
    cm.__aexit__ = AsyncMock(return_value=None)

    db_manager = Mock()
    db_manager.get_session = Mock(return_value=cm)
    return db_manager, session_mock


def _make_version(
    id=1,
    version_number=1,
    accuracy=0.90,
    precision_huntable=0.88,
    precision_not_huntable=0.91,
    recall_huntable=0.87,
    recall_not_huntable=0.92,
    f1_score_huntable=0.875,
    f1_score_not_huntable=0.915,
    training_data_size=1000,
    feedback_samples_count=10,
    trained_at=None,
    is_current=False,
    comparison_results=None,
    model_file_path=None,
):
    v = Mock()
    v.id = id
    v.version_number = version_number
    v.accuracy = accuracy
    v.precision_huntable = precision_huntable
    v.precision_not_huntable = precision_not_huntable
    v.recall_huntable = recall_huntable
    v.recall_not_huntable = recall_not_huntable
    v.f1_score_huntable = f1_score_huntable
    v.f1_score_not_huntable = f1_score_not_huntable
    v.training_data_size = training_data_size
    v.feedback_samples_count = feedback_samples_count
    v.trained_at = trained_at or datetime(2026, 3, 25, 10, 0)
    v.is_current = is_current
    v.comparison_results = comparison_results
    v.model_file_path = model_file_path
    return v


# ---------------------------------------------------------------------------
# get_latest_version()
# ---------------------------------------------------------------------------


class TestGetLatestVersion:
    """get_latest_version: returns latest or None."""

    @pytest.mark.asyncio
    async def test_returns_version_when_exists(self):
        version = _make_version(id=5, version_number=5)
        db_manager, session = _make_db_manager()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = version
        session.execute.return_value = result_mock

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.get_latest_version()

        assert result is not None
        assert result.version_number == 5

    @pytest.mark.asyncio
    async def test_returns_none_when_no_versions(self):
        db_manager, session = _make_db_manager()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.get_latest_version()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(self):
        db_manager, session = _make_db_manager()
        session.execute.side_effect = RuntimeError("DB down")

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.get_latest_version()

        assert result is None


# ---------------------------------------------------------------------------
# get_all_versions()
# ---------------------------------------------------------------------------


class TestGetAllVersions:
    """get_all_versions: returns list of versions ordered by version_number desc."""

    @pytest.mark.asyncio
    async def test_returns_versions_list(self):
        v1 = _make_version(id=1, version_number=1)
        v2 = _make_version(id=2, version_number=2)

        db_manager, session = _make_db_manager()
        result_mock = Mock()
        scalars_mock = Mock()
        scalars_mock.all.return_value = [v2, v1]
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.get_all_versions()

        assert len(result) == 2
        assert result[0].version_number == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_error(self):
        db_manager, session = _make_db_manager()
        session.execute.side_effect = RuntimeError("DB error")

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.get_all_versions()

        assert result == []


# ---------------------------------------------------------------------------
# get_versions_paginated()
# ---------------------------------------------------------------------------


class TestGetVersionsPaginated:
    """get_versions_paginated: pagination and optional version filter."""

    @pytest.mark.asyncio
    async def test_returns_versions_and_total(self):
        v1 = _make_version(id=1, version_number=1)

        db_manager, session = _make_db_manager()
        # First call: count query
        count_result = Mock()
        count_result.scalar.return_value = 5
        # Second call: paginated rows
        rows_result = Mock()
        scalars_mock = Mock()
        scalars_mock.all.return_value = [v1]
        rows_result.scalars.return_value = scalars_mock

        session.execute.side_effect = [count_result, rows_result]

        mgr = MLModelVersionManager(db_manager)
        versions, total = await mgr.get_versions_paginated(page=1, limit=1)

        assert total == 5
        assert len(versions) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        db_manager, session = _make_db_manager()
        session.execute.side_effect = RuntimeError("DB error")

        mgr = MLModelVersionManager(db_manager)
        versions, total = await mgr.get_versions_paginated()

        assert versions == []
        assert total == 0


# ---------------------------------------------------------------------------
# compare_versions()
# ---------------------------------------------------------------------------


class TestCompareVersions:
    """compare_versions: generates comparison report between two versions."""

    @pytest.mark.asyncio
    async def test_generates_comparison_with_improvements(self):
        old = _make_version(id=1, version_number=1, accuracy=0.80, precision_huntable=0.75, recall_huntable=0.70)
        new = _make_version(
            id=2,
            version_number=2,
            accuracy=0.92,
            precision_huntable=0.88,
            recall_huntable=0.85,
            training_data_size=1500,
            feedback_samples_count=20,
        )

        db_manager, _ = _make_db_manager()
        mgr = MLModelVersionManager(db_manager)

        with patch.object(mgr, "get_version_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda vid: old if vid == 1 else new
            result = await mgr.compare_versions(1, 2)

        assert "improvements" in result
        assert result["improvements"]["accuracy_change"] == pytest.approx(0.12, abs=0.001)
        assert result["summary"]["overall_improvement"] is True
        assert len(result["summary"]["key_improvements"]) > 0

    @pytest.mark.asyncio
    async def test_reports_accuracy_decrease_as_concern(self):
        old = _make_version(id=1, version_number=1, accuracy=0.95, precision_huntable=0.90, recall_huntable=0.90)
        new = _make_version(id=2, version_number=2, accuracy=0.85, precision_huntable=0.80, recall_huntable=0.80)

        db_manager, _ = _make_db_manager()
        mgr = MLModelVersionManager(db_manager)

        with patch.object(mgr, "get_version_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = lambda vid: old if vid == 1 else new
            result = await mgr.compare_versions(1, 2)

        assert result["summary"]["overall_improvement"] is False
        assert len(result["summary"]["areas_of_concern"]) > 0

    @pytest.mark.asyncio
    async def test_raises_when_version_not_found(self):
        db_manager, _ = _make_db_manager()
        mgr = MLModelVersionManager(db_manager)

        with patch.object(mgr, "get_version_by_id", AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="not found"):
                await mgr.compare_versions(1, 2)


# ---------------------------------------------------------------------------
# save_evaluation_metrics()
# ---------------------------------------------------------------------------


class TestSaveEvaluationMetrics:
    """save_evaluation_metrics: saves eval metrics to a version row."""

    @pytest.mark.asyncio
    async def test_saves_metrics_successfully(self):
        version = _make_version(id=1)
        db_manager, session = _make_db_manager()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = version
        session.execute.return_value = result_mock

        mgr = MLModelVersionManager(db_manager)
        metrics = {
            "accuracy": 0.91,
            "precision_huntable": 0.89,
            "precision_not_huntable": 0.93,
            "recall_huntable": 0.88,
            "recall_not_huntable": 0.94,
            "f1_score_huntable": 0.885,
            "f1_score_not_huntable": 0.935,
            "confusion_matrix": {"true_positive": 45, "true_negative": 50, "false_positive": 3, "false_negative": 2},
        }

        result = await mgr.save_evaluation_metrics(1, metrics)

        assert result is True
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_version_not_found(self):
        db_manager, session = _make_db_manager()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.save_evaluation_metrics(999, {"accuracy": 0.5})

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_db_error(self):
        db_manager, session = _make_db_manager()
        session.execute.side_effect = RuntimeError("DB error")

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.save_evaluation_metrics(1, {"accuracy": 0.5})

        assert result is False


# ---------------------------------------------------------------------------
# update_comparison_results()
# ---------------------------------------------------------------------------


class TestUpdateComparisonResults:
    """update_comparison_results: stores comparison dict on a version row."""

    @pytest.mark.asyncio
    async def test_stores_results_successfully(self):
        version = _make_version(id=1)
        db_manager, session = _make_db_manager()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = version
        session.execute.return_value = result_mock

        mgr = MLModelVersionManager(db_manager)
        comparison = {"old_version": {}, "new_version": {}, "improvements": {}}
        result = await mgr.update_comparison_results(1, comparison)

        assert result is True
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_version_not_found(self):
        db_manager, session = _make_db_manager()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.update_comparison_results(999, {})

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_db_error(self):
        db_manager, session = _make_db_manager()
        session.execute.side_effect = RuntimeError("DB error")

        mgr = MLModelVersionManager(db_manager)
        result = await mgr.update_comparison_results(1, {})

        assert result is False


# ---------------------------------------------------------------------------
# save_model_version()
# ---------------------------------------------------------------------------


class TestSaveModelVersion:
    """save_model_version: persists new version with metrics."""

    @pytest.mark.asyncio
    async def test_saves_version_with_next_number(self):
        db_manager, session = _make_db_manager()
        mgr = MLModelVersionManager(db_manager)

        # get_latest_version returns version_number=3 so next should be 4
        latest = _make_version(id=3, version_number=3)
        with patch.object(mgr, "get_latest_version", AsyncMock(return_value=latest)):
            # session.add receives the new MLModelVersionTable instance
            # session.refresh populates its id
            def set_id(obj):
                obj.id = 4

            session.refresh.side_effect = set_id

            result = await mgr.save_model_version(
                metrics={"accuracy": 0.91, "training_data_size": 500},
                _training_config={},
                feedback_count=15,
                model_file_path="/app/models/v4.pkl",
            )

        assert result == 4
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_first_version_gets_number_one(self):
        db_manager, session = _make_db_manager()
        mgr = MLModelVersionManager(db_manager)

        with patch.object(mgr, "get_latest_version", AsyncMock(return_value=None)):

            def set_id(obj):
                obj.id = 1

            session.refresh.side_effect = set_id

            result = await mgr.save_model_version(
                metrics={"accuracy": 0.85, "training_data_size": 200},
                _training_config={},
            )

        assert result == 1
