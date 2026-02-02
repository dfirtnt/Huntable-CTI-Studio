"""
API routes for agentic workflow execution monitoring.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, AppSettingsTable, ArticleTable
from src.services.eval_bundle_service import EvalBundleService
from src.utils.langfuse_client import get_langfuse_trace_id_for_session
from src.workflows.status_utils import extract_termination_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# Singleton DatabaseManager instance to prevent connection pool exhaustion
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """Get or create singleton DatabaseManager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def calculate_extraction_counts(extraction_result: dict[str, Any] | None) -> dict[str, int]:
    """
    Derive observable counts from extract agent results.
    Prefers explicit subresult counts; falls back to counting observables by type.
    """
    keys = ["cmdline", "process_lineage"]
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
        fallback_counts: dict[str, int] = {}
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
    article_title: str | None
    article_url: str | None
    status: str
    current_step: str | None
    ranking_score: float | None
    config_snapshot: dict[str, Any] | None
    error_message: str | None
    retry_count: int
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str
    termination_reason: str | None = None
    termination_details: dict[str, Any] | None = None
    extraction_counts: dict[str, int] = Field(default_factory=dict)


class ExecutionDetailResponse(ExecutionResponse):
    """Detailed response with step results."""

    ranking_reasoning: str | None
    junk_filter_result: dict[str, Any] | None
    extraction_result: dict[str, Any] | None
    sigma_rules: list[dict[str, Any]] | None
    similarity_results: list[dict[str, Any]] | None
    error_log: dict[str, Any] | None
    queued_rules_count: int | None = 0
    queued_rule_ids: list[int] | None = None  # IDs of queued rules for linking
    article_content: str | None = None  # Full article content for showing inputs
    article_content_preview: str | None = None  # Preview (first 500 chars)


class ExecutionListResponse(BaseModel):
    """Response model for execution list with counts."""

    executions: list[ExecutionResponse]
    total: int
    running: int
    completed: int
    failed: int
    pending: int


