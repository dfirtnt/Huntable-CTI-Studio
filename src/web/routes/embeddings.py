"""
Embedding-related API routes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter(tags=["Embeddings"])


@router.get("/api/embeddings/stats")
async def api_embedding_stats():
    """Get statistics about embedding coverage and usage."""
    try:
        from src.services.rag_service import get_rag_service

        rag_service = get_rag_service()
        stats = await rag_service.get_embedding_coverage()
        return stats

    except Exception as exc:  # noqa: BLE001
        logger.error("Embedding stats error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/embeddings/update")
async def api_update_embeddings(request: Request):
    """
    Trigger embedding update for articles without embeddings.
    """
    try:
        from celery import Celery
        from src.services.rag_service import get_rag_service

        body = await request.json()
        batch_size = body.get("batch_size", 50)

        celery_app = Celery("cti_scraper")
        celery_app.config_from_object("src.worker.celeryconfig")

        task = celery_app.send_task(
            "src.worker.celery_app.retroactive_embed_all_articles",
            args=[batch_size],
            queue="default",
        )

        rag_service = get_rag_service()
        stats = await rag_service.get_embedding_coverage()

        return {
            "success": True,
            "message": "Embedding update task started",
            "task_id": task.id,
            "batch_size": batch_size,
            "estimated_articles": stats.get("pending_embeddings", 0),
            "current_coverage": stats.get("embedding_coverage_percent", 0),
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Embedding update error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/articles/{article_id}/embed")
async def api_generate_embedding(article_id: int):
    """
    Generate embedding for a specific article.
    """
    try:
        from src.worker.celery_app import generate_article_embedding

        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        if article.embedding:
            return {
                "status": "already_embedded",
                "message": f"Article {article_id} already has an embedding",
                "embedded_at": article.embedded_at,
            }

        task = generate_article_embedding.delay(article_id)

        return {
            "status": "task_submitted",
            "task_id": task.id,
            "message": f"Embedding generation started for article {article_id}",
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Generate embedding error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

