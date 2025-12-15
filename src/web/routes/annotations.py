"""
Article annotation API endpoints.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.database.async_manager import async_db_manager
from src.models.annotation import (
    ArticleAnnotationCreate,
    ArticleAnnotationUpdate,
    ANNOTATION_MODE_TYPES,
    ALL_ANNOTATION_TYPES,
    ANNOTATION_USAGE_VALUES,
)
from src.models.article import ArticleUpdate
from src.web.dependencies import logger

router = APIRouter(tags=["Annotations"])


@router.post("/api/articles/{article_id}/annotations")
async def create_annotation(article_id: int, annotation_data: dict):
    """Create a new text annotation for an article."""
    try:
        annotation_type = annotation_data.get("annotation_type")
        if not annotation_type:
            raise HTTPException(status_code=400, detail="annotation_type is required")

        if annotation_type not in ALL_ANNOTATION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported annotation type '{annotation_type}'",
            )

        text_length = len(annotation_data.get("selected_text", ""))
        if annotation_type in ANNOTATION_MODE_TYPES["huntability"] and (
            text_length < 950 or text_length > 1050
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Annotation text must be approximately 1000 characters for training purposes "
                    f"(current: {text_length})"
                ),
            )
        if annotation_type in ANNOTATION_MODE_TYPES["observables"] and text_length == 0:
            raise HTTPException(
                status_code=400,
                detail="Annotation text is required for observable annotations",
            )

        usage = annotation_data.get("usage")
        if annotation_type in ANNOTATION_MODE_TYPES["observables"]:
            if not usage:
                raise HTTPException(
                    status_code=400,
                    detail="usage is required for observable annotations",
                )
            usage = usage.lower()
            if usage not in ANNOTATION_USAGE_VALUES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported annotation usage '{usage}'",
                )
        else:
            usage = usage or "train"

        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        annotation_create = ArticleAnnotationCreate(
            article_id=article_id,
            annotation_type=annotation_type,
            selected_text=annotation_data.get("selected_text"),
            start_position=annotation_data.get("start_position"),
            end_position=annotation_data.get("end_position"),
            context_before=annotation_data.get("context_before"),
            context_after=annotation_data.get("context_after"),
            confidence_score=annotation_data.get("confidence_score", 1.0),
            usage=usage,
        )

        annotation = await async_db_manager.create_annotation(annotation_create)
        if not annotation:
            raise HTTPException(status_code=500, detail="Failed to create annotation")

        try:
            annotations = await async_db_manager.get_article_annotations(article_id)
            annotation_count = len(annotations)
            current_metadata = article.article_metadata.copy() if article.article_metadata else {}
            current_metadata["annotation_count"] = annotation_count

            update_data = ArticleUpdate(article_metadata=current_metadata)
            await async_db_manager.update_article(article_id, update_data)

            logger.info("Updated annotation count to %s for article %s", annotation_count, article_id)

        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to update annotation count for article %s: %s", article_id, exc)

        logger.info("Created annotation %s for article %s", annotation.id, article_id)

        return {"success": True, "annotation": annotation, "message": "Annotation created successfully"}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create annotation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/articles/{article_id}/annotations")
async def get_article_annotations(article_id: int):
    """Get all annotations for a specific article."""
    try:
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        annotations = await async_db_manager.get_article_annotations(article_id)

        return {
            "success": True,
            "article_id": article_id,
            "annotations": annotations,
            "count": len(annotations),
        }

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get annotations: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/articles/{article_id}/annotations/{annotation_id}")
async def delete_article_annotation(article_id: int, annotation_id: int):
    """Delete a specific annotation tied to an article."""
    try:
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        success = await async_db_manager.delete_annotation(annotation_id)
        if success:
            try:
                annotations = await async_db_manager.get_article_annotations(article_id)
                annotation_count = len(annotations)
                current_metadata = article.article_metadata.copy() if article.article_metadata else {}
                current_metadata["annotation_count"] = annotation_count

                update_data = ArticleUpdate(article_metadata=current_metadata)
                await async_db_manager.update_article(article_id, update_data)

                logger.info("Updated annotation count to %s for article %s", annotation_count, article_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to update annotation count for article %s: %s", article_id, exc)

            return {"success": True, "message": "Annotation deleted successfully"}

        raise HTTPException(status_code=404, detail="Annotation not found")

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete annotation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/annotations/stats")
async def get_annotation_stats():
    """Get annotation statistics."""
    try:
        stats = await async_db_manager.get_annotation_stats()
        return {"success": True, "stats": stats}
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get annotation stats: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/annotations/types")
async def get_annotation_types():
    """Return supported annotation modes and types."""
    return {"success": True, "modes": ANNOTATION_MODE_TYPES}


@router.get("/api/annotations/{annotation_id}")
async def get_annotation(annotation_id: int):
    """Get a specific annotation by ID."""
    try:
        annotation = await async_db_manager.get_annotation(annotation_id)
        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found")

        return {"success": True, "annotation": annotation}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get annotation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/api/annotations/{annotation_id}")
async def update_annotation(annotation_id: int, update_data: ArticleAnnotationUpdate):
    """Update an existing annotation."""
    try:
        annotation = await async_db_manager.update_annotation(annotation_id, update_data)
        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found")

        logger.info("Updated annotation %s", annotation_id)

        return {"success": True, "annotation": annotation, "message": "Annotation updated successfully"}

    except HTTPException:
        raise
    except ValueError as exc:
        # Catch ValueError from service layer (e.g., usage immutability)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to update annotation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/annotations/{annotation_id}")
async def delete_annotation(annotation_id: int):
    """Delete an annotation."""
    try:
        annotation = await async_db_manager.get_annotation(annotation_id)
        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found")

        article_id = annotation.article_id
        success = await async_db_manager.delete_annotation(annotation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Annotation not found")

        try:
            article = await async_db_manager.get_article(article_id)
            if article:
                annotations = await async_db_manager.get_article_annotations(article_id)
                annotation_count = len(annotations)

                current_metadata = article.article_metadata.copy() if article.article_metadata else {}
                current_metadata["annotation_count"] = annotation_count

                update_data = ArticleUpdate(article_metadata=current_metadata)
                await async_db_manager.update_article(article_id, update_data)

                logger.info("Updated annotation count to %s for article %s", annotation_count, article_id)

        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to update annotation count for article %s: %s", article_id, exc)

        logger.info("Deleted annotation %s", annotation_id)

        return {"success": True, "message": "Annotation deleted successfully"}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete annotation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
