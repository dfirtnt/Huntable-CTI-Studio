"""
Agentic Workflow using LangGraph for processing high-hunt-score articles.

This workflow processes articles through 7 steps:
0. Junk Filter
1. LLM Rank Article
1.5. OS Detection (Windows only continues)
2. Extract Agent
3. Generate SIGMA rules
4. Similarity Search
5. Promote to Queue
"""

import logging
import json
import yaml
from typing import Dict, Any, Optional, TypedDict
from datetime import datetime
from pathlib import Path

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.database.models import (
    ArticleTable, AgenticWorkflowExecutionTable, SigmaRuleQueueTable,
    AgenticWorkflowConfigTable, SubagentEvaluationTable
)
from src.utils.content_filter import ContentFilter
from src.services.llm_service import LLMService
from src.services.rag_service import RAGService
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.qa_agent_service import QAAgentService
from src.utils.langfuse_client import trace_workflow_execution, log_workflow_step, get_langfuse_client, is_langfuse_enabled
from src.utils.subagent_utils import build_subagent_lookup_values, normalize_subagent_name
from src.workflows.status_utils import (
    mark_execution_completed,
    TERMINATION_REASON_RANK_THRESHOLD,
    TERMINATION_REASON_NO_SIGMA_RULES,
    TERMINATION_REASON_NON_WINDOWS_OS,
)

logger = logging.getLogger(__name__)
 
