"""
Administrative action endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter(prefix="/api/actions", tags=["Actions"])


async def mark_feedback_as_used():
    """Mark all unused feedback as used for training."""
    try:
        count = await async_db_manager.mark_chunk_feedback_as_used()
        logger.info("Marked %s feedback entries as used for training", count)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error marking feedback as used: %s", exc)


@router.post("/rescore-all")
async def api_rescore_all(background_tasks: BackgroundTasks):
    """Rescore all articles."""
    try:
        articles = await async_db_manager.list_articles()
        total_articles = len(articles)

        if total_articles == 0:
            return {"success": True, "message": "No articles found to rescore", "processed": 0}

        # This endpoint backs the dashboard's "Rescore All Articles" action.
        # Unlike the CLI's default backfill behavior, the explicit dashboard
        # action must recompute scores for articles that already have one.
        background_tasks.add_task(_rescore_articles, articles)
        return {
            "success": True,
            "message": f"Rescoring started for {total_articles} articles",
            "processed": 0,
            "total": total_articles,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Rescore all error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


async def _rescore_articles(articles):
    """Recompute and persist scores after the dashboard request returns."""
    from src.core.processor import ContentProcessor
    from src.models.article import ArticleCreate

    processor = ContentProcessor(enable_content_enhancement=True)
    success_count = 0
    error_count = 0

    for article in articles:
        try:
            article_create = ArticleCreate(
                source_id=article.source_id,
                canonical_url=article.canonical_url,
                title=article.title,
                content=article.content,
                content_hash=article.content_hash,
                published_at=article.published_at,
                article_metadata=article.article_metadata or {},
            )
            enhanced_metadata = await processor._enhance_metadata(article_create)

            if "threat_hunting_score" not in enhanced_metadata:
                error_count += 1
                continue

            if not article.article_metadata:
                article.article_metadata = {}
            article.article_metadata["threat_hunting_score"] = enhanced_metadata["threat_hunting_score"]
            article.article_metadata["perfect_keyword_matches"] = enhanced_metadata.get("perfect_keyword_matches", [])
            article.article_metadata["good_keyword_matches"] = enhanced_metadata.get("good_keyword_matches", [])
            article.article_metadata["lolbas_matches"] = enhanced_metadata.get("lolbas_matches", [])
            article.article_metadata["os_classification"] = enhanced_metadata.get("os_classification")

            await async_db_manager.update_article(article.id, article)
            success_count += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Error processing article %s: %s", article.id, exc)
            error_count += 1

    logger.info("Rescoring completed: %s articles processed successfully, %s errors", success_count, error_count)


@router.post("/generate-report")
async def api_generate_report():
    """Generate system report."""
    return {
        "success": True,
        "message": "Report generation not yet implemented",
        "download_url": "/api/export/articles",
    }


@router.post("/trigger-ingestion")
async def api_trigger_ingestion():
    """Manually trigger article ingestion by running check_all_sources task."""
    try:
        from celery import Celery

        celery_app = Celery("cti_scraper")
        celery_app.config_from_object("src.worker.celeryconfig")

        task = celery_app.send_task(
            "src.worker.celery_app.check_all_sources",
            queue="source_checks",
        )

        return {
            "success": True,
            "message": "Article ingestion started. This may take several minutes.",
            "task_id": task.id,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Trigger ingestion error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
