"""
Search-related API routes for articles.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.utils.search_parser import get_search_help_text
from src.web.dependencies import logger

router = APIRouter(tags=["Search"])


@router.get("/api/search/help")
async def api_search_help():
    """Get search syntax help."""
    return {"help_text": get_search_help_text()}


@router.post("/api/search/semantic")
async def api_semantic_search(request: Request):
    """
    Perform semantic search on articles using vector embeddings.
    """
    try:
        from src.services.rag_service import get_rag_service

        body = await request.json()
        query = body.get("query", "")

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        top_k = body.get("top_k", 10)
        threshold = body.get("threshold", 0.7)
        source_id = body.get("source_id")

        rag_service = get_rag_service()
        results = await rag_service.semantic_search(
            query=query,
            filters={"top_k": top_k, "threshold": threshold, "source_id": source_id},
        )

        return results

    except HTTPException:
        # Re-raise HTTP exceptions (like validation errors) as-is
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Semantic search error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/api/articles/{article_id:int}/similar")
async def api_similar_articles(article_id: int, limit: int = 10, threshold: float = 0.7):
    """
    Find similar articles to a given article using embeddings.
    """
    try:
        from src.services.rag_service import get_rag_service

        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        if not article.embedding:
            raise HTTPException(status_code=400, detail="Article does not have an embedding")

        rag_service = get_rag_service()
        similar_articles = await rag_service.find_similar_articles(
            query=article.title + " " + article.content[:500],
            top_k=limit + 1,
            threshold=threshold,
        )

        similar_articles = [item for item in similar_articles if item["id"] != article_id][:limit]

        return {
            "target_article": {
                "id": article.id,
                "title": article.title,
                "source_id": article.source_id,
            },
            "similar_articles": similar_articles,
            "total_results": len(similar_articles),
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Similar articles error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
