"""Session-injection tests for the migrated ml_hunt_comparison routes.

These lock the property that makes the routes -> service layering worth doing: the
handlers receive their session from ``Depends(get_db_session)``, so a test (or any
other caller) can substitute one via ``app.dependency_overrides`` without patching
``DatabaseManager``. Before the migration each handler constructed its own session
internally and no override point existed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.web.dependencies import get_db_session  # noqa: E402
from src.web.routes import ml_hunt_comparison  # noqa: E402


@pytest.fixture
def injected_session() -> MagicMock:
    return MagicMock(name="injected_session")


@pytest.fixture
def client(injected_session: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(ml_hunt_comparison.router)
    app.dependency_overrides[get_db_session] = lambda: injected_session
    return TestClient(app)


def test_stats_uses_injected_session(client: TestClient, injected_session: MagicMock) -> None:
    with patch.object(ml_hunt_comparison, "ChunkAnalysisService") as service_cls:
        service_cls.return_value.get_model_comparison_stats.return_value = [{"model_version": "v1"}]

        response = client.get("/api/ml-model-performance/stats")

    assert response.status_code == 200
    assert response.json() == {"success": True, "stats": [{"model_version": "v1"}]}
    service_cls.assert_called_once_with(injected_session)


def test_model_versions_uses_injected_session(client: TestClient, injected_session: MagicMock) -> None:
    with patch.object(ml_hunt_comparison, "ChunkAnalysisService") as service_cls:
        service_cls.return_value.get_available_model_versions.return_value = ["v1", "v2"]

        response = client.get("/api/ml-model-performance/model-versions")

    assert response.status_code == 200
    assert response.json()["model_versions"] == ["v1", "v2"]
    service_cls.assert_called_once_with(injected_session)


def test_eligible_count_uses_injected_session(client: TestClient, injected_session: MagicMock) -> None:
    with patch.object(ml_hunt_comparison, "ChunkAnalysisBackfillService") as service_cls:
        service_cls.return_value.get_eligible_articles.return_value = [1, 2, 3]

        response = client.get("/api/ml-model-performance/eligible-count?min_hunt_score=60")

    assert response.status_code == 200
    assert response.json() == {"success": True, "count": 3, "min_hunt_score": 60.0}
    service_cls.assert_called_once_with(injected_session)
    service_cls.return_value.get_eligible_articles.assert_called_once_with(60.0)


def test_summary_counts_model_versions_via_service(client: TestClient, injected_session: MagicMock) -> None:
    """The /summary endpoint must not issue its own ORM query for the registry count."""
    with patch.object(ml_hunt_comparison, "ChunkAnalysisService") as service_cls:
        service = service_cls.return_value
        service.get_model_comparison_stats.return_value = []
        service.get_available_model_versions.return_value = ["v1"]
        service.count_registered_model_versions.return_value = 7
        service.get_chunk_analysis_results.return_value = []

        response = client.get("/api/ml-model-performance/summary")

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["total_model_versions"] == 7
    service_cls.assert_called_once_with(injected_session)
    service.count_registered_model_versions.assert_called_once_with()
    # No direct query() on the session — the route owns no data access of its own.
    injected_session.query.assert_not_called()


def test_service_error_maps_to_500(client: TestClient) -> None:
    with patch.object(ml_hunt_comparison, "ChunkAnalysisService") as service_cls:
        service_cls.return_value.get_model_comparison_stats.side_effect = RuntimeError("boom")

        response = client.get("/api/ml-model-performance/stats")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