@router.get("/executions", response_model=ExecutionListResponse)
async def list_workflow_executions(
    request: Request, article_id: int | None = None, status: str | None = None, limit: int = 500
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
            running = base_query.filter(AgenticWorkflowExecutionTable.status == "running").count()
            completed = base_query.filter(AgenticWorkflowExecutionTable.status == "completed").count()
            failed = base_query.filter(AgenticWorkflowExecutionTable.status == "failed").count()
            pending = base_query.filter(AgenticWorkflowExecutionTable.status == "pending").count()

            # Get filtered executions
            executions = query.order_by(AgenticWorkflowExecutionTable.created_at.desc()).limit(limit).all()

            result = []
            for execution in executions:
                # Get article title
                article = db_session.query(ArticleTable).filter(ArticleTable.id == execution.article_id).first()
                term_reason, term_details = extract_termination_info(execution.error_log)

                # Convert timestamps to local time if they're timezone-aware
                def to_local_iso(dt):
                    if dt is None:
                        return None
                    if dt.tzinfo is not None:
                        # Convert to local time and remove timezone info
                        return dt.astimezone().replace(tzinfo=None).isoformat()
                    # Already naive, assume it's in local time
                    return dt.isoformat()

                result.append(
                    ExecutionResponse(
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
                        started_at=to_local_iso(execution.started_at),
                        completed_at=to_local_iso(execution.completed_at),
                        created_at=to_local_iso(execution.created_at),
                        updated_at=to_local_iso(execution.updated_at),
                        termination_reason=term_reason,
                        termination_details=term_details,
                        extraction_counts=calculate_extraction_counts(execution.extraction_result),
                    )
                )

            return ExecutionListResponse(
                executions=result, total=total, running=running, completed=completed, failed=failed, pending=pending
            )
        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Error listing workflow executions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions/{execution_id}", response_model=ExecutionDetailResponse)
async def get_workflow_execution(request: Request, execution_id: int):
    """Get detailed workflow execution information."""
    try:
        db_manager = get_db_manager()
        db_session = db_manager.get_session()

        try:
            # Query with fresh session to ensure we get latest data
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")

            # Explicitly expire and refresh to bypass any session cache
            db_session.expire(execution)
            db_session.refresh(execution)

            # Get article title and URL
            article = db_session.query(ArticleTable).filter(ArticleTable.id == execution.article_id).first()

            # Get queued rules for this execution
            from src.database.models import SigmaRuleQueueTable

            queued_rules = (
                db_session.query(SigmaRuleQueueTable)
                .filter(SigmaRuleQueueTable.workflow_execution_id == execution.id)
                .all()
            )
            queued_count = len(queued_rules)
            queued_rule_ids = [rule.id for rule in queued_rules]

            # Get article content for displaying inputs
            article_content = article.content if article else None
            article_content_preview = (
                article_content[:500] + "..." if article_content and len(article_content) > 500 else article_content
            )
            term_reason, term_details = extract_termination_info(execution.error_log)

            # Convert timestamps to local time if they're timezone-aware
            def to_local_iso(dt):
                if dt is None:
                    return None
                if dt.tzinfo is not None:
                    # Convert to local time and remove timezone info
                    return dt.astimezone().replace(tzinfo=None).isoformat()
                # Already naive, assume it's in local time
                return dt.isoformat()

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
                started_at=to_local_iso(execution.started_at),
                completed_at=to_local_iso(execution.completed_at),
                created_at=to_local_iso(execution.created_at),
                updated_at=to_local_iso(execution.updated_at),
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
                extraction_counts=calculate_extraction_counts(execution.extraction_result),
            )
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow execution: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/executions/cleanup-stale")
async def cleanup_stale_executions(
    request: Request,
    max_age_hours: float = Query(1.0, description="Maximum age in hours for running executions to be considered stale"),
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
            cutoff_time = datetime.now() - timedelta(hours=float(max_age_hours))

            # Find stale running or pending executions
            # Use started_at if available, otherwise fall back to created_at
            stale_executions = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.status.in_(["running", "pending"]))
                .filter(
                    or_(
                        and_(
                            AgenticWorkflowExecutionTable.started_at.isnot(None),
                            AgenticWorkflowExecutionTable.started_at < cutoff_time,
                        ),
                        and_(
                            AgenticWorkflowExecutionTable.started_at.is_(None),
                            AgenticWorkflowExecutionTable.created_at < cutoff_time,
                        ),
                    )
                )
                .all()
            )

            count = 0
            for execution in stale_executions:
                original_status = execution.status
                execution.status = "failed"
                execution.error_message = (
                    execution.error_message
                    or f"Execution marked as failed due to timeout ({original_status} for more than {max_age_hours} hour(s))"
                )
                execution.completed_at = datetime.now()
                count += 1

            if count > 0:
                db_session.commit()
                logger.info(f"Marked {count} stale execution(s) as failed")
                return {"success": True, "message": f"Marked {count} stale execution(s) as failed", "count": count}
            return {"success": True, "message": "No stale executions found", "count": 0}
        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Error cleaning up stale executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


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
                    execution = (
                        db_session.query(AgenticWorkflowExecutionTable)
                        .filter(AgenticWorkflowExecutionTable.id == execution_id)
                        .first()
                    )

                    if not execution:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Execution not found'})}\n\n"
                        break

                    # Check for updates
                    current_step = execution.current_step
                    current_status = execution.status
                    current_error_log = execution.error_log
                    current_ranking_score = execution.ranking_score

                    # Send ranking score as soon as it becomes available (independent of step changes)
                    if current_ranking_score is not None and last_ranking_score is None:
                        yield f"data: {json.dumps({'type': 'ranking', 'score': current_ranking_score, 'reasoning': execution.ranking_reasoning, 'timestamp': datetime.now().isoformat()})}\n\n"
                        last_ranking_score = current_ranking_score

                    # Check for step completion markers and emit completion events
                    if current_error_log and isinstance(current_error_log, dict):
                        # Check if extract_agent just completed
                        extract_agent_log = current_error_log.get("extract_agent", {})
                        if isinstance(extract_agent_log, dict) and extract_agent_log.get("completed"):
                            # Emit step completion event (only once per completion)
                            last_extract_log = last_error_log.get("extract_agent", {}) if last_error_log else {}
                            if not isinstance(last_extract_log, dict) or not last_extract_log.get("completed"):
                                yield f"data: {json.dumps({'type': 'step_complete', 'step': 'extract_agent', 'timestamp': extract_agent_log.get('completed_at', datetime.now().isoformat())})}\n\n"

                    # Send step update
                    if current_step != last_step:
                        last_step = current_step
                        yield f"data: {json.dumps({'type': 'step', 'step': current_step, 'timestamp': datetime.now().isoformat()})}\n\n"

                    # Send status update
                    if current_status != last_status:
                        last_status = current_status
                        yield f"data: {json.dumps({'type': 'status', 'status': current_status, 'timestamp': datetime.now().isoformat()})}\n\n"

                        # If completed or failed, send final update and close
                        if current_status in ["completed", "failed"]:
                            yield f"data: {json.dumps({'type': 'complete', 'status': current_status, 'error_message': execution.error_message, 'timestamp': datetime.now().isoformat()})}\n\n"
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
                        for agent_name in ["rank_article", "extract_agent", "generate_sigma", "os_detection"]:
                            agent_log = current_error_log.get(agent_name, {})
                            last_agent_log = last_error_log.get(agent_name, {})

                            # Ensure agent_log is a dict
                            if not isinstance(agent_log, dict):
                                agent_log = {}
                            if not isinstance(last_agent_log, dict):
                                last_agent_log = {}

                            # Check for conversation_log (Rank, Extract, SIGMA, etc.)
                            if "conversation_log" in agent_log:
                                conversation_log = agent_log["conversation_log"]
                                last_conversation_log = last_agent_log.get("conversation_log", [])

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
                                                    if (
                                                        last_entry.get("attempt") is not None
                                                        and entry.get("attempt") is not None
                                                    ):
                                                        if last_entry.get("attempt") == entry.get("attempt"):
                                                            is_new = False
                                                            break
                                                    # Check by agent name + items_count (for extract_agent sub-agents)
                                                    elif agent_name == "extract_agent":
                                                        if last_entry.get("agent") == entry.get(
                                                            "agent"
                                                        ) and last_entry.get("items_count") == entry.get("items_count"):
                                                            is_new = False
                                                            break
                                                    # Fallback: if both have no attempt and no agent, compare by index
                                                    elif (
                                                        last_entry.get("attempt") is None
                                                        and entry.get("attempt") is None
                                                        and last_entry.get("agent") is None
                                                        and entry.get("agent") is None
                                                    ):
                                                        # Same entry structure - consider duplicate
                                                        is_new = False
                                                        break

                                        if is_new and isinstance(entry, dict):
                                            # For extract_agent sub-agents, use the sub-agent name
                                            display_agent = (
                                                entry.get("agent", agent_name)
                                                if agent_name == "extract_agent"
                                                else agent_name
                                            )

                                            # Filter out removed subagents (SigExtract, EventCodeExtract, RegExtract)
                                            removed_agents = {
                                                "SigExtract",
                                                "EventCodeExtract",
                                                "RegExtract",
                                                "SigQA",
                                                "EventCodeQA",
                                                "RegQA",
                                            }
                                            if display_agent in removed_agents:
                                                continue  # Skip displaying removed agents

                                            # Add step context to event - map agent_name to workflow step
                                            step_context = agent_name  # Default to agent_name as step

                                            event_payload = {
                                                "type": "llm_interaction",
                                                "step": step_context,
                                                "agent": display_agent,
                                                "messages": entry.get("messages", []),
                                                "response": entry.get("llm_response", ""),
                                                "attempt": entry.get("attempt", 1),
                                                "score": entry.get("score"),
                                                "discrete_huntables_count": entry.get("discrete_huntables_count")
                                                or entry.get("items_count"),
                                                "timestamp": datetime.now().isoformat(),
                                            }
                                            if entry.get("attention_preprocessor") is not None:
                                                event_payload["attention_preprocessor"] = entry[
                                                    "attention_preprocessor"
                                                ]
                                            yield f"data: {json.dumps(event_payload)}\n\n"

                        # Check for QA results (moved outside agent loop for efficiency)
                        if "qa_results" in current_error_log:
                            qa_results = current_error_log["qa_results"]
                            last_qa_results = last_error_log.get("qa_results", {})

                            # Ensure qa_results is a dict before iterating
                            if isinstance(qa_results, dict) and isinstance(last_qa_results, dict):
                                # Filter out removed agents from QA results
                                removed_agents = {
                                    "SigExtract",
                                    "EventCodeExtract",
                                    "RegExtract",
                                    "SigQA",
                                    "EventCodeQA",
                                    "RegQA",
                                }

                                # Map QA agent names to workflow agent names
                                agent_mapping = {
                                    "RankAgent": "rank_article",
                                    "ExtractAgent": "extract_agent",
                                    "SigmaAgent": "generate_sigma",
                                    "OSDetectionAgent": "os_detection",
                                    # Extraction sub-agents
                                    "CmdlineExtract": "extract_agent",
                                    "CmdLineQA": "extract_agent",
                                    "ProcTreeExtract": "extract_agent",
                                    "ProcTreeQA": "extract_agent",
                                }

                                # Deduplicate by mapped agent name to avoid emitting same result twice
                                # Prefer primary agent names (e.g., "CmdlineExtract") over QA names (e.g., "CmdLineQA")
                                primary_agents = {
                                    "RankAgent",
                                    "ExtractAgent",
                                    "SigmaAgent",
                                    "OSDetectionAgent",
                                    "CmdlineExtract",
                                    "ProcTreeExtract",
                                    "HuntQueriesExtract",
                                }

                                # Track which mapped agents we've already sent in this iteration
                                sent_mapped_agents = set()
                                # Track last sent result by mapped agent name (not qa_agent_name) to prevent duplicates
                                last_sent_by_mapped = {}

                                # First pass: process primary agents
                                for qa_agent_name in primary_agents:
                                    if qa_agent_name not in qa_results or qa_agent_name in removed_agents:
                                        continue

                                    qa_result = qa_results[qa_agent_name]
                                    if not isinstance(qa_result, dict):
                                        continue

                                    mapped_agent_name = agent_mapping.get(qa_agent_name, qa_agent_name)

                                    # Check if we've already sent a result for this mapped agent in this iteration
                                    if mapped_agent_name in sent_mapped_agents:
                                        continue

                                    # Check if this result is different from what we last sent for this mapped agent
                                    # Check all qa_agent_names that map to this mapped_agent_name
                                    last_verdict = None
                                    for check_name, check_result in last_qa_results.items():
                                        if isinstance(check_result, dict):
                                            check_mapped = agent_mapping.get(check_name, check_name)
                                            if check_mapped == mapped_agent_name:
                                                last_verdict = check_result.get("verdict")
                                                break

                                    # Only send if verdict changed or this is first time
                                    if last_verdict != qa_result.get("verdict"):
                                        # Add step context - QA results belong to their parent workflow step
                                        step_context = mapped_agent_name  # QA results are for the workflow step
                                        yield f"data: {json.dumps({'type': 'qa_result', 'step': step_context, 'agent': mapped_agent_name, 'verdict': qa_result.get('verdict'), 'summary': qa_result.get('summary'), 'issues': qa_result.get('issues', []), 'timestamp': datetime.now().isoformat()})}\n\n"
                                        sent_mapped_agents.add(mapped_agent_name)
                                        last_sent_by_mapped[mapped_agent_name] = qa_result.get("verdict")

                                # Second pass: process QA agents only if primary agent wasn't found
                                for qa_agent_name, qa_result in qa_results.items():
                                    # Skip removed agents or already processed primary agents
                                    if qa_agent_name in removed_agents or qa_agent_name in primary_agents:
                                        continue

                                    if not isinstance(qa_result, dict):
                                        continue

                                    mapped_agent_name = agent_mapping.get(qa_agent_name, qa_agent_name)

                                    # Skip if we've already sent a result for this mapped agent
                                    if mapped_agent_name in sent_mapped_agents:
                                        continue

                                    # Check if this result is different from what we last sent for this mapped agent
                                    last_verdict = last_sent_by_mapped.get(mapped_agent_name)
                                    if last_verdict is None:
                                        # Check last_qa_results for any agent that maps to this mapped_agent_name
                                        for check_name, check_result in last_qa_results.items():
                                            if isinstance(check_result, dict):
                                                check_mapped = agent_mapping.get(check_name, check_name)
                                                if check_mapped == mapped_agent_name:
                                                    last_verdict = check_result.get("verdict")
                                                    break

                                    # Only send if verdict changed or this is first time
                                    if last_verdict != qa_result.get("verdict"):
                                        # Add step context - QA results belong to their parent workflow step
                                        step_context = mapped_agent_name  # QA results are for the workflow step
                                        yield f"data: {json.dumps({'type': 'qa_result', 'step': step_context, 'agent': mapped_agent_name, 'verdict': qa_result.get('verdict'), 'summary': qa_result.get('summary'), 'issues': qa_result.get('issues', []), 'timestamp': datetime.now().isoformat()})}\n\n"
                                        sent_mapped_agents.add(mapped_agent_name)
                                        last_sent_by_mapped[mapped_agent_name] = qa_result.get("verdict")

                        # Update last_error_log after processing
                        last_error_log = json.loads(json.dumps(current_error_log)) if current_error_log else {}

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
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/executions/trigger-stuck")
async def trigger_stuck_executions(request: Request):
    """
    Manually trigger all pending workflow executions.

    This bypasses Celery and directly runs the workflow for any stuck pending executions.
    """
    try:
        from src.workflows.agentic_workflow import run_workflow

        db_manager = get_db_manager()
        db_session = db_manager.get_session()

        try:
            # Find all pending executions
            pending_executions = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.status == "pending")
                .order_by(AgenticWorkflowExecutionTable.created_at.asc())
                .all()
            )

            if not pending_executions:
                return {"success": True, "message": "No pending executions found", "count": 0, "results": []}

            results = []
            for execution in pending_executions:
                try:
                    logger.info(f"Triggering stuck execution {execution.id} for article {execution.article_id}")
                    result = await run_workflow(execution.article_id, db_session, execution_id=execution.id)

                    results.append(
                        {
                            "execution_id": execution.id,
                            "article_id": execution.article_id,
                            "success": result.get("success", False),
                            "message": result.get("message", "Workflow completed"),
                        }
                    )

                except Exception as e:
                    logger.error(f"Error triggering execution {execution.id}: {e}", exc_info=True)
                    results.append(
                        {
                            "execution_id": execution.id,
                            "article_id": execution.article_id,
                            "success": False,
                            "message": str(e),
                        }
                    )

            successful = sum(1 for r in results if r["success"])
            failed = len(results) - successful

            return {
                "success": True,
                "message": f"Triggered {len(results)} execution(s): {successful} successful, {failed} failed",
                "count": len(results),
                "successful": successful,
                "failed": failed,
                "results": results,
            }

        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Error triggering stuck executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/executions/{execution_id}/retry")
