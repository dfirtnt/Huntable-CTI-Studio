"""
API routes for agentic workflow execution monitoring.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, Query
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


class ExecutionListResponse(BaseModel):
    """Response model for execution list with counts."""
    executions: List[ExecutionResponse]
    total: int
    running: int
    completed: int
    failed: int
    pending: int


@router.get("/executions", response_model=ExecutionListResponse)
async def list_workflow_executions(
    request: Request,
    article_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """List workflow executions with accurate counts."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Base query for counting (no filters applied)
            base_query = db_session.query(AgenticWorkflowExecutionTable)
            
            # Filtered query for results
            query = db_session.query(AgenticWorkflowExecutionTable)
            
            if article_id:
                query = query.filter(AgenticWorkflowExecutionTable.article_id == article_id)
                base_query = base_query.filter(AgenticWorkflowExecutionTable.article_id == article_id)
            
            if status:
                query = query.filter(AgenticWorkflowExecutionTable.status == status)
                # Don't filter base_query by status for counts
            
            # Get total counts (before status filter)
            total = base_query.count()
            running = base_query.filter(AgenticWorkflowExecutionTable.status == 'running').count()
            completed = base_query.filter(AgenticWorkflowExecutionTable.status == 'completed').count()
            failed = base_query.filter(AgenticWorkflowExecutionTable.status == 'failed').count()
            pending = base_query.filter(AgenticWorkflowExecutionTable.status == 'pending').count()
            
            # Get filtered executions
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
            
            return ExecutionListResponse(
                executions=result,
                total=total,
                running=running,
                completed=completed,
                failed=failed,
                pending=pending
            )
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
            # Query with fresh session to ensure we get latest data
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == execution_id
            ).first()
            
            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")
            
            # Explicitly expire and refresh to bypass any session cache
            db_session.expire(execution)
            db_session.refresh(execution)
            
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


async def _trigger_via_langgraph_server(article_id: int, execution_id: int, langgraph_server_url: str, thread_id: str) -> bool:
    """
    Trigger workflow via LangGraph server API (creates traces).
    
    Returns True if successful, False otherwise.
    """
    import httpx
    try:
        # Get article and config
        from src.services.workflow_trigger_service import WorkflowTriggerService
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                return False
            
            trigger_service = WorkflowTriggerService(db_session)
            config_obj = trigger_service.get_active_config()
            config = {
                'min_hunt_score': config_obj.min_hunt_score if config_obj else 97.0,
                'ranking_threshold': config_obj.ranking_threshold if config_obj else 6.0,
                'similarity_threshold': config_obj.similarity_threshold if config_obj else 0.5
            }
            
            # Prepare initial state for LangGraph server
            # Format matches ExposableWorkflowState - direct input mode
            initial_state = {
                "article_id": article_id,
                "execution_id": execution_id,
                "input": {
                    "article_id": article_id,
                    "min_hunt_score": config['min_hunt_score'],
                    "ranking_threshold": config['ranking_threshold'],
                    "similarity_threshold": config['similarity_threshold']
                },
                "messages": None,  # Direct input mode, not chat mode
                "current_step": "junk_filter",
                "status": "running"
            }
            
            # Call LangGraph server API
            async with httpx.AsyncClient(timeout=60.0) as client:
                # LangGraph server expects assistant_id as UUID, but graph name works for creating threads
                # First, try to get/create thread, then submit run
                # Format: POST /threads/{thread_id}/runs (simpler format that works with graph names)
                
                # Try alternative endpoint format that accepts graph names
                # LangGraph dev server may support graph name directly in threads endpoint
                try:
                    # Try: POST /threads/{thread_id}/runs with assistant_id in body
                    # LangGraph expects the input to match the workflow state format
                    url = f"{langgraph_server_url}/threads/{thread_id}/runs"
                    
                    # Format input according to ExposableWorkflowState - use direct input, not nested
                    # The workflow expects article_id, execution_id, etc. at top level
                    workflow_input = {
                        "article_id": article_id,
                        "execution_id": execution_id,
                        "min_hunt_score": config['min_hunt_score'],
                        "ranking_threshold": config['ranking_threshold'],
                        "similarity_threshold": config['similarity_threshold'],
                        "current_step": "junk_filter",
                        "status": "running"
                    }
                    
                    response = await client.post(
                        url,
                        json={
                            "assistant_id": "agentic_workflow",  # Graph name
                            "input": workflow_input,  # Direct state, not nested
                            "stream": False
                        }
                    )
                    
                    if response.status_code in [200, 201]:
                        logger.info(f"Workflow triggered via LangGraph server for execution {execution_id}")
                        return True
                    
                    # Fallback: Try with assistant_id in URL (UUID format may be required)
                    # If that fails, try the original format
                    logger.info(f"First attempt returned {response.status_code}, trying alternative format")
                    
                except httpx.ConnectError:
                    logger.warning(f"Cannot connect to LangGraph server at {langgraph_server_url}")
                    return False
                except httpx.TimeoutException:
                    logger.warning(f"Timeout connecting to LangGraph server at {langgraph_server_url}")
                    return False
                except Exception as e:
                    logger.warning(f"Error with alternative endpoint format: {e}")
                
                # Fallback: Try original format in case it works with different version
                try:
                    url = f"{langgraph_server_url}/assistants/agentic_workflow/threads/{thread_id}/runs"
                    response = await client.post(
                        url,
                        json={
                            "input": initial_state,
                            "stream": False
                        }
                    )
                    
                    if response.status_code in [200, 201]:
                        logger.info(f"Workflow triggered via LangGraph server for execution {execution_id}")
                        return True
                    else:
                        logger.warning(f"LangGraph server returned {response.status_code}: {response.text}")
                        return False
                        
                except Exception as e:
                    logger.error(f"Error triggering via LangGraph server: {e}")
                    return False
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error triggering via LangGraph server: {e}")
        return False


