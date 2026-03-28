"""
Integration test: run agentic workflow with real DB and mocked LLM/external services.

Asserts that run_workflow() executes against the test database and updates execution
status; all LLM and embedding/similarity calls are mocked.
"""

import asyncio
import uuid
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.database.manager import DatabaseManager
from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SourceTable,
)
from src.workflows.agentic_workflow import run_workflow


@pytest.mark.integration
@pytest.mark.integration_full
def test_workflow_execution_with_real_db_mocked_llm():
    """Run workflow with real test DB; LLM, Sigma generation, and similarity search mocked."""
    db_url = _sync_test_db_url()
    db = DatabaseManager(database_url=db_url)
    session = db.get_session()

    try:
        # Ensure active workflow config exists (get_active_config will create default if missing)
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
                description="Test default",
                qa_enabled={},
                agent_prompts={},
            )
            session.add(config)
            session.commit()
            session.refresh(config)

        # Create source and article (unique identifier for parallel/suite runs)
        uid = uuid.uuid4().hex[:8]
        source = SourceTable(
            identifier=f"test-workflow-integration-source-{uid}",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            check_frequency=3600,
            lookback_days=180,
            active=True,
        )
        session.add(source)
        session.commit()
        session.refresh(source)

        article = ArticleTable(
            source_id=source.id,
            canonical_url=f"https://example.com/workflow-integration-article-{uid}",
            title="Test Article for Workflow Integration",
            published_at=datetime.now(),
            content="Windows PowerShell and registry content for detection.",
            content_hash=f"workflow-integration-hash-{uid}",
            article_metadata={},
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = article.id

        # Create execution with config_snapshot that skips rank and OS detection to minimize LLM
        config_snapshot = {
            "skip_rank_agent": True,
            "eval_run": True,
            "skip_os_detection": True,
            "min_hunt_score": 97.0,
            "ranking_threshold": 6.0,
            "similarity_threshold": 0.5,
            "junk_filter_threshold": 0.8,
            "agent_models": {},
            "agent_prompts": config.agent_prompts if config.agent_prompts else {},
            "qa_enabled": {},
            "rank_agent_enabled": False,
            "cmdline_attention_preprocessor_enabled": True,
            "config_id": config.id,
            "config_version": config.version,
        }
        execution = AgenticWorkflowExecutionTable(
            article_id=article_id,
            status="pending",
            config_snapshot=config_snapshot,
        )
        session.add(execution)
        session.commit()
        session.refresh(execution)
        execution_id = execution.id

        @contextmanager
        def noop_trace(*args, **kwargs):
            yield None

        async def mock_check_context(*args, **kwargs):
            return {"context_length": 128000, "threshold": 100000}

        async def mock_rank(*args, **kwargs):
            return {"score": 7, "reasoning": "mocked"}

        async def mock_run_extraction(*args, **kwargs):
            return {"items": [], "count": 0, "cmdline_items": []}

        def mock_compare_proposed(*args, **kwargs):
            return {
                "matches": [],
                "total_candidates_evaluated": 0,
                "behavioral_matches_found": 0,
                "engine_used": "legacy",
            }

        # Patch Langfuse, LLM, Sigma generation, and similarity so workflow runs without real APIs
        with (
            patch("src.workflows.agentic_workflow.trace_workflow_execution", noop_trace),
            patch(
                "src.workflows.agentic_workflow.LLMService.check_model_context_length",
                new_callable=AsyncMock,
                side_effect=mock_check_context,
            ),
            patch(
                "src.workflows.agentic_workflow.LLMService.rank_article",
                new_callable=AsyncMock,
                side_effect=mock_rank,
            ),
            patch(
                "src.workflows.agentic_workflow.LLMService.run_extraction_agent",
                new_callable=AsyncMock,
                side_effect=mock_run_extraction,
            ),
        ):
            # Patch sigma generation and similarity (services used inside workflow nodes)
            with (
                patch(
                    "src.services.sigma_generation_service.SigmaGenerationService.generate_sigma_rules",
                    new_callable=AsyncMock,
                    return_value={"rules": [], "conversation_log": []},
                ),
                patch(
                    "src.services.sigma_matching_service.SigmaMatchingService.compare_proposed_rule_to_embeddings",
                    side_effect=mock_compare_proposed,
                ),
            ):
                result = asyncio.run(run_workflow(article_id, session, execution_id=execution_id))

        session.expire_all()  # Reload from DB
        execution_after = (
            session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == execution_id)
            .first()
        )
        assert execution_after is not None
        assert execution_after.status in ("completed", "running", "failed"), (
            f"Execution status should be completed/running/failed, got {execution_after.status}"
        )
        assert result is not None
        assert "success" in result or "error" in result or execution_after.status == "completed"
    finally:
        session.close()


def _sync_test_db_url() -> str:
    import os

    password = os.getenv("POSTGRES_PASSWORD", "cti_password")
    default_url = f"postgresql+asyncpg://cti_user:{password}@localhost:5433/cti_scraper_test"
    url = os.getenv("TEST_DATABASE_URL", default_url)
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    return url