async def retry_workflow_execution(request: Request, execution_id: int):
    """
    Retry a failed workflow execution.
    """
    try:
        from src.worker.celery_app import trigger_agentic_workflow

        db_manager = get_db_manager()
        db_session = db_manager.get_session()

        try:
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")

            if execution.status not in ["failed", "completed"]:
                raise HTTPException(status_code=400, detail="Can only retry failed or completed executions")

            # Merge old config_snapshot with current active config to ensure rank_agent_enabled is up-to-date
            from src.services.workflow_trigger_service import WorkflowTriggerService

            trigger_service = WorkflowTriggerService(db_session)
            current_config = trigger_service.get_active_config()

            # Start with old snapshot (preserves eval flags, thresholds, etc.)
            new_config_snapshot = execution.config_snapshot.copy() if execution.config_snapshot else {}

            # Update rank_agent_enabled from current active config (if available)
            # CRITICAL: Always use current active config value, not the old snapshot value
            if current_config and hasattr(current_config, "rank_agent_enabled"):
                new_config_snapshot["rank_agent_enabled"] = bool(current_config.rank_agent_enabled)
                logger.info(
                    f"Retry execution {execution_id}: Updated rank_agent_enabled to {new_config_snapshot['rank_agent_enabled']} (was {execution.config_snapshot.get('rank_agent_enabled') if execution.config_snapshot else 'N/A'}) from current active config"
                )
            elif "rank_agent_enabled" not in new_config_snapshot:
                # Fallback: ensure it exists even if not in old snapshot
                new_config_snapshot["rank_agent_enabled"] = True
                logger.info(
                    f"Retry execution {execution_id}: Added default rank_agent_enabled=True to config_snapshot (no current config available)"
                )
            else:
                # Convert existing value to bool to ensure consistency
                new_config_snapshot["rank_agent_enabled"] = bool(new_config_snapshot.get("rank_agent_enabled", True))
                logger.info(
                    f"Retry execution {execution_id}: Preserved rank_agent_enabled={new_config_snapshot['rank_agent_enabled']} from old snapshot (no current config to update from)"
                )

            # Create new execution record
            new_execution = AgenticWorkflowExecutionTable(
                article_id=execution.article_id,
                status="pending",
                config_snapshot=new_config_snapshot,
                retry_count=execution.retry_count + 1,
            )
            db_session.add(new_execution)
            db_session.commit()
            db_session.refresh(new_execution)

            # Verify the snapshot was saved correctly
            logger.info(
                f"Retry execution {execution_id}: Created new execution {new_execution.id} with rank_agent_enabled={new_config_snapshot.get('rank_agent_enabled')} in snapshot"
            )

            # Trigger workflow via Celery (uses Langfuse if enabled)
            logger.info(f"Retry requested for execution {execution_id}")
            trigger_agentic_workflow.delay(execution.article_id, new_execution.id)

            return {
                "success": True,
                "message": f"Retry initiated for execution {execution_id} (via Celery, Langfuse tracing if enabled)",
                "new_execution_id": new_execution.id,
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying workflow execution: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")

            if execution.status not in ["running", "pending"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot cancel execution with status '{execution.status}'. Only running or pending executions can be cancelled.",
                )

            # Mark as failed with cancellation message
            execution.status = "failed"
            execution.error_message = f"Execution cancelled by user (was {execution.status})"
            execution.completed_at = datetime.now()
            db_session.commit()

            logger.info(f"Execution {execution_id} cancelled by user")

            return {
                "success": True,
                "message": f"Execution {execution_id} cancelled successfully",
                "execution_id": execution_id,
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling workflow execution: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/executions/cancel-all-running")
async def cancel_all_running_executions(request: Request):
    """
    Cancel all running or pending workflow executions.

    Marks all executions with status 'running' or 'pending' as failed with a cancellation message.
    Note: This only marks the executions as cancelled in the database.
    The actual Celery tasks may continue running until they complete or time out.
    """
    try:
        db_manager = get_db_manager()
        db_session = db_manager.get_session()

        try:
            # Find all running or pending executions
            running_executions = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.status.in_(["running", "pending"]))
                .all()
            )

            if not running_executions:
                return {"success": True, "message": "No running or pending executions found", "count": 0}

            count = 0
            for execution in running_executions:
                original_status = execution.status
                execution.status = "failed"
                execution.error_message = f"Execution cancelled by user (was {original_status})"
                execution.completed_at = datetime.now()
                count += 1

            db_session.commit()
            logger.info(f"Cancelled {count} running/pending execution(s) by user")

            return {"success": True, "message": f"Cancelled {count} execution(s) successfully", "count": count}
        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Error cancelling all running executions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


