"""
API tests for ML model rollback endpoints.

Covers:
- POST /api/model/rollback/{version_id}
- GET  /api/model/versions  (is_current + has_artifact fields)

These tests patch MLModelVersionManager so no live database or .pkl files
are required.  Mark integration_full tests hit the real DB/server.
"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_version_row(
    id=3,
    version_number=3,
    is_current=False,
    model_file_path="/app/models/content_filter_v3.pkl",
    accuracy=0.92,
    eval_accuracy=0.90,
    eval_f1_score_huntable=0.88,
    eval_precision_huntable=0.87,
    eval_recall_huntable=0.89,
    training_data_size=1800,
    feedback_samples_count=25,
    training_duration_seconds=38.4,
    trained_at=None,
    evaluated_at=None,
    comparison_results=None,
    eval_confusion_matrix=None,
):
    """Return a lightweight mock that mimics MLModelVersionTable."""
    from datetime import datetime

    v = Mock()
    v.id = id
    v.version_number = version_number
    v.is_current = is_current
    v.model_file_path = model_file_path
    v.accuracy = accuracy
    v.eval_accuracy = eval_accuracy
    v.eval_f1_score_huntable = eval_f1_score_huntable
    v.eval_precision_huntable = eval_precision_huntable
    v.eval_recall_huntable = eval_recall_huntable
    v.eval_precision_not_huntable = 0.91
    v.eval_recall_not_huntable = 0.90
    v.eval_f1_score_not_huntable = 0.905
    v.precision_huntable = 0.87
    v.precision_not_huntable = 0.91
    v.recall_huntable = 0.89
    v.recall_not_huntable = 0.90
    v.f1_score_huntable = 0.88
    v.f1_score_not_huntable = 0.905
    v.training_data_size = training_data_size
    v.feedback_samples_count = feedback_samples_count
    v.training_duration_seconds = training_duration_seconds
    v.trained_at = trained_at or datetime(2026, 3, 28, 10, 0, 0)
    v.evaluated_at = evaluated_at or datetime(2026, 3, 28, 10, 5, 0)
    v.comparison_results = comparison_results
    v.eval_confusion_matrix = eval_confusion_matrix
    return v


# ---------------------------------------------------------------------------
# POST /api/model/rollback/{version_id}
# ---------------------------------------------------------------------------


class TestModelRollbackEndpoint:
    """POST /api/model/rollback/{version_id}"""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_successful_rollback_returns_success(self, async_client: httpx.AsyncClient):
        """A valid version with an artifact returns success=True and version info."""
        version = _make_version_row(id=3, version_number=3, is_current=False)

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.return_value = version
            instance.activate_version.return_value = True

            with patch("os.path.exists", return_value=True), patch("threading.Thread") as MockThread:
                MockThread.return_value.start = Mock()

                response = await async_client.post("/api/model/rollback/3")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["version_number"] == 3
        assert data["version_id"] == 3
        assert "re-scoring" in data["message"].lower() or "background" in data["message"].lower()

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_rollback_nonexistent_version_returns_404(self, async_client: httpx.AsyncClient):
        """A version ID that does not exist in the DB yields 404."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.return_value = None

            response = await async_client.post("/api/model/rollback/9999")

        assert response.status_code == 404

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_rollback_version_without_artifact_returns_422(self, async_client: httpx.AsyncClient):
        """A version whose model_file_path is None returns 422 Unprocessable Entity."""
        version = _make_version_row(id=1, version_number=1, is_current=False, model_file_path=None)

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.return_value = version

            with patch("os.path.exists", return_value=False):
                response = await async_client.post("/api/model/rollback/1")

        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_rollback_artifact_file_missing_on_disk_returns_422(self, async_client: httpx.AsyncClient):
        """Returns 422 when the .pkl path exists in DB but is absent on disk."""
        version = _make_version_row(
            id=2, version_number=2, is_current=False, model_file_path="/app/models/content_filter_v2.pkl"
        )

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.return_value = version

            with patch("os.path.exists", return_value=False):
                response = await async_client.post("/api/model/rollback/2")

        assert response.status_code == 422
        assert "artifact" in response.json()["detail"].lower()

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_rollback_already_active_version_returns_success_false(self, async_client: httpx.AsyncClient):
        """Rolling back to the already-active version is a no-op with success=False."""
        version = _make_version_row(id=4, version_number=4, is_current=True)

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.return_value = version

            response = await async_client.post("/api/model/rollback/4")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "already" in data["message"].lower()

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_rollback_triggers_background_backfill(self, async_client: httpx.AsyncClient):
        """A background thread is started to re-score chunks after rollback."""
        version = _make_version_row(id=3, version_number=3, is_current=False)

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.return_value = version
            instance.activate_version.return_value = True

            with patch("os.path.exists", return_value=True), patch("threading.Thread") as MockThread:
                thread_instance = Mock()
                MockThread.return_value = thread_instance

                await async_client.post("/api/model/rollback/3")

        MockThread.assert_called_once()
        thread_instance.start.assert_called_once()

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_rollback_activate_version_error_propagates_as_422(self, async_client: httpx.AsyncClient):
        """If activate_version raises FileNotFoundError the endpoint returns 422."""
        version = _make_version_row(id=3, version_number=3, is_current=False)

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.return_value = version
            instance.activate_version.side_effect = FileNotFoundError("artifact gone")

            with patch("os.path.exists", return_value=True):
                response = await async_client.post("/api/model/rollback/3")

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/model/versions — is_current + has_artifact fields
# ---------------------------------------------------------------------------


