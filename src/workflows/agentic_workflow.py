"""
Agentic Workflow using LangGraph for processing high-hunt-score articles.

This workflow processes articles through 6 steps:
0. Junk Filter
1. LLM Rank Article
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

from src.database.models import (
    ArticleTable, AgenticWorkflowExecutionTable, SigmaRuleQueueTable,
    AgenticWorkflowConfigTable
)
from src.utils.content_filter import ContentFilter
from src.services.llm_service import LLMService
from src.services.rag_service import RAGService
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.utils.langfuse_client import trace_workflow_execution, log_workflow_step
from src.workflows.status_utils import (
    mark_execution_completed,
    TERMINATION_REASON_RANK_THRESHOLD,
    TERMINATION_REASON_NO_SIGMA_RULES,
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
        """Step 0: Filter content using conservative junk filter."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 0: Junk Filter")
            
            article = state['article']
            if not article:
                raise ValueError("Article not found in state")
            
            # Validate article content
            if not article.content or len(article.content.strip()) == 0:
                raise ValueError(f"Article {article.id} has no content to filter")
            
            # Get junk filter threshold from config
            junk_filter_threshold = state['config'].get('junk_filter_threshold', 0.8) if state.get('config') else 0.8
            
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
        """Step 1: Rank article using LLM."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 1: LLM Ranking")
            
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
            agent_models = config_obj.agent_models if config_obj else None
            llm_service = LLMService(config_models=agent_models)
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"
            
            # Rank article using LLM
            ranking_result = await llm_service.rank_article(
                title=article.title,
                content=filtered_content,
                source=source_name,
                url=article.canonical_url or "",
                execution_id=state['execution_id'],
                article_id=article.id
            )
            
            ranking_score = ranking_result['score']
            ranking_threshold = state['config'].get('ranking_threshold', 6.0) if state.get('config') else 6.0
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
    
    async def extract_agent_node(state: WorkflowState) -> WorkflowState:
        """Step 2: Extract behaviors using ExtractAgent."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 2: Extract Agent")
            
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
            
            # Extract behaviors using ExtractAgent prompt
            # Must use database prompt from config - no fallback
            config_obj = trigger_service.get_active_config()
            if not config_obj:
                raise ValueError("No active workflow configuration found")
            
            if not config_obj.agent_prompts or "ExtractAgent" not in config_obj.agent_prompts:
                raise ValueError(f"ExtractAgent prompt not found in workflow config (version {config_obj.version}). Please configure it in the workflow settings.")
            
            agent_prompt_data = config_obj.agent_prompts["ExtractAgent"]
            
            # Parse prompt JSON (stored as string in database)
            prompt_config_dict = None
            if isinstance(agent_prompt_data.get("prompt"), str):
                prompt_str = agent_prompt_data["prompt"].strip()
                try:
                    prompt_config_dict = json.loads(prompt_str)
                    # Handle nested JSON structure if present
                    if isinstance(prompt_config_dict, dict) and len(prompt_config_dict) == 1:
                        # If it's a dict with one key, might be nested - try unwrapping
                        first_value = next(iter(prompt_config_dict.values()))
                        if isinstance(first_value, dict):
                            prompt_config_dict = first_value
                        elif isinstance(first_value, str):
                            # Try parsing the inner string as JSON
                            try:
                                prompt_config_dict = json.loads(first_value)
                            except:
                                pass
                except json.JSONDecodeError as e:
                    # Try to fix double-wrapped JSON (starts with "{\n  {" or "{{")
                    # Find the second opening brace and extract from there
                    if prompt_str.startswith('{\n  {') or prompt_str.startswith('{{'):
                        # Find the second opening brace
                        second_brace_idx = prompt_str.find('{', 1)
                        if second_brace_idx > 0:
                            # Extract from second brace to matching closing brace
                            brace_count = 0
                            for i in range(second_brace_idx, len(prompt_str)):
                                if prompt_str[i] == '{':
                                    brace_count += 1
                                elif prompt_str[i] == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        # Found matching closing brace
                                        inner_json = prompt_str[second_brace_idx:i + 1]
                                        try:
                                            prompt_config_dict = json.loads(inner_json)
                                            logger.info(f"[Workflow {state['execution_id']}] Successfully unwrapped double-wrapped JSON prompt")
                                            break
                                        except json.JSONDecodeError as e2:
                                            raise ValueError(f"Failed to parse unwrapped prompt JSON: {e2}")
                            if prompt_config_dict is None:
                                raise ValueError(f"Failed to parse ExtractAgent prompt JSON: {e}")
                        else:
                            raise ValueError(f"Failed to parse ExtractAgent prompt JSON: {e}")
                    else:
                        raise ValueError(f"Failed to parse ExtractAgent prompt JSON: {e}")
            elif isinstance(agent_prompt_data.get("prompt"), dict):
                prompt_config_dict = agent_prompt_data["prompt"]
            else:
                raise ValueError("ExtractAgent prompt is not in valid format (expected string or dict)")
            
            instructions_template_str = agent_prompt_data.get("instructions")
            if not instructions_template_str:
                raise ValueError("ExtractAgent instructions template not found in workflow config")
            
            if not prompt_config_dict:
                raise ValueError("ExtractAgent prompt config is empty")
            
            logger.info(f"[Workflow {state['execution_id']}] Using database ExtractAgent prompt (config version {config_obj.version})")
            
            # Get config models for LLMService
            agent_models = config_obj.agent_models if config_obj else None
            llm_service = LLMService(config_models=agent_models)
            
            # Use database prompt
            extraction_result = await llm_service.extract_behaviors(
                content=filtered_content,
                title=article.title,
                url=article.canonical_url or "",
                prompt_config_dict=prompt_config_dict,
                instructions_template_str=instructions_template_str,
                execution_id=state['execution_id'],
                article_id=article.id
            )
            
            discrete_count = extraction_result.get('discrete_huntables_count', 0)
            
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
            agent_models = config_obj.agent_models if config_obj else None
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"
            
            # Generate SIGMA rules using service
            sigma_service = SigmaGenerationService(config_models=agent_models)
            generation_result = await sigma_service.generate_sigma_rules(
                article_title=article.title,
                article_content=filtered_content,
                source_name=source_name,
                url=article.canonical_url or "",
                ai_model='lmstudio',  # Use Deepseek-R1 via LMStudio
                max_attempts=3,
                min_confidence=0.9,  # Use high confidence for filtered content
                execution_id=state['execution_id'],
                article_id=state['article_id']
            )
            
            sigma_rules = generation_result.get('rules', [])
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
            similarity_threshold = state['config'].get('similarity_threshold', 0.5) if state.get('config') else 0.5
            
            # Search for similar rules for each generated rule
            for rule in sigma_rules:
                # Create query text from rule title and description
                query_text = f"{rule.get('title', '')} {rule.get('description', '')}"
                
                # Find similar rules
                similar_rules = await rag_service.find_similar_sigma_rules(
                    query=query_text,
                    top_k=10,
                    threshold=similarity_threshold
                )
                
                rule_similarities = [r['similarity'] for r in similar_rules]
                rule_max_sim = max(rule_similarities) if rule_similarities else 0.0
                
                similarity_results.append({
                    'rule_title': rule.get('title'),
                    'similar_rules': similar_rules,
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
            similarity_threshold = state['config'].get('similarity_threshold', 0.5) if state.get('config') else 0.5
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
    
    def check_should_continue(state: WorkflowState) -> str:
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
    workflow.add_node("extract_agent", extract_agent_node)
    workflow.add_node("generate_sigma", generate_sigma_node)
    workflow.add_node("similarity_search", similarity_search_node)
    workflow.add_node("promote_to_queue", promote_to_queue_node)
    
    # Define edges
    workflow.set_entry_point("junk_filter")
    workflow.add_edge("junk_filter", "rank_article")
    workflow.add_conditional_edges(
        "rank_article",
        check_should_continue,
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
            'junk_filter_threshold': config_obj.junk_filter_threshold if config_obj else 0.8
        } if config_obj else {
            'min_hunt_score': 97.0,
            'ranking_threshold': 6.0,
            'similarity_threshold': 0.5,
            'junk_filter_threshold': 0.8
        }
        
        # Initialize state
        execution.status = 'running'
        execution.started_at = datetime.utcnow()
        execution.current_step = 'junk_filter'
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
            'extraction_result': None,
            'discrete_huntables_count': None,
            'sigma_rules': None,
            'similarity_results': None,
            'max_similarity': None,
            'queued_rules': None,
            'error': None,
            'current_step': 'junk_filter',
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