def _get_langfuse_setting(db_session: Session, key: str, env_key: str, default: str | None = None) -> str | None:
    """Get Langfuse setting from database first, then fall back to environment variable.

    Priority: database setting > environment variable > default
    """
    # Check database setting first (highest priority - user preference from UI)
    try:
        setting = db_session.query(AppSettingsTable).filter(AppSettingsTable.key == key).first()

        if setting and setting.value:
            logger.info(f"✅ Using {key} from database setting (value length: {len(setting.value)})")
            return setting.value
        logger.debug(f"⚠️ No database setting found for {key}")
    except Exception as e:
        logger.warning(f"❌ Could not fetch {key} from database: {e}")

    # Fall back to environment variable (second priority)
    import os

    env_value = os.getenv(env_key)
    if env_value:
        logger.info(f"✅ Using {env_key} from environment (value length: {len(env_value)})")
        return env_value
    logger.debug(f"⚠️ No environment variable found for {env_key}")

    # Return default if provided
    if default:
        logger.debug(f"📝 Using default value for {key}: {default}")
    return default


@router.get("/executions/{execution_id}/debug-info")
async def get_workflow_debug_info(request: Request, execution_id: int):
    """Get debug information for opening execution in Agent Chat UI."""
    try:
        db_manager = get_db_manager()
        db_session = db_manager.get_session()

        try:
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")

            # Check if Langfuse is configured (preferred for debugging)
            # Priority: database setting > environment variable > default
            langfuse_host = _get_langfuse_setting(
                db_session, "LANGFUSE_HOST", "LANGFUSE_HOST", "https://us.cloud.langfuse.com"
            )
            langfuse_public_key = _get_langfuse_setting(db_session, "LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY")
            langfuse_project_id = _get_langfuse_setting(db_session, "LANGFUSE_PROJECT_ID", "LANGFUSE_PROJECT_ID")

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
                session_id,
            )

            # Normalize host URL (remove trailing slash)
            langfuse_host = langfuse_host.rstrip("/") if langfuse_host else "https://us.cloud.langfuse.com"

            # Prefer /traces/{trace_id}: direct trace URLs work. /sessions/{session_id} 404s
            # ("Session not found" / sessions.byIdWithScores). Fallback: traces?search={session_id}.
            if resolved_trace_id and langfuse_project_id:
                agent_chat_url = f"{langfuse_host}/project/{langfuse_project_id}/traces/{resolved_trace_id}"
            elif resolved_trace_id:
                agent_chat_url = f"{langfuse_host}/traces/{resolved_trace_id}"
            elif langfuse_project_id:
                agent_chat_url = f"{langfuse_host}/project/{langfuse_project_id}/traces?search={session_id}"
            else:
                agent_chat_url = f"{langfuse_host}/traces?search={session_id}"

            logger.info(f"🔗 Generated Langfuse URL: {agent_chat_url} (trace_id={bool(resolved_trace_id)})")
            logger.info(
                "   Trace ID: %s (lookup=%s, hash=%s), Session ID: %s (execution #%s)",
                resolved_trace_id,
                trace_lookup_used,
                trace_id_hash,
                session_id,
                execution_id,
            )

            if langfuse_public_key:
                instructions = (
                    f"Opening Langfuse session for execution #{execution_id}.\n"
                    f"Session ID: {session_id}\n"
                    "This session contains all traces for this workflow execution."
                )
            else:
                # Warn user that Langfuse may not be configured, but still try to open session
                logger.warning(
                    f"⚠️ Langfuse keys not configured for execution {execution_id}. "
                    f"Opening session URL anyway - session may exist if execution ran with Langfuse enabled. "
                    f"Configure Langfuse in Settings page or set LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY in environment."
                )
                instructions = (
                    f"Opening Langfuse session for execution #{execution_id}.\n"
                    f"Session ID: {session_id}\n"
                    "Note: Langfuse keys not configured. Session will only exist if execution ran with Langfuse tracing enabled. "
                    f"If you get a 404, search for session_id '{session_id}' in Langfuse UI."
                )

            return {
                "execution_id": execution_id,
                "article_id": execution.article_id,
                "agent_chat_url": agent_chat_url,
                "trace_id": resolved_trace_id,
                "session_id": session_id,
                "thread_id": trace_id_hash,
                "graph_id": "agentic_workflow",
                "langfuse_host": langfuse_host,
                "langfuse_project_id": langfuse_project_id,
                "search_url": (
                    f"{langfuse_host}/project/{langfuse_project_id}/traces?search={session_id}"
                    if langfuse_project_id
                    else f"{langfuse_host}/traces?search={session_id}"
                ),
                "instructions": instructions,
                "uses_langsmith": bool(langfuse_public_key),  # Keep field name for backwards compatibility
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting debug info: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/articles/{article_id}/trigger")
async def trigger_workflow_for_article(request: Request, article_id: int):
    """
    Manually trigger agentic workflow for an article via Celery.
    """
    try:
        from src.services.workflow_trigger_service import WorkflowTriggerService

        db_manager = get_db_manager()
        db_session = db_manager.get_session()

        try:
            # Ensure we have a clean transaction state
            try:
                db_session.rollback()
            except Exception:
                pass

            trigger_service = WorkflowTriggerService(db_session)

            # Check for existing active executions BEFORE triggering
            # Also check for stuck pending executions (older than 5 minutes)
            from datetime import timedelta

            cutoff_time = datetime.now() - timedelta(minutes=5)

            existing_execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(
                    AgenticWorkflowExecutionTable.article_id == article_id,
                    AgenticWorkflowExecutionTable.status.in_(["pending", "running"]),
                )
                .first()
            )

            if existing_execution:
                # Check if it's a stuck pending execution (older than 5 minutes and never started)
                if (
                    existing_execution.status == "pending"
                    and existing_execution.created_at < cutoff_time
                    and existing_execution.started_at is None
                ):
                    logger.warning(
                        f"Found stuck pending execution {existing_execution.id} for article {article_id} "
                        f"(created {existing_execution.created_at}, never started). Marking as failed."
                    )
                    existing_execution.status = "failed"
                    existing_execution.error_message = (
                        existing_execution.error_message
                        or f"Execution stuck in pending status for more than 5 minutes (created: {existing_execution.created_at})"
                    )
                    existing_execution.completed_at = datetime.now()
                    db_session.commit()
                    # Continue to create new execution
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Article {article_id} already has an active workflow execution (ID: {existing_execution.id})",
                    )

            if trigger_service.trigger_workflow(article_id):
                # Get the newly created execution
                execution = (
                    db_session.query(AgenticWorkflowExecutionTable)
                    .filter(AgenticWorkflowExecutionTable.article_id == article_id)
                    .order_by(AgenticWorkflowExecutionTable.created_at.desc())
                    .first()
                )

                return {
                    "success": True,
                    "message": f"Workflow triggered for article {article_id}",
                    "execution_id": execution.id if execution else None,
                    "article_id": article_id,
                }
            # trigger_workflow returned False - this should not happen if we checked above
            # But handle it gracefully
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                raise HTTPException(status_code=404, detail=f"Article {article_id} not found")

            # Should not reach here if trigger_workflow logic is correct
            # But if it does, it's not a hunt score issue (threshold check disabled)
            raise HTTPException(
                status_code=400, detail=f"Failed to trigger workflow for article {article_id} (unknown reason)"
            )
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        # Rollback any failed transaction
        try:
            db_session.rollback()
        except Exception:
            pass
        logger.error(f"Error triggering workflow for article {article_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


class ExportBundleRequest(BaseModel):
    """Request model for eval bundle export."""

    agent_name: str = Field(..., description="Agent name (e.g., 'CmdlineExtract', 'rank_article')")
    attempt: int = Field(1, description="Attempt number (1-indexed)")
    inline_large_text: bool = Field(False, description="Whether to inline large text fields")
    max_inline_chars: int = Field(200000, description="Maximum characters to inline before truncation")


@router.post("/executions/{execution_id}/export-bundle")
async def export_eval_bundle(request: Request, execution_id: int, export_request: ExportBundleRequest):
    """
    Export evaluation bundle for a specific LLM call within a workflow execution.

    Returns eval_bundle_v1 JSON with all inputs, outputs, and provenance data.
    """
    try:
        db_manager = get_db_manager()
        db_session = db_manager.get_session()

        try:
            bundle_service = EvalBundleService(db_session)
            bundle = bundle_service.generate_bundle(
                execution_id=execution_id,
                agent_name=export_request.agent_name,
                attempt=export_request.attempt,
                inline_large_text=export_request.inline_large_text,
                max_inline_chars=export_request.max_inline_chars,
            )

            # Update workflow metadata with agent_name and attempt
            bundle["workflow"]["agent_name"] = export_request.agent_name
            bundle["workflow"]["attempt"] = export_request.attempt

            # Recompute bundle_sha256 with updated workflow metadata
            bundle_for_hash = bundle.copy()
            bundle_for_hash["integrity"] = {"bundle_sha256": "", "warnings": bundle["integrity"]["warnings"]}
            from src.services.eval_bundle_service import compute_sha256_json

            bundle_sha256 = compute_sha256_json(bundle_for_hash)
            bundle["integrity"]["bundle_sha256"] = bundle_sha256

            return bundle
        finally:
            db_session.close()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error exporting eval bundle for execution {execution_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions/{execution_id}/export-bundle")
async def get_eval_bundle_metadata(
    request: Request, execution_id: int, agent_name: str | None = None, attempt: int = 1
):
    """
    Get metadata for the most recent eval bundle or regenerate on demand.

    Query params:
    - agent_name: Agent name (optional, defaults to first available)
    - attempt: Attempt number (defaults to 1)
    """
    try:
        db_manager = get_db_manager()
        db_session = db_manager.get_session()

        try:
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(status_code=404, detail="Workflow execution not found")

            # If agent_name not provided, try to detect from error_log
            if not agent_name:
                error_log = execution.error_log or {}
                available_agents = list(error_log.keys())
                if available_agents:
                    agent_name = available_agents[0]
                else:
                    agent_name = "extract_agent"  # Default

            bundle_service = EvalBundleService(db_session)
            bundle = bundle_service.generate_bundle(
                execution_id=execution_id,
                agent_name=agent_name,
                attempt=attempt,
                inline_large_text=False,
                max_inline_chars=200000,
            )

            # Update workflow metadata
            bundle["workflow"]["agent_name"] = agent_name
            bundle["workflow"]["attempt"] = attempt

            # Recompute bundle_sha256
            bundle_for_hash = bundle.copy()
            bundle_for_hash["integrity"] = {"bundle_sha256": "", "warnings": bundle["integrity"]["warnings"]}
            from src.services.eval_bundle_service import compute_sha256_json

            bundle_sha256 = compute_sha256_json(bundle_for_hash)
            bundle["integrity"]["bundle_sha256"] = bundle_sha256

            return {
                "bundle_id": bundle["bundle_id"],
                "bundle_sha256": bundle_sha256,
                "collected_at": bundle["collected_at"],
                "warnings": bundle["integrity"]["warnings"],
                "bundle": bundle,  # Include full bundle
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting eval bundle metadata for execution {execution_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
