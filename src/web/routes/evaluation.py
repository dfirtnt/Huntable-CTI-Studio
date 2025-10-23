"""
Endpoints for RAG evaluation metrics and feedback.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.web.dependencies import logger

router = APIRouter(tags=["Evaluation"])


@router.post("/api/eval/hallucination")
async def api_eval_hallucination(request: Request):
    """Evaluate RAG response for hallucination detection."""
    try:
        body = await request.json()
        chat_log_id = body.get("chat_log_id")
        hallucination_detected = body.get("hallucination_detected", False)
        user_feedback = body.get("user_feedback", "")

        from src.database.models import ChatLogTable
        from src.database.async_manager import AsyncDatabaseManager

        async with AsyncDatabaseManager().get_session() as session:
            chat_log = await session.get(ChatLogTable, chat_log_id)
            if not chat_log:
                raise HTTPException(status_code=404, detail="Chat log not found")

            chat_log.hallucination_detected = hallucination_detected
            chat_log.user_feedback = user_feedback
            await session.commit()
            return {"status": "success", "message": "Hallucination evaluation recorded"}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Hallucination evaluation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/eval/relevance")
async def api_eval_relevance(request: Request):
    """Evaluate RAG response for relevance scoring."""
    try:
        body = await request.json()
        chat_log_id = body.get("chat_log_id")
        relevance_score = body.get("relevance_score", 3.0)
        accuracy_rating = body.get("accuracy_rating", 3.0)
        user_feedback = body.get("user_feedback", "")

        from src.database.models import ChatLogTable
        from src.database.async_manager import AsyncDatabaseManager

        async with AsyncDatabaseManager().get_session() as session:
            chat_log = await session.get(ChatLogTable, chat_log_id)
            if not chat_log:
                raise HTTPException(status_code=404, detail="Chat log not found")

            chat_log.relevance_score = relevance_score
            chat_log.accuracy_rating = accuracy_rating
            chat_log.user_feedback = user_feedback
            await session.commit()
            return {"status": "success", "message": "Relevance evaluation recorded"}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Relevance evaluation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/metrics")
async def api_eval_metrics():
    """Get RAG evaluation metrics."""
    try:
        from sqlalchemy import Float, Integer, func, select
        from src.database.models import ChatLogTable
        from src.database.async_manager import AsyncDatabaseManager

        async with AsyncDatabaseManager().get_session() as session:
            total_chats = await session.scalar(select(func.count(ChatLogTable.id)))

            avg_relevance = await session.scalar(
                select(func.avg(ChatLogTable.relevance_score)).where(ChatLogTable.relevance_score.is_not(None))
            )
            avg_accuracy = await session.scalar(
                select(func.avg(ChatLogTable.accuracy_rating)).where(ChatLogTable.accuracy_rating.is_not(None))
            )
            hallucination_rate = await session.scalar(
                select(func.avg(func.cast(ChatLogTable.hallucination_detected, Integer))).where(
                    ChatLogTable.hallucination_detected.is_not(None)
                )
            )
            avg_response_time = await session.scalar(
                select(func.avg(ChatLogTable.response_time_ms)).where(ChatLogTable.response_time_ms.is_not(None))
            )

            return {
                "total_chats": total_chats or 0,
                "avg_relevance_score": round(avg_relevance or 0, 2),
                "avg_accuracy_rating": round(avg_accuracy or 0, 2),
                "hallucination_rate": round((hallucination_rate or 0) * 100, 2),
                "avg_response_time_ms": round(avg_response_time or 0, 0),
            }

    except Exception as exc:  # noqa: BLE001
        logger.error("Metrics evaluation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

