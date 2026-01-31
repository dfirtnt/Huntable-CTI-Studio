"""
UI routes for agent evaluation pages.
"""

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.database.manager import DatabaseManager
from src.services.evaluation.evaluation_tracker import EvaluationTracker
from src.web.dependencies import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evaluation-ui"])


@router.get("/evaluations", response_class=HTMLResponse)
async def evaluations_page(request: Request):
    """Main evaluations dashboard page."""
    try:
        return templates.TemplateResponse("evaluations.html", {"request": request})
    except Exception as e:
        logger.error(f"Error loading evaluations page: {e}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": f"Error loading evaluations page: {str(e)}"}, status_code=500
        )


@router.get("/evaluations/compare", response_class=HTMLResponse)
async def compare_evaluations_page(request: Request, baseline_id: int = Query(...), current_id: int = Query(...)):
    """Compare two evaluations."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        tracker = EvaluationTracker(db_session)
        comparison = tracker.compare_evaluations(baseline_id, current_id)

        return templates.TemplateResponse("evaluation_comparison.html", {"request": request, "comparison": comparison})
    except ValueError as e:
        return templates.TemplateResponse("error.html", {"request": request, "error": str(e)}, status_code=400)
    finally:
        db_session.close()


@router.get("/evaluations/{agent_name}/{subagent_name}", response_class=HTMLResponse)
async def subagent_evaluation_page(
    request: Request, agent_name: str, subagent_name: str, evaluation_id: int | None = Query(None)
):
    """Subagent-specific evaluation page."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        try:
            tracker = EvaluationTracker(db_session)

            # Get evaluation history for the subagent
            # Note: Subagents may not have separate evaluations, so we'll show parent agent's evaluations
            # filtered by subagent if available
            history = tracker.get_evaluation_history(agent_name, limit=50)

            # Get latest evaluation
            latest = tracker.get_latest_evaluation(agent_name)

            # Get specific evaluation if requested
            selected_evaluation = None
            if evaluation_id:
                from src.database.models import AgentEvaluationTable

                selected_evaluation = (
                    db_session.query(AgentEvaluationTable).filter(AgentEvaluationTable.id == evaluation_id).first()
                )
                if selected_evaluation:
                    selected_evaluation = {
                        "id": selected_evaluation.id,
                        "agent_name": selected_evaluation.agent_name,
                        "evaluation_type": selected_evaluation.evaluation_type,
                        "model_version": selected_evaluation.model_version,
                        "metrics": selected_evaluation.metrics,
                        "created_at": selected_evaluation.created_at.isoformat()
                        if selected_evaluation.created_at
                        else None,
                        "total_articles": selected_evaluation.total_articles,
                    }
        except Exception as db_error:
            # Handle case where table doesn't exist yet
            logger.warning(f"Database error loading evaluations (table may not exist): {db_error}")
            history = []
            latest = None
            selected_evaluation = None

        return templates.TemplateResponse(
            "subagent_evaluation.html",
            {
                "request": request,
                "agent_name": agent_name,
                "subagent_name": subagent_name,
                "history": history or [],
                "latest": latest,
                "selected_evaluation": selected_evaluation,
            },
        )
    finally:
        db_session.close()


@router.get("/evaluations/{agent_name}", response_class=HTMLResponse)
async def agent_evaluation_page(request: Request, agent_name: str, evaluation_id: int | None = Query(None)):
    """Agent-specific evaluation page."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        try:
            tracker = EvaluationTracker(db_session)

            # Get evaluation history
            history = tracker.get_evaluation_history(agent_name, limit=50)

            # Get latest evaluation
            latest = tracker.get_latest_evaluation(agent_name)

            # Get specific evaluation if requested
            selected_evaluation = None
            if evaluation_id:
                from src.database.models import AgentEvaluationTable

                selected_evaluation = (
                    db_session.query(AgentEvaluationTable).filter(AgentEvaluationTable.id == evaluation_id).first()
                )
                if selected_evaluation:
                    selected_evaluation = {
                        "id": selected_evaluation.id,
                        "agent_name": selected_evaluation.agent_name,
                        "evaluation_type": selected_evaluation.evaluation_type,
                        "model_version": selected_evaluation.model_version,
                        "metrics": selected_evaluation.metrics,
                        "created_at": selected_evaluation.created_at.isoformat()
                        if selected_evaluation.created_at
                        else None,
                        "total_articles": selected_evaluation.total_articles,
                    }
        except Exception as db_error:
            # Handle case where table doesn't exist yet
            logger.warning(f"Database error loading evaluations (table may not exist): {db_error}")
            history = []
            latest = None
            selected_evaluation = None

        return templates.TemplateResponse(
            "agent_evaluation.html",
            {
                "request": request,
                "agent_name": agent_name,
                "history": history or [],
                "latest": latest,
                "selected_evaluation": selected_evaluation,
            },
        )
    finally:
        db_session.close()
