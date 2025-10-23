"""
Core article management API routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger


class SimpleFilter:
    def __init__(
        self,
        limit: Optional[int] = None,
        sort_by: str = "threat_hunting_score",
        sort_order: str = "desc",
        source_id: Optional[int] = None,
        processing_status: Optional[str] = None,
    ):
        self.limit = limit
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.source_id = source_id
        self.processing_status = processing_status
        self.offset = 0
        self.published_after = None
        self.published_before = None
        self.content_contains = None


router = APIRouter(prefix="/api/articles", tags=["Articles"])


@router.get("")
async def api_articles_list(
    limit: Optional[int] = 100,
    sort_by: str = "threat_hunting_score",
    sort_order: str = "desc",
    source_id: Optional[int] = None,
    processing_status: Optional[str] = None,
):
    """API endpoint for listing articles with sorting and filtering."""
    logger.debug("=" * 50)
    logger.debug("API ARTICLES ENDPOINT CALLED!")
    logger.debug("=" * 50)
    logger.debug("Function parameters: sort_by=%s, sort_order=%s", sort_by, sort_order)
    try:
        logger.debug("DEBUG: API called with sort_by=%s, sort_order=%s", sort_by, sort_order)
        logger.info("DEBUG: API called with sort_by=%s, sort_order=%s", sort_by, sort_order)
        try:
            article_filter = SimpleFilter(
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order,
                source_id=source_id,
                processing_status=processing_status,
            )
            logger.info(
                "DEBUG: Created filter with sort_by=%s, sort_order=%s",
                article_filter.sort_by,
                article_filter.sort_order,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("DEBUG: Error creating filter: %s", exc)
            article_filter = None

        articles = await async_db_manager.list_articles(article_filter=article_filter)
        logger.info("DEBUG: Retrieved %s articles", len(articles))

        total_count = await async_db_manager.get_articles_count(
            source_id=source_id,
            processing_status=processing_status,
        )

        return {
            "articles": [article.dict() for article in articles],
            "total": total_count,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("API articles list error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/next-unclassified")
async def api_get_next_unclassified(current_article_id: Optional[int] = None):
    """API endpoint for getting the next unclassified article."""
    try:
        articles = await async_db_manager.list_articles()
        articles.sort(key=lambda x: x.id)

        if not current_article_id:
            for article in articles:
                if not article.article_metadata or article.article_metadata.get("training_category") not in [
                    "chosen",
                    "rejected",
                ]:
                    return {"article_id": article.id}
        else:
            found_current = False
            for article in articles:
                if article.id == current_article_id:
                    found_current = True
                    continue

                if found_current and (
                    not article.article_metadata
                    or article.article_metadata.get("training_category") not in ["chosen", "rejected"]
                ):
                    return {"article_id": article.id}

        return {"article_id": None, "message": "No unclassified articles found"}

    except Exception as exc:  # noqa: BLE001
        logger.error("API get next unclassified error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/next")
async def api_get_next_article(current_article_id: int):
    """API endpoint for getting the next article by ID."""
    try:
        articles = await async_db_manager.list_articles()
        articles.sort(key=lambda x: x.id)

        found_current = False
        for article in articles:
            if article.id == current_article_id:
                found_current = True
                continue

            if found_current:
                return {"article_id": article.id}

        return {"article_id": None, "message": "No next article found"}

    except Exception as exc:  # noqa: BLE001
        logger.error("API get next article error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/previous")
async def api_get_previous_article(current_article_id: int):
    """API endpoint for getting the previous article by ID."""
    try:
        articles = await async_db_manager.list_articles()
        articles.sort(key=lambda x: x.id)

        previous_article = None
        for article in articles:
            if article.id == current_article_id:
                break
            previous_article = article

        if previous_article:
            return {"article_id": previous_article.id}
        return {"article_id": None, "message": "No previous article found"}

    except Exception as exc:  # noqa: BLE001
        logger.error("API get previous article error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/top")
async def api_articles_top(limit: int = 10):
    """Get top-scoring articles for dashboard."""
    try:
        articles = await async_db_manager.list_articles(limit=limit, order_by="hunt_score", order_desc=True)

        top_articles = []
        for article in articles:
            if article.get("hunt_score", 0) > 0:
                top_articles.append(
                    {
                        "id": article.get("id"),
                        "title": article.get("title", "Untitled")[:100],
                        "hunt_score": round(article.get("hunt_score", 0), 1),
                        "classification": article.get("classification", "Unclassified"),
                    }
                )

        return top_articles
    except Exception as exc:  # noqa: BLE001
        logger.error("Top articles error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{article_id}")
async def api_get_article(article_id: int):
    """API endpoint for getting a specific article."""
    try:
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        return article.dict()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("API get article error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{article_id}/classify")
async def api_classify_article(article_id: int, request: Request):
    """API endpoint for classifying an article with metadata update."""
    try:
        body = await request.json()
        category = body.get("category")
        reason = body.get("reason", "")

        if not category or category not in {"chosen", "rejected", "unclassified"}:
            raise HTTPException(status_code=400, detail="Invalid or missing category")

        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        from src.models.article import ArticleUpdate

        current_metadata = article.article_metadata.copy() if article.article_metadata else {}
        current_metadata["training_category"] = category
        current_metadata["training_reason"] = reason
        current_metadata["training_categorized_at"] = datetime.now().isoformat()

        update_data = ArticleUpdate(article_metadata=current_metadata)
        updated_article = await async_db_manager.update_article(article_id, update_data)

        if not updated_article:
            raise HTTPException(status_code=500, detail="Failed to update article")

        return {
            "success": True,
            "article_id": article_id,
            "category": category,
            "reason": reason,
            "categorized_at": current_metadata["training_categorized_at"],
        }

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("API classify article error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/bulk-action")
async def api_bulk_action(request: Request):
    """API endpoint for performing bulk actions on multiple articles."""
    try:
        body = await request.json()
        action = body.get("action")
        article_ids = body.get("article_ids", [])

        if not action:
            raise HTTPException(status_code=400, detail="Action is required")

        if not article_ids:
            raise HTTPException(status_code=400, detail="Article IDs are required")

        if action not in {"chosen", "rejected", "unclassified", "delete"}:
            raise HTTPException(status_code=400, detail="Invalid action")

        processed_count = 0
        errors: list[str] = []

        for article_id in article_ids:
            try:
                if action == "delete":
                    await async_db_manager.delete_article(article_id)
                    processed_count += 1
                else:
                    article = await async_db_manager.get_article(article_id)
                    if not article:
                        errors.append(f"Article {article_id} not found")
                        continue

                    from src.models.article import ArticleUpdate

                    current_metadata = article.article_metadata.copy() if article.article_metadata else {}
                    current_metadata["training_category"] = action
                    current_metadata["training_categorized_at"] = datetime.now().isoformat()

                    update_data = ArticleUpdate(article_metadata=current_metadata)
                    await async_db_manager.update_article(article_id, update_data)
                    processed_count += 1

            except Exception as exc:  # noqa: BLE001
                errors.append(f"Article {article_id}: {exc}")
                logger.error("Bulk action error for article %s: %s", article_id, exc)

        return {
            "success": True,
            "processed_count": processed_count,
            "total_requested": len(article_ids),
            "errors": errors,
        }

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("API bulk action error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{article_id}")
async def delete_article(article_id: int):
    """Delete an article and all its related data."""
    try:
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        success = await async_db_manager.delete_article(article_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete article")

        logger.info("Deleted article %s", article_id)

        return {"success": True, "message": "Article deleted successfully"}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete article: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

