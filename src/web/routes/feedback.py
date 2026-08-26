"""
Feedback collection endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter(tags=["Feedback"])


@router.post("/api/feedback/chunk-classification")
async def api_feedback_chunk_classification(request: Request):
    """Collect user feedback on chunk classifications for model improvement."""
    try:
        feedback_data = await request.json()

        required_fields = [
            "article_id",
            "chunk_id",
            "chunk_text",
            "model_classification",
            "is_correct",
        ]
        for field in required_fields:
            if field not in feedback_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        await async_db_manager.create_chunk_feedback(
            {
                "article_id": feedback_data["article_id"],
                "chunk_id": feedback_data["chunk_id"],
                "chunk_text": feedback_data["chunk_text"],
                "model_classification": feedback_data["model_classification"],
                "model_confidence": feedback_data.get("model_confidence", 0),
                "model_reason": feedback_data.get("model_reason", ""),
                "is_correct": feedback_data["is_correct"],
                "user_classification": feedback_data.get("user_classification", ""),
                "comment": feedback_data.get("comment", ""),
                "used_for_training": False,
            }
        )

        return {"success": True, "message": "Feedback recorded successfully"}

    except Exception as exc:  # noqa: BLE001
        logger.error("Feedback collection failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/api/feedback/chunk-classification/{article_id}")
async def api_get_article_chunk_feedback(article_id: int):
    """Get every stored chunk feedback for an article, keyed by chunk id.

    The Junk Filter Tuning modal previously called the single-chunk route once
    per chunk while rendering: 150 requests on article 7216, and 1,250 after a
    full analysis, essentially all of them returning ``feedback: null`` because
    chunk feedback is rare. This serves the same information in one round trip.

    Rows are ordered newest-first and reduced to the first hit per chunk, which
    matches the single-chunk route's ``ORDER BY created_at DESC LIMIT 1``. The
    reduction is done here rather than in SQL (no DISTINCT ON / window function)
    because feedback volume per article is tiny -- tens of rows at most -- and
    this keeps the query portable and the ordering contract obvious.
    """
    try:
        from sqlalchemy import desc, select

        from src.database.models import ChunkClassificationFeedbackTable

        async with async_db_manager.get_session() as session:
            result = await session.execute(
                select(ChunkClassificationFeedbackTable)
                .where(ChunkClassificationFeedbackTable.article_id == article_id)
                .order_by(desc(ChunkClassificationFeedbackTable.created_at))
            )
            records = result.scalars().all()

        feedback_by_chunk: dict[str, dict] = {}
        for record in records:
            key = str(record.chunk_id)
            if key in feedback_by_chunk:
                continue  # newest wins; rows arrive newest-first
            feedback_by_chunk[key] = {
                "timestamp": str(record.created_at),
                "is_correct": bool(record.is_correct),
                "user_classification": str(record.user_classification),
                "comment": str(record.comment),
                "model_classification": str(record.model_classification),
                "model_confidence": float(record.model_confidence),
            }

        return {"success": True, "feedback": feedback_by_chunk}

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get article chunk feedback: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/api/feedback/chunk-classification/{article_id}/{chunk_id}")
async def api_get_chunk_feedback(article_id: int, chunk_id: int):
    """Get existing feedback for a specific chunk."""
    try:
        from sqlalchemy import desc, select

        from src.database.models import ChunkClassificationFeedbackTable

        async with async_db_manager.get_session() as session:
            result = await session.execute(
                select(ChunkClassificationFeedbackTable)
                .where(
                    ChunkClassificationFeedbackTable.article_id == article_id,
                    ChunkClassificationFeedbackTable.chunk_id == chunk_id,
                )
                .order_by(desc(ChunkClassificationFeedbackTable.created_at))
                .limit(1)
            )
            feedback_record = result.scalar_one_or_none()

            if not feedback_record:
                return {"success": True, "feedback": None}

            return {
                "success": True,
                "feedback": {
                    "timestamp": str(feedback_record.created_at),
                    "is_correct": bool(feedback_record.is_correct),
                    "user_classification": str(feedback_record.user_classification),
                    "comment": str(feedback_record.comment),
                    "model_classification": str(feedback_record.model_classification),
                    "model_confidence": float(feedback_record.model_confidence),
                },
            }

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get chunk feedback: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
