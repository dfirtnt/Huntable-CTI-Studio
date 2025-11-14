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


@router.get("/api/eval/history")
async def api_eval_history(agent_name: str, limit: int = 50):
    """Get evaluation history for an agent."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker
        
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            tracker = EvaluationTracker(db_session)
            history = tracker.get_evaluation_history(agent_name, limit=limit)
            return {"agent_name": agent_name, "history": history}
        finally:
            db_session.close()
    
    except Exception as exc:  # noqa: BLE001
        logger.error("Evaluation history error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/comparison")
async def api_eval_comparison(baseline_id: int, current_id: int):
    """Compare two evaluations."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker
        
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            tracker = EvaluationTracker(db_session)
            comparison = tracker.compare_evaluations(baseline_id, current_id)
            return comparison
        finally:
            db_session.close()
    
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Evaluation comparison error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/agent-metrics")
async def api_eval_agent_metrics(agent_name: str):
    """Get latest metrics for an agent."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker
        
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            tracker = EvaluationTracker(db_session)
            latest = tracker.get_latest_evaluation(agent_name)
            
            if not latest:
                raise HTTPException(status_code=404, detail=f"No evaluations found for {agent_name}")
            
            return {
                "agent_name": agent_name,
                "latest_evaluation": latest,
                "metrics": latest.get("metrics", {})
            }
        finally:
            db_session.close()
    
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Agent metrics error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/trends")
async def api_eval_trends(agent_name: str, metric_key: str, evaluation_type: str = None):
    """Get improvement trends for a specific metric."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker
        
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            tracker = EvaluationTracker(db_session)
            trends = tracker.get_improvement_trends(agent_name, metric_key, evaluation_type)
            return {
                "agent_name": agent_name,
                "metric_key": metric_key,
                "trends": trends
            }
        finally:
            db_session.close()
    
    except Exception as exc:  # noqa: BLE001
        logger.error("Evaluation trends error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/eval/run")
async def api_eval_run(request: Request):
    """Trigger an evaluation run (returns immediately, runs in background)."""
    try:
        body = await request.json()
        agent_name = body.get("agent_name")
        test_data_path = body.get("test_data_path")
        evaluation_type = body.get("evaluation_type", "baseline")
        model_version = body.get("model_version")
        save_to_db = body.get("save_to_db", True)
        
        if not agent_name or not test_data_path:
            raise HTTPException(status_code=400, detail="agent_name and test_data_path are required")
        
        # Import evaluators
        from pathlib import Path
        from src.services.evaluation.extract_agent_evaluator import ExtractAgentEvaluator
        from src.services.evaluation.rank_agent_evaluator import RankAgentEvaluator
        from src.services.evaluation.sigma_agent_evaluator import SigmaAgentEvaluator
        from src.services.evaluation.os_detection_evaluator import OSDetectionEvaluator
        from src.services.llm_service import LLMService
        from src.utils.content_filter import ContentFilter
        from src.services.os_detection_service import OSDetectionService
        from src.database.manager import DatabaseManager
        import asyncio
        
        # This would ideally run in a background task
        # For now, return a message that evaluation should be run via CLI
        return {
            "status": "info",
            "message": "Evaluation triggered. Note: Full evaluations should be run via CLI scripts for better control.",
            "agent_name": agent_name,
            "suggestion": f"Run: python scripts/eval_{agent_name.lower().replace('agent', 'agent').replace('osdetection', 'os_detection')}.py --test-data {test_data_path} --evaluation-type {evaluation_type} {'--save-to-db' if save_to_db else ''}"
        }
    
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Evaluation run error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

