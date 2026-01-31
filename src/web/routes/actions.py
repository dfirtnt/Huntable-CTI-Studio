"""
Administrative action endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

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
async def api_rescore_all():
    """Rescore all articles."""
    try:
        from src.core.processor import ContentProcessor
        from src.models.article import ArticleCreate

        articles = await async_db_manager.list_articles()
        total_articles = len(articles)

        if total_articles == 0:
            return {"success": True, "message": "No articles found to rescore", "processed": 0}

        articles_to_rescore = [
            article
            for article in articles
            if not article.article_metadata or "threat_hunting_score" not in article.article_metadata
        ]

        if not articles_to_rescore:
            return {"success": True, "message": "All articles already have scores", "processed": 0}

        processor = ContentProcessor(enable_content_enhancement=True)

        success_count = 0
        error_count = 0
        batch_size = 10

        for i in range(0, len(articles_to_rescore), batch_size):
            batch = articles_to_rescore[i : i + batch_size]

            for article in batch:
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

                    if "threat_hunting_score" in enhanced_metadata:
                        if not article.article_metadata:
                            article.article_metadata = {}

                        article.article_metadata["threat_hunting_score"] = enhanced_metadata["threat_hunting_score"]
                        article.article_metadata["perfect_keyword_matches"] = enhanced_metadata.get(
                            "perfect_keyword_matches", []
                        )
                        article.article_metadata["good_keyword_matches"] = enhanced_metadata.get(
                            "good_keyword_matches", []
                        )
                        article.article_metadata["lolbas_matches"] = enhanced_metadata.get("lolbas_matches", [])

                        await async_db_manager.update_article(article.id, article)
                        success_count += 1
                    else:
                        error_count += 1

                except Exception as exc:  # noqa: BLE001
                    logger.error("Error processing article %s: %s", article.id, exc)
                    error_count += 1

        return {
            "success": True,
            "message": f"Rescoring completed: {success_count} articles processed successfully, {error_count} errors",
            "processed": success_count,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Rescore all error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate-report")
async def api_generate_report():
    """Generate system report."""
    try:
        return {
            "success": True,
            "message": "Report generation not yet implemented",
            "download_url": "/api/export/articles",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Generate report error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
