"""
API tests for observable extractor training endpoints.
"""

import pytest
import httpx


class TestObservableTrainingSummary:
    """Tests for /api/observables/training/summary."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_summary_endpoint(self, async_client: httpx.AsyncClient, monkeypatch):
        async def fake_summary():
            return {
                "supported_types": ["CMD", "PROC_LINEAGE"],
                "total_annotations": 12,
                "types": {
                    "CMD": {
                        "counts": {"total": 10, "unused": 4, "used": 6},
                        "dataset_directory": "outputs/evaluation_data/observables/cmd",
                        "artifact_directory": "outputs/observables/cmd",
                        "active_version": "20250101_000000",
                        "recent_artifacts": [],
                        "latest_artifact": None,
                    },
                    "PROC_LINEAGE": {
                        "counts": {"total": 2, "unused": 2, "used": 0},
                        "dataset_directory": "outputs/evaluation_data/observables/proc_lineage",
                        "artifact_directory": "outputs/observables/proc_lineage",
                        "active_version": None,
                        "recent_artifacts": [],
                        "latest_artifact": None,
                    },
                },
            }

        monkeypatch.setattr(
            "src.web.routes.observable_training.get_observable_training_summary",
            fake_summary,
        )

        response = await async_client.get("/api/observables/training/summary")
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["types"]["CMD"]["counts"]["unused"] == 4


class TestObservableTrainingRun:
    """Tests for /api/observables/training/run."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_training_endpoint_fallback(self, async_client: httpx.AsyncClient, monkeypatch):
        class FailingTask:
            def delay(self, observable_type=None):
                raise RuntimeError("broker unavailable")

        def fake_training_job(observable_type):
            return {"status": "completed", "processed_count": 3, "observable_type": observable_type}

        monkeypatch.setattr(
            "src.web.routes.observable_training.train_observable_extractor",
            FailingTask(),
        )
        monkeypatch.setattr(
            "src.web.routes.observable_training.run_observable_training_job",
            fake_training_job,
        )

        response = await async_client.post("/api/observables/training/run", json={"observable_type": "CMD"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["mode"] == "sync"
        assert payload["result"]["processed_count"] == 3
