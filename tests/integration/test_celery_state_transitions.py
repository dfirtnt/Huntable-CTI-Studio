"""Tests for Celery task state transitions."""

import uuid
from unittest.mock import patch

import pytest

from src.database.manager import DatabaseManager
from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SourceTable,
)


def _sync_test_db_url():
    import os

    password = os.getenv("POSTGRES_PASSWORD", "cti_password")
    default_url = f"postgresql+asyncpg://cti_user:{password}@localhost:5433/cti_scraper_test"
    url = os.getenv("TEST_DATABASE_URL", default_url)
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    return url


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
@pytest.mark.integration_full
def test_trigger_agentic_workflow_eager_touches_db():
    """Celery trigger_agentic_workflow (eager) runs and updates DB execution state."""
    from datetime import datetime

    from src.worker.celery_app import celery_app, trigger_agentic_workflow

    db_url = _sync_test_db_url()
    db = DatabaseManager(database_url=db_url)
    session = db.get_session()
    try:
        # Ensure active config
        config = (
            session.query(AgenticWorkflowConfigTable)
            .filter(AgenticWorkflowConfigTable.is_active == True)
            .order_by(AgenticWorkflowConfigTable.version.desc())
            .first()
        )
        if not config:
            config = AgenticWorkflowConfigTable(
                min_hunt_score=97.0,
                ranking_threshold=6.0,
                similarity_threshold=0.5,
                junk_filter_threshold=0.8,
                version=1,
                is_active=True,
                description="Test",
                qa_enabled={},
                agent_prompts={},
            )
            session.add(config)
            session.commit()
            session.refresh(config)

        uid = uuid.uuid4().hex[:8]
        source = SourceTable(
            identifier=f"test-celery-db-source-{uid}",
            name="Test",
            url="https://example.com",
            rss_url="https://example.com/feed",
            check_frequency=3600,
            lookback_days=180,
            active=True,
        )
        session.add(source)
        session.commit()
        session.refresh(source)

        article = ArticleTable(
            source_id=source.id,
            canonical_url=f"https://example.com/celery-db-article-{uid}",
            title="Celery DB Test",
            published_at=datetime.now(),
            content="Content",
            content_hash=f"celery-db-hash-{uid}",
            article_metadata={},
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = article.id

        execution = AgenticWorkflowExecutionTable(
            article_id=article_id,
            status="pending",
            config_snapshot={"config_id": config.id, "config_version": config.version},
        )
        session.add(execution)
        session.commit()
        session.refresh(execution)
        execution_id = execution.id
    finally:
        session.close()

    async def mock_run_workflow(article_id, db_session, execution_id=None):
        """Minimal success so task completes without running full workflow."""
        execution = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == execution_id)
            .first()
        )
        if execution:
            execution.status = "completed"
            execution.current_step = "promote_to_queue"
            db_session.commit()
        return {"success": True}

    celery_app.conf.task_always_eager = True
    try:
        with patch("src.workflows.agentic_workflow.run_workflow", side_effect=mock_run_workflow):
            result = trigger_agentic_workflow.apply_async(
                kwargs={"article_id": article_id, "execution_id": execution_id}
            )
            data = result.get(timeout=10)
        assert data is not None
        assert data.get("success") is True

        session2 = db.get_session()
        try:
            exec_after = (
                session2.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )
            assert exec_after is not None
            assert exec_after.status == "completed"
        finally:
            session2.close()
    finally:
        celery_app.conf.task_always_eager = False
