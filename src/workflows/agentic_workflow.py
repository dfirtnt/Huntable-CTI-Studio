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
    AgenticWorkflowConfigTable
)
from src.utils.content_filter import ContentFilter
from src.services.llm_service import LLMService
from src.services.rag_service import RAGService
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.qa_agent_service import QAAgentService
from src.utils.langfuse_client import trace_workflow_execution, log_workflow_step, get_langfuse_client, is_langfuse_enabled
from src.workflows.status_utils import (
    mark_execution_completed,
    TERMINATION_REASON_RANK_THRESHOLD,
    TERMINATION_REASON_NO_SIGMA_RULES,
    TERMINATION_REASON_NON_WINDOWS_OS,
)

logger = logging.getLogger(__name__)


class WorkflowState(TypedDict):
    """State for the agentic workflow."""
    article_id: int
    execution_id: int
    article: Optional[ArticleTable]
    config: Optional[Dict[str, Any]]
    
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
            
            article = state['article']
            if not article:
                raise ValueError("Article not found in state")
            
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
    
    async def rank_article_node(state: WorkflowState) -> WorkflowState:
        """Step 2: Rank article using LLM."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 2: LLM Ranking")
            
            article = state['article']
            filtered_content = state.get('filtered_content') or article.content if article else ""
            
            if not article:
                raise ValueError("Article not found in state")
            
            # Update execution record BEFORE calling LLM (so status is accurate during long-running LLM call)
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
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
            
            max_qa_retries = 5
            qa_feedback = None
            ranking_result = None
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"
            
            # Get agent prompt for QA
            agent_prompt = "Rank the article from 1-10 for SIGMA huntability based on telemetry observables, behavioral patterns, and detection rule feasibility."
            if config_obj and config_obj.agent_prompts and "RankAgent" in config_obj.agent_prompts:
                rank_prompt_data = config_obj.agent_prompts["RankAgent"]
                if isinstance(rank_prompt_data.get("prompt"), str):
                    agent_prompt = rank_prompt_data["prompt"][:5000]  # Truncate for QA context
            
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
                    execution_id=state['execution_id'],
                    article_id=article.id,
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
            
            article = state['article']
            # OS detection runs first, so use original content
            content = article.content if article else ""
            
            if not article:
                raise ValueError("Article not found in state")
            
            # Update execution record
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            if execution:
                execution.current_step = 'os_detection'
                db_session.commit()
            
            # Import OS detection service
            from src.services.os_detection_service import OSDetectionService
            
            # Get OS detection config from workflow config
            config = state.get('config')
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
            
            article = state['article']
            filtered_content = state.get('filtered_content') or article.content if article else ""
            
            if not article:
                raise ValueError("Article not found in state")
            
            # Update execution record BEFORE calling LLM
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == state['execution_id']
            ).first()
            
            if execution:
                execution.current_step = 'extract_agent'
                db_session.commit()
            
            # Extract behaviors using sequential sub-agents and Supervisor (like LangGraph server workflow)
            logger.info(f"[Workflow {state['execution_id']}] Step 3: Extract Agent (Supervisor Mode with Sub-Agents)")
            
            config_obj = trigger_service.get_active_config()
            qa_flags = (
                config_obj.qa_enabled
                if config_obj and config_obj.qa_enabled
                else (state.get('config', {}).get('qa_enabled', {}) or {})
            )
            if not config_obj:
                raise ValueError("No active workflow configuration found")
            
            # Initialize sub-results accumulator
            subresults = {
                "cmdline": {"items": [], "count": 0},
                "sigma_queries": {"items": [], "count": 0},
                "event_ids": {"items": [], "count": 0},
                "process_lineage": {"items": [], "count": 0},
                "registry_keys": {"items": [], "count": 0}
            }
            
            # Get config models for LLMService
            agent_models = config_obj.agent_models if config_obj else None
            llm_service = LLMService(config_models=agent_models)
            
            # --- Sub-Agents (including CmdlineExtract) ---
            sub_agents = [
                ("CmdlineExtract", "cmdline", "CmdLineQA"),
                ("SigExtract", "sigma_queries", "SigQA"),
                ("EventCodeExtract", "event_ids", "EventCodeQA"),
                ("ProcTreeExtract", "process_lineage", "ProcTreeQA"),
                ("RegExtract", "registry_keys", "RegQA")
            ]
            
            prompts_dir = Path(__file__).parent.parent / "prompts"
            
            # Initialize conversation log for extract_agent
            conversation_log = []
            
            for agent_name, result_key, qa_name in sub_agents:
                try:
                    # Load Prompts
                    prompt_path = prompts_dir / agent_name
                    qa_path = prompts_dir / qa_name

                    if prompt_path.exists():
                        with open(prompt_path, 'r') as f:
                            prompt_config = json.load(f)
                    else:
                        logger.warning(f"Prompt file missing for {agent_name}, skipping")
                        continue
                        
                    qa_config = None
                    if qa_path.exists():
                        with open(qa_path, 'r') as f:
                            qa_config = json.load(f)
                    
                    # Check if QA is enabled for this agent (no master ExtractAgent toggle)
                    qa_enabled = qa_flags.get(agent_name, False) and qa_config is not None
                    
                    # Get model and temperature for this agent
                    model_key = f"{agent_name}_model"
                    temperature_key = f"{agent_name}_temperature"
                    agent_model = agent_models.get(model_key) if agent_models else None
                    if not agent_model:
                        agent_model = agent_models.get("ExtractAgent") if agent_models else None
                    agent_temperature = agent_models.get(temperature_key, 0.0) if agent_models else 0.0
                    
                    # Run Agent
                    qa_model_override = agent_models.get(qa_name) if agent_models else None
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
                        qa_model_override=qa_model_override
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
                    'sub_agents_run': [agent[0] for agent in sub_agents]
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
            
            article = state['article']
            filtered_content = state.get('filtered_content') or article.content if article else ""
            
            if not article:
                raise ValueError("Article not found in state")
            
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
            
            max_qa_retries = 5
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
            
            # Generate SIGMA rules using service
            sigma_service = SigmaGenerationService(config_models=agent_models)
            
            # Single attempt; rely on pySigma validation instead of a Sigma QA agent
            generation_result = await sigma_service.generate_sigma_rules(
                article_title=article.title,
                article_content=content_to_use,
                source_name=source_name,
                url=article.canonical_url or "",
                ai_model='lmstudio',  # Use Deepseek-R1 via LMStudio
                max_attempts=3,
                min_confidence=0.9,  # Use high confidence for filtered content
                execution_id=state['execution_id'],
                article_id=state['article_id'],
                qa_feedback=qa_feedback
            )
            
            sigma_rules = generation_result.get('rules', []) if generation_result else []
            sigma_errors = generation_result.get('errors')
            sigma_metadata = generation_result.get('metadata', {})
            
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
            logger.error(f"[Workflow {state['execution_id']}] SIGMA generation error: {e}")
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
        # Continue to similarity search if no error
        logger.info(f"[Workflow {state.get('execution_id')}] SIGMA generation succeeded, continuing to similarity search")
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
                    article = state['article']
                    
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
    
    def check_should_continue_after_rank(state: WorkflowState) -> str:
        """Check if workflow should continue after ranking."""
        if state.get('should_continue', False):
            return "extract_agent"
        else:
            return "end"
    
    # Build workflow graph
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("junk_filter", junk_filter_node)
    workflow.add_node("rank_article", rank_article_node)
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
    workflow.add_edge("junk_filter", "rank_article")
    workflow.add_conditional_edges(
        "rank_article",
        check_should_continue_after_rank,
        {
            "extract_agent": "extract_agent",
            "end": END
        }
    )
    workflow.add_edge("extract_agent", "generate_sigma")
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


async def run_workflow(article_id: int, db_session: Session) -> Dict[str, Any]:
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
        
        execution = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.article_id == article_id,
            AgenticWorkflowExecutionTable.status == 'pending'
        ).order_by(AgenticWorkflowExecutionTable.created_at.desc()).first()
        
        if not execution:
            raise ValueError(f"No pending execution found for article {article_id}")
        
        # Get config
        trigger_service = WorkflowTriggerService(db_session)
        config_obj = trigger_service.get_active_config()
        config = {
            'min_hunt_score': config_obj.min_hunt_score if config_obj else 97.0,
            'ranking_threshold': config_obj.ranking_threshold if config_obj else 6.0,
            'similarity_threshold': config_obj.similarity_threshold if config_obj else 0.5,
            'junk_filter_threshold': config_obj.junk_filter_threshold if config_obj else 0.8,
            'qa_enabled': config_obj.qa_enabled if config_obj and config_obj.qa_enabled and isinstance(config_obj.qa_enabled, dict) else {},
            'agent_models': config_obj.agent_models if config_obj and config_obj.agent_models and isinstance(config_obj.agent_models, dict) else {}
        } if config_obj else {
            'min_hunt_score': 97.0,
            'ranking_threshold': 6.0,
            'similarity_threshold': 0.5,
            'junk_filter_threshold': 0.8,
            'qa_enabled': {},
            'agent_models': {}
        }
        
        # Initialize state
        execution.status = 'running'
        execution.started_at = datetime.utcnow()
        execution.current_step = 'os_detection'
        db_session.commit()
        
        initial_state: WorkflowState = {
            'article_id': article_id,
            'execution_id': execution.id,
            'article': article,
            'config': config,
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
        
        # Create and run workflow with LangFuse tracing
        workflow_completed = False
        workflow_error = None
        final_state = None
        
        try:
            with trace_workflow_execution(execution_id=execution.id, article_id=article_id) as trace:
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
            # Trace cleanup/operations failed - log but don't fail execution if workflow succeeded
            if workflow_completed and final_state is not None:
                logger.warning(
                    f"Trace cleanup error for execution {execution.id} (workflow completed successfully): {trace_error}"
                )
                # Suppress the exception - workflow succeeded, trace cleanup is non-critical
                # This prevents the outer exception handler from marking execution as failed
                pass
            else:
                # Workflow didn't complete or trace error happened during workflow execution
                logger.error(f"Trace error during workflow execution {execution.id}: {trace_error}")
                if final_state is None:
                    # Workflow never started or failed early - re-raise the exception
                    raise
                # Workflow completed but trace cleanup failed - continue to status update
                # Suppress the exception so outer handler doesn't mark as failed
                pass
        
        # Ensure execution status matches final state
        # Refresh execution from database to get latest status
        db_session.refresh(execution)
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
                logger.info(f"[Workflow {execution.id}] Marked as 'completed' - workflow finished normally")
            elif execution.status == 'failed':
                # Already marked as failed - ensure current_step is correct
                if not execution.current_step or execution.current_step == 'promote_to_queue':
                    if final_state:
                        execution.current_step = final_state.get('current_step', 'generate_sigma')
                        db_session.commit()
                        logger.info(f"[Workflow {execution.id}] Updated current_step to {execution.current_step} for failed execution")
        
        return {
            'success': final_state.get('error') is None if final_state else False,
            'execution_id': execution.id,
            'final_state': final_state,
            'error': final_state.get('error') if final_state else None
        }
        
    except Exception as e:
        # Only mark as failed if this is NOT a trace cleanup error for a completed workflow
        # Check if execution exists and has sigma_rules (indicating workflow succeeded)
        if execution:
            # Refresh execution from database to get latest state including sigma_rules
            db_session.refresh(execution)
            # Check if workflow actually completed successfully despite the error
            if execution.sigma_rules and len(execution.sigma_rules) > 0:
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
                return
            else:
                # Check for generator errors - these often occur during trace cleanup
                if 'generator didn\'t stop' in str(e).lower() or 'generator' in str(e).lower():
                    logger.warning(
                        f"Generator error for execution {execution.id}, "
                        f"no sigma rules found. Error: {e}"
                    )
                    # For generator errors without rules, mark as failed but don't re-raise
                    execution.status = 'failed'
                    execution.error_message = str(e)
                    db_session.commit()
                    return
                else:
                    # Real workflow failure - mark as failed
                    logger.error(f"Workflow execution error for article {article_id}: {e}")
                    execution.status = 'failed'
                    execution.error_message = str(e)
                    db_session.commit()
        else:
            # No execution record - this is a real error
            logger.error(f"Workflow execution error for article {article_id}: {e}")
        
        # Only re-raise if it's not a generator/trace error
        if 'generator' not in str(e).lower() and 'trace' not in str(e).lower():
            raise