class TestModelVersionsResponse:
    """GET /api/model/versions — rollback-related fields."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_versions_include_is_current_field(self, async_client: httpx.AsyncClient):
        """Every version object in the response contains an is_current boolean."""
        active = _make_version_row(id=5, version_number=5, is_current=True)
        inactive = _make_version_row(id=4, version_number=4, is_current=False)

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_all_versions.return_value = [active, inactive]

            response = await async_client.get("/api/model/versions")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        versions = data["versions"]
        assert len(versions) == 2

        active_row = next(v for v in versions if v["version_number"] == 5)
        inactive_row = next(v for v in versions if v["version_number"] == 4)

        assert active_row["is_current"] is True
        assert inactive_row["is_current"] is False

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_versions_include_has_artifact_field(self, async_client: httpx.AsyncClient):
        """has_artifact is True when model_file_path is set, False when None."""
        with_artifact = _make_version_row(id=5, version_number=5, model_file_path="/app/models/v5.pkl")
        without_artifact = _make_version_row(id=1, version_number=1, model_file_path=None)

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_all_versions.return_value = [with_artifact, without_artifact]

            response = await async_client.get("/api/model/versions")

        assert response.status_code == 200
        versions = response.json()["versions"]

        row_with = next(v for v in versions if v["version_number"] == 5)
        row_without = next(v for v in versions if v["version_number"] == 1)

        assert row_with["has_artifact"] is True
        assert row_without["has_artifact"] is False

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_versions_empty_list_returns_success(self, async_client: httpx.AsyncClient):
        """An empty version list still returns success=True with versions=[]."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_all_versions.return_value = []

            response = await async_client.get("/api/model/versions")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["versions"] == []
        assert data["total_versions"] == 0

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_exactly_one_version_is_current(self, async_client: httpx.AsyncClient):
        """Only the active version has is_current=True; all others are False."""
        versions = [_make_version_row(id=i, version_number=i, is_current=(i == 5)) for i in range(1, 6)]

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_all_versions.return_value = versions

            response = await async_client.get("/api/model/versions")

        current_rows = [v for v in response.json()["versions"] if v["is_current"]]
        assert len(current_rows) == 1
        assert current_rows[0]["version_number"] == 5


# ---------------------------------------------------------------------------
# GET /api/model/versions — pagination
# ---------------------------------------------------------------------------


class TestModelVersionsPagination:
    """GET /api/model/versions?page=&limit=&version= — paginated mode."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_paginated_response_includes_page_metadata(self, async_client: httpx.AsyncClient):
        """When page param is provided, response includes page/limit/total_pages."""
        versions = [_make_version_row(id=i, version_number=i) for i in range(1, 4)]

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_versions_paginated.return_value = (versions, 3)

            response = await async_client.get("/api/model/versions?page=1&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["page"] == 1
        assert data["limit"] == 10
        assert data["total_versions"] == 3
        assert data["total_pages"] == 1
        assert len(data["versions"]) == 3

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_paginated_total_pages_calculation(self, async_client: httpx.AsyncClient):
        """total_pages is ceil(total / limit)."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_versions_paginated.return_value = ([_make_version_row(id=1, version_number=1)], 25)

            response = await async_client.get("/api/model/versions?page=1&limit=10")

        data = response.json()
        assert data["total_pages"] == 3  # ceil(25/10)
        assert data["total_versions"] == 25

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_paginated_empty_page_returns_empty_list(self, async_client: httpx.AsyncClient):
        """A page beyond total returns empty versions with correct metadata."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_versions_paginated.return_value = ([], 5)

            response = await async_client.get("/api/model/versions?page=99&limit=10")

        data = response.json()
        assert data["success"] is True
        assert data["versions"] == []
        assert data["total_versions"] == 5

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_version_search_passes_version_number(self, async_client: httpx.AsyncClient):
        """The version query param is forwarded to get_versions_paginated."""
        target = _make_version_row(id=7, version_number=7)

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_versions_paginated.return_value = ([target], 1)

            response = await async_client.get("/api/model/versions?page=1&limit=10&version=7")

        assert response.status_code == 200
        data = response.json()
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version_number"] == 7

        # Verify the manager was called with version_number=7
        instance.get_versions_paginated.assert_called_once_with(
            page=1,
            limit=10,
            version_number=7,
        )

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_unpaginated_mode_when_no_page_param(self, async_client: httpx.AsyncClient):
        """Without page param, the legacy unpaginated path is used."""
        versions = [_make_version_row(id=1, version_number=1)]

        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_all_versions.return_value = versions

            response = await async_client.get("/api/model/versions")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Legacy response has no page/limit/total_pages keys
        assert "page" not in data
        assert "total_pages" not in data
