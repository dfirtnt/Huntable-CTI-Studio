"""
API tests for model management endpoints not covered by rollback tests.

Covers:
- GET  /api/model/retrain-status
- POST /api/model/retrain
- GET  /api/model/eval-chunk-count
- GET  /api/model/feedback-count
- GET  /api/model/versions (pagination edge cases)
"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# GET /api/model/retrain-status
# ---------------------------------------------------------------------------


class TestRetrainStatus:
    """GET /api/model/retrain-status"""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_idle_when_no_status_file(self, async_client: httpx.AsyncClient):
        """Returns idle status when no retrain status file exists."""
        with patch("os.path.exists", return_value=False):
            response = await async_client.get("/api/model/retrain-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "idle"
        assert data["progress"] == 0

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_returns_status_from_file(self, async_client: httpx.AsyncClient):
        """Returns status data from the status file when it exists."""
        import json

        status_data = {"status": "loading", "progress": 40, "message": "Loading data..."}

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", create=True) as mock_open,
        ):
            mock_open.return_value.__enter__ = Mock(return_value=mock_open.return_value)
            mock_open.return_value.__exit__ = Mock(return_value=False)
            mock_open.return_value.read = Mock(return_value=json.dumps(status_data))
            with patch("json.load", return_value=status_data):
                response = await async_client.get("/api/model/retrain-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "loading"
        assert data["progress"] == 40

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_error_does_not_leak_details(self, async_client: httpx.AsyncClient):
        """Error response hides internal exception details."""
        with patch("os.path.exists", side_effect=PermissionError("/secret/path denied")):
            response = await async_client.get("/api/model/retrain-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "/secret/path" not in data["message"]


# ---------------------------------------------------------------------------
# POST /api/model/retrain
# ---------------------------------------------------------------------------


class TestRetrainEndpoint:
    """POST /api/model/retrain"""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_no_feedback_returns_failure(self, async_client: httpx.AsyncClient):
        """Returns success=False when no feedback or annotations available."""
        mock_session = AsyncMock()

        # Both queries return 0
        result_mock = Mock()
        result_mock.scalar.return_value = 0
        mock_session.execute.return_value = result_mock

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=None)

        with patch("src.web.routes.models.async_db_manager") as mock_db:
            mock_db.get_session.return_value = cm
            response = await async_client.post("/api/model/retrain")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "no feedback" in data["message"].lower() or "no" in data["message"].lower()


# ---------------------------------------------------------------------------
# GET /api/model/eval-chunk-count
# ---------------------------------------------------------------------------


class TestEvalChunkCount:
    """GET /api/model/eval-chunk-count"""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_eval_file(self, async_client: httpx.AsyncClient):
        """Returns count=0 when eval CSV does not exist."""
        with patch("os.path.exists", return_value=False):
            response = await async_client.get("/api/model/eval-chunk-count")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 0

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_returns_count_from_csv(self, async_client: httpx.AsyncClient):
        """Returns correct count from eval CSV file."""
        mock_df = Mock()
        mock_df.__len__ = Mock(return_value=42)

        with (
            patch("os.path.exists", return_value=True),
            patch("pandas.read_csv", return_value=mock_df),
        ):
            response = await async_client.get("/api/model/eval-chunk-count")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 42

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_error_does_not_leak_path(self, async_client: httpx.AsyncClient):
        """Error response does not reveal filesystem paths."""
        with (
            patch("os.path.exists", return_value=True),
            patch("pandas.read_csv", side_effect=FileNotFoundError("/app/outputs/evaluation_data/eval_set.csv")),
        ):
            response = await async_client.get("/api/model/eval-chunk-count")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "/app/" not in data["message"]


# ---------------------------------------------------------------------------
# GET /api/model/feedback-count
# ---------------------------------------------------------------------------


class TestFeedbackCount:
    """GET /api/model/feedback-count"""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_returns_counts(self, async_client: httpx.AsyncClient):
        """Returns feedback and annotation counts."""
        mock_session = AsyncMock()

        # Simulate 4 queries returning different counts
        results = [Mock(scalar=Mock(return_value=v)) for v in [5, 3, 10, 7]]
        mock_session.execute.side_effect = results

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=None)

        with patch("src.web.routes.models.async_db_manager") as mock_db:
            mock_db.get_session.return_value = cm
            response = await async_client.get("/api/model/feedback-count")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["feedback_count"] == 5
        assert data["annotation_count"] == 3
        assert data["count"] == 8  # 5 + 3

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_error_does_not_leak_details(self, async_client: httpx.AsyncClient):
        """Error response hides DB connection details."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = RuntimeError("FATAL: database 'cti_scraper' does not exist")

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock(return_value=None)

        with patch("src.web.routes.models.async_db_manager") as mock_db:
            mock_db.get_session.return_value = cm
            response = await async_client.get("/api/model/feedback-count")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "cti_scraper" not in data["message"]


# ---------------------------------------------------------------------------
# GET /api/model/versions — pagination
# ---------------------------------------------------------------------------


class TestVersionsPagination:
    """GET /api/model/versions — pagination and search."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_unpaginated_returns_all(self, async_client: httpx.AsyncClient):
        """Without page param, returns all versions (chart mode)."""
        from datetime import datetime

        v = Mock()
        v.id = 1
        v.version_number = 1
        v.is_current = True
        v.model_file_path = "/app/models/v1.pkl"
        v.accuracy = 0.90
        v.eval_accuracy = 0.88
        v.eval_precision_huntable = 0.87
        v.eval_precision_not_huntable = 0.91
        v.eval_recall_huntable = 0.86
        v.eval_recall_not_huntable = 0.92
        v.eval_f1_score_huntable = 0.865
        v.eval_f1_score_not_huntable = 0.915
        v.precision_huntable = 0.87
        v.precision_not_huntable = 0.91
        v.recall_huntable = 0.86
        v.recall_not_huntable = 0.92
        v.f1_score_huntable = 0.865
        v.f1_score_not_huntable = 0.915
        v.training_data_size = 1000
        v.feedback_samples_count = 10
        v.training_duration_seconds = 30.0
        v.trained_at = datetime(2026, 3, 25, 10, 0)
        v.evaluated_at = datetime(2026, 3, 25, 10, 5)
        v.comparison_results = None
        v.eval_confusion_matrix = None

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_all_versions.return_value = [v]

            response = await async_client.get("/api/model/versions")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_versions"] == 1
        assert "page" not in data  # unpaginated mode

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_paginated_returns_page_info(self, async_client: httpx.AsyncClient):
        """With page param, returns pagination metadata."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_versions_paginated.return_value = ([], 0)

            response = await async_client.get("/api/model/versions?page=1&limit=5")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "page" in data
        assert "total_pages" in data
