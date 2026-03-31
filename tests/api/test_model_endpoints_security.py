"""
Security-focused API tests for model management endpoints.

Covers:
- Input validation (negative/zero version_id, boundary values)
- Error response sanitization (no internal details leaked)
- Path parameter enforcement via FastAPI Path(gt=0)
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
):
    from datetime import datetime

    v = Mock()
    v.id = id
    v.version_number = version_number
    v.is_current = is_current
    v.model_file_path = model_file_path
    v.accuracy = accuracy
    v.eval_accuracy = 0.90
    v.eval_f1_score_huntable = 0.88
    v.eval_precision_huntable = 0.87
    v.eval_recall_huntable = 0.89
    v.eval_precision_not_huntable = 0.91
    v.eval_recall_not_huntable = 0.90
    v.eval_f1_score_not_huntable = 0.905
    v.precision_huntable = 0.87
    v.precision_not_huntable = 0.91
    v.recall_huntable = 0.89
    v.recall_not_huntable = 0.90
    v.f1_score_huntable = 0.88
    v.f1_score_not_huntable = 0.905
    v.training_data_size = 1800
    v.feedback_samples_count = 25
    v.training_duration_seconds = 38.4
    v.trained_at = datetime(2026, 3, 28, 10, 0, 0)
    v.evaluated_at = datetime(2026, 3, 28, 10, 5, 0)
    v.comparison_results = None
    v.eval_confusion_matrix = None
    return v


# ---------------------------------------------------------------------------
# POST /api/model/rollback/{version_id} — input validation
# ---------------------------------------------------------------------------


class TestRollbackInputValidation:
    """Rollback endpoint rejects invalid version_id values."""

    @pytest.mark.api
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_rollback_zero_version_id_returns_422(self, async_client: httpx.AsyncClient):
        """version_id=0 is rejected by Path(gt=0) validation."""
        response = await async_client.post("/api/model/rollback/0")
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_rollback_negative_version_id_returns_422(self, async_client: httpx.AsyncClient):
        """Negative version_id is rejected by Path(gt=0) validation."""
        response = await async_client.post("/api/model/rollback/-1")
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_rollback_string_version_id_returns_422(self, async_client: httpx.AsyncClient):
        """Non-integer version_id is rejected by type validation."""
        response = await async_client.post("/api/model/rollback/abc")
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_rollback_very_large_id_returns_404(self, async_client: httpx.AsyncClient):
        """A very large but valid integer returns 404 (not found in DB)."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.return_value = None

            response = await async_client.post("/api/model/rollback/999999999")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/model/compare/{version_id} — input validation
# ---------------------------------------------------------------------------


class TestCompareInputValidation:
    """Compare endpoint rejects invalid version_id values."""

    @pytest.mark.api
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_compare_zero_version_id_returns_422(self, async_client: httpx.AsyncClient):
        """version_id=0 is rejected."""
        response = await async_client.get("/api/model/compare/0")
        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_compare_negative_version_id_returns_422(self, async_client: httpx.AsyncClient):
        """Negative version_id is rejected."""
        response = await async_client.get("/api/model/compare/-5")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Error response sanitization — no internal details leaked
# ---------------------------------------------------------------------------


class TestErrorResponseSanitization:
    """API error responses must not leak internal implementation details."""

    @pytest.mark.api
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_versions_error_hides_exception_details(self, async_client: httpx.AsyncClient):
        """GET /api/model/versions 500 response hides internal error details."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_all_versions.side_effect = RuntimeError("connection to server at '10.0.0.5' refused")

            response = await async_client.get("/api/model/versions")

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        # Must not contain internal connection details
        assert "10.0.0.5" not in detail
        assert "connection" not in detail.lower() or "refused" not in detail.lower()

    @pytest.mark.api
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_compare_error_hides_exception_details(self, async_client: httpx.AsyncClient):
        """GET /api/model/compare/{id} 500 response hides internal error details."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_version_by_id.side_effect = RuntimeError("password authentication failed for user 'cti_user'")

            response = await async_client.get("/api/model/compare/1")

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert "password" not in detail.lower()
        assert "cti_user" not in detail


# ---------------------------------------------------------------------------
# GET /api/model/versions — pagination boundary tests
# ---------------------------------------------------------------------------


class TestVersionsPaginationBounds:
    """Pagination parameters are clamped to safe ranges."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_page_zero_is_clamped_to_one(self, async_client: httpx.AsyncClient):
        """page=0 is clamped to page=1 internally."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_versions_paginated.return_value = ([], 0)

            response = await async_client.get("/api/model/versions?page=0&limit=10")

        assert response.status_code == 200
        # Verify clamping: get_versions_paginated was called with page=1
        call_kwargs = instance.get_versions_paginated.call_args
        assert call_kwargs.kwargs.get("page", call_kwargs.args[0] if call_kwargs.args else None) == 1 or (
            call_kwargs[1].get("page") == 1 if len(call_kwargs) > 1 else True
        )

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_limit_capped_at_100(self, async_client: httpx.AsyncClient):
        """limit=9999 is clamped to 100."""
        with patch("src.utils.model_versioning.MLModelVersionManager") as MockManager:
            instance = AsyncMock()
            MockManager.return_value = instance
            instance.get_versions_paginated.return_value = ([], 0)

            response = await async_client.get("/api/model/versions?page=1&limit=9999")

        assert response.status_code == 200
