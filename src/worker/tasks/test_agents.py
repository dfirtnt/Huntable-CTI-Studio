"""
Celery tasks for testing individual agents on specific articles.

These tasks are dispatched from the workflow config API endpoints
(/config/test-subagent, /config/test-rankagent, /config/test-sigmaagent)
so that agent tests run in the Celery worker rather than blocking the web process.
"""

from __future__ import annotations

import asyncio
import logging

from src.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db_session():
    """Create a sync database session for use inside Celery tasks."""
    from src.database.manager import DatabaseManager

    db = DatabaseManager()
    return db.get_session()


def _load_article(db_session, article_id: int):
    """Load an article by ID, raising ValueError if not found."""
    from src.database.models import ArticleTable

    article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
    if not article:
        raise ValueError(f"Article {article_id} not found")
    return article


def _get_active_config(db_session):
    """Get the active workflow configuration."""
    from src.services.workflow_trigger_service import WorkflowTriggerService

    trigger_service = WorkflowTriggerService(db_session)
    config = trigger_service.get_active_config()
    if not config:
        raise ValueError("No active workflow configuration found")
    return config


def _filter_content(article, use_junk_filter: bool, junk_filter_threshold: float) -> str:
    """Optionally apply content filtering and return the content to use."""
    if not use_junk_filter:
        return article.content

    from src.utils.content_filter import ContentFilter

    content_filter = ContentFilter()
    try:
        filter_result = content_filter.filter_content(
            article.content,
            min_confidence=junk_filter_threshold,
            hunt_score=(article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0),
            article_id=article.id,
        )
        return filter_result.filtered_content if filter_result.filtered_content else article.content
    except Exception:
        logger.warning("Content filtering failed, using original content", exc_info=True)
        return article.content


@celery_app.task(bind=True, max_retries=0, name="test_agents.test_sub_agent")
def test_sub_agent_task(
    self,
    agent_name: str,
    article_id: int,
    use_junk_filter: bool = True,
    junk_filter_threshold: float = 0.8,
):
    """Test a sub-agent extraction on a specific article."""
    db_session = _get_db_session()
    try:
        article = _load_article(db_session, article_id)
        config = _get_active_config(db_session)

        content = _filter_content(article, use_junk_filter, junk_filter_threshold)
        source_name = article.source.name if article.source else "Unknown"

        # Build prompt config for the requested sub-agent
        agent_prompts = config.agent_prompts or {}
        prompt_config = agent_prompts.get(agent_name, {})
        agent_models = config.agent_models if config.agent_models else {}

        # Determine QA config
        qa_flags = config.qa_enabled if config.qa_enabled else {}
        qa_prompt_config = None
        if qa_flags.get(agent_name, False):
            qa_prompt_key = f"{agent_name}_QA"
            qa_prompt_config = agent_prompts.get(qa_prompt_key, {})

        max_qa_retries = config.qa_max_retries if hasattr(config, "qa_max_retries") else 5

        from src.services.llm_service import LLMService

        llm_service = LLMService(config_models=agent_models)

        async def _run():
            return await llm_service.run_extraction_agent(
                agent_name=agent_name,
                content=content,
                title=article.title,
                url=article.canonical_url or "",
                prompt_config=prompt_config,
                qa_prompt_config=qa_prompt_config,
                max_retries=max_qa_retries,
                execution_id=None,
            )

        result = asyncio.get_event_loop().run_until_complete(_run())
        return {"success": True, "agent_name": agent_name, "article_id": article_id, "result": result}
    except Exception as exc:
        logger.error("test_sub_agent_task failed: %s", exc, exc_info=True)
        return {"success": False, "agent_name": agent_name, "article_id": article_id, "error": str(exc)}
    finally:
        db_session.close()