@router.post("/executions/{execution_id}/retry")
async def retry_workflow_execution(request: Request, execution_id: int, use_langgraph_server: bool = Query(False)):
    """
    Retry a failed workflow execution.
    
    Args:
        use_langgraph_server: If True, uses LangGraph server API (creates traces).
                             If False, uses direct Celery execution (no traces, faster).
    """
    try:
        import os
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
            logger.info(f"Retry requested for execution {execution_id}, use_langgraph_server={use_langgraph_server}")
            if use_langgraph_server:
                langgraph_server_url = os.getenv("LANGGRAPH_SERVER_URL", "http://localhost:2024")
                thread_id = f"workflow_exec_{new_execution.id}"
                
                # Try LangGraph server API
                logger.info(f"Attempting to connect to LangGraph server at {langgraph_server_url}")
                success = await _trigger_via_langgraph_server(
                    execution.article_id,
                    new_execution.id,
                    langgraph_server_url,
                    thread_id
                )
                
                # Fallback: try localhost if service name failed (for local dev)
                if not success and langgraph_server_url != "http://localhost:2024":
                    logger.info(f"Service name connection failed, trying localhost fallback")
                    success = await _trigger_via_langgraph_server(
                        execution.article_id,
                        new_execution.id,
                        "http://localhost:2024",
                        thread_id
                    )
                
                if success:
                    # Update execution status
                    new_execution.status = 'running'
                    new_execution.started_at = datetime.utcnow()
                    new_execution.current_step = 'junk_filter'
                    db_session.commit()
                    
                    return {
                        "success": True,
                        "message": f"Retry initiated via LangGraph server for execution {execution_id} (creates traces)",
                        "new_execution_id": new_execution.id,
                        "via_langgraph_server": True
                    }
                else:
                    # Fail with error instead of falling back
                    new_execution.status = 'failed'
                    new_execution.error_message = f"LangGraph server unavailable at {langgraph_server_url}"
                    db_session.commit()
                    
                    raise HTTPException(
                        status_code=503,
                        detail=f"LangGraph server unavailable at {langgraph_server_url}. Make sure the server is running on port 2024."
                    )
            else:
                # Direct Celery execution (default)
                trigger_agentic_workflow.delay(execution.article_id)
            
            return {
                "success": True,
                "message": f"Retry initiated for execution {execution_id}",
                    "new_execution_id": new_execution.id,
                    "via_langgraph_server": False
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
                # For localhost, LangSmith Studio may have CORS issues
                # Format: https://smith.langchain.com/studio/?baseUrl={server_url}&thread={thread_id}&graph={graph_id}
                
                # Check if server URL is localhost - may need ngrok or local access
                if "localhost" in langgraph_server_url or "127.0.0.1" in langgraph_server_url:
                    # For localhost, ensure we use localhost (not 0.0.0.0) for browser access
                    local_url = langgraph_server_url.replace("0.0.0.0", "localhost").replace("127.0.0.1", "localhost")
                    
                    agent_chat_url = (
                        f"https://smith.langchain.com/studio/"
                        f"?baseUrl={local_url}"
                        f"&thread={thread_id}"
                        f"&graph=agentic_workflow"
                    )
                    instructions = (
                        "Opening LangSmith Studio with local server.\n\n"
                        "✅ LOCALHOST ACCESS:\n"
                        "• Using: http://localhost:2024\n"
                        "• Make sure LangGraph server is running: docker-compose ps langgraph-server\n"
                        "• Use Chrome or Firefox (Safari blocks HTTP localhost)\n\n"
                        "⚠️ IF YOU SEE 'Failed to fetch':\n"
                        "• Browser may block cross-origin requests to localhost\n"
                        "• Try Chrome/Firefox instead of Safari\n"
                        "• Verify server is running: curl http://localhost:2024/assistants\n"
                        "• Traces only exist if execution ran via LangGraph server (not Celery)\n\n"
                        "ALTERNATIVES:\n"
                        "• Use ngrok for public tunnel: ngrok http 2024\n"
                        "• Use local Agent Chat UI: cd cti-agent-chat && pnpm dev\n"
                        "• View database details with 'View' button instead"
                    )
                else:
                    # Public URL should work
                    agent_chat_url = (
                        f"https://smith.langchain.com/studio/"
                        f"?baseUrl={langgraph_server_url}"
                    f"&thread={thread_id}"
                    f"&graph=agentic_workflow"
                )
                    instructions = (
                        "Opening LangSmith Studio. Important notes:\n"
                        "• Traces only appear if executions ran through the LangGraph server\n"
                        "• Most executions run directly via Celery/Python, so traces may not exist\n"
                        "• If no traces appear, the execution wasn't captured in LangSmith"
                    )
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
async def trigger_workflow_for_article(request: Request, article_id: int, use_langgraph_server: bool = Query(False)):
    """
    Manually trigger agentic workflow for an article.
    
    Args:
        use_langgraph_server: If True, uses LangGraph server API (creates traces).
                             If False, uses direct Celery execution (no traces, faster).
    """
    try:
        import os
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
                
                if use_langgraph_server and execution:
                    langgraph_server_url = os.getenv("LANGGRAPH_SERVER_URL", "http://localhost:2024")
                    thread_id = f"workflow_exec_{execution.id}"
                    
                    # Try LangGraph server API
                    logger.info(f"Attempting to connect to LangGraph server at {langgraph_server_url}")
                    success = await _trigger_via_langgraph_server(
                        article_id,
                        execution.id,
                        langgraph_server_url,
                        thread_id
                    )
                    
                    # Fallback: try localhost if service name failed (for local dev)
                    if not success and langgraph_server_url != "http://localhost:2024":
                        logger.info(f"Service name connection failed, trying localhost fallback")
                        success = await _trigger_via_langgraph_server(
                            article_id,
                            execution.id,
                            "http://localhost:2024",
                            thread_id
                        )
                    
                    if success:
                        # Update execution status
                        execution.status = 'running'
                        execution.started_at = datetime.utcnow()
                        execution.current_step = 'junk_filter'
                        db_session.commit()
                        
                        return {
                            "success": True,
                            "message": f"Workflow triggered via LangGraph server for article {article_id} (creates traces)",
                            "execution_id": execution.id,
                            "article_id": article_id,
                            "via_langgraph_server": True
                        }
                    else:
                        # Fail with error instead of falling back
                        execution.status = 'failed'
                        execution.error_message = f"LangGraph server unavailable at {langgraph_server_url}"
                        db_session.commit()
                        
                        raise HTTPException(
                            status_code=503,
                            detail=f"LangGraph server unavailable at {langgraph_server_url}. Make sure the server is running on port 2024."
                        )
                
                return {
                    "success": True,
                    "message": f"Workflow triggered for article {article_id}",
                    "execution_id": execution.id if execution else None,
                    "article_id": article_id,
                    "via_langgraph_server": False
                }
            else:
                # Check why it failed (hunt score threshold check is DISABLED)
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                if not article:
                    raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
                
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
                
                # Should not reach here if trigger_workflow logic is correct
                # But if it does, it's not a hunt score issue (threshold check disabled)
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to trigger workflow for article {article_id} (unknown reason)"
                )
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering workflow for article {article_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