def _bool_from_value(val: Any) -> bool:
    """Normalize various truthy/falsey inputs to a boolean."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() == 'true'
    return bool(val)


class WorkflowState(TypedDict):
    """State for the agentic workflow."""
    article_id: int
    execution_id: int
    article: Optional[ArticleTable]
    config: Optional[Dict[str, Any]]
    eval_run: bool
    skip_rank_agent: bool
    
    # Step 0: Junk Filter
    filtered_content: Optional[str]
    junk_filter_result: Optional[Dict[str, Any]]
    
    # Step 1: LLM Ranking
    ranking_score: Optional[float]
    ranking_reasoning: Optional[str]
    should_continue: bool
    
    # Step 1.5: OS Detection
    os_detection_result: Optional[Dict[str, Any]]
    detected_os: Optional[str]
    
    # Step 2: Extract Agent
    extraction_result: Optional[Dict[str, Any]]
    discrete_huntables_count: Optional[int]
    
    # Step 3: SIGMA Generation
    sigma_rules: Optional[list]
    
    # Step 4: Similarity Search
    similarity_results: Optional[list]
    max_similarity: Optional[float]
    
    # Step 5: Queue Promotion
    queued_rules: Optional[list]
    
    # Error handling
    error: Optional[str]
    current_step: str
    status: Optional[str]
    termination_reason: Optional[str]
    termination_details: Optional[Dict[str, Any]]


def _update_subagent_eval_on_completion(execution: AgenticWorkflowExecutionTable, db_session: Session) -> None:
    """
    Update SubagentEvaluationTable when workflow execution completes.
    Extracts count from extraction_result.subresults.{subagent_name} and calculates score.
    """
    try:
        config_snapshot = execution.config_snapshot or {}
        subagent_name = normalize_subagent_name(config_snapshot.get('subagent_eval'))
        
        if not subagent_name:
            # Not an eval run
            return
        
        # Find the eval record for this execution
        eval_record = db_session.query(SubagentEvaluationTable).filter(
            SubagentEvaluationTable.workflow_execution_id == execution.id
        ).first()
        
        if not eval_record:
            logger.warning(f"No SubagentEvaluation record found for execution {execution.id}")
            return
        
        # Extract count from extraction_result
        extraction_result = execution.extraction_result
        if not extraction_result or not isinstance(extraction_result, dict):
            logger.warning(f"No extraction_result for execution {execution.id}")
            eval_record.status = 'failed'
            db_session.commit()
            return
        
        subresults = extraction_result.get('subresults', {})
        if not isinstance(subresults, dict):
            logger.warning(f"No subresults in extraction_result for execution {execution.id}")
            eval_record.status = 'failed'
            db_session.commit()
            return
        
        # Get count for the specific subagent
        subagent_result = subresults.get(subagent_name, {})
        if not isinstance(subagent_result, dict):
            logger.warning(f"No {subagent_name} result in subresults for execution {execution.id}")
            eval_record.status = 'failed'
            db_session.commit()
            return
        
        # Extract count (prefer count field, fallback to items array length)
        actual_count = subagent_result.get('count')
        if actual_count is None:
            items = subagent_result.get('items', [])
            if isinstance(items, list):
                actual_count = len(items)
            else:
                actual_count = 0
        
        if not isinstance(actual_count, int):
            actual_count = int(actual_count) if actual_count else 0
        
        # Calculate score
        score = actual_count - eval_record.expected_count
        
        # Update eval record
        eval_record.actual_count = actual_count
        eval_record.score = score
        eval_record.status = 'completed'
        eval_record.completed_at = datetime.utcnow()
        
        # Commit the update
        db_session.commit()
        
        logger.info(
            f"Updated SubagentEvaluation {eval_record.id}: "
            f"subagent={subagent_name}, expected={eval_record.expected_count}, "
            f"actual={actual_count}, score={score}"
        )
        
    except Exception as e:
        logger.error(f"Error updating SubagentEvaluation for execution {execution.id}: {e}", exc_info=True)
        # Don't fail the workflow if eval update fails
        pass


def create_agentic_workflow(db_session: Session) -> StateGraph:
    """
    Create LangGraph workflow for agentic processing.
    
    Workflow steps:
    0. OS Detection - Detect operating system (Windows/Linux/MacOS/multiple)
    1. Junk Filter - Filter content using conservative junk filter
    2. LLM Ranking - Rank article using LLM
    3. Extract Agent - Extract behaviors using ExtractAgent
    4. Generate SIGMA - Generate SIGMA detection rules
    5. Similarity Search - Check similarity against existing rules
    6. Queue Promotion - Queue new rules for human review
    
    Args:
        db_session: Database session
    
    Returns:
        Compiled LangGraph workflow
    """
    
    # Initialize services
    content_filter = ContentFilter()
    # LLMService will be initialized per-node with config models
    rag_service = RAGService()
    trigger_service = WorkflowTriggerService(db_session)
    
    # Define workflow nodes
    
    def junk_filter_node(state: WorkflowState) -> WorkflowState:
        """Step 1: Filter content using conservative junk filter."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 1: Junk Filter")
            
            # Load article from DB instead of state (state['article'] is None to avoid serialization issues)
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state['article_id']).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            
            # Validate article content
            if not article.content or len(article.content.strip()) == 0:
                raise ValueError(f"Article {article.id} has no content to filter")
            
            # Get junk filter threshold from config
            config = state.get('config')
            junk_filter_threshold = config.get('junk_filter_threshold', 0.8) if config and isinstance(config, dict) else 0.8
            
            # Use configured filter threshold
            try:
                filter_result = content_filter.filter_content(
                    article.content,
                    min_confidence=junk_filter_threshold,
                    hunt_score=article.article_metadata.get('threat_hunting_score', 0) if article.article_metadata else 0,
                    article_id=article.id
                )
            except Exception as filter_error:
                logger.error(f"[Workflow {state['execution_id']}] ContentFilter error: {filter_error}", exc_info=True)
                raise ValueError(f"ContentFilter failed: {filter_error}") from filter_error
            
            # Update execution record
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            if execution:
                execution.current_step = 'junk_filter'
                # Calculate chunks kept (total chunks - removed chunks)
                total_chunks = (len(article.content) // 1000) + 1  # Rough estimate
                chunks_removed = len(filter_result.removed_chunks) if filter_result.removed_chunks else 0
                chunks_kept = total_chunks - chunks_removed if chunks_removed > 0 else total_chunks
                
                execution.junk_filter_result = {
                    'filtered_length': len(filter_result.filtered_content) if filter_result.filtered_content else 0,
                    'original_length': len(article.content),
                    'chunks_kept': chunks_kept,
                    'chunks_removed': chunks_removed,
                    'is_huntable': filter_result.is_huntable,
                    'confidence': filter_result.confidence
                }
                db_session.commit()
            
            return {
                **state,
                'filtered_content': filter_result.filtered_content or article.content,
                'junk_filter_result': execution.junk_filter_result if execution else None,
                'current_step': 'junk_filter',
                'status': state.get('status', 'running'),
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Junk filter error: {e}", exc_info=True)
            # Update execution with error
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            if execution:
                execution.status = 'failed'
                execution.current_step = 'junk_filter'
                db_session.commit()
            return {
                **state,
                'error': str(e),
                'current_step': 'junk_filter',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
    
    def rank_agent_bypass_node(state: WorkflowState) -> WorkflowState:
        """Bypass node when rank agent is disabled or skipped for evals - sets should_continue=True and skips ranking."""
        execution = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.id == state['execution_id']
        ).first()
        
        # Determine bypass reason
        config_snapshot = execution.config_snapshot if execution else {}
        eval_run_flag = _bool_from_value(config_snapshot.get('eval_run', False))
        skip_rank_flag = _bool_from_value(config_snapshot.get('skip_rank_agent', False))
        state_eval_run = _bool_from_value(state.get('eval_run', False))
        is_eval_run = state_eval_run or eval_run_flag
        bypass_reason = "Rank Agent skipped for eval run" if is_eval_run else "Rank Agent disabled - bypassed"
        
        logger.info(f"[Workflow {state['execution_id']}] {bypass_reason}")
        
        # Update execution record
        if execution:
            execution.current_step = 'rank_article_bypassed'
            execution.ranking_score = None
            execution.ranking_reasoning = bypass_reason
            db_session.commit()
        
        return {
            **state,
            'ranking_score': None,
            'ranking_reasoning': bypass_reason,
            'should_continue': True,
            'current_step': 'rank_article_bypassed',
            'status': state.get('status', 'running'),
            'termination_reason': state.get('termination_reason'),
            'termination_details': state.get('termination_details')
        }
    
    async def rank_article_node(state: WorkflowState) -> WorkflowState:
        """Step 2: Rank article using LLM."""
        try:
            # CRITICAL: Check if this is an eval run - evals MUST NOT use rank agent
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            state_eval_run = _bool_from_value(state.get('eval_run', False))
            state_skip_rank = _bool_from_value(state.get('skip_rank_agent', False))
            if state_eval_run or state_skip_rank:
                logger.warning(f"[Workflow {state['execution_id']}] BLOCKED: Rank agent node called for eval run - redirecting to bypass")
                if execution:
                    execution.current_step = 'rank_article_bypassed'
                    execution.ranking_score = None
                    execution.ranking_reasoning = "Rank Agent blocked for eval run"
                    db_session.commit()

                return {
                    **state,
                    'ranking_score': None,
                    'ranking_reasoning': "Rank Agent blocked for eval run",
                    'should_continue': True,
                    'current_step': 'rank_article_bypassed',
                    'status': state.get('status', 'running'),
                }

            if execution and execution.config_snapshot:
                config_snapshot = execution.config_snapshot or {}
                skip_rank_agent = (
                    _bool_from_value(config_snapshot.get('skip_rank_agent', False)) or
                    _bool_from_value(config_snapshot.get('eval_run', False))
                )

                if skip_rank_agent:
                    logger.warning(f"[Workflow {state['execution_id']}] BLOCKED: Rank agent node called for eval run - redirecting to bypass")
                    # Redirect to bypass node behavior
                    if execution:
                        execution.current_step = 'rank_article_bypassed'
                        execution.ranking_score = None
                        execution.ranking_reasoning = "Rank Agent blocked for eval run"
                        db_session.commit()

                    return {
                        **state,
                        'ranking_score': None,
                        'ranking_reasoning': "Rank Agent blocked for eval run",
                        'should_continue': True,
                        'current_step': 'rank_article_bypassed',
                        'status': state.get('status', 'running'),
                    }
            
            logger.info(f"[Workflow {state['execution_id']}] Step 2: LLM Ranking")
            
            # Load article from DB instead of state
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state['article_id']).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            filtered_content = state.get('filtered_content') or article.content if article else ""
            
            # Update execution record BEFORE calling LLM (so status is accurate during long-running LLM call)
            if execution:
                execution.current_step = 'rank_article'
                db_session.commit()
            
            # Get config models for LLMService
            config_obj = trigger_service.get_active_config()
            qa_flags = (
                config_obj.qa_enabled
                if config_obj and config_obj.qa_enabled
                else (state.get('config', {}).get('qa_enabled', {}) or {})
            )
            agent_models = config_obj.agent_models if config_obj else None
            llm_service = LLMService(config_models=agent_models)
            llm_service._current_execution_id = state['execution_id']
            llm_service._current_article_id = article.id
            
            # Check if QA is enabled for Rank Agent
            qa_enabled = qa_flags.get("RankAgent", False)
            
            # Get QA max retries from config
            max_qa_retries = config_obj.qa_max_retries if config_obj and hasattr(config_obj, 'qa_max_retries') else 5
            qa_feedback = None
            ranking_result = None
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"

            hunt_score = article.article_metadata.get('threat_hunting_score') if article.article_metadata else None
            ml_score = article.article_metadata.get('ml_hunt_score') if article.article_metadata else None
            ground_truth_details = LLMService.compute_rank_ground_truth(hunt_score, ml_score)
            ground_truth_rank = ground_truth_details.get("ground_truth_rank")
            
            # Get agent prompt from config (for both ranking and QA)
            rank_prompt_template = None
            agent_prompt = "Rank the article from 1-10 for SIGMA huntability based on telemetry observables, behavioral patterns, and detection rule feasibility."
            if config_obj and config_obj.agent_prompts and "RankAgent" in config_obj.agent_prompts:
                rank_prompt_data = config_obj.agent_prompts["RankAgent"]
                if isinstance(rank_prompt_data.get("prompt"), str):
                    rank_prompt_template = rank_prompt_data["prompt"]
                    agent_prompt = rank_prompt_template[:5000]  # Truncate for QA context
                    logger.info(f"Using RankAgent prompt from workflow config (length: {len(rank_prompt_template)} chars)")
            
            # Initialize conversation log for rank_article
            conversation_log = []
            
            # QA retry loop
            for qa_attempt in range(max_qa_retries):
                # Rank article using LLM
                ranking_result = await llm_service.rank_article(
                    title=article.title,
                    content=filtered_content,
                    source=source_name,
                    url=article.canonical_url or "",
                    prompt_template=rank_prompt_template,
                    execution_id=state['execution_id'],
                    article_id=article.id,
                    ground_truth_rank=ground_truth_rank,
                    ground_truth_details=ground_truth_details,
                    qa_feedback=qa_feedback
                )
                
                # Store LLM interaction in conversation log
                conversation_log.append({
                    'attempt': qa_attempt + 1,
                    'messages': [
                        {
                            'role': 'system',
                            'content': 'You are a cybersecurity detection engineer. Score threat intelligence articles 1-10 for SIGMA huntability.'
                        },
                        {
                            'role': 'user',
                            'content': f"Title: {article.title}\nSource: {source_name}\nURL: {article.canonical_url or ''}\n\nContent: {filtered_content[:2000]}..." if len(filtered_content) > 2000 else f"Title: {article.title}\nSource: {source_name}\nURL: {article.canonical_url or ''}\n\nContent: {filtered_content}"
                        }
                    ],
                    'llm_response': ranking_result.get('raw_response', ranking_result.get('reasoning', '')),
                    'score': ranking_result.get('score'),
                    'qa_feedback': qa_feedback
                })
                
                # Store conversation log in execution.error_log
                if execution:
                    if execution.error_log is None:
                        execution.error_log = {}
                    execution.error_log['rank_article'] = {
                        'conversation_log': conversation_log
                    }
                    db_session.commit()
                
                # If QA not enabled, break after first attempt
                if not qa_enabled:
                    break
                
                # Run QA check
                qa_service = QAAgentService(llm_service=llm_service)
                qa_result = await qa_service.evaluate_agent_output(
                    article=article,
                    agent_prompt=agent_prompt,
                    agent_output=ranking_result,
                    agent_name="RankAgent",
                    config_obj=config_obj,
                    execution_id=state['execution_id']
                )
                
                # Store QA result in error_log
                if execution:
                    if execution.error_log is None:
                        execution.error_log = {}
                    if 'qa_results' not in execution.error_log:
                        execution.error_log['qa_results'] = {}
                    execution.error_log['qa_results']['RankAgent'] = qa_result
                    flag_modified(execution, 'error_log')
                    db_session.commit()
                
                # If QA passes, break
                if qa_result.get('verdict') == 'pass':
                    break
                
                # Generate feedback for retry
                qa_feedback = await qa_service.generate_feedback(qa_result, "RankAgent")
                
                # If critical failure, raise error
                if qa_result.get('verdict') == 'critical_failure' and qa_attempt == max_qa_retries - 1:
                    raise ValueError(f"QA critical failure after {max_qa_retries} attempts: {qa_result.get('summary', 'Unknown error')}")
            
            ranking_score = ranking_result['score'] if ranking_result else 0.0
            config = state.get('config')
            ranking_threshold = config.get('ranking_threshold', 6.0) if config and isinstance(config, dict) else 6.0
            should_continue = ranking_score >= ranking_threshold
            
            termination_reason = state.get('termination_reason')
            termination_details = state.get('termination_details')

            # Update execution record with ranking results
            if execution:
                execution.ranking_score = ranking_score
                execution.ranking_reasoning = ranking_result.get('reasoning', '')  # Store full reasoning
                execution.current_step = 'rank_article'
                if should_continue:
                    execution.status = 'running'
                    db_session.commit()
                else:
                    termination_details = {
                        'ranking_score': ranking_score,
                        'ranking_threshold': ranking_threshold
                    }
                    mark_execution_completed(
                        execution,
                        'rank_article',
                        db_session=db_session,
                        reason=TERMINATION_REASON_RANK_THRESHOLD,
                        details=termination_details,
                        commit=False
                    )
                    db_session.commit()
                    termination_reason = TERMINATION_REASON_RANK_THRESHOLD
            
            logger.info(f"[Workflow {state['execution_id']}] Ranking: {ranking_score}/10 (threshold: {ranking_threshold}), continue: {should_continue}")
            
            return {
                **state,
                'ranking_score': ranking_score,
                'ranking_reasoning': ranking_result.get('reasoning'),
                'should_continue': should_continue,
                'current_step': 'rank_article',
                'status': 'completed' if not should_continue else 'running',
                'termination_reason': termination_reason,
                'termination_details': termination_details
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            error_repr = repr(e).lower()
            # Check if this is a generator error from Langfuse cleanup (non-critical)
            # Check both str() and repr() to catch all variations
            is_generator_error = (
                ("generator" in error_msg and ("didn't stop" in error_msg or "didn't stop" in error_repr or "throw" in error_msg)) or
                ("generator" in error_repr and ("didn't stop" in error_repr or "throw" in error_repr))
            )
            
            if is_generator_error:
                logger.warning(
                    f"[Workflow {state['execution_id']}] Generator error during ranking (Langfuse cleanup issue, non-critical): {e}"
                )
                # Don't mark as failed for generator errors - they're tracing issues, not workflow failures
                # Return state indicating workflow should stop due to ranking failure, but don't set error
                return {
                    **state,
                    'error': None,  # Don't propagate generator errors as workflow errors
                    'should_continue': False,
                    'current_step': 'rank_article',
                    'status': 'completed',  # Mark as completed, not failed
                    'termination_reason': TERMINATION_REASON_RANK_THRESHOLD,
                    'termination_details': {'reason': 'Generator error during ranking (non-critical)'}
                }
            
            logger.error(f"[Workflow {state['execution_id']}] Ranking error: {e}")
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            if execution:
                execution.status = 'failed'
                execution.error_message = str(e)
                db_session.commit()
            
            return {
                **state,
                'error': str(e),
                'should_continue': False,
                'current_step': 'rank_article',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
    
    async def os_detection_node(state: WorkflowState) -> WorkflowState:
        """Step 0: Detect operating system from article content."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 0: OS Detection")
            
            # Load article from DB instead of state
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state['article_id']).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            # OS detection runs first, so use original content
            content = article.content if article else ""
            
            # Update execution record
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            if execution:
                execution.current_step = 'os_detection'
                db_session.commit()
            
            # Check if OS detection should be skipped (for eval runs)
            config = state.get('config')
            config_snapshot = execution.config_snapshot if execution else {}
            # Handle JSONB - it might be a dict or need parsing
            if config_snapshot and not isinstance(config_snapshot, dict):
                import json
                if isinstance(config_snapshot, str):
                    try:
                        config_snapshot = json.loads(config_snapshot)
                    except:
                        config_snapshot = {}
                else:
                    config_snapshot = {}
            
            # Handle both boolean and string "true"/"false" values from JSON
            skip_os_detection_flag = config_snapshot.get('skip_os_detection', False) if config_snapshot else False
            if isinstance(skip_os_detection_flag, str):
                skip_os_detection_flag = skip_os_detection_flag.lower() == 'true'
            eval_run_flag = config_snapshot.get('eval_run', False) if config_snapshot else False
            if isinstance(eval_run_flag, str):
                eval_run_flag = eval_run_flag.lower() == 'true'
            state_skip_flag = state.get('skip_os_detection', False)
            if isinstance(state_skip_flag, str):
                state_skip_flag = state_skip_flag.lower() == 'true'
            
            skip_os_detection = (
                skip_os_detection_flag or
                eval_run_flag or
                state_skip_flag
            )
            
            if skip_os_detection:
                logger.info(f"[Workflow {state['execution_id']}] Skipping OS Detection (eval run)")
                # For eval runs, force Windows detection to allow workflow to continue
                detected_os = 'Windows'
                os_result = {
                    'operating_system': 'Windows',
                    'method': 'eval_skip',
                    'confidence': 1.0,
                    'similarities': {'Windows': 1.0}
                }
            else:
                # Import OS detection service
                from src.services.os_detection_service import OSDetectionService
                
                # Get OS detection config from workflow config
                agent_models = config.get('agent_models', {}) if config and isinstance(config, dict) else {}
                embedding_model = agent_models.get('OSDetectionAgent_embedding', 'ibm-research/CTI-BERT')
                fallback_model = agent_models.get('OSDetectionAgent_fallback')
                
                # Initialize service with configured embedding model
                service = OSDetectionService(model_name=embedding_model)
                
                # Detect OS with configured fallback model
                os_result = await service.detect_os(
                    content=content,
                    use_classifier=True,
                    use_fallback=True,
                    fallback_model=fallback_model
                )
                
                detected_os = os_result.get('operating_system', 'Unknown') if os_result else 'Unknown'
            
            # Check if Windows is detected or has the highest similarity
            # This handles cases where Windows has highest similarity but confidence is low
            similarities = os_result.get('similarities', {}) if os_result else {}
            windows_similarity = similarities.get('Windows', 0.0) if isinstance(similarities, dict) else 0.0
            
            # If Windows has the highest similarity but detected_os is "Unknown", override it
            if detected_os == 'Unknown' and similarities:
                max_similarity_os = max(similarities, key=similarities.get)
                if max_similarity_os == 'Windows' and windows_similarity > 0.0:
                    detected_os = 'Windows'
                    # Update the os_result to reflect this
                    os_result['operating_system'] = 'Windows'
                    logger.info(f"[Workflow {state['execution_id']}] Overriding detected_os from 'Unknown' to 'Windows' (highest similarity: {windows_similarity:.1%})")
            
            # Continue if:
            # 1. detected_os is 'Windows', OR
            # 2. detected_os is 'multiple' and Windows is included, OR
            # 3. Windows has the highest similarity (even if confidence is low)
            is_windows = (
                detected_os == 'Windows' or
                (detected_os == 'multiple' and windows_similarity > 0.0) or
                (windows_similarity > 0.0 and windows_similarity == max(similarities.values()) if similarities else False)
            )
            
            termination_reason = state.get('termination_reason')
            termination_details = state.get('termination_details')
            
            # Update execution record
            if execution:
                execution.current_step = 'os_detection'
                
                # Store OS detection result in error_log for retrieval
                # (We'll add a dedicated os_detection_result column later via migration)
                if execution.error_log is None:
                    execution.error_log = {}
                execution.error_log['os_detection_result'] = {
                    'detected_os': detected_os,
                    'detection_method': os_result.get('method'),
                    'confidence': os_result.get('confidence'),
                    'similarities': os_result.get('similarities'),
                    'max_similarity': os_result.get('max_similarity'),
                    'probabilities': os_result.get('probabilities')
                }
                
                if is_windows:
                    execution.status = 'running'
                    db_session.commit()
                else:
                    termination_details = {
                        'detected_os': detected_os,
                        'detection_method': os_result.get('method'),
                        'confidence': os_result.get('confidence'),
                        'similarities': os_result.get('similarities'),
                        'max_similarity': os_result.get('max_similarity')
                    }
                    mark_execution_completed(
                        execution,
                        'os_detection',
                        db_session=db_session,
                        reason=TERMINATION_REASON_NON_WINDOWS_OS,
                        details=termination_details,
                        commit=False
                    )
                    db_session.commit()
                    termination_reason = TERMINATION_REASON_NON_WINDOWS_OS
            
            logger.info(f"[Workflow {state['execution_id']}] OS Detection: {detected_os}, continue: {is_windows}")
            
            return {
                **state,
                'os_detection_result': os_result,
                'detected_os': detected_os,
                'should_continue': is_windows,
                'current_step': 'os_detection',
                'status': 'completed' if not is_windows else 'running',
                'termination_reason': termination_reason,
                'termination_details': termination_details
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] OS detection error: {e}")
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            if execution:
                execution.status = 'failed'
                execution.error_message = str(e)
                db_session.commit()
            
            return {
                **state,
                'error': str(e),
                'should_continue': False,
                'current_step': 'os_detection',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
    
    async def extract_agent_node(state: WorkflowState) -> WorkflowState:
        """Step 3: Extract behaviors using ExtractAgent."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 3: Extract Agent")
            
            # Load article from DB instead of state
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state['article_id']).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            filtered_content = state.get('filtered_content') or article.content if article else ""
            
            # Update execution record BEFORE calling LLM
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            if execution:
                execution.current_step = 'extract_agent'
                db_session.commit()
            
            # Extract behaviors using sequential sub-agents and Supervisor
            logger.info(f"[Workflow {state['execution_id']}] Step 3: Extract Agent (Supervisor Mode with Sub-Agents)")
            
            config_obj = trigger_service.get_active_config()
            qa_flags = (
                config_obj.qa_enabled
                if config_obj and config_obj.qa_enabled
                else (state.get('config', {}).get('qa_enabled', {}) or {})
            )
            if not config_obj:
                raise ValueError("No active workflow configuration found")
            
            # Check if this is a subagent eval run - if so, filter qa_flags to only the evaluated agent
            config_snapshot = execution.config_snapshot if execution else {}
            state_config = state.get('config', {})
            subagent_eval = normalize_subagent_name(
                config_snapshot.get('subagent_eval') or state_config.get('subagent_eval')
            )
            if subagent_eval:
                # Map subagent names to agent names
                subagent_to_agent = {
                    "cmdline": "CmdlineExtract",
                    "sigma_queries": "SigExtract",
                    "event_ids": "EventCodeExtract",
                    "process_lineage": "ProcTreeExtract",
                    "registry_keys": "RegExtract"
                }
                agent_name = subagent_to_agent.get(subagent_eval)
                if agent_name:
                    # Only keep QA flag for the evaluated agent
                    original_qa_flags = qa_flags.copy() if isinstance(qa_flags, dict) else {}
                    qa_flags = {agent_name: qa_flags.get(agent_name, False)} if isinstance(qa_flags, dict) else {}
                    logger.info(
                        f"[Workflow {state['execution_id']}] Subagent eval ({subagent_eval}): Filtering QA flags to only {agent_name}. "
                        f"Original: {original_qa_flags}, Filtered: {qa_flags}"
                    )
                else:
                    logger.warning(
                        f"[Workflow {state['execution_id']}] Unknown subagent_eval value: {subagent_eval}. "
                        f"Available: {list(subagent_to_agent.keys())}"
                    )
            
            # Initialize sub-results accumulator
            subresults = {
                "cmdline": {"items": [], "count": 0},
                "sigma_queries": {"items": [], "count": 0},
                "event_ids": {"items": [], "count": 0},
                "process_lineage": {"items": [], "count": 0},
                "registry_keys": {"items": [], "count": 0}
            }
            
            # Get config models for LLMService
            # For eval runs, exclude SigmaAgent to avoid loading the SIGMA model unnecessarily
            # For subagent evals, only include models for the agent being evaluated
            agent_models = config_obj.agent_models if config_obj else None
            if agent_models:
                # Check if this is an eval run (check both config_snapshot and state config)
                config_snapshot = execution.config_snapshot if execution else {}
                state_config = state.get('config', {})
                is_eval_run = (
                    _bool_from_value(config_snapshot.get('eval_run', False)) or
                    _bool_from_value(config_snapshot.get('skip_sigma_generation', False)) or
                    _bool_from_value(state_config.get('eval_run', False)) or
                    _bool_from_value(state_config.get('skip_sigma_generation', False))
                )
                # subagent_eval was already set and normalized above, don't overwrite it
                # subagent_eval = config_snapshot.get('subagent_eval') or state_config.get('subagent_eval')
                
                if is_eval_run:
                    # Remove SigmaAgent from models to prevent loading it
                    original_count = len(agent_models)
                    agent_models = {k: v for k, v in agent_models.items() if not k.startswith('SigmaAgent')}
                    filtered_count = len(agent_models)
                    logger.info(
                        f"[Workflow {state['execution_id']}] Eval run: Excluding SigmaAgent models from LLMService initialization "
                        f"(filtered {original_count} -> {filtered_count} models). "
                        f"Remaining models: {list(agent_models.keys())}"
                    )
                
                # For subagent evals, filter to only include models for the agent being evaluated
                # subagent_eval was already normalized above (line 818), ensure it's still normalized
                if subagent_eval:
                    # Ensure it's still normalized (defensive check)
                    subagent_eval = str(subagent_eval).lower().strip() if subagent_eval else None
                if subagent_eval:
                    # Map subagent names to agent names
                    subagent_to_agent = {
                        "cmdline": "CmdlineExtract",
                        "sigma_queries": "SigExtract",
                        "event_ids": "EventCodeExtract",
                        "process_lineage": "ProcTreeExtract",
                        "registry_keys": "RegExtract"
                    }
                    agent_name = subagent_to_agent.get(subagent_eval)
                    if agent_name:
                        # Keep only models for this agent and its QA, plus ExtractAgent (fallback)
                        # Also keep RankAgent if needed (though it should be skipped in eval)
                        prefixes_to_keep = [
                            f"{agent_name}_",  # Agent model, temperature, provider
                            "ExtractAgent",  # Fallback model
                            "RankAgent"  # May be needed for initialization
                        ]
                        # Also include QA model prefix if present
                        qa_names = {
                            "CmdlineExtract": "CmdLineQA",
                            "SigExtract": "SigQA",
                            "EventCodeExtract": "EventCodeQA",
                            "ProcTreeExtract": "ProcTreeQA",
                            "RegExtract": "RegQA"
                        }
                        qa_name = qa_names.get(agent_name)
                        if qa_name:
                            prefixes_to_keep.append(qa_name)
                        
                        original_count = len(agent_models)
                        agent_models = {
                            k: v for k, v in agent_models.items()
                            if any(k.startswith(prefix) or k == prefix for prefix in prefixes_to_keep)
                        }
                        filtered_count = len(agent_models)
                        logger.info(
                            f"[Workflow {state['execution_id']}] Subagent eval ({subagent_eval}): Filtering models to only {agent_name} "
                            f"(filtered {original_count} -> {filtered_count} models). "
                            f"Remaining models: {list(agent_models.keys())}"
                        )
            llm_service = LLMService(config_models=agent_models)
            
            # --- Sub-Agents (including CmdlineExtract) ---
            sub_agents = [
                ("CmdlineExtract", "cmdline", "CmdLineQA"),
                ("SigExtract", "sigma_queries", "SigQA"),
                ("EventCodeExtract", "event_ids", "EventCodeQA"),
                ("ProcTreeExtract", "process_lineage", "ProcTreeQA"),
                ("RegExtract", "registry_keys", "RegQA")
            ]
            
            # Initialize conversation log for extract_agent
            conversation_log = []
            sub_agents_run = []
            disabled_sub_agents = []

            # Determine disabled sub-agents (supports list or map in config)
            disabled_agents_cfg = set()
            extract_settings = {}
            
            # Try to get disabled agents from config_obj.agent_prompts
            if config_obj:
                logger.info(f"[Workflow {state['execution_id']}] config_obj found. agent_prompts type: {type(config_obj.agent_prompts)}, is None: {config_obj.agent_prompts is None}")
                if config_obj.agent_prompts is not None:
                    logger.info(f"[Workflow {state['execution_id']}] agent_prompts keys: {list(config_obj.agent_prompts.keys()) if isinstance(config_obj.agent_prompts, dict) else 'not a dict'}")
                if config_obj.agent_prompts and isinstance(config_obj.agent_prompts, dict):
                    extract_settings = (
                        config_obj.agent_prompts.get("ExtractAgentSettings")
                        or config_obj.agent_prompts.get("ExtractAgent")
                        or {}
                    )
                    logger.info(f"[Workflow {state['execution_id']}] Found extract_settings from agent_prompts: {extract_settings}")
                else:
                    logger.warning(f"[Workflow {state['execution_id']}] agent_prompts not available or not a dict. agent_prompts type: {type(config_obj.agent_prompts)}, value: {config_obj.agent_prompts}")
            else:
                logger.warning(f"[Workflow {state['execution_id']}] config_obj is None - cannot read disabled agents")
            
            # Fallback to state config if extract_settings is still empty
            state_config = state.get('config', {}) if isinstance(state.get('config', {}), dict) else {}
            if not extract_settings and isinstance(state_config.get('extract_agents_disabled'), (list, dict)):
                extract_settings = {"disabled_agents": state_config.get('extract_agents_disabled')}
                logger.debug(f"[Workflow {state['execution_id']}] Found extract_settings from state config: {extract_settings}")

            disabled_agents_value = (
                extract_settings.get("disabled_agents")
                or extract_settings.get("disabled_sub_agents")
                or []
            )
            
            logger.info(f"[Workflow {state['execution_id']}] disabled_agents_value: {disabled_agents_value} (type: {type(disabled_agents_value)})")
            
            if isinstance(disabled_agents_value, dict):
                disabled_agents_cfg = {
                    name for name, enabled in disabled_agents_value.items()
                    if enabled is False or (isinstance(enabled, str) and enabled.lower() == "false")
                }
            elif isinstance(disabled_agents_value, list):
                disabled_agents_cfg = set(disabled_agents_value)
            
            logger.info(f"[Workflow {state['execution_id']}] Final disabled_agents_cfg: {disabled_agents_cfg}")
            
            # Check if this is a subagent eval run - if so, only run the specified agent
            # Re-read subagent_eval directly from execution to ensure we have the correct value
            # (config_snapshot was redefined at line 858, so we need to read from execution again)
            logger.info(
                f"[Workflow {state['execution_id']}] 🔍 DEBUG: About to check subagent_eval. execution is None: {execution is None}, "
                f"config_snapshot keys: {list(config_snapshot.keys()) if config_snapshot else 'None'}"
            )
            
            if execution:
                config_snapshot_for_filter = execution.config_snapshot if execution.config_snapshot else {}
                logger.info(
                    f"[Workflow {state['execution_id']}] 🔍 DEBUG: execution.config_snapshot keys: {list(config_snapshot_for_filter.keys()) if config_snapshot_for_filter else 'None'}"
                )
            else:
                config_snapshot_for_filter = config_snapshot
                logger.warning(
                    f"[Workflow {state['execution_id']}] ⚠️ execution is None, using config_snapshot from state"
                )
            state_config_for_filter = state.get('config', {})
            raw_subagent_eval = (
                config_snapshot_for_filter.get('subagent_eval')
                or state_config_for_filter.get('subagent_eval')
            )
            subagent_eval_for_filter, eval_lookup_values = build_subagent_lookup_values(raw_subagent_eval)
            subagent_eval = subagent_eval_for_filter
            eval_lookup_values = {
                str(value).strip().lower()
                for value in (eval_lookup_values or set())
                if value is not None and str(value).strip()
            }
            if subagent_eval and subagent_eval not in eval_lookup_values:
                eval_lookup_values.add(subagent_eval)
            
            # Log for debugging
            logger.info(
                f"[Workflow {state['execution_id']}] 🔍 Filtering check - subagent_eval from execution: '{raw_subagent_eval}' "
                f"(normalized: '{subagent_eval}'), lookup_values={sorted(eval_lookup_values)}, "
                f"type={type(raw_subagent_eval)}, execution is None: {execution is None}"
            )
            
            if eval_lookup_values:
                
                # Filter sub_agents to only include the agent being evaluated
                # subagent_eval is the subagent name (e.g., "process_lineage"), so compare with alias and agent name
                original_sub_agents = sub_agents
                
                # Debug: log what we're comparing
                logger.info(
                    f"[Workflow {state['execution_id']}] 🔍 BEFORE FILTERING - subagent_eval='{subagent_eval}' "
                    f"(lookup_values={sorted(eval_lookup_values)}), sub_agents list: "
                    f"{[(name, subagent, f'match={subagent.lower() in eval_lookup_values or name.lower() in eval_lookup_values}') for name, subagent, _ in original_sub_agents]}"
                )
                
                # Filter with explicit comparison logging
                filtered_agents = []
                for agent in sub_agents:
                    agent_subagent = agent[1].lower() if len(agent) > 1 else ""
                    agent_name = agent[0].lower() if len(agent) > 0 else ""
                    matches = agent_subagent in eval_lookup_values or agent_name in eval_lookup_values
                    logger.info(
                        f"[Workflow {state['execution_id']}] 🔍 Comparing: agent[0]='{agent[0]}' -> lower()='{agent_name}', "
                        f"agent[1]='{agent[1]}' -> lower()='{agent_subagent}' vs lookup_values={sorted(eval_lookup_values)} -> {matches}"
                    )
                    if matches:
                        filtered_agents.append(agent)
                
                sub_agents = filtered_agents
                
                logger.info(
                    f"[Workflow {state['execution_id']}] AFTER FILTERING - looking for subagent='{subagent_eval}'. "
                    f"Original count: {len(original_sub_agents)}, Filtered count: {len(sub_agents)}. "
                    f"Original agents: {[(name, subagent) for name, subagent, _ in original_sub_agents]}. "
                    f"Filtered agents: {[(name, subagent) for name, subagent, _ in sub_agents]}"
                )
                
                # CRITICAL: Verify filtering worked
                if len(sub_agents) != 1:
                    logger.error(
                        f"[Workflow {state['execution_id']}] 🚫 CRITICAL FILTERING ERROR: Expected 1 agent, got {len(sub_agents)}. "
                        f"Filtered agents: {[(name, subagent) for name, subagent, _ in sub_agents]}. "
                        f"This will cause incorrect agent execution!"
                    )
                
                if not sub_agents:
                    logger.error(
                        f"[Workflow {state['execution_id']}] ⚠️ subagent_eval='{subagent_eval}' not found in sub_agents list. "
                        f"Available subagents: {[subagent for _, subagent, _ in original_sub_agents]}. "
                        f"CRITICAL: This should not happen - filtering failed!"
                    )
                    # DO NOT reset to original - this is a critical error
                    # Instead, keep the empty list so no agents run
                    logger.error(
                        f"[Workflow {state['execution_id']}] 🚫 CRITICAL: Filtering failed, keeping empty sub_agents list to prevent all agents from running"
                    )
                else:
                    logger.info(
                        f"[Workflow {state['execution_id']}] 🔬 Eval mode: Only running {subagent_eval}. "
                        f"Filtered sub_agents: {[name for name, _, _ in sub_agents]}. "
                        f"Other agents will be skipped."
                    )
                    # Mark all non-evaluated agents as skipped
                    evaluated_agent_names = {agent[0] for agent in sub_agents}
                    for agent_name, result_key, _ in original_sub_agents:
                        if agent_name not in evaluated_agent_names and agent_name not in disabled_agents_cfg:
                            subresults[result_key] = {
                                "items": [],
                                "count": 0,
                                "raw": {"status": "skipped_for_eval"}
                            }
                            conversation_log.append({
                                'agent': agent_name,
                                'items_count': 0,
                                'result': {'status': 'skipped_for_eval'}
                            })
                            logger.info(
                                f"[Workflow {state['execution_id']}] ⏭️ {agent_name} skipped (eval mode: only {subagent_eval} running)"
                            )
            
            logger.info(
                f"[Workflow {state['execution_id']}] 🔍 FINAL CHECK - Sub-agents to process: {[name for name, _, _ in sub_agents]}, "
                f"subagent_eval='{subagent_eval}', count={len(sub_agents)}"
            )
            
            # Final safety check: if subagent_eval is set, ensure we only process the evaluated agent
            if subagent_eval:
                evaluated_subagent_names = {agent[1] for agent in sub_agents}
                if subagent_eval not in evaluated_subagent_names:
                    logger.error(
                        f"[Workflow {state['execution_id']}] CRITICAL: subagent_eval={subagent_eval} not in filtered sub_agents! "
                        f"Filtered agents: {evaluated_subagent_names}. This should not happen."
                    )
            
            logger.info(
                f"[Workflow {state['execution_id']}] 🔍 ABOUT TO LOOP - sub_agents count: {len(sub_agents)}, "
                f"agents: {[(name, subagent) for name, subagent, _ in sub_agents]}, subagent_eval='{subagent_eval}'"
            )
            
            for agent_name, result_key, qa_name in sub_agents:
                # CRITICAL SAFETY CHECK: If this is a subagent eval, ensure we only run the evaluated agent
                logger.info(
                    f"[Workflow {state['execution_id']}] 🔍 LOOP START for {agent_name} - execution exists: {execution is not None}, "
                    f"config_snapshot exists: {execution.config_snapshot is not None if execution else False}"
                )
                
                # ALWAYS re-read subagent_eval from execution config_snapshot FIRST (defensive - ensure we have latest value)
                current_subagent_eval = None
                if execution and execution.config_snapshot:
                    config_subagent_eval = execution.config_snapshot.get('subagent_eval')
                    logger.info(
                        f"[Workflow {state['execution_id']}] 🔍 Reading subagent_eval from execution: raw={config_subagent_eval}, "
                        f"type={type(config_subagent_eval)}"
                    )
                    if config_subagent_eval:
                        current_subagent_eval = normalize_subagent_name(config_subagent_eval)
                        logger.info(f"[Workflow {state['execution_id']}] 🔍 Normalized subagent_eval: '{current_subagent_eval}'")
                # Fallback to the variable if execution read failed - CRITICAL: preserve existing value
                if not current_subagent_eval:
                    if subagent_eval:
                        current_subagent_eval = str(subagent_eval).lower().strip()
                        logger.info(f"[Workflow {state['execution_id']}] 🔍 Using fallback subagent_eval: '{current_subagent_eval}'")
                    else:
                        logger.warning(f"[Workflow {state['execution_id']}] ⚠️ No subagent_eval found in execution or variable for {agent_name}")
                
                # Use the re-read value ONLY if we have one, otherwise keep existing
                if current_subagent_eval:
                    subagent_eval = current_subagent_eval
                logger.info(f"[Workflow {state['execution_id']}] 🔍 Final subagent_eval for {agent_name}: '{subagent_eval}' (will block if not match)")
                
                # Map agent names to their subagent names (hardcoded for reliability)
                agent_to_subagent = {
                    "CmdlineExtract": "cmdline",
                    "SigExtract": "sigma_queries",
                    "EventCodeExtract": "event_ids",
                    "ProcTreeExtract": "process_lineage",
                    "RegExtract": "registry_keys"
                }
                
                agent_subagent_name = agent_to_subagent.get(agent_name)
                
                # UNCONDITIONAL BLOCKING CHECK: If this is a subagent eval, block any agent that doesn't match
                eval_match_values = set(eval_lookup_values or set())
                if subagent_eval:
                    eval_match_values.add(str(subagent_eval).lower().strip())
                if eval_match_values:
                    normalized_agent_subagent = str(agent_subagent_name).lower().strip() if agent_subagent_name else None
                    normalized_agent_name = agent_name.lower().strip()
                    matches = (
                        (normalized_agent_subagent in eval_match_values if normalized_agent_subagent else False)
                        or normalized_agent_name in eval_match_values
                    )
                    
                    logger.info(
                        f"[Workflow {state['execution_id']}] 🔍 SAFETY CHECK for {agent_name}: "
                        f"eval_values={sorted(eval_match_values)}, agent_subagent='{normalized_agent_subagent}', "
                        f"agent_name='{normalized_agent_name}', match={matches}"
                    )
                    
                    if not matches:
                        logger.error(
                            f"[Workflow {state['execution_id']}] 🚫 BLOCKING {agent_name} - eval_values={sorted(eval_match_values)} "
                            f"but agent subagent='{normalized_agent_subagent}', agent_name='{normalized_agent_name}'. Skipping this agent!"
                        )
                        # Mark as skipped and continue to next agent
                        subresults[result_key] = {"items": [], "count": 0, "raw": {"status": "blocked_by_eval_filter"}}
                        conversation_log.append({'agent': agent_name, 'items_count': 0, 'result': {'status': 'blocked_by_eval_filter'}})
                        continue
                    
                    # Log that we're allowing this agent to run
                    logger.info(
                        f"[Workflow {state['execution_id']}] ✅ Allowing {agent_name} to run - matches eval_values={sorted(eval_match_values)}"
                    )
                elif subagent_eval is None or subagent_eval == '':
                    logger.warning(
                        f"[Workflow {state['execution_id']}] ⚠️ subagent_eval is None/empty, allowing {agent_name} to run (normal mode)"
                    )
                
                try:
                    if agent_name in disabled_agents_cfg:
                        logger.info(f"[Workflow {state['execution_id']}] ⚠️ {agent_name} is DISABLED via config; SKIPPING execution")
                        subresults[result_key] = {
                            "items": [],
                            "count": 0,
                            "raw": {"status": "disabled"}
                        }
                        conversation_log.append({
                            'agent': agent_name,
                            'items_count': 0,
                            'result': {'status': 'disabled'}
                        })
                        disabled_sub_agents.append(agent_name)
                        continue

                    sub_agents_run.append(agent_name)

                    # Load Prompts from config only (no file fallback)
                    prompt_config = None
                    qa_config = None
                    
                    # Get prompt from config
                    if not config_obj or not config_obj.agent_prompts or agent_name not in config_obj.agent_prompts:
                        logger.error(f"{agent_name} prompt not found in workflow config, skipping")
                        continue
                    
                    agent_prompt_data = config_obj.agent_prompts[agent_name]
                    if not isinstance(agent_prompt_data.get("prompt"), str):
                        logger.error(f"{agent_name} prompt in config is not a string, skipping")
                        continue
                    
                    try:
                        prompt_config = json.loads(agent_prompt_data["prompt"])
                        logger.info(f"Using {agent_name} prompt from workflow config (length: {len(agent_prompt_data['prompt'])} chars)")
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse {agent_name} prompt from config as JSON: {e}, skipping")
                        continue
                    
                    # Get QA prompt from config (optional - only if QA is enabled)
                    qa_enabled = qa_flags.get(agent_name, False)
                    if qa_enabled:
                        if qa_name not in config_obj.agent_prompts:
                            logger.warning(f"{qa_name} prompt not found in config but QA is enabled for {agent_name}, disabling QA")
                            qa_enabled = False
                        else:
                            qa_prompt_data = config_obj.agent_prompts[qa_name]
                            if isinstance(qa_prompt_data.get("prompt"), str):
                                try:
                                    qa_config = json.loads(qa_prompt_data["prompt"])
                                    logger.info(f"Using {qa_name} prompt from workflow config (length: {len(qa_prompt_data['prompt'])} chars)")
                                except json.JSONDecodeError as e:
                                    logger.warning(f"Failed to parse {qa_name} prompt from config as JSON: {e}, disabling QA")
                                    qa_enabled = False
                                    qa_config = None
                            else:
                                logger.warning(f"{qa_name} prompt in config is not a string, disabling QA")
                                qa_enabled = False
                                qa_config = None
                    
                    # QA enabled flag is set above when loading QA config
                    
                    # Get model and temperature for this agent
                    model_key = f"{agent_name}_model"
                    temperature_key = f"{agent_name}_temperature"
                    agent_model = agent_models.get(model_key) if agent_models else None
                    if not agent_model:
                        agent_model = agent_models.get("ExtractAgent") if agent_models else None
                    agent_temperature = agent_models.get(temperature_key, 0.0) if agent_models else 0.0
                    
                    # FINAL SAFETY CHECK: ALWAYS re-read subagent_eval from execution and block if doesn't match
                    # Map agent name to subagent name
                    agent_to_subagent = {
                        "CmdlineExtract": "cmdline",
                        "SigExtract": "sigma_queries",
                        "EventCodeExtract": "event_ids",
                        "ProcTreeExtract": "process_lineage",
                        "RegExtract": "registry_keys"
                    }
                    agent_subagent = agent_to_subagent.get(agent_name)
                    
                    # ALWAYS check execution config_snapshot for subagent_eval (defensive)
                    raw_final_eval = None
                    if execution and execution.config_snapshot:
                        raw_final_eval = execution.config_snapshot.get('subagent_eval')
                    
                    # Fallback to variable if execution read failed
                    if not raw_final_eval and subagent_eval:
                        raw_final_eval = subagent_eval
                    
                    final_subagent_eval_check, final_lookup_values = build_subagent_lookup_values(raw_final_eval)
                    final_eval_lookup = {
                        str(value).strip().lower()
                        for value in (final_lookup_values or set())
                        if value is not None and str(value).strip()
                    }
                    if final_subagent_eval_check and final_subagent_eval_check not in final_eval_lookup:
                        final_eval_lookup.add(final_subagent_eval_check)
                    
                    # Block if this is a subagent eval and agent doesn't match
                    if final_eval_lookup:
                        normalized_agent_subagent = str(agent_subagent).lower().strip() if agent_subagent else None
                        normalized_agent_name = agent_name.lower().strip()
                        
                        if normalized_agent_subagent not in final_eval_lookup and normalized_agent_name not in final_eval_lookup:
                            logger.error(
                                f"[Workflow {state['execution_id']}] 🚫 BLOCKING EXECUTION of {agent_name} "
                                f"(subagent={normalized_agent_subagent}) - does not match eval_values={sorted(final_eval_lookup)}"
                            )
                            # Skip this agent completely
                            subresults[result_key] = {
                                "items": [],
                                "count": 0,
                                "raw": {"status": "blocked_for_eval", "reason": f"eval_values={sorted(final_eval_lookup)}"}
                            }
                            conversation_log.append({
                                'agent': agent_name,
                                'items_count': 0,
                                'result': {'status': 'blocked_for_eval', 'reason': f'eval_values={sorted(final_eval_lookup)}'}
                            })
                            continue
                    
                    # ABSOLUTE FINAL BLOCKING CHECK: Re-read subagent_eval directly from execution before LLM call
                    # This MUST execute - it's the last line of defense before the LLM call
                    raw_final_blocking_eval = None
                    if execution and execution.config_snapshot:
                        raw_final_blocking_eval = execution.config_snapshot.get('subagent_eval')
                    
                    final_blocking_eval, final_block_lookup_values = build_subagent_lookup_values(raw_final_blocking_eval)
                    final_block_lookup = {
                        str(value).strip().lower()
                        for value in (final_block_lookup_values or set())
                        if value is not None and str(value).strip()
                    }
                    if final_blocking_eval and final_blocking_eval not in final_block_lookup:
                        final_block_lookup.add(final_blocking_eval)
                    
                    if final_block_lookup:
                        agent_to_subagent_final = {
                            "CmdlineExtract": "cmdline",
                            "SigExtract": "sigma_queries",
                            "EventCodeExtract": "event_ids",
                            "ProcTreeExtract": "process_lineage",
                            "RegExtract": "registry_keys"
                        }
                        agent_subagent_final = agent_to_subagent_final.get(agent_name)
                        normalized_agent_subagent = str(agent_subagent_final).lower().strip() if agent_subagent_final else None
                        normalized_agent_name = agent_name.lower().strip()
                        matches = (
                            (normalized_agent_subagent in final_block_lookup if normalized_agent_subagent else False)
                            or normalized_agent_name in final_block_lookup
                        )
                        logger.info(
                            f"[Workflow {state['execution_id']}] 🔍 FINAL BLOCK CHECK: {agent_name} subagent='{normalized_agent_subagent}' "
                            f"agent_name='{normalized_agent_name}' vs eval_values={sorted(final_block_lookup)} -> match={matches}"
                        )
                        if not matches:
                            logger.error(
                                f"[Workflow {state['execution_id']}] 🚫 ABSOLUTE FINAL BLOCK: {agent_name} "
                                f"subagent='{normalized_agent_subagent}' != eval_values={sorted(final_block_lookup)} - SKIPPING LLM CALL"
                            )
                            subresults[result_key] = {"items": [], "count": 0, "raw": {"status": "blocked_absolute_final"}}
                            conversation_log.append({'agent': agent_name, 'items_count': 0, 'result': {'status': 'blocked_absolute_final'}})
                            continue
                    else:
                        logger.info(f"[Workflow {state['execution_id']}] ℹ️ No final_blocking_eval, allowing {agent_name} (normal mode)")
                    
                    # Run Agent
                    qa_model_override = agent_models.get(qa_name) if agent_models else None
                    logger.info(f"[Workflow {state['execution_id']}] 🚀 About to call LLM for {agent_name}")
                    agent_result = await llm_service.run_extraction_agent(
                        agent_name=agent_name,
                        content=filtered_content,
                        title=article.title,
                        url=article.canonical_url or "",
                        prompt_config=prompt_config,
                        qa_prompt_config=qa_config if qa_enabled else None,
                        max_retries=5 if qa_enabled else 1,
                        execution_id=state['execution_id'],
                        model_name=agent_model,
                        temperature=float(agent_temperature),
                        qa_model_override=qa_model_override,
                        use_hybrid_extractor=False  # UI-triggered workflows use prompt from config
                    )
                    
                    # Store Result
                    items = []
                    # Try to find the specific list for this agent
                    if result_key in agent_result:
                        items = agent_result[result_key]
                    elif agent_name == "CmdlineExtract" and "cmdline_items" in agent_result:
                        # CmdlineExtract uses cmdline_items field
                        items = agent_result["cmdline_items"]
                    elif "items" in agent_result:
                         items = agent_result["items"]
                    else:
                        # Fallback: find first list
                        for v in agent_result.values():
                            if isinstance(v, list):
                                items = v
                                break
                    
                    subresults[result_key] = {
                        "items": items,
                        "count": len(items),
                        "raw": agent_result
                    }
                    logger.info(f"[Workflow {state['execution_id']}] {agent_name}: {len(items)} items")

                    # Make cmdline items available on state for downstream consumers (e.g., SIGMA)
                    if agent_name == "CmdlineExtract":
                        state["cmdline_items"] = items
                        state["count"] = len(items)
                    
                    # Store agent result in conversation log
                    conversation_log.append({
                        'agent': agent_name,
                        'items_count': len(items),
                        'result': agent_result
                    })
                    
                    # Store QA result if available
                    if qa_enabled and '_qa_result' in agent_result:
                        # Use the execution object we already have, don't refresh (avoids transaction isolation issues)
                        if execution:
                            qa_result = agent_result.get('_qa_result')
                            if execution.error_log is None:
                                execution.error_log = {}
                            if 'qa_results' not in execution.error_log:
                                execution.error_log['qa_results'] = {}
                            # Store using both agent_name and qa_name for UI compatibility
                            execution.error_log['qa_results'][agent_name] = qa_result
                            execution.error_log['qa_results'][qa_name] = qa_result
                            # Mark as modified so SQLAlchemy tracks the change
                            from sqlalchemy.orm.attributes import flag_modified
                            flag_modified(execution, 'error_log')
                            db_session.commit()
                            logger.info(f"[Workflow {state['execution_id']}] Stored QA result for {agent_name}: {qa_result.get('verdict', 'unknown')}, error_log keys: {list(execution.error_log.keys())}")
                        else:
                            logger.warning(f"[Workflow {state['execution_id']}] Execution not found when storing QA result for {agent_name}")
                    
                except Exception as e:
                    logger.error(f"[Workflow {state['execution_id']}] {agent_name} failed: {e}")
                    subresults[result_key] = {
                        "items": [],
                        "count": 0,
                        "raw": {},
                        "error": str(e)
                    }
            
            # --- Supervisor Aggregation ---
            # Merge all items into a single 'observables' list for backward compatibility
            all_observables = []
            content_summary = []  # Accumulate text summary for content field
            
            # Tag and merge
            for cat, data in subresults.items():
                items = data.get("items", [])
                # Normalize non-list payloads (avoid iterating over strings character-by-character)
                if items is None:
                    items = []
                elif not isinstance(items, list):
                    items = [items]
                if items:
                    content_summary.append(f"Extracted {cat.replace('_', ' ').title()}:")
                    for item in items:
                        # Normalize to observable structure
                        # Ensure item is serializable
                        if isinstance(item, dict):
                            # For structured items (lineage, registry), keep as dict but maybe stringify for 'value' field if needed
                            val = item.get('value') if 'value' in item else item
                        else:
                            val = item
                            
                        all_observables.append({
                            "type": cat,
                            "value": val,
                            "original_data": item if isinstance(item, dict) else None,
                            "source": "supervisor_aggregation"
                        })
                        
                        # Add to text summary
                        item_str = str(item)
                        if isinstance(item, dict):
                            item_str = json.dumps(item, indent=None)
                        content_summary.append(f"- {item_str}")
                    content_summary.append("")  # Newline separator
            
            total_count = len(all_observables)
            
            # Construct final result matching existing schema
            extraction_result = {
                "observables": all_observables,
                "summary": {
                    "count": total_count,
                    "source_url": article.canonical_url,
                    "platforms_detected": ["Windows"]  # Default assumption or derived
                },
                "discrete_huntables_count": total_count,
                "subresults": subresults,  # Persist detailed breakdown
                "content": "\n".join(content_summary) if content_summary else "",  # Synthesized content for Sigma Agent
                "raw_response": json.dumps(subresults, indent=2)  # Store subresults as raw_response for compatibility
            }
            
            # Store conversation log in execution.error_log (merge, don't overwrite)
            # Use the execution object we already have (don't refresh to avoid transaction isolation issues)
            if execution:
                # Ensure error_log is a dict
                if execution.error_log is None or not isinstance(execution.error_log, dict):
                    execution.error_log = {}
                # Preserve all existing keys (especially qa_results we stored earlier in the loop)
                existing_qa_results = execution.error_log.get('qa_results', {})
                # Merge extract_agent data, preserving existing qa_results and all other keys
                execution.error_log['extract_agent'] = {
                    'conversation_log': conversation_log,
                    'sub_agents_run': sub_agents_run,
                    'sub_agents_disabled': disabled_sub_agents
                }
                # Ensure qa_results is preserved (it should already be there from earlier commits in the loop)
                if existing_qa_results:
                    execution.error_log['qa_results'] = existing_qa_results
                # Mark as modified so SQLAlchemy tracks the change
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(execution, 'error_log')
                db_session.commit()
                logger.info(f"[Workflow {state['execution_id']}] Stored extract_agent log, preserved {len(existing_qa_results)} QA results, error_log keys: {list(execution.error_log.keys())}")
            
            discrete_count = total_count
            
            # Update execution record with extraction results
            if execution:
                execution.extraction_result = extraction_result
                db_session.commit()
            
            logger.info(f"[Workflow {state['execution_id']}] Extraction: {discrete_count} discrete huntables")
            
            return {
                **state,
                'extraction_result': extraction_result,
                'discrete_huntables_count': discrete_count,
                'current_step': 'extract_agent',
                'status': state.get('status', 'running'),
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Extraction error: {e}")
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            if execution:
                execution.status = 'failed'
                execution.error_message = str(e)
                execution.current_step = 'extract_agent'
                db_session.commit()
            
            return {
                **state,
                'error': str(e),
                'current_step': 'extract_agent',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
    
    async def generate_sigma_node(state: WorkflowState) -> WorkflowState:
        """Step 3: Generate SIGMA rules."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 3: Generate SIGMA")
            
            from src.services.sigma_generation_service import SigmaGenerationService
            
            # Load article from DB instead of state
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state['article_id']).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            filtered_content = state.get('filtered_content') or article.content if article else ""
            
            # Update execution record BEFORE calling LLM
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            if execution:
                execution.current_step = 'generate_sigma'
                db_session.commit()
            
            # Get config models for SigmaGenerationService
            config_obj = trigger_service.get_active_config()
            qa_flags = (
                config_obj.qa_enabled
                if config_obj and config_obj.qa_enabled
                else (state.get('config', {}).get('qa_enabled', {}) or {})
            )
            agent_models = config_obj.agent_models if config_obj else None
            
            # Get SIGMA fallback setting from config
            sigma_fallback_enabled = config_obj.sigma_fallback_enabled if config_obj and hasattr(config_obj, 'sigma_fallback_enabled') else False
            
            # Check if QA is enabled for Sigma Agent
            qa_enabled = qa_flags.get("SigmaAgent", False)
            
            # Get QA max retries from config
            max_qa_retries = config_obj.qa_max_retries if config_obj and hasattr(config_obj, 'qa_max_retries') else 5
            qa_feedback = None
            generation_result = None
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"
            
            # Get agent prompt for QA
            agent_prompt = "Generate SIGMA detection rules from the article content following SIGMA rule format and validation requirements."
            if config_obj and config_obj.agent_prompts and "SigmaAgent" in config_obj.agent_prompts:
                sigma_prompt_data = config_obj.agent_prompts["SigmaAgent"]
                if isinstance(sigma_prompt_data.get("prompt"), str):
                    agent_prompt = sigma_prompt_data["prompt"][:5000]  # Truncate for QA context
            
            # Determine content to use for SIGMA generation
            extraction_result = state.get('extraction_result', {})
            content_to_use = None
            
            if extraction_result and extraction_result.get('discrete_huntables_count', 0) > 0:
                # Prefer extracted content if we have meaningful huntables
                extracted_content = extraction_result.get('content', '')
                if extracted_content and len(extracted_content) > 100:
                    content_to_use = extracted_content
                    logger.info(f"[Workflow {state['execution_id']}] Using extracted content ({len(extracted_content)} chars) for SIGMA generation")
                else:
                    logger.warning(f"[Workflow {state['execution_id']}] Extraction result has {extraction_result.get('discrete_huntables_count', 0)} huntables but no usable content")
            
            # Fallback logic: only use filtered_content if fallback is enabled
            if content_to_use is None:
                if sigma_fallback_enabled:
                    content_to_use = filtered_content
                    logger.info(f"[Workflow {state['execution_id']}] SIGMA fallback enabled: using filtered_content ({len(filtered_content)} chars) for SIGMA generation")
                else:
                    # No extraction result and fallback disabled - skip SIGMA generation
                    logger.warning(f"[Workflow {state['execution_id']}] No extraction result or zero huntables, and SIGMA fallback is disabled. Skipping SIGMA generation.")
                    return {
                        **state,
                        'sigma_rules': [],
                        'current_step': 'generate_sigma',
                        'status': state.get('status', 'running'),
                        'termination_reason': TERMINATION_REASON_NO_SIGMA_RULES,
                        'termination_details': {
                            'reason': 'No extraction results and SIGMA fallback disabled',
                            'discrete_huntables_count': extraction_result.get('discrete_huntables_count', 0) if extraction_result else 0,
                            'sigma_fallback_enabled': False
                        }
                    }
            
            # Generate SIGMA rules using service (single attempt on chosen content)
            sigma_service = SigmaGenerationService(config_models=agent_models)
            generation_result = await sigma_service.generate_sigma_rules(
                article_title=article.title,
                article_content=content_to_use,
                source_name=source_name,
                url=article.canonical_url or "",
                ai_model='lmstudio',  # Provider resolved via config_models
                max_attempts=3,
                min_confidence=0.9,
                execution_id=state['execution_id'],
                article_id=state['article_id'],
                qa_feedback=qa_feedback
            )
            
            sigma_rules = generation_result.get('rules', []) if generation_result else []
            sigma_errors = generation_result.get('errors')
            sigma_metadata = generation_result.get('metadata', {}) if generation_result else {}
            
            # Treat Langfuse generator cleanup errors as non-fatal: skip rules, continue workflow
            if sigma_errors and isinstance(sigma_errors, str):
                err_lower = sigma_errors.lower()
                if "generator" in err_lower and ("didn't stop" in err_lower or "stop after throw" in err_lower or "throw" in err_lower):
                    logger.warning(f"[Workflow {state['execution_id']}] SIGMA generation returned generator error; treating as no-rules and continuing. Error: {sigma_errors}")
                    sigma_errors = None
                    sigma_rules = []
                    if execution:
                        execution.error_message = None
                        execution.status = execution.status or 'running'
                        db_session.commit()
            
            # Update execution record with SIGMA results
            if execution:
                execution.sigma_rules = sigma_rules
                
                # Store detailed error info in error_log for debugging (even when no errors, for conversation log display)
                # Always store if conversation_log exists OR validation_results exist
                conversation_log = sigma_metadata.get('conversation_log', [])
                validation_results = sigma_metadata.get('validation_results', [])
                
                # Store if we have conversation_log (even if empty), validation_results, or errors
                if 'conversation_log' in sigma_metadata or validation_results or sigma_errors:
                    error_log_entry = {
                        'errors': sigma_errors,
                        'total_attempts': sigma_metadata.get('total_attempts', len(conversation_log) if conversation_log else 0),
                        'validation_results': validation_results,
                        'conversation_log': conversation_log if conversation_log else []  # Ensure it's always a list
                    }
                    execution.error_log = {**(execution.error_log or {}), 'generate_sigma': error_log_entry}
                    logger.debug(f"Stored conversation_log with {len(conversation_log)} entries")
                
                # Check if SIGMA validation failed (no valid rules generated)
                # Check both errors field and metadata validation results
                validation_failed = (
                    not sigma_rules and sigma_errors
                ) or (
                    sigma_metadata.get('valid_rules', 0) == 0 and 
                    sigma_metadata.get('validation_results') and
                    not any(r.get('is_valid', False) for r in sigma_metadata.get('validation_results', []))
                )
                
                if validation_failed:
                    error_msg = sigma_errors or "SIGMA validation failed: No valid rules generated after all attempts"
                    execution.status = 'failed'
                    execution.error_message = error_msg
                    execution.current_step = 'generate_sigma'
                    db_session.commit()
                    logger.error(f"[Workflow {state['execution_id']}] SIGMA validation failed: {error_msg}")
                    
                    return {
                        **state,
                        'sigma_rules': [],
                        'error': error_msg,
                        'current_step': 'generate_sigma',
                        'should_continue': False
                    }
                
                db_session.commit()
            
            logger.info(f"[Workflow {state['execution_id']}] Generated {len(sigma_rules)} SIGMA rules")
            
            return {
                **state,
                'sigma_rules': sigma_rules,
                'current_step': 'generate_sigma',
                'status': state.get('status', 'running'),
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
            
        except Exception as e:
            err_msg = str(e)
            is_generator_error = "generator" in err_msg.lower() and ("didn't stop" in err_msg.lower() or "throw" in err_msg.lower())
            if is_generator_error:
                logger.warning(
                    f"[Workflow {state['execution_id']}] SIGMA generation encountered Langfuse generator error "
                    f"(non-critical): {e}. Treating as no-rules and continuing."
                )
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == state['execution_id']
                ).first()
                if execution:
                    # Do NOT mark failed; just note no rules
                    execution.current_step = 'generate_sigma'
                    execution.sigma_rules = []
                    execution.error_message = None
                    execution.status = execution.status or 'running'
                    db_session.commit()
                
                # Return state with no rules but no error so workflow continues
                return {
                    **state,
                    'sigma_rules': [],
                    'error': None,
                    'current_step': 'generate_sigma',
                    'should_continue': False,
                    'status': state.get('status', 'running'),
                    'termination_reason': TERMINATION_REASON_NO_SIGMA_RULES,
                    'termination_details': {
                        'reason': 'Langfuse generator error during SIGMA generation',
                        **(state.get('termination_details') or {})
                    }
                }
            
            logger.error(f"[Workflow {state['execution_id']}] SIGMA generation error: {e}")
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            if execution:
                execution.status = 'failed'
                execution.error_message = err_msg
                db_session.commit()
            
            return {
                **state,
                'error': err_msg,
                'current_step': 'generate_sigma',
                'should_continue': False,
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
    
    def check_sigma_generation(state: WorkflowState) -> str:
        """Check if SIGMA generation succeeded or if workflow should stop."""
        # Only stop if there's an actual error (SIGMA validation failure)
        # Don't stop for threshold-based stops (those are handled by rank_article check)
        if state.get('error'):
            logger.warning(f"[Workflow {state.get('execution_id')}] SIGMA generation failed with error, stopping workflow")
            return "end"
        # If there are zero rules but no error (e.g., generator error handled), treat as no-rules and still continue so downstream can mark termination_reason
        logger.info(f"[Workflow {state.get('execution_id')}] SIGMA generation completed (rules: {len(state.get('sigma_rules') or [])}); continuing to similarity search")
        return "similarity_search"
    
    async def similarity_search_node(state: WorkflowState) -> WorkflowState:
        """Step 4: Search for similar SIGMA rules."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 4: Similarity Search")
            
            # Check if workflow already failed (e.g., SIGMA validation failed)
            if state.get('error'):
                logger.warning(f"[Workflow {state['execution_id']}] Workflow has error, skipping similarity search")
                return {
                    **state,
                    'similarity_results': None,  # None indicates search didn't run
                    'max_similarity': 1.0,
                    'current_step': state.get('current_step', 'similarity_search'),
                    'status': state.get('status', 'running'),
                    'termination_reason': state.get('termination_reason'),
                    'termination_details': state.get('termination_details')
                }
            
            sigma_rules = state.get('sigma_rules', [])
            if not sigma_rules:
                logger.warning(f"[Workflow {state['execution_id']}] No SIGMA rules to search")
                return {
                    **state,
                    'similarity_results': None,  # None indicates search didn't run
                    'max_similarity': 0.0,
                    'current_step': 'similarity_search',
                    'status': state.get('status', 'running'),
                    'termination_reason': state.get('termination_reason'),
                    'termination_details': state.get('termination_details')
                }
            
            similarity_results = []
            max_similarity = 0.0
            config = state.get('config')
            similarity_threshold = config.get('similarity_threshold', 0.5) if config and isinstance(config, dict) else 0.5
            
            # Get config models for embedding model selection
            config_obj = trigger_service.get_active_config()
            agent_models = config_obj.agent_models if config_obj else None
            
            # Initialize SigmaMatchingService for 4-segment weighted similarity search
            sigma_matching_service = SigmaMatchingService(db_session, config_models=agent_models)
            
            # Search for similar rules for each generated rule using 4-segment weighted approach
            for rule in sigma_rules:
                # Use compare_proposed_rule_to_embeddings for 4-segment weighted similarity
                # This uses: title (4.2%), description (4.2%), tags (4.2%), signature (87.4%)
                similar_rules = sigma_matching_service.compare_proposed_rule_to_embeddings(
                    proposed_rule=rule,
                    threshold=0.0  # Get all results, filter by threshold below
                )
                
                # Filter by threshold and limit to top 10
                filtered_rules = [r for r in similar_rules if r.get('similarity', 0.0) >= similarity_threshold][:10]
                
                rule_similarities = [r['similarity'] for r in filtered_rules]
                rule_max_sim = max(rule_similarities) if rule_similarities else 0.0
                
                similarity_results.append({
                    'rule_title': rule.get('title'),
                    'similar_rules': filtered_rules,
                    'max_similarity': rule_max_sim
                })
                
                max_similarity = max(max_similarity, rule_max_sim)
            
            # Update execution record
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            if execution:
                # Only update current_step if workflow didn't fail earlier
                if execution.status != 'failed':
                    execution.current_step = 'similarity_search'
                execution.similarity_results = similarity_results
                db_session.commit()
            
            logger.info(f"[Workflow {state['execution_id']}] Similarity: max={max_similarity:.2f}")
            
            return {
                **state,
                'similarity_results': similarity_results,
                'max_similarity': max_similarity,
                'current_step': 'similarity_search',
                'status': state.get('status', 'running'),
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Similarity search error: {e}")
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            if execution:
                execution.status = 'failed'
                execution.error_message = str(e)
                execution.current_step = 'similarity_search'
                db_session.commit()
            
            return {
                **state,
                'error': str(e),
                'current_step': 'similarity_search',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
    
    def promote_to_queue_node(state: WorkflowState) -> WorkflowState:
        """Step 5: Promote rules to queue if similarity is low."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 5: Promote to Queue")
            
            # Check if workflow already failed - should not reach here if conditional edge works correctly
            if state.get('error'):
                logger.warning(f"[Workflow {state['execution_id']}] Workflow has error, skipping queue promotion")
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == state['execution_id']
                ).first()
                if execution and execution.status != 'failed':
                    execution.status = 'failed'
                    execution.error_message = state.get('error')
                    execution.current_step = state.get('current_step', 'generate_sigma')
                    db_session.commit()
                return {
                    **state,
                    'queued_rules': [],
                    'current_step': state.get('current_step', 'generate_sigma'),
                    'status': 'failed',
                    'termination_reason': state.get('termination_reason'),
                    'termination_details': state.get('termination_details')
                }
            
            sigma_rules = state.get('sigma_rules', [])
            similarity_results = state.get('similarity_results')
            config = state.get('config')
            similarity_threshold = config.get('similarity_threshold', 0.5) if config and isinstance(config, dict) else 0.5
            termination_reason = state.get('termination_reason')
            termination_details = state.get('termination_details')
            
            if not sigma_rules:
                if termination_reason is None:
                    termination_reason = TERMINATION_REASON_NO_SIGMA_RULES
                if termination_details is None:
                    termination_details = {'generated_rules': 0}
            
            # Check if similarity search failed or didn't run
            # Don't queue if similarity search failed (error in state) or didn't run (similarity_results is None)
            if state.get('error') or similarity_results is None:
                logger.warning(f"[Workflow {state['execution_id']}] Similarity search failed or didn't run - skipping queue promotion")
                queued_rules = []
            else:
                # Similarity search ran successfully - calculate max_similarity from results
                if len(similarity_results) > 0:
                    max_similarity = max([r.get('max_similarity', 0.0) for r in similarity_results], default=0.0)
                else:
                    # Similarity search ran successfully but found 0 matches - treat as 0.0 similarity
                    max_similarity = 0.0
                    logger.info(f"[Workflow {state['execution_id']}] Similarity search completed with 0 matches - treating as 0.0 similarity")
                
                # Only promote if max similarity is below threshold
                if max_similarity >= similarity_threshold:
                    logger.info(f"[Workflow {state['execution_id']}] Max similarity {max_similarity:.2f} >= threshold {similarity_threshold}, skipping queue")
                    queued_rules = []
                else:
                    queued_rules = []
                    # Load article from DB instead of state
                    article = db_session.query(ArticleTable).filter(ArticleTable.id == state['article_id']).first()
                    
                    # Queue each rule with low similarity
                    for idx, rule in enumerate(sigma_rules):
                        rule_similarity = similarity_results[idx] if idx < len(similarity_results) else {'max_similarity': 0.0}
                        rule_max_sim = rule_similarity.get('max_similarity', 0.0)
                        
                        if rule_max_sim < similarity_threshold:
                            # Convert rule dict to YAML
                            rule_yaml = yaml.dump(rule, default_flow_style=False, sort_keys=False)
                            
                            # Create queue entry
                            queue_entry = SigmaRuleQueueTable(
                                article_id=article.id if article else state['article_id'],
                                workflow_execution_id=state['execution_id'],
                                rule_yaml=rule_yaml,
                                rule_metadata={
                                    'title': rule.get('title'),
                                    'description': rule.get('description'),
                                    'tags': rule.get('tags', []),
                                    'level': rule.get('level'),
                                    'status': rule.get('status', 'experimental')
                                },
                                similarity_scores=rule_similarity.get('similar_rules', []),
                                max_similarity=rule_max_sim,
                                status='pending'
                            )
                            db_session.add(queue_entry)
                            queued_rules.append(queue_entry.id)
                
                db_session.commit()
                logger.info(f"[Workflow {state['execution_id']}] Queued {len(queued_rules)} rules")
            
            # Update execution record to completed
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            if execution:
                # Only update current_step if workflow didn't fail earlier
                if execution.status != 'failed':
                    mark_execution_completed(
                        execution,
                        'promote_to_queue',
                        db_session=db_session,
                        reason=termination_reason,
                        details=termination_details,
                        commit=False
                    )
                db_session.commit()
            
            return {
                **state,
                'queued_rules': queued_rules,
                'current_step': 'promote_to_queue',
                'status': 'completed',
                'termination_reason': termination_reason,
                'termination_details': termination_details
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Queue promotion error: {e}")
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            if execution:
                execution.status = 'failed'
                execution.error_message = str(e)
                execution.current_step = 'promote_to_queue'
                db_session.commit()
            
            return {
                **state,
                'error': str(e),
                'current_step': 'promote_to_queue',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
    
    def check_should_continue_after_os_detection(state: WorkflowState) -> str:
        """Check if workflow should continue after OS detection (only if Windows)."""
        should_continue = state.get('should_continue', False)
        detected_os = state.get('detected_os')
        os_result = state.get('os_detection_result', {})
        
        # Check if Windows is detected or has highest similarity
        if should_continue:
            # Already determined to continue (Windows detected)
            return "junk_filter"
        elif detected_os == 'Windows':
            return "junk_filter"
        else:
            # Check if Windows has highest similarity even if detected_os is Unknown
            similarities = os_result.get('similarities', {}) if isinstance(os_result, dict) else {}
            if isinstance(similarities, dict) and similarities:
                windows_sim = similarities.get('Windows', 0.0)
                if windows_sim > 0.0 and windows_sim == max(similarities.values()):
                    return "junk_filter"
        
        return "end"
    
    def check_rank_agent_enabled(state: WorkflowState) -> str:
        """Check if rank agent is enabled and route accordingly.
        
        Evals ALWAYS skip rank agent regardless of config setting.
        """
        config = state.get('config', {})
        execution_id = state.get('execution_id')
        state_eval_run = _bool_from_value(state.get('eval_run', False))
        state_skip_rank = _bool_from_value(state.get('skip_rank_agent', False))
        if state_eval_run or state_skip_rank:
            reason = "eval run from state config" if state_eval_run else "skip flag in state"
            logger.info(f"[Workflow {execution_id}] Skipping Rank Agent ({reason})")
            return "rank_agent_bypass"
        
        # Check if this is an eval run that should skip rank agent
        # This check takes precedence over any config setting
        execution = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.id == execution_id
        ).first()
        
        # Check execution config_snapshot first (most reliable for evals)
        if execution and execution.config_snapshot:
            config_snapshot = execution.config_snapshot
            skip_rank_agent = (
                _bool_from_value(config_snapshot.get('skip_rank_agent', False)) or
                _bool_from_value(config_snapshot.get('eval_run', False))
            )
            
            if skip_rank_agent:
                logger.info(f"[Workflow {execution_id}] Skipping Rank Agent (eval run - always bypassed)")
                return "rank_agent_bypass"
        
        # Also check state config (in case it was set during config merge)
        if isinstance(config, dict):
            skip_from_state = (
                _bool_from_value(config.get('skip_rank_agent', False)) or
                _bool_from_value(config.get('eval_run', False))
            )
            if skip_from_state:
                logger.info(f"[Workflow {execution_id}] Skipping Rank Agent (eval run from state config)")
                return "rank_agent_bypass"
        
        # Check config setting (only if not an eval run)
        # CRITICAL: Use _bool_from_value to handle string/None values correctly
        rank_agent_enabled_raw = config.get('rank_agent_enabled', True) if isinstance(config, dict) else True
        rank_agent_enabled = _bool_from_value(rank_agent_enabled_raw)
        logger.info(f"[Workflow {execution_id}] Rank agent enabled check: rank_agent_enabled={rank_agent_enabled} (raw: {rank_agent_enabled_raw}, type: {type(rank_agent_enabled_raw).__name__}), config keys: {list(config.keys()) if isinstance(config, dict) else 'N/A'}")
        if rank_agent_enabled:
            return "rank_article"
        else:
            logger.info(f"[Workflow {execution_id}] Rank agent disabled - bypassing to extract_agent")
            return "rank_agent_bypass"
    
    def check_should_continue_after_rank(state: WorkflowState) -> str:
        """Check if workflow should continue after ranking."""
        if state.get('should_continue', False):
            return "extract_agent"
        else:
            return "end"
    
    def check_should_skip_sigma_for_eval(state: WorkflowState) -> str:
        """Check if SIGMA generation should be skipped for eval runs."""
        execution = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.id == state['execution_id']
        ).first()
        
        if execution:
            config_snapshot = execution.config_snapshot or {}
            skip_sigma = (
                _bool_from_value(config_snapshot.get('skip_sigma_generation', False)) or
                _bool_from_value(config_snapshot.get('eval_run', False)) or
                _bool_from_value(state.get('skip_sigma_generation', False))
            )
            
            if skip_sigma:
                logger.info(f"[Workflow {state['execution_id']}] Skipping SIGMA generation (eval run)")
                # Mark execution as completed after extraction
                execution.status = 'completed'
                execution.current_step = 'extract_agent'
                execution.completed_at = datetime.utcnow()
                db_session.commit()
                return "end"
        
        return "generate_sigma"
    
    # Build workflow graph
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("junk_filter", junk_filter_node)
    workflow.add_node("rank_article", rank_article_node)
    workflow.add_node("rank_agent_bypass", rank_agent_bypass_node)
    workflow.add_node("os_detection", os_detection_node)
    workflow.add_node("extract_agent", extract_agent_node)
    workflow.add_node("generate_sigma", generate_sigma_node)
    workflow.add_node("similarity_search", similarity_search_node)
    workflow.add_node("promote_to_queue", promote_to_queue_node)
    
    # Define edges
    workflow.set_entry_point("os_detection")
    workflow.add_conditional_edges(
        "os_detection",
        check_should_continue_after_os_detection,
        {
            "junk_filter": "junk_filter",
            "end": END
        }
    )
    workflow.add_conditional_edges(
        "junk_filter",
        check_rank_agent_enabled,
        {
            "rank_article": "rank_article",
            "rank_agent_bypass": "rank_agent_bypass"
        }
    )
    workflow.add_conditional_edges(
        "rank_article",
        check_should_continue_after_rank,
        {
            "extract_agent": "extract_agent",
            "end": END
        }
    )
    workflow.add_edge("rank_agent_bypass", "extract_agent")
    workflow.add_conditional_edges(
        "extract_agent",
        check_should_skip_sigma_for_eval,
        {
            "generate_sigma": "generate_sigma",
            "end": END
        }
    )
    workflow.add_conditional_edges(
        "generate_sigma",
        check_sigma_generation,
        {
            "similarity_search": "similarity_search",
            "end": END
        }
    )
    workflow.add_edge("similarity_search", "promote_to_queue")
    workflow.add_edge("promote_to_queue", END)
    
    return workflow.compile()


async def run_workflow(article_id: int, db_session: Session, execution_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Run agentic workflow for an article.
    
    Args:
        article_id: ID of article to process
        db_session: Database session
    
    Returns:
        Workflow execution result
    """
    try:
        # Get article and execution
        article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
        if not article:
            raise ValueError(f"Article {article_id} not found")
        
        execution = None
        if execution_id is not None:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == execution_id
            ).first()

        if not execution:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.article_id == article_id,
                AgenticWorkflowExecutionTable.status.in_(['pending', 'running'])
            ).order_by(AgenticWorkflowExecutionTable.created_at.desc()).first()
        
        # Get config service (needed for both paths)
        trigger_service = WorkflowTriggerService(db_session)
        
        if not execution:
            # Create execution record if it doesn't exist (e.g., when called directly via Celery)
            # NOTE: This should rarely happen for evals since they create execution first
            logger.warning(f"No pending/running execution found for article {article_id}, creating one...")
            config_obj = trigger_service.get_active_config()
            execution = AgenticWorkflowExecutionTable(
                article_id=article_id,
                status='pending',
                config_snapshot={
                    'min_hunt_score': config_obj.min_hunt_score if config_obj else 97.0,
                    'ranking_threshold': config_obj.ranking_threshold if config_obj else 6.0,
                    'similarity_threshold': config_obj.similarity_threshold if config_obj else 0.5,
                    'junk_filter_threshold': config_obj.junk_filter_threshold if config_obj else 0.8,
                    'agent_models': config_obj.agent_models if config_obj else {},
                    'agent_prompts': config_obj.agent_prompts if config_obj else {},
                    'qa_enabled': config_obj.qa_enabled if config_obj else {},
                    'rank_agent_enabled': config_obj.rank_agent_enabled if config_obj and hasattr(config_obj, 'rank_agent_enabled') else True,
                    'config_id': config_obj.id if config_obj else None,
                    'config_version': config_obj.version if config_obj else None
                } if config_obj else None
            )
            db_session.add(execution)
            db_session.commit()
            db_session.refresh(execution)
            logger.info(f"Created execution record {execution.id} for article {article_id}")
        else:
            logger.info(f"Found existing execution {execution.id} for article {article_id}, status: {execution.status}, has config_snapshot: {execution.config_snapshot is not None}")
        
        # Get config
        config_obj = trigger_service.get_active_config()
        config = {
            'min_hunt_score': config_obj.min_hunt_score if config_obj else 97.0,
            'ranking_threshold': config_obj.ranking_threshold if config_obj else 6.0,
            'similarity_threshold': config_obj.similarity_threshold if config_obj else 0.5,
            'junk_filter_threshold': config_obj.junk_filter_threshold if config_obj else 0.8,
            'qa_enabled': config_obj.qa_enabled if config_obj and config_obj.qa_enabled and isinstance(config_obj.qa_enabled, dict) else {},
            'agent_models': config_obj.agent_models if config_obj and config_obj.agent_models and isinstance(config_obj.agent_models, dict) else {},
            'rank_agent_enabled': config_obj.rank_agent_enabled if config_obj and hasattr(config_obj, 'rank_agent_enabled') else True
        } if config_obj else {
            'min_hunt_score': 97.0,
            'ranking_threshold': 6.0,
            'similarity_threshold': 0.5,
            'junk_filter_threshold': 0.8,
            'qa_enabled': {},
            'agent_models': {},
            'rank_agent_enabled': True
        }
        
        # Merge config_snapshot from execution (for eval runs and other overrides)
        # Use deep merge for nested dicts like agent_models, agent_prompts, qa_enabled
        if execution.config_snapshot:
            snapshot = execution.config_snapshot
            # Merge top-level values
            for key, value in snapshot.items():
                if key in ('agent_models', 'agent_prompts', 'qa_enabled') and isinstance(value, dict):
                    # Deep merge nested dicts - preserve existing values, add/update from snapshot
                    if key in config and isinstance(config[key], dict):
                        config[key] = {**config[key], **value}
                    else:
                        config[key] = value.copy() if isinstance(value, dict) else value
                else:
                    # Overwrite other values (eval flags, thresholds, etc.)
                    config[key] = value
            
            # Ensure evals always skip rank agent regardless of config setting
            skip_rank_agent = (
                _bool_from_value(snapshot.get('skip_rank_agent', False)) or
                _bool_from_value(snapshot.get('eval_run', False))
            )
            
            if skip_rank_agent:
                config['rank_agent_enabled'] = False
                logger.info(f"[Workflow {execution.id}] Rank agent disabled: skip_rank_agent=True (eval run)")
            elif 'rank_agent_enabled' in snapshot:
                # Explicitly use rank_agent_enabled from snapshot if present (for non-eval runs)
                # CRITICAL: Convert to bool to handle string/None values
                snapshot_value = snapshot.get('rank_agent_enabled', True)
                config['rank_agent_enabled'] = _bool_from_value(snapshot_value)
                logger.info(f"[Workflow {execution.id}] Using rank_agent_enabled={config['rank_agent_enabled']} from config_snapshot (raw value: {snapshot_value}, type: {type(snapshot_value).__name__})")
            else:
                # Snapshot doesn't have rank_agent_enabled - keep value from active config
                logger.info(f"[Workflow {execution.id}] rank_agent_enabled not in snapshot, using active config value: {config.get('rank_agent_enabled', True)}")
        
        state_eval_run_flag = _bool_from_value(config.get('eval_run', False))
        state_skip_rank_flag = _bool_from_value(config.get('skip_rank_agent', False))
        
        # Initialize state
        execution.status = 'running'
        execution.started_at = datetime.utcnow()
        execution.current_step = 'os_detection'
        db_session.commit()
        
        initial_state: WorkflowState = {
            'article_id': article_id,
            'execution_id': execution.id,
            'article': None,  # Don't store ArticleTable in state - load from DB when needed
            'config': config,
            'eval_run': state_eval_run_flag,
            'skip_rank_agent': state_skip_rank_flag,
            'filtered_content': None,
            'junk_filter_result': None,
            'ranking_score': None,
            'ranking_reasoning': None,
            'should_continue': True,
            'os_detection_result': None,
            'detected_os': None,
            'extraction_result': None,
            'discrete_huntables_count': None,
            'sigma_rules': None,
            'similarity_results': None,
            'max_similarity': None,
            'queued_rules': None,
            'error': None,
            'current_step': 'os_detection',
            'status': 'running',
            'termination_reason': None,
            'termination_details': None
        }
        
        # Get config models for context check (use config if available, otherwise env vars)
        config_obj = trigger_service.get_active_config()
        agent_models = config_obj.agent_models if config_obj else None
        
        # Set execution context for LLM service tracing
        llm_service = LLMService(config_models=agent_models)
        llm_service._current_execution_id = execution.id
        llm_service._current_article_id = article_id
        
        # Check context length before starting workflow
        # Skip rank agent model check if rank_agent_enabled is False
        rank_agent_enabled = _bool_from_value(config.get('rank_agent_enabled', True))
        logger.info(f"[Workflow {execution.id}] Context check: rank_agent_enabled={rank_agent_enabled}, config keys: {list(config.keys())}")
        if rank_agent_enabled:
            try:
                context_check = await llm_service.check_model_context_length()
                logger.info(
                    f"Context length validation passed for workflow execution {execution.id}: "
                    f"{context_check['context_length']} tokens (threshold: {context_check['threshold']})"
                )
            except RuntimeError as e:
                # Update execution status to failed with context length error
                execution.status = 'failed'
                execution.error_message = str(e)
                execution.current_step = 'context_length_check'
                db_session.commit()
                logger.error(f"Workflow execution {execution.id} failed context length check: {e}")
                raise
        else:
            logger.info(
                f"Workflow execution {execution.id}: Skipping rank agent context length check "
                f"(rank_agent_enabled=False)"
            )
        
        # Create and run workflow with LangFuse tracing
        workflow_completed = False
        workflow_error = None
        final_state = None

        try:
            with trace_workflow_execution(execution_id=execution.id, article_id=article_id) as trace:
                # Persist Langfuse trace_id immediately so debug links can be direct
                try:
                    if trace:
                        trace_id_value = getattr(trace, "trace_id", None) or getattr(trace, "id", None)
                        if trace_id_value:
                            # Refresh execution to avoid stale state
                            db_session.refresh(execution)
                            log_data = execution.error_log if isinstance(execution.error_log, dict) else {}
                            if not isinstance(log_data, dict):
                                log_data = {}
                            log_data["langfuse_trace_id"] = trace_id_value
                            execution.error_log = log_data
                            db_session.commit()
                            logger.info(
                                "Persisted Langfuse trace_id for execution %s: %s",
                                execution.id,
                                trace_id_value,
                            )
                        else:
                            logger.warning(
                                "Langfuse trace missing id for execution %s; cannot persist",
                                execution.id,
                            )
                except Exception as trace_persist_error:
                    logger.debug(f"Could not persist Langfuse trace_id for execution {execution.id}: {trace_persist_error}")
                    # Rollback any failed transaction from trace persistence
                    try:
                        db_session.rollback()
                    except Exception:
                        pass

                workflow_graph = create_agentic_workflow(db_session)
                final_state = await workflow_graph.ainvoke(initial_state)
                
                # Update trace with final output (non-critical - wrap in try/except)
                if trace:
                    try:
                        trace.update(
                            output={
                                "status": "completed" if final_state.get('error') is None else "failed",
                                "ranking_score": final_state.get('ranking_score'),
                                "sigma_rules_count": len(final_state.get('sigma_rules', [])),
                                "queued_rules_count": len(final_state.get('queued_rules', [])),
                                "final_step": final_state.get('current_step'),
                                "error": final_state.get('error')
                            }
                        )
                    except Exception as update_error:
                        logger.debug(f"Could not update trace output: {update_error}")
                
                # Log workflow completion (non-critical - wrap in try/except)
                if trace:
                    try:
                        log_workflow_step(
                            trace,
                            "workflow_completed",
                            step_result={
                                "success": final_state.get('error') is None,
                                "ranking_score": final_state.get('ranking_score'),
                                "sigma_rules_count": len(final_state.get('sigma_rules', [])),
                                "queued_rules_count": len(final_state.get('queued_rules', []))
                            },
                            error=None if final_state.get('error') is None else Exception(final_state.get('error')),
                            metadata={"final_step": final_state.get('current_step')}
                        )
                    except Exception as log_error:
                        logger.debug(f"Could not log workflow step: {log_error}")
                
                # Mark workflow as completed if it finished successfully
                # This MUST happen before trace cleanup to ensure status is set correctly
                workflow_completed = True
                workflow_error = final_state.get('error')
        except Exception as trace_error:
            trace_err_msg = str(trace_error).lower()
            is_generator_err = "generator" in trace_err_msg and ("didn't stop" in trace_err_msg or "throw" in trace_err_msg or "stop after" in trace_err_msg)
            # Trace cleanup/operations failed - log but don't fail execution if workflow succeeded
            if workflow_completed and final_state is not None:
                logger.warning(
                    f"Trace cleanup error for execution {execution.id} (workflow completed successfully): {trace_error}"
                )
                # Suppress
            elif is_generator_err:
                logger.warning(
                    f"Trace/Langfuse generator error during workflow execution {execution.id}: {trace_error} "
                    f"(suppressing and treating as completed/no-rules)."
                )
                workflow_completed = True
                workflow_error = None
                if final_state is None:
                    final_state = initial_state
            else:
                # Workflow didn't complete or trace error happened during workflow execution
                logger.error(f"Trace error during workflow execution {execution.id}: {trace_error}")
                if final_state is None:
                    # Workflow never started or failed early - re-raise the exception
                    raise
                # Suppress so status update can proceed
        
        # Ensure execution status matches final state
        # Refresh execution from database to get latest status
        try:
            db_session.refresh(execution)
        except Exception as refresh_error:
            logger.warning(f"Error refreshing execution: {refresh_error}")
            # Rollback and get fresh copy
            try:
                db_session.rollback()
            except Exception:
                pass

        execution = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.id == execution.id
        ).first()
        
        if execution:
            # Determine final status based on final state
            # Only mark as failed if there's an actual workflow error (not trace cleanup errors)
            has_error = workflow_error is not None
            
            if has_error:
                # Actual error occurred - mark as failed
                if execution.status != 'failed':
                    execution.status = 'failed'
                    execution.error_message = workflow_error
                    execution.current_step = final_state.get('current_step', 'generate_sigma')
                    db_session.commit()
                    logger.warning(f"[Workflow {execution.id}] Marked as 'failed' due to error: {workflow_error}")
                else:
                    # Already failed, just ensure current_step is correct
                    if not execution.current_step or execution.current_step == 'promote_to_queue':
                        execution.current_step = final_state.get('current_step', 'generate_sigma')
                        db_session.commit()
            elif execution.status == 'running':
                # No error - mark as completed (even if stopped by thresholds)
                execution.status = 'completed'
                execution.completed_at = datetime.utcnow()
                execution.current_step = final_state.get('current_step', 'rank_article')
                
                db_session.commit()
                
                # Update SubagentEvaluationTable if this is an eval run
                # Do this AFTER commit to ensure execution.extraction_result is saved
                # Refresh execution to ensure we have the latest extraction_result
                db_session.refresh(execution)
                _update_subagent_eval_on_completion(execution, db_session)
                
                logger.info(f"[Workflow {execution.id}] Marked as 'completed' - workflow finished normally")
            elif execution.status == 'completed':
                # Execution already marked as completed - still update eval if needed
                # This handles cases where execution was completed elsewhere
                # Refresh execution to ensure we have the latest extraction_result
                db_session.refresh(execution)
                _update_subagent_eval_on_completion(execution, db_session)
            elif execution.status == 'failed':
                # Already marked as failed - ensure current_step is correct
                if not execution.current_step or execution.current_step == 'promote_to_queue':
                    if final_state:
                        execution.current_step = final_state.get('current_step', 'generate_sigma')
                        db_session.commit()
                        logger.info(f"[Workflow {execution.id}] Updated current_step to {execution.current_step} for failed execution")
        
        # Build minimal return dict with ONLY JSON-safe primitives
        # NEVER return ArticleTable or any ORM objects - Celery JSON serializer cannot handle SQLAlchemy models
        # Never return final_state - it contains ArticleTable and other ORM objects
        # Extract execution.id as primitive BEFORE any potential serialization issues
        execution_id_primitive = int(execution.id) if execution else None
        
        return_dict = {
            'success': final_state.get('error') is None if final_state else False,
            'execution_id': execution_id_primitive,
            'error': str(final_state.get('error')) if final_state and final_state.get('error') else None,
            # Only include safe primitive values from final_state
            'ranking_score': float(final_state.get('ranking_score')) if final_state and final_state.get('ranking_score') is not None else None,
            'discrete_huntables_count': int(final_state.get('discrete_huntables_count')) if final_state and final_state.get('discrete_huntables_count') is not None else None,
            'sigma_rules_count': int(len(final_state.get('sigma_rules', []))) if final_state and final_state.get('sigma_rules') else 0,
            'queued_rules_count': int(len(final_state.get('queued_rules', []))) if final_state and final_state.get('queued_rules') else 0,
        }
        
        # Final validation: ensure it's JSON serializable
        import json
        try:
            # Test serialization - this will catch any ORM objects
            serialized = json.dumps(return_dict)
            # Verify we can deserialize it too
            json.loads(serialized)
        except (TypeError, ValueError) as e:
            logger.error(f"Return value still contains non-serializable objects: {e}")
            logger.error(f"Return dict contents: {return_dict}")
            # Fallback: return absolute minimal safe dict with only primitives
            return {
                'success': False,
                'execution_id': execution_id_primitive,
                'error': 'Serialization error: workflow result contained non-serializable objects'
            }
        
        return return_dict
        
    except Exception as e:
        # Rollback any failed transaction
        try:
            db_session.rollback()
        except Exception as rollback_error:
            logger.warning(f"Error rolling back transaction: {rollback_error}")

        # Only mark as failed if this is NOT a trace cleanup error for a completed workflow
        # Check if execution exists and has sigma_rules (indicating workflow succeeded)
        if execution:
            # Refresh execution from database to get latest state including sigma_rules
            try:
                db_session.refresh(execution)
            except Exception as refresh_error:
                logger.warning(f"Error refreshing execution: {refresh_error}")
                # Try to get a fresh copy from database
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution.id
                ).first()

            # Check if workflow actually completed successfully despite the error
            if execution and execution.sigma_rules and len(execution.sigma_rules) > 0:
                # Workflow succeeded - don't mark as failed
                logger.warning(
                    f"Outer exception handler caught error for execution {execution.id}, "
                    f"but workflow succeeded (generated {len(execution.sigma_rules)} rules). "
                    f"Error: {e}. Not marking as failed."
                )
                # Update status to completed instead
                execution.status = 'completed'
                execution.completed_at = datetime.utcnow()
                execution.error_message = None
                db_session.commit()
                # Don't re-raise - workflow succeeded
                # Extract execution.id as primitive to avoid ORM serialization issues
                execution_id_primitive = int(execution.id) if execution else None
                return {
                    'success': True,
                    'execution_id': execution_id_primitive,
                    'error': None
                }
            else:
                # Check for generator errors - these often occur during trace cleanup
                err_msg = str(e).lower()
                if 'generator didn\'t stop' in err_msg or 'generator' in err_msg:
                    logger.warning(
                        f"Generator error for execution {execution.id}; treating as completed/no-rules. Error: {e}"
                    )
                    execution.status = 'completed'
                    execution.completed_at = datetime.utcnow()
                    execution.error_message = None
                    if not execution.current_step:
                        execution.current_step = 'generate_sigma'
                    db_session.commit()
                    # Extract execution.id as primitive to avoid ORM serialization issues
                    execution_id_primitive = int(execution.id) if execution else None
                    return {
                        'success': True,
                        'execution_id': execution_id_primitive,
                        'error': None
                    }
                else:
                    # Real workflow failure - mark as failed
                    logger.error(f"Workflow execution error for article {article_id}: {e}")
                    execution.status = 'failed'
                    execution.error_message = str(e)
                    db_session.commit()
        else:
            # No execution record - this is a real error
            logger.error(f"Workflow execution error for article {article_id}: {e}")
        
        # Return error result (sanitized) instead of raising to avoid serialization issues
        # Only re-raise if it's not a generator/trace error
        if 'generator' not in str(e).lower() and 'trace' not in str(e).lower():
            # Sanitize error message to ensure no ArticleTable references
            error_msg = str(e)
            # Extract execution.id as primitive to avoid ORM serialization issues
            execution_id_primitive = int(execution.id) if execution else None
            # Return sanitized error result instead of raising
            return {
                'success': False,
                'execution_id': execution_id_primitive,
                'error': error_msg
            }
        else:
            # Generator/trace error - return success with no rules
            # Extract execution.id as primitive to avoid ORM serialization issues
            execution_id_primitive = int(execution.id) if execution else None
            return {
                'success': True,
                'execution_id': execution_id_primitive,
                'error': None
            }
