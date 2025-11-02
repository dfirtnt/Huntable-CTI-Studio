"""
API routes for agentic workflow execution monitoring.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class ExecutionResponse(BaseModel):
    """Response model for workflow execution."""
    id: int
    article_id: int
    article_title: Optional[str]
    status: str
    current_step: Optional[str]
    ranking_score: Optional[float]
    config_snapshot: Optional[Dict[str, Any]]
    error_message: Optional[str]
    retry_count: int
    started_at: Optional[str]
    completed_at: Optional[str]
    created_at: str
    updated_at: str


class ExecutionDetailResponse(ExecutionResponse):
    """Detailed response with step results."""
    junk_filter_result: Optional[Dict[str, Any]]
    extraction_result: Optional[Dict[str, Any]]
    sigma_rules: Optional[List[Dict[str, Any]]]
    similarity_results: Optional[List[Dict[str, Any]]]
    error_log: Optional[Dict[str, Any]]


@router.get("/executions", response_model=List[ExecutionResponse])
async def list_workflow_executions(
    request: Request,
    article_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """List workflow executions."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            query = db_session.query(AgenticWorkflowExecutionTable)
            
            if article_id:
                query = query.filter(AgenticWorkflowExecutionTable.article_id == article_id)
            
            if status:
                query = query.filter(AgenticWorkflowExecutionTable.status == status)
            
            executions = query.order_by(AgenticWorkflowExecutionTable.created_at.desc()).limit(limit).all()
            
            result = []
            for execution in executions:
                # Get article title
                article = db_session.query(ArticleTable).filter(ArticleTable.id == execution.article_id).first()
                
                result.append(ExecutionResponse(
                    id=execution.id,
                    article_id=execution.article_id,
                    article_title=article.title if article else None,
                    status=execution.status,
                    current_step=execution.current_step,
                    ranking_score=execution.ranking_score,
                    config_snapshot=execution.config_snapshot,
                    error_message=execution.error_message,
                    retry_count=execution.retry_count,
                    started_at=execution.started_at.isoformat() if execution.started_at else None,
                    completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
                    created_at=execution.created_at.isoformat(),
                    updated_at=execution.updated_at.isoformat()
                ))
            
            return result
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error listing workflow executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}", response_model=ExecutionDetailResponse)
async def get_workflow_execution(request: Request, execution_id: int):
    """Get detailed workflow execution information."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == execution_id
            ).first()
            
            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")
            
            # Get article title
            article = db_session.query(ArticleTable).filter(ArticleTable.id == execution.article_id).first()
            
            return ExecutionDetailResponse(
                id=execution.id,
                article_id=execution.article_id,
                article_title=article.title if article else None,
                status=execution.status,
                current_step=execution.current_step,
                ranking_score=execution.ranking_score,
                config_snapshot=execution.config_snapshot,
                error_message=execution.error_message,
                retry_count=execution.retry_count,
                started_at=execution.started_at.isoformat() if execution.started_at else None,
                completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
                created_at=execution.created_at.isoformat(),
                updated_at=execution.updated_at.isoformat(),
                junk_filter_result=execution.junk_filter_result,
                extraction_result=execution.extraction_result,
                sigma_rules=execution.sigma_rules,
                similarity_results=execution.similarity_results,
                error_log=execution.error_log
            )
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{execution_id}/retry")
async def retry_workflow_execution(request: Request, execution_id: int):
    """Retry a failed workflow execution."""
    try:
        from src.worker.celery_app import trigger_agentic_workflow
        
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == execution_id
            ).first()
            
            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")
            
            if execution.status not in ['failed', 'completed']:
                raise HTTPException(status_code=400, detail="Can only retry failed or completed executions")
            
            # Create new execution record
            new_execution = AgenticWorkflowExecutionTable(
                article_id=execution.article_id,
                status='pending',
                config_snapshot=execution.config_snapshot,
                retry_count=execution.retry_count + 1
            )
            db_session.add(new_execution)
            db_session.commit()
            db_session.refresh(new_execution)
            
            # Trigger workflow
            trigger_agentic_workflow.delay(execution.article_id)
            
            return {
                "success": True,
                "message": f"Retry initiated for execution {execution_id}",
                "new_execution_id": new_execution.id
            }
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying workflow execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}/debug-info")
async def get_workflow_debug_info(request: Request, execution_id: int):
    """Get debug information for opening execution in Agent Chat UI."""
    import os
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == execution_id
            ).first()
            
            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")
            
            # Get LangGraph server URL from environment or config
            langgraph_server_url = os.getenv("LANGGRAPH_SERVER_URL", "http://localhost:2024")
            
            # Check if LangSmith is configured (preferred for debugging)
            langsmith_api_key = os.getenv("LANGSMITH_API_KEY")
            thread_id = f"workflow_exec_{execution_id}"
            
            if langsmith_api_key:
                # Use LangSmith Studio (free Developer plan available)
                # Format: https://smith.langchain.com/studio/?baseUrl={server_url}&thread={thread_id}&graph={graph_id}
                agent_chat_url = (
                    f"https://smith.langchain.com/studio/"
                    f"?baseUrl={langgraph_server_url}"
                    f"&thread={thread_id}"
                    f"&graph=agentic_workflow"
                )
                instructions = "Opening LangSmith Studio for debugging. Connect to your workspace if prompted."
            else:
                # Fallback to open-source Agent Chat UI
                agent_chat_base = os.getenv("AGENT_CHAT_UI_URL", "https://chat.langchain.com")
                agent_chat_url = f"{agent_chat_base}/?graph=agentic_workflow&thread={thread_id}&server={langgraph_server_url}"
                instructions = (
                    "Opening Agent Chat UI. Note: LangSmith Studio is preferred for debugging. "
                    "Set LANGSMITH_API_KEY in .env to use LangSmith Studio (free Developer plan available)."
                )
            
            return {
                "execution_id": execution_id,
                "article_id": execution.article_id,
                "langgraph_server_url": langgraph_server_url,
                "agent_chat_url": agent_chat_url,
                "thread_id": thread_id,
                "graph_id": "agentic_workflow",
                "instructions": instructions,
                "uses_langsmith": bool(langsmith_api_key)
            }
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting debug info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/articles/{article_id}/trigger")
async def trigger_workflow_for_article(request: Request, article_id: int):
    """Manually trigger agentic workflow for an article."""
    try:
        from src.services.workflow_trigger_service import WorkflowTriggerService
        
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            trigger_service = WorkflowTriggerService(db_session)
            
            if trigger_service.trigger_workflow(article_id):
                # Get the newly created execution
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.article_id == article_id
                ).order_by(AgenticWorkflowExecutionTable.created_at.desc()).first()
                
                return {
                    "success": True,
                    "message": f"Workflow triggered for article {article_id}",
                    "execution_id": execution.id if execution else None,
                    "article_id": article_id
                }
            else:
                # Check why it failed
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                if not article:
                    raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
                
                hunt_score = article.article_metadata.get('threat_hunting_score', 0) if article.article_metadata else 0
                config = trigger_service.get_active_config()
                min_score = config.min_hunt_score if config else 97.0
                
                # Check if already has active execution
                existing_execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.article_id == article_id,
                    AgenticWorkflowExecutionTable.status.in_(['pending', 'running'])
                ).first()
                
                if existing_execution:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Article {article_id} already has an active workflow execution (ID: {existing_execution.id})"
                    )
                
                raise HTTPException(
                    status_code=400,
                    detail=f"Article {article_id} hunt score ({hunt_score}) is below threshold ({min_score})"
                )
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering workflow for article {article_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

