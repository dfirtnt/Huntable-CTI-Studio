"""Tests for Celery task state transitions."""

import pytest


@pytest.mark.integration
def test_task_execution_eager_mode():
    """Task runs and returns result when task_always_eager=True (no worker)."""
    from src.worker.celery_app import celery_app, test_source_connectivity

    celery_app.conf.task_always_eager = True
    try:
        result = test_source_connectivity.apply_async(kwargs={"source_id": 42})
        data = result.get(timeout=5)
    finally:
        celery_app.conf.task_always_eager = False
    assert data["status"] == "success"
    assert data["source_id"] == 42
    assert "message" in data


@pytest.mark.integration
class TestCeleryStateTransitions:
    """Test Celery task state machine transitions."""

    @pytest.mark.skip(reason="Requires Celery worker and Redis - implement with test containers")
    def test_task_pending_to_started(self):
        """Test task transitions from PENDING to STARTED."""
        # TODO: Implement with test containers
        # Create task
        # Assert initial state is PENDING
        # Start task
        # Assert state transitions to STARTED
        pass

    @pytest.mark.skip(reason="Requires Celery worker and Redis - implement with test containers")
    def test_task_started_to_success(self):
        """Test task transitions from STARTED to SUCCESS."""
        # TODO: Implement with test containers
        pass

    @pytest.mark.skip(reason="Requires Celery worker and Redis - implement with test containers")
    def test_task_started_to_retry(self):
        """Test task transitions from STARTED to RETRY on failure."""
        # TODO: Implement with test containers
        pass

    @pytest.mark.skip(reason="Requires Celery worker and Redis - implement with test containers")
    def test_task_retry_limit(self):
        """Test task fails after max retries."""
        # TODO: Implement with test containers
        pass

    @pytest.mark.skip(reason="Requires Celery worker and Redis - implement with test containers")
    def test_task_idempotency(self):
        """Test that tasks are idempotent (can be retried safely)."""
        # TODO: Implement with test containers
        pass