@celery_app.task(bind=True, max_retries=0, name="test_agents.test_rank_agent")
def test_rank_agent_task(
    self,
    article_id: int,
    use_junk_filter: bool = True,
    junk_filter_threshold: float = 0.8,
):
    """Test the Rank Agent on a specific article."""
    db_session = _get_db_session()
    try:
        article = _load_article(db_session, article_id)
        config = _get_active_config(db_session)

        content = _filter_content(article, use_junk_filter, junk_filter_threshold)
        source_name = article.source.name if article.source else "Unknown"

        agent_models = config.agent_models if config.agent_models else {}
        agent_prompts = config.agent_prompts or {}

        # Get RankAgent prompt
        rank_prompt_template = None
        if "RankAgent" in agent_prompts:
            rank_prompt_data = agent_prompts["RankAgent"]
            if isinstance(rank_prompt_data.get("prompt"), str):
                rank_prompt_template = rank_prompt_data["prompt"]

        # Compute ground truth for Langfuse logging
        hunt_score = article.article_metadata.get("threat_hunting_score") if article.article_metadata else None
        ml_score = article.article_metadata.get("ml_hunt_score") if article.article_metadata else None

        from src.services.llm_service import LLMService

        ground_truth_details = LLMService.compute_rank_ground_truth(hunt_score, ml_score)
        ground_truth_rank = ground_truth_details.get("ground_truth_rank")

        llm_service = LLMService(config_models=agent_models)

        async def _run():
            return await llm_service.rank_article(
                title=article.title,
                content=content,
                source=source_name,
                url=article.canonical_url or "",
                prompt_template=rank_prompt_template,
                execution_id=None,
                article_id=article.id,
                ground_truth_rank=ground_truth_rank,
                ground_truth_details=ground_truth_details,
            )

        result = asyncio.get_event_loop().run_until_complete(_run())
        return {"success": True, "article_id": article_id, "result": result}
    except Exception as exc:
        logger.error("test_rank_agent_task failed: %s", exc, exc_info=True)
        return {"success": False, "article_id": article_id, "error": str(exc)}
    finally:
        db_session.close()


@celery_app.task(bind=True, max_retries=0, name="test_agents.test_sigma_agent")
def test_sigma_agent_task(
    self,
    article_id: int,
    use_junk_filter: bool = True,
    junk_filter_threshold: float = 0.8,
    max_attempts: int = 3,
):
    """Test the SIGMA generation agent on a specific article."""
    db_session = _get_db_session()
    try:
        article = _load_article(db_session, article_id)
        config = _get_active_config(db_session)

        content = _filter_content(article, use_junk_filter, junk_filter_threshold)

        agent_models = config.agent_models if config.agent_models else {}
        agent_prompts = config.agent_prompts or {}

        # Get SigmaAgent prompt and system prompt
        sigma_prompt_template = None
        sigma_system_prompt = None
        if "SigmaAgent" in agent_prompts:
            sigma_prompt_data = agent_prompts["SigmaAgent"]
            if isinstance(sigma_prompt_data.get("prompt"), str):
                sigma_prompt_template = sigma_prompt_data["prompt"]
            sigma_system_prompt = sigma_prompt_data.get("system") or sigma_prompt_data.get("role")

        # Determine provider
        sigma_provider = agent_models.get("SigmaAgent_provider") if agent_models else None
        if not sigma_provider:
            sigma_provider = "lmstudio"

        from src.services.sigma_generation_service import SigmaGenerationService

        sigma_service = SigmaGenerationService(config_models=agent_models)

        async def _run():
            return await sigma_service.generate_sigma_rules(
                article_title=article.title,
                article_content=content,
                source_name=article.source.name if article.source else "Unknown",
                url=article.canonical_url or "",
                ai_model=sigma_provider,
                max_attempts=max_attempts,
                min_confidence=junk_filter_threshold,
                execution_id=None,
                article_id=article.id,
                sigma_prompt_template=sigma_prompt_template,
                sigma_system_prompt=sigma_system_prompt,
            )

        result = asyncio.get_event_loop().run_until_complete(_run())

        # Summarize result for task output
        rules = result.get("rules", []) if result else []
        return {
            "success": True,
            "article_id": article_id,
            "rules_count": len(rules),
            "rules": rules,
            "errors": result.get("errors") if result else None,
            "metadata": result.get("metadata") if result else None,
        }
    except Exception as exc:
        logger.error("test_sigma_agent_task failed: %s", exc, exc_info=True)
        return {"success": False, "article_id": article_id, "error": str(exc)}
    finally:
        db_session.close()
