"""
Search-related API routes for articles.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.utils.search_parser import get_search_help_text, parse_boolean_search
from src.web.dependencies import logger

router = APIRouter(tags=["Search"])


@router.get("/api/articles/search")
async def api_search_articles(
    q: str,
    source_id: Optional[int] = None,
    classification: Optional[str] = None,
    threat_hunting_min: Optional[int] = None,
    limit: Optional[int] = 100,
    offset: Optional[int] = 0,
):
    """Search articles with wildcard and boolean support."""
    try:
        all_articles = await async_db_manager.list_articles()
        filtered_articles = all_articles

        if source_id:
            filtered_articles = [article for article in filtered_articles if article.source_id == source_id]

        if classification:
            filtered_articles = [
                article
                for article in filtered_articles
                if article.article_metadata
                and article.article_metadata.get("training_category") == classification
            ]

        if threat_hunting_min is not None:
            filtered_articles = [
                article
                for article in filtered_articles
                if article.article_metadata
                and article.article_metadata.get("threat_hunting_score", 0) >= threat_hunting_min
            ]

        articles_dict = [
            {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "source_id": article.source_id,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "canonical_url": article.canonical_url,
                "metadata": article.article_metadata,
            }
            for article in filtered_articles
        ]

        search_results = parse_boolean_search(q, articles_dict)

        total_results = len(search_results)
        paginated_results = search_results[offset : offset + limit]

        return {
            "query": q,
            "total_results": total_results,
            "articles": paginated_results,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total_results,
            },
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Search API error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/articles/{article_id}/similar")
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc

