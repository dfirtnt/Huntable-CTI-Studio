"""
API routes for agentic workflow execution monitoring.
"""

import logging
import asyncio
import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from datetime import datetime, timedelta

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable, AppSettingsTable
from src.workflows.status_utils import extract_termination_info
from src.utils.langfuse_client import get_langfuse_trace_id_for_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# Singleton DatabaseManager instance to prevent connection pool exhaustion
_db_manager: Optional[DatabaseManager] = None

def get_db_manager() -> DatabaseManager:
    """Get or create singleton DatabaseManager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def calculate_extraction_counts(extraction_result: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """
    Derive observable counts from extract agent results.
    Prefers explicit subresult counts; falls back to counting observables by type.
    """
    keys = ["cmdline", "process_lineage", "registry_keys", "sigma_queries", "event_ids"]
    counts = {key: 0 for key in keys}
    
    if not extraction_result or not isinstance(extraction_result, dict):
        return counts
    
    subresults = extraction_result.get("subresults", {})
    if isinstance(subresults, dict):
        for key in keys:
            sub = subresults.get(key, {})
            if isinstance(sub, dict):
                sub_count = sub.get("count")
                if isinstance(sub_count, int):
                    counts[key] = sub_count
                    continue
                items = sub.get("items")
                if isinstance(items, list):
                    counts[key] = len(items)
    
    # Only fall back to observables when we don't already have a positive count
    observables = extraction_result.get("observables", [])
    if isinstance(observables, list):
        fallback_counts: Dict[str, int] = {}
        for obs in observables:
            if isinstance(obs, dict):
                obs_type = obs.get("type")
                if obs_type in keys:
                    fallback_counts[obs_type] = fallback_counts.get(obs_type, 0) + 1
        for key in keys:
            if counts[key] == 0 and key in fallback_counts:
                counts[key] = fallback_counts[key]
    
    return counts


class ExecutionResponse(BaseModel):
    """Response model for workflow execution."""
    id: int
    article_id: int
    article_title: Optional[str]
    article_url: Optional[str]
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
    termination_reason: Optional[str] = None
    termination_details: Optional[Dict[str, Any]] = None
    extraction_counts: Dict[str, int] = Field(default_factory=dict)


class ExecutionDetailResponse(ExecutionResponse):
    """Detailed response with step results."""
    ranking_reasoning: Optional[str]
    junk_filter_result: Optional[Dict[str, Any]]
    extraction_result: Optional[Dict[str, Any]]
    sigma_rules: Optional[List[Dict[str, Any]]]
    similarity_results: Optional[List[Dict[str, Any]]]
    error_log: Optional[Dict[str, Any]]
    queued_rules_count: Optional[int] = 0
    queued_rule_ids: Optional[List[int]] = None  # IDs of queued rules for linking
    article_content: Optional[str] = None  # Full article content for showing inputs
    article_content_preview: Optional[str] = None  # Preview (first 500 chars)


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
    limit: int = 500
):
    """List workflow executions with accurate counts."""
    try:
        db_manager = get_db_manager()
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
                term_reason, term_details = extract_termination_info(execution.error_log)
                
                result.append(ExecutionResponse(
                    id=execution.id,
                    article_id=execution.article_id,
                    article_title=article.title if article else None,
                    article_url=article.canonical_url if article else None,
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
                    termination_reason=term_reason,
                    termination_details=term_details,
                    extraction_counts=calculate_extraction_counts(execution.extraction_result)
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
        db_manager = get_db_manager()
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
            
            # Get article title and URL
            article = db_session.query(ArticleTable).filter(ArticleTable.id == execution.article_id).first()
            
            # Get queued rules for this execution
            from src.database.models import SigmaRuleQueueTable
            queued_rules = db_session.query(SigmaRuleQueueTable).filter(
                SigmaRuleQueueTable.workflow_execution_id == execution.id
            ).all()
            queued_count = len(queued_rules)
            queued_rule_ids = [rule.id for rule in queued_rules]
            
            # Get article content for displaying inputs
            article_content = article.content if article else None
            article_content_preview = article_content[:500] + '...' if article_content and len(article_content) > 500 else article_content
            term_reason, term_details = extract_termination_info(execution.error_log)
            
            return ExecutionDetailResponse(
                id=execution.id,
                article_id=execution.article_id,
                article_title=article.title if article else None,
                article_url=article.canonical_url if article else None,
                status=execution.status,
                current_step=execution.current_step,
                ranking_score=execution.ranking_score,
                ranking_reasoning=execution.ranking_reasoning,
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
                error_log=execution.error_log,
                queued_rules_count=queued_count,
                queued_rule_ids=queued_rule_ids,
                article_content=article_content,
                article_content_preview=article_content_preview,
                termination_reason=term_reason,
                termination_details=term_details,
                extraction_counts=calculate_extraction_counts(execution.extraction_result)
            )
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/cleanup-stale")
async def cleanup_stale_executions(
    request: Request,
    max_age_hours: float = Query(1.0, description="Maximum age in hours for running executions to be considered stale")
):
    """
    Mark stale running or pending executions as failed.
    
    Finds all executions with status='running' or 'pending' that are older than max_age_hours
    and marks them as failed with an appropriate error message.
    """
    try:
        db_manager = get_db_manager()
        db_session = db_manager.get_session()
        
        try:
            # Calculate cutoff time (convert hours to timedelta)
            cutoff_time = datetime.utcnow() - timedelta(hours=float(max_age_hours))
            
            # Find stale running or pending executions
            # Use started_at if available, otherwise fall back to created_at
            stale_executions = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.status.in_(['running', 'pending'])
            ).filter(
                or_(
                    and_(
                        AgenticWorkflowExecutionTable.started_at.isnot(None),
                        AgenticWorkflowExecutionTable.started_at < cutoff_time
                    ),
                    and_(
                        AgenticWorkflowExecutionTable.started_at.is_(None),
                        AgenticWorkflowExecutionTable.created_at < cutoff_time
                    )
                )
            ).all()
            
            count = 0
            for execution in stale_executions:
                original_status = execution.status
                execution.status = 'failed'
                execution.error_message = (
                    execution.error_message or 
                    f"Execution marked as failed due to timeout ({original_status} for more than {max_age_hours} hour(s))"
                )
                execution.completed_at = datetime.utcnow()
                count += 1
            
            if count > 0:
                db_session.commit()
                logger.info(f"Marked {count} stale execution(s) as failed")
                return {
                    "success": True,
                    "message": f"Marked {count} stale execution(s) as failed",
                    "count": count
                }
            else:
                return {
                    "success": True,
                    "message": "No stale executions found",
                    "count": 0
                }
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error cleaning up stale executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}/stream")
async def stream_execution_updates(execution_id: int):
    """
    Server-Sent Events (SSE) endpoint for streaming real-time execution updates.
    
    Streams:
    - Current step changes
    - Status updates
    - LLM chat completions (requests/responses)
    - Error messages
    - Progress indicators
    """
    async def event_generator():
        db_manager = get_db_manager()  # Use singleton to prevent connection pool exhaustion
        last_step = None
        last_status = None
        last_error_log = None
        last_ranking_score = None  # Track if we've already sent the ranking score
        
        try:
            while True:
                db_session = db_manager.get_session()
                try:
                    execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                        AgenticWorkflowExecutionTable.id == execution_id
                    ).first()
                    
                    if not execution:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Execution not found'})}\n\n"
                        break
                    
                    # Check for updates
                    current_step = execution.current_step
                    current_status = execution.status
                    current_error_log = execution.error_log
                    current_ranking_score = execution.ranking_score
                    
                    # Send step update
                    if current_step != last_step:
                        last_step = current_step
                        yield f"data: {json.dumps({'type': 'step', 'step': current_step, 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                        
                        # Include ranking score with step update if available and not yet sent
                        if current_ranking_score is not None and last_ranking_score is None:
                            yield f"data: {json.dumps({'type': 'ranking', 'score': current_ranking_score, 'reasoning': execution.ranking_reasoning, 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                            last_ranking_score = current_ranking_score
                    
                    # Send status update
                    if current_status != last_status:
                        last_status = current_status
                        yield f"data: {json.dumps({'type': 'status', 'status': current_status, 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                        
                        # If completed or failed, send final update and close
                        if current_status in ['completed', 'failed']:
                            yield f"data: {json.dumps({'type': 'complete', 'status': current_status, 'error_message': execution.error_message, 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                            break
                    
                    # Send LLM interaction updates from error_log
                    if current_error_log and current_error_log != last_error_log:
                        # Normalize current_error_log to dict if it's not already
                        if not isinstance(current_error_log, dict):
                            current_error_log = {}
                        
                        # Normalize last_error_log to dict if it's not already
                        if last_error_log is None or not isinstance(last_error_log, dict):
                            last_error_log = {}
                        
                        # Check for LLM interactions in each agent's error_log entry
                        for agent_name in ['rank_article', 'extract_agent', 'generate_sigma', 'os_detection']:
                            agent_log = current_error_log.get(agent_name, {})
                            last_agent_log = last_error_log.get(agent_name, {})
                            
                            # Ensure agent_log is a dict
                            if not isinstance(agent_log, dict):
                                agent_log = {}
                            if not isinstance(last_agent_log, dict):
                                last_agent_log = {}
                            
                            # Check for conversation_log (Rank, Extract, SIGMA, etc.)
                            if 'conversation_log' in agent_log:
                                conversation_log = agent_log['conversation_log']
                                last_conversation_log = last_agent_log.get('conversation_log', [])
                                
                                if conversation_log and isinstance(conversation_log, list):
                                    # Only send new entries (entries not in last_error_log)
                                    for entry in conversation_log:
                                        # Check if this entry is new
                                        # For extract_agent: use agent name + items_count as unique key
                                        # For other agents: use attempt number
                                        is_new = True
                                        if isinstance(last_conversation_log, list):
                                            for last_entry in last_conversation_log:
                                                if isinstance(last_entry, dict) and isinstance(entry, dict):
                                                    # Check by attempt number (for rank_article, generate_sigma)
                                                    if last_entry.get('attempt') is not None and entry.get('attempt') is not None:
                                                        if last_entry.get('attempt') == entry.get('attempt'):
                                                            is_new = False
                                                            break
                                                    # Check by agent name + items_count (for extract_agent sub-agents)
                                                    elif agent_name == 'extract_agent':
                                                        if (last_entry.get('agent') == entry.get('agent') and 
                                                            last_entry.get('items_count') == entry.get('items_count')):
                                                            is_new = False
                                                            break
                                                    # Fallback: if both have no attempt and no agent, compare by index
                                                    elif (last_entry.get('attempt') is None and entry.get('attempt') is None and
                                                          last_entry.get('agent') is None and entry.get('agent') is None):
                                                        # Same entry structure - consider duplicate
                                                        is_new = False
                                                        break
                                        
                                        if is_new and isinstance(entry, dict):
                                            # For extract_agent sub-agents, use the sub-agent name
                                            display_agent = entry.get('agent', agent_name) if agent_name == 'extract_agent' else agent_name
                                            yield f"data: {json.dumps({'type': 'llm_interaction', 'agent': display_agent, 'messages': entry.get('messages', []), 'response': entry.get('llm_response', ''), 'attempt': entry.get('attempt', 1), 'score': entry.get('score'), 'discrete_huntables_count': entry.get('discrete_huntables_count') or entry.get('items_count'), 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                        
                        # Check for QA results (moved outside agent loop for efficiency)
                        if 'qa_results' in current_error_log:
                            qa_results = current_error_log['qa_results']
                            last_qa_results = last_error_log.get('qa_results', {})
                            
                            # Ensure qa_results is a dict before iterating
                            if isinstance(qa_results, dict) and isinstance(last_qa_results, dict):
                                for qa_agent_name, qa_result in qa_results.items():
                                    # Ensure qa_result is a dict
                                    if not isinstance(qa_result, dict):
                                        continue
                                    
                                    # Map QA agent names to workflow agent names
                                    agent_mapping = {
                                        'RankAgent': 'rank_article',
                                        'ExtractAgent': 'extract_agent',
                                        'SigmaAgent': 'generate_sigma',
                                        'OSDetectionAgent': 'os_detection',
                                        # Extraction sub-agents
                                        'CmdlineExtract': 'extract_agent',
                                        'CmdLineQA': 'extract_agent',
                                        'SigExtract': 'extract_agent',
                                        'SigQA': 'extract_agent',
                                        'EventCodeExtract': 'extract_agent',
                                        'EventCodeQA': 'extract_agent',
                                        'ProcTreeExtract': 'extract_agent',
                                        'ProcTreeQA': 'extract_agent',
                                        'RegExtract': 'extract_agent',
                                        'RegQA': 'extract_agent'
                                    }
                                    mapped_agent_name = agent_mapping.get(qa_agent_name, qa_agent_name)
                                    
                                    # Only send if this QA result is new or updated
                                    last_qa_result = last_qa_results.get(qa_agent_name)
                                    if not isinstance(last_qa_result, dict) or last_qa_result.get('verdict') != qa_result.get('verdict'):
                                        yield f"data: {json.dumps({'type': 'qa_result', 'agent': mapped_agent_name, 'verdict': qa_result.get('verdict'), 'summary': qa_result.get('summary'), 'issues': qa_result.get('issues', []), 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                        
                        # Update last_error_log after processing
                        last_error_log = json.loads(json.dumps(current_error_log)) if current_error_log else {}
                    
                    # Send ranking score only once when it first becomes available
                    if current_ranking_score is not None and last_ranking_score is None:
                        yield f"data: {json.dumps({'type': 'ranking', 'score': current_ranking_score, 'reasoning': execution.ranking_reasoning, 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                        last_ranking_score = current_ranking_score
                    
                finally:
                    db_session.close()
                
                # Poll every 1 second
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in execution stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.post("/executions/trigger-stuck")
async def trigger_stuck_executions(request: Request):
    """
    Manually trigger all pending workflow executions.
    
    This bypasses Celery and directly runs the workflow for any stuck pending executions.
    """
    try:
        import asyncio
        from src.workflows.agentic_workflow import run_workflow
        
        db_manager = get_db_manager()
        db_session = db_manager.get_session()
        
        try:
            # Find all pending executions
            pending_executions = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.status == 'pending'
            ).order_by(AgenticWorkflowExecutionTable.created_at.asc()).all()
            
            if not pending_executions:
                return {
                    "success": True,
                    "message": "No pending executions found",
                    "count": 0,
                    "results": []
                }
            
            results = []
            for execution in pending_executions:
                try:
                    logger.info(f"Triggering stuck execution {execution.id} for article {execution.article_id}")
                    result = await run_workflow(execution.article_id, db_session)
                    
                    results.append({
                        'execution_id': execution.id,
                        'article_id': execution.article_id,
                        'success': result.get('success', False),
                        'message': result.get('message', 'Workflow completed')
                    })
                    
                except Exception as e:
                    logger.error(f"Error triggering execution {execution.id}: {e}", exc_info=True)
                    results.append({
                        'execution_id': execution.id,
                        'article_id': execution.article_id,
                        'success': False,
                        'message': str(e)
                    })
            
            successful = sum(1 for r in results if r['success'])
            failed = len(results) - successful
            
            return {
                "success": True,
                "message": f"Triggered {len(results)} execution(s): {successful} successful, {failed} failed",
                "count": len(results),
                "successful": successful,
                "failed": failed,
                "results": results
            }
            
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error triggering stuck executions: {e}", exc_info=True)
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
        db_manager = get_db_manager()
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
            # LangGraph server requires thread IDs to be UUIDs, not strings
            import uuid
            langgraph_thread_id = str(uuid.uuid4())
            
            async with httpx.AsyncClient(timeout=60.0) as client:
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
                
                # LangGraph dev server requires two-step process:
                # Step 1: POST /threads to create thread
                # Step 2: POST /threads/{thread_id}/runs to submit workflow run
                try:
                    # Step 1: Create thread
                    create_thread_url = f"{langgraph_server_url}/threads"
                    create_response = await client.post(
                        create_thread_url,
                        json={
                            "assistant_id": "agentic_workflow"
                        }
                    )
                    
                    if create_response.status_code not in [200, 201]:
                        logger.warning(f"Thread creation returned {create_response.status_code}: {create_response.text[:200]}")
                        return False
                    
                    thread_data = create_response.json()
                    # Extract thread_id from response
                    if isinstance(thread_data, dict):
                        langgraph_thread_id = thread_data.get('thread_id') or thread_data.get('id') or langgraph_thread_id
                    logger.info(f"Created LangGraph thread: {langgraph_thread_id}")
                    
                    # Step 2: Submit run to thread
                    url = f"{langgraph_server_url}/threads/{langgraph_thread_id}/runs"
                    response = await client.post(
                        url,
                        json={
                            "assistant_id": "agentic_workflow",  # Graph name
                            "input": workflow_input,  # Direct state, not nested
                            "stream": False
                        }
                    )
                    
                    if response.status_code in [200, 201]:
                        run_data = response.json()
                        run_id = run_data.get('run_id') if isinstance(run_data, dict) else None
                        logger.info(f"Workflow triggered via LangGraph server for execution {execution_id}, thread {langgraph_thread_id}, run {run_id}")
                        return True
                    else:
                        logger.warning(f"Run submission returned {response.status_code}: {response.text[:200]}")
                        return False
                    
                except httpx.ConnectError:
                    logger.warning(f"Cannot connect to LangGraph server at {langgraph_server_url}")
                    return False
                except httpx.TimeoutException:
                    logger.warning(f"Timeout connecting to LangGraph server at {langgraph_server_url}")
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
                             If False, uses direct workflow execution with Langfuse tracing (if enabled).
    """
    try:
        import os
        import asyncio
        from src.worker.celery_app import trigger_agentic_workflow
        from src.workflows.agentic_workflow import run_workflow
        
        db_manager = get_db_manager()
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
                # "Retry (Trace)" - Use direct execution with Langfuse tracing
                # This ensures Langfuse traces are always created when using trace mode
                logger.info(f"Running workflow directly with Langfuse tracing for execution {new_execution.id}")
                # Don't set status to 'running' here - let run_workflow do it
                # run_workflow expects to find a 'pending' execution and will set it to 'running'
                
                # Run workflow directly (this will create Langfuse traces if enabled)
                result = await run_workflow(execution.article_id, db_session)
                
                return {
                    "success": True,
                    "message": f"Retry completed for execution {execution_id} (direct execution with Langfuse tracing)",
                    "new_execution_id": new_execution.id,
                    "via_langgraph_server": False,
                    "via_direct_execution": True,
                    "workflow_result": result
                }
            else:
                # Regular "Retry" - Use Celery (uses Langfuse if enabled, but async)
                trigger_agentic_workflow.delay(execution.article_id)
                
                return {
                    "success": True,
                    "message": f"Retry initiated for execution {execution_id} (via Celery, Langfuse tracing if enabled)",
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


@router.post("/executions/{execution_id}/cancel")
async def cancel_workflow_execution(request: Request, execution_id: int):
    """
    Cancel a running or pending workflow execution.
    
    Marks the execution as failed with a cancellation message.
    Note: This only marks the execution as cancelled in the database.
    The actual Celery task may continue running until it completes or times out.
    """
    try:
        db_manager = get_db_manager()
        db_session = db_manager.get_session()
        
        try:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == execution_id
            ).first()
            
            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")
            
            if execution.status not in ['running', 'pending']:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Cannot cancel execution with status '{execution.status}'. Only running or pending executions can be cancelled."
                )
            
            # Mark as failed with cancellation message
            execution.status = 'failed'
            execution.error_message = f"Execution cancelled by user (was {execution.status})"
            execution.completed_at = datetime.utcnow()
            db_session.commit()
            
            logger.info(f"Execution {execution_id} cancelled by user")
            
            return {
                "success": True,
                "message": f"Execution {execution_id} cancelled successfully",
                "execution_id": execution_id
            }
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling workflow execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_langfuse_setting(db_session: Session, key: str, env_key: str, default: Optional[str] = None) -> Optional[str]:
    """Get Langfuse setting from database first, then fall back to environment variable.
    
    Priority: database setting > environment variable > default
    """
    # Check database setting first (highest priority - user preference from UI)
    try:
        setting = db_session.query(AppSettingsTable).filter(
            AppSettingsTable.key == key
        ).first()
        
        if setting and setting.value:
            logger.info(f"✅ Using {key} from database setting (value length: {len(setting.value)})")
            return setting.value
        else:
            logger.debug(f"⚠️ No database setting found for {key}")
    except Exception as e:
        logger.warning(f"❌ Could not fetch {key} from database: {e}")
    
    # Fall back to environment variable (second priority)
    import os
    env_value = os.getenv(env_key)
    if env_value:
        logger.info(f"✅ Using {env_key} from environment (value length: {len(env_value)})")
        return env_value
    else:
        logger.debug(f"⚠️ No environment variable found for {env_key}")
    
    # Return default if provided
    if default:
        logger.debug(f"📝 Using default value for {key}: {default}")
    return default


@router.get("/executions/{execution_id}/debug-info")
async def get_workflow_debug_info(request: Request, execution_id: int):
    """Get debug information for opening execution in Agent Chat UI."""
    import os
    try:
        db_manager = get_db_manager()
        db_session = db_manager.get_session()
        
        try:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == execution_id
            ).first()
            
            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")
            
            # Get LangGraph server URL from environment or config
            langgraph_server_url = os.getenv("LANGGRAPH_SERVER_URL", "http://localhost:2024")
            
            # Check if Langfuse is configured (preferred for debugging)
            # Priority: database setting > environment variable > default
            langfuse_host = _get_langfuse_setting(
                db_session, 
                "LANGFUSE_HOST", 
                "LANGFUSE_HOST", 
                "https://us.cloud.langfuse.com"
            )
            langfuse_public_key = _get_langfuse_setting(
                db_session,
                "LANGFUSE_PUBLIC_KEY",
                "LANGFUSE_PUBLIC_KEY"
            )
            langfuse_project_id = _get_langfuse_setting(
                db_session,
                "LANGFUSE_PROJECT_ID",
                "LANGFUSE_PROJECT_ID"
            )
            
            # Build session/trace identifiers
            import hashlib
            session_id = f"workflow_exec_{execution_id}"
            trace_id_hash = hashlib.md5(session_id.encode()).hexdigest()
            resolved_trace_id = None
            trace_lookup_used = False

            # Prefer persisted trace_id from execution.error_log if present
            try:
                if execution.error_log and isinstance(execution.error_log, dict):
                    persisted_trace_id = execution.error_log.get("langfuse_trace_id")
                    if persisted_trace_id:
                        resolved_trace_id = persisted_trace_id
                        trace_lookup_used = True
            except Exception:
                pass

            if not resolved_trace_id and langfuse_public_key:
                actual_trace_id = get_langfuse_trace_id_for_session(session_id)
                if actual_trace_id:
                    resolved_trace_id = actual_trace_id
                    trace_lookup_used = True

            # Debug logging
            logger.debug(
                "Langfuse debug info - host: %s, public_key present: %s, project_id: %s, "
                "resolved_trace_id: %s, trace_id_hash: %s, session_id: %s",
                langfuse_host,
                bool(langfuse_public_key),
                langfuse_project_id,
                resolved_trace_id,
                trace_id_hash,
                session_id
            )

            # Always generate Langfuse trace URL (traces may exist even if keys aren't currently configured)
            # Normalize host URL (remove trailing slash)
            langfuse_host = langfuse_host.rstrip('/') if langfuse_host else "https://us.cloud.langfuse.com"

            # Prefer direct trace URL when resolved; otherwise fall back to session filter search
            if resolved_trace_id:
                if langfuse_project_id:
                    agent_chat_url = f"{langfuse_host}/project/{langfuse_project_id}/traces/{resolved_trace_id}"
                else:
                    agent_chat_url = f"{langfuse_host}/traces/{resolved_trace_id}"
            else:
                import json, urllib.parse
                filters_payload = {
                    "filters": [
                        {"key": "sessionId", "value": session_id}
                    ],
                    "searchQuery": session_id,
                    "searchColumns": ["id", "name", "sessionId"],
                    "orderBy": {
                        "column": "timestamp",
                        "order": "DESC"
                    }
                }
                filters = urllib.parse.quote(json.dumps(filters_payload))
                if langfuse_project_id:
                    agent_chat_url = f"{langfuse_host}/project/{langfuse_project_id}/traces?filters={filters}"
                else:
                    agent_chat_url = f"{langfuse_host}/traces?filters={filters}"

            logger.info(f"🔗 Generated Langfuse trace URL: {agent_chat_url}")
            logger.info(
                "   Trace ID: %s (lookup=%s, hash=%s), Session ID: %s (execution #%s)",
                resolved_trace_id,
                trace_lookup_used,
                trace_id_hash,
                session_id,
                execution_id
            )

            if langfuse_public_key:
                instructions = (
                    "Opening Langfuse trace for execution #{}.\n"
                    "Trace ID: {}\n"
                    "Session ID: {}\n"
                    "Trace ID resolved by searching Langfuse for session_id '{}'."
                ).format(execution_id, resolved_trace_id or "n/a", session_id, session_id)
            else:
                # Warn user that Langfuse may not be configured, but still try to open trace
                logger.warning(
                    f"⚠️ Langfuse keys not configured for execution {execution_id}. "
                    f"Opening trace URL anyway - trace may exist if execution ran with Langfuse enabled. "
                    f"Configure Langfuse in Settings page or set LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY in environment."
                )
                instructions = (
                    "Opening Langfuse trace for execution #{}.\n"
                    "Trace ID: {}\n"
                    "Session ID: {}\n"
                    "Note: Langfuse keys not configured. Trace will only exist if execution ran with Langfuse tracing enabled. "
                    "If you get a 404, search for session_id '{}' in Langfuse UI."
                ).format(execution_id, trace_id_hash, session_id, session_id)

            return {
                "execution_id": execution_id,
                "article_id": execution.article_id,
                "langgraph_server_url": langgraph_server_url,
                "agent_chat_url": agent_chat_url,
                "trace_id": resolved_trace_id,
                "session_id": session_id,
                "thread_id": trace_id_hash,
                "graph_id": "agentic_workflow",
                "langfuse_host": langfuse_host,
                "langfuse_project_id": langfuse_project_id,
                "search_url": (
                    f"{langfuse_host}/project/{langfuse_project_id}/traces?search={session_id}"
                    if langfuse_project_id else f"{langfuse_host}/traces?search={session_id}"
                ),
                "instructions": instructions,
                "uses_langsmith": bool(langfuse_public_key)  # Keep field name for backwards compatibility
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
        
        db_manager = get_db_manager()
        db_session = db_manager.get_session()
        
        try:
            trigger_service = WorkflowTriggerService(db_session)
            
            # Check for existing active executions BEFORE triggering
            # Also check for stuck pending executions (older than 5 minutes)
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(minutes=5)
            
            existing_execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.article_id == article_id,
                AgenticWorkflowExecutionTable.status.in_(['pending', 'running'])
            ).first()
            
            if existing_execution:
                # Check if it's a stuck pending execution (older than 5 minutes and never started)
                if (existing_execution.status == 'pending' and 
                    existing_execution.created_at < cutoff_time and 
                    existing_execution.started_at is None):
                    logger.warning(
                        f"Found stuck pending execution {existing_execution.id} for article {article_id} "
                        f"(created {existing_execution.created_at}, never started). Marking as failed."
                    )
                    existing_execution.status = 'failed'
                    existing_execution.error_message = (
                        existing_execution.error_message or 
                        f"Execution stuck in pending status for more than 5 minutes (created: {existing_execution.created_at})"
                    )
                    existing_execution.completed_at = datetime.utcnow()
                    db_session.commit()
                    # Continue to create new execution
                else:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Article {article_id} already has an active workflow execution (ID: {existing_execution.id})"
                    )
            
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
                # trigger_workflow returned False - this should not happen if we checked above
                # But handle it gracefully
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                if not article:
                    raise HTTPException(status_code=404, detail=f"Article {article_id} not found")
                
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
