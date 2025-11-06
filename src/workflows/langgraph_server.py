"""
LangGraph server integration for agentic workflow.

This module exposes the workflow via LangGraph's HTTP server for use with
Agent Chat UI, enabling debugging, state inspection, and time-travel debugging.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, TypedDict, Annotated
from datetime import datetime

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage
import json

from src.database.manager import DatabaseManager
from src.database.models import (
    ArticleTable, AgenticWorkflowExecutionTable, SigmaRuleQueueTable,
    AgenticWorkflowConfigTable
)
from src.utils.content_filter import ContentFilter
from src.services.llm_service import LLMService
from src.services.rag_service import RAGService
from src.services.sigma_generation_service import SigmaGenerationService
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.workflows.status_utils import (
    mark_execution_completed,
    TERMINATION_REASON_RANK_THRESHOLD,
    TERMINATION_REASON_NO_SIGMA_RULES,
)

logger = logging.getLogger(__name__)


class ExposableWorkflowState(TypedDict, total=False):
    """State for the exposable workflow (checkpoint-compatible)."""
    article_id: Optional[int]  # Optional initially, set by parse_input_node
    execution_id: Optional[int]
    
    # Chat messages (from Agent Chat UI)
    messages: Optional[list]  # List of message objects from chat
    
    # Direct input (from API/structured calls)
    input: Optional[Dict[str, Any]]  # Direct structured input
    
    # Configuration (optional, will use defaults if not provided)
    min_hunt_score: Optional[float]
    ranking_threshold: Optional[float]
    similarity_threshold: Optional[float]
    
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
    error_log: Optional[Dict[str, Any]]
    current_step: str
    status: str  # pending, running, completed, failed
    termination_reason: Optional[str]
    termination_details: Optional[Dict[str, Any]]


def get_db_session():
    """Get database session (called from nodes)."""
    db_manager = DatabaseManager()
    return db_manager.get_session()


def create_exposable_workflow():
    """
    Create LangGraph workflow exposed via LangGraph server.
    
    This version uses checkpointing and can be accessed via Agent Chat UI.
    
    Returns:
        Compiled LangGraph workflow with checkpointing
    """
    # Initialize services (shared across nodes)
    content_filter = ContentFilter()
    # LLMService and SigmaGenerationService will be initialized per-node with config models
    logger.info(f"LLMStudio URL: {os.getenv('LMSTUDIO_API_URL', 'http://host.docker.internal:1234/v1')}")
    # RAGService lazy-loaded in similarity_search_node to avoid loading embedding models at startup
    
    def parse_input_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Parse chat input and initialize workflow state."""
        try:
            # Get the latest message content
            messages = state.get("messages", [])
            last_message_content = ""
            if messages:
                last_message = messages[-1]
                if isinstance(last_message, dict):
                    last_message_content = last_message.get("content", "").strip().lower()
                elif hasattr(last_message, "content"):
                    last_message_content = last_message.content.strip().lower()
                else:
                    last_message_content = str(last_message).strip().lower()
            
            # Handle conversational queries (no article_id needed)
            conversational_keywords = ["hi", "hello", "help", "what", "how"]
            is_conversational = (
                last_message_content and 
                any(keyword in last_message_content for keyword in conversational_keywords) and 
                not any(char.isdigit() for char in last_message_content) and
                "article" not in last_message_content
            )
            
            if is_conversational:
                # Return conversational response immediately
                response_text = """👋 Hello! I'm the Agentic Workflow agent for threat intelligence processing.

**To process an article, send:**
- `article 1988` (replace 1988 with your article ID)
- `process article 1988`
- `{"article_id": 1988}`

**What I do:**
1. Filter junk content
2. Rank article for huntability (1-10)
3. Extract huntable behaviors
4. Generate SIGMA detection rules
5. Check similarity against existing rules
6. Queue new rules for human review

**Example:** Send `article 1988` to process article #1988 through the workflow."""
                
                # Return AIMessage for chat UI - this will end the workflow immediately
                return {
                    **state,
                    "messages": [
                        *state.get("messages", []),
                        AIMessage(content=response_text)
                    ],
                    "status": "completed",
                    "current_step": "conversational_response",
                    "article_id": None,  # No article processing needed
                    "termination_reason": None,
                    "termination_details": None
                }
            
            # Priority 1: Direct article_id in state (from API/structured input)
            article_id = state.get("article_id")
            
            # Priority 2: Extract from messages (from Agent Chat UI)
            if not article_id and messages:
                # Extract the last human message
                last_message = messages[-1] if messages else None
                content = ""
                
                if isinstance(last_message, dict):
                    content = last_message.get("content", "")
                elif hasattr(last_message, "content"):
                    content = last_message.content
                elif isinstance(last_message, str):
                    content = last_message
                else:
                    content = str(last_message)
                
                # Try to parse JSON from message
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "article_id" in parsed:
                        article_id = parsed["article_id"]
                except json.JSONDecodeError:
                    pass
                
                # If not JSON, try to extract article_id from text
                if not article_id:
                    import re
                    # Try patterns like "article 1988", "article_id: 1988", "1988"
                    match = re.search(r'article[_\s]*id[:\s]*(\d+)', content, re.IGNORECASE)
                    if match:
                        article_id = int(match.group(1))
                    else:
                        # Try to find any number in the message (assume it's article_id)
                        numbers = re.findall(r'\d+', content)
                        if numbers:
                            article_id = int(numbers[-1])  # Use last number found
                            logger.info(f"Extracted article_id {article_id} from message: {content[:100]}")
            
            # Priority 3: Try to get from state input (fallback)
            if not article_id:
                # Check if input was passed directly
                input_data = state.get("input", {})
                if isinstance(input_data, dict):
                    article_id = input_data.get("article_id")
            
            if not article_id:
                # Return helpful error message instead of raising
                error_msg = """❌ No article ID found in your message.

**Please send:**
- `article 1988` (replace 1988 with your article ID)
- `process article 1988`
- `{"article_id": 1988}`

**Need help?** Send `help` or `hi` for more information."""
                
                return {
                    **state,
                    "messages": [
                        *state.get("messages", []),
                        AIMessage(content=error_msg)
                    ],
                    "status": "failed",
                    "error": "No article_id found",
                    "current_step": "parse_input"
                }
            
            # Get or create execution
            db_session = get_db_session()
            try:
                # Always create a new execution for chat-based workflows
                # (State might persist across threads, so don't reuse execution_id from state)
                # Get config for defaults
                trigger_service = WorkflowTriggerService(db_session)
                config = trigger_service.get_active_config()
                
                # Validate article exists and has content before creating execution
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                if not article:
                    error_msg = f"""❌ Article {article_id} not found in database.

Please verify the article ID is correct."""
                    return {
                        **state,
                        "messages": [
                            *state.get("messages", []),
                            AIMessage(content=error_msg)
                        ],
                        "status": "failed",
                        "error": f"Article {article_id} not found",
                        "current_step": "parse_input"
                    }
                
                if not article.content or len(article.content.strip()) == 0:
                    error_msg = f"""❌ Article {article_id} has no content.

Cannot process empty articles."""
                    return {
                        **state,
                        "messages": [
                            *state.get("messages", []),
                            AIMessage(content=error_msg)
                        ],
                        "status": "failed",
                        "error": f"Article {article_id} has no content",
                        "current_step": "parse_input"
                    }
                
                # Get agent models from config
                agent_models = config.agent_models if config else None
                
                # Create new execution
                execution = AgenticWorkflowExecutionTable(
                    article_id=article_id,
                    status='pending',
                    config_snapshot={
                        'min_hunt_score': config.min_hunt_score if config else 97.0,
                        'ranking_threshold': config.ranking_threshold if config else 6.0,
                        'similarity_threshold': config.similarity_threshold if config else 0.5,
                        'junk_filter_threshold': config.junk_filter_threshold if config else 0.8,
                        'agent_models': agent_models
                    } if config else None
                )
                db_session.add(execution)
                db_session.commit()
                db_session.refresh(execution)
                execution_id = execution.id
                logger.info(f"Created execution {execution_id} for article {article_id} (content length: {len(article.content)})")
                
                # Get config values with proper defaults
                min_score = state.get("min_hunt_score") or (config.min_hunt_score if config else 97.0)
                rank_threshold = state.get("ranking_threshold") or (config.ranking_threshold if config else 6.0)
                sim_threshold = state.get("similarity_threshold") or (config.similarity_threshold if config else 0.5)
                junk_filter_threshold = state.get("junk_filter_threshold") or (config.junk_filter_threshold if config else 0.8)
                
                return {
                    **state,
                    "article_id": article_id,
                    "execution_id": execution_id,
                    "min_hunt_score": min_score,
                    "ranking_threshold": rank_threshold,
                    "similarity_threshold": sim_threshold,
                    "junk_filter_threshold": junk_filter_threshold,
                    "status": "pending",
                    "current_step": "parse_input",
                    "should_continue": True,
                    "termination_reason": None,
                    "termination_details": None,
                    # Initialize with article content (will be filtered in junk_filter_node)
                    "filtered_content": None,  # Will be set by junk_filter_node
                    "junk_filter_result": None,
                    "ranking_score": None,
                    "ranking_reasoning": None,
                    "extraction_result": None,
                    "discrete_huntables_count": None,
                    "sigma_rules": None,
                    "similarity_results": None,
                    "max_similarity": None,
                    "queued_rules": None,
                    "error": None,
                    "error_log": None
                }
            finally:
                db_session.close()
                
        except Exception as e:
            logger.error(f"Parse input error: {e}")
            return {
                **state,
                "error": str(e),
                "status": "failed",
                "current_step": "parse_input"
            }
    
    def junk_filter_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Step 0: Filter content using conservative junk filter."""
        db_session = get_db_session()
        try:
            logger.info(f"[Workflow {state.get('execution_id')}] Step 0: Junk Filter")
            
            article_id = state['article_id']
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                raise ValueError(f"Article {article_id} not found")
            
            # Get junk filter threshold from state or config
            junk_filter_threshold = state.get('junk_filter_threshold', 0.8)
            
            # Use configured filter threshold
            filter_result = content_filter.filter_content(
                article.content,
                min_confidence=junk_filter_threshold,
                hunt_score=article.article_metadata.get('threat_hunting_score', 0) if article.article_metadata else 0,
                article_id=article.id
            )
            
            # Update or create execution record
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
            else:
                # Get agent models from config
                trigger_service = WorkflowTriggerService(db_session)
                config_obj = trigger_service.get_active_config()
                agent_models = config_obj.agent_models if config_obj else None
                
                # Create new execution
                execution = AgenticWorkflowExecutionTable(
                    article_id=article_id,
                    status='running',
                    started_at=datetime.utcnow(),
                    config_snapshot={
                        'min_hunt_score': state.get('min_hunt_score', 97.0),
                        'ranking_threshold': state.get('ranking_threshold', 6.0),
                        'similarity_threshold': state.get('similarity_threshold', 0.5),
                        'junk_filter_threshold': state.get('junk_filter_threshold', 0.8),
                        'agent_models': agent_models
                    }
                )
                db_session.add(execution)
                db_session.commit()
                db_session.refresh(execution)
                execution_id = execution.id
            
            if execution:
                execution.current_step = 'junk_filter'
                execution.junk_filter_result = {
                    'filtered_length': len(filter_result.filtered_content) if filter_result.filtered_content else 0,
                    'original_length': len(article.content),
                    'chunks_kept': len(filter_result.removed_chunks) if filter_result.removed_chunks else 0,  # Note: removed_chunks contains removed items, but we track kept separately
                    'chunks_removed': len(filter_result.removed_chunks) if filter_result.removed_chunks else 0,
                    'is_huntable': filter_result.is_huntable,
                    'confidence': filter_result.confidence
                }
                db_session.commit()
            
            return {
                **state,
                'execution_id': execution_id,
                'filtered_content': filter_result.filtered_content or article.content,
                'junk_filter_result': execution.junk_filter_result if execution else None,
                'current_step': 'junk_filter',
                'status': 'running',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] Junk filter error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'junk_filter': str(e)},
                'current_step': 'junk_filter',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
        finally:
            db_session.close()
    
    async def rank_article_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Step 1: Rank article using LLM."""
        db_session = get_db_session()
        try:
            logger.info(f"[Workflow {state.get('execution_id')}] Step 1: LLM Ranking")
            
            article_id = state['article_id']
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                raise ValueError(f"Article {article_id} not found")
            
            filtered_content = state.get('filtered_content') or article.content
            
            # Get config models for LLMService
            trigger_service = WorkflowTriggerService(db_session)
            config_obj = trigger_service.get_active_config()
            agent_models = config_obj.agent_models if config_obj else None
            llm_service = LLMService(config_models=agent_models)
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"
            
            # Rank article using LLM
            # Use relative path for prompt (works in Docker and local)
            prompt_file = Path(__file__).parent.parent / "prompts" / "lmstudio_sigma_ranking.txt"
            ranking_result = await llm_service.rank_article(
                title=article.title,
                content=filtered_content,
                source=source_name,
                url=article.canonical_url or "",
                prompt_template_path=str(prompt_file) if prompt_file.exists() else None
            )
            
            ranking_score = ranking_result['score']
            ranking_threshold = state.get('ranking_threshold', 6.0)
            should_continue = ranking_score >= ranking_threshold
            
            # Validate ranking result has non-empty response
            ranking_reasoning = ranking_result.get('reasoning', '')
            raw_response = ranking_result.get('raw_response', '')
            if not raw_response or len(raw_response.strip()) == 0:
                raise ValueError("Ranking returned empty response - LLM did not provide valid output")
            
            termination_reason = state.get('termination_reason')
            termination_details = state.get('termination_details')

            # Update execution record
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                
                if execution:
                    execution.current_step = 'rank_article'
                    execution.ranking_score = ranking_score
                    execution.ranking_reasoning = ranking_reasoning  # Store full reasoning
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
            
            logger.info(f"[Workflow {execution_id}] Ranking: {ranking_score}/10 (threshold: {ranking_threshold}), continue: {should_continue}")
            
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
            logger.error(f"[Workflow {state.get('execution_id')}] Ranking error: {e}")
            
            # Update execution record on error
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                if execution:
                    execution.current_step = 'rank_article'
                    execution.status = 'failed'
                    # Don't set ranking_score on error - keep it NULL
                    db_session.commit()
            
            return {
                **state,
                'ranking_score': None,  # Clear score on error
                'ranking_reasoning': None,  # Clear reasoning on error
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'rank_article': str(e)},
                'current_step': 'rank_article',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
        finally:
            db_session.close()
    
    async def extract_agent_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Step 2: Extract behaviors using Extract Agent."""
        db_session = get_db_session()
        try:
            logger.info(f"[Workflow {state.get('execution_id')}] Step 2: Extract Agent")
            
            article_id = state['article_id']
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                raise ValueError(f"Article {article_id} not found")
            
            filtered_content = state.get('filtered_content') or article.content
            
            # Extract behaviors using ExtractAgent prompt
            # Must use database prompt from config - no fallback
            trigger_service = WorkflowTriggerService(db_session)
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
                                            logger.info(f"[Workflow {state.get('execution_id')}] Successfully unwrapped double-wrapped JSON prompt")
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
            
            logger.info(f"[Workflow {state.get('execution_id')}] Using database ExtractAgent prompt (config version {config_obj.version})")
            
            # Get config models for LLMService
            agent_models = config_obj.agent_models if config_obj else None
            llm_service = LLMService(config_models=agent_models)
            
            # Use database prompt
            extraction_result = await llm_service.extract_behaviors(
                content=filtered_content,
                title=article.title,
                url=article.canonical_url or "",
                prompt_config_dict=prompt_config_dict,
                instructions_template_str=instructions_template_str
            )
            
            discrete_huntables = extraction_result.get('discrete_huntables_count', 0)
            
            # Fail if extraction result is invalid or empty
            raw_response = extraction_result.get('raw_response', '')
            if not raw_response or len(raw_response.strip()) == 0:
                error_msg = "Extraction returned empty response - LLM did not provide valid output"
                logger.error(f"[Workflow {state.get('execution_id')}] {error_msg}")
                raise ValueError(error_msg)
            
            # Log extraction quality for debugging
            logger.info(f"[Workflow {state.get('execution_id')}] Extraction completed: {discrete_huntables} huntables, {len(extraction_result.get('observables', []))} observables")
            
            # Update execution record
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                
                if execution:
                    execution.current_step = 'extract_agent'
                    execution.extraction_result = extraction_result
                    db_session.commit()
            
            return {
                **state,
                'extraction_result': extraction_result,
                'discrete_huntables_count': discrete_huntables,
                'current_step': 'extract_agent',
                'status': 'running',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] Extract agent error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'extract_agent': str(e)},
                'current_step': 'extract_agent',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
        finally:
            db_session.close()
    
    async def generate_sigma_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Step 3: Generate SIGMA rules."""
        db_session = get_db_session()
        try:
            logger.info(f"[Workflow {state.get('execution_id')}] Step 3: Generate SIGMA")
            
            article_id = state['article_id']
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                raise ValueError(f"Article {article_id} not found")
            
            extraction_result = state.get('extraction_result', {})
            filtered_content = state.get('filtered_content') or article.content
            
            # Use extraction_result content if available and has huntables, otherwise use filtered_content
            content_to_use = filtered_content
            if extraction_result and extraction_result.get('discrete_huntables_count', 0) > 0:
                # Prefer extracted content if we have meaningful huntables
                extracted_content = extraction_result.get('content', '')
                if extracted_content and len(extracted_content) > 100:
                    content_to_use = extracted_content
                    logger.info(f"[Workflow {state.get('execution_id')}] Using extracted content ({len(extracted_content)} chars) for SIGMA generation")
                else:
                    logger.warning(f"[Workflow {state.get('execution_id')}] Extraction result has {extraction_result.get('discrete_huntables_count', 0)} huntables but no usable content, using filtered_content")
            else:
                logger.warning(f"[Workflow {state.get('execution_id')}] No extraction result or zero huntables, using filtered_content for SIGMA generation")
            
            # Get config models for SigmaGenerationService
            trigger_service = WorkflowTriggerService(db_session)
            config_obj = trigger_service.get_active_config()
            agent_models = config_obj.agent_models if config_obj else None
            
            # Generate SIGMA rules
            source_name = article.source.name if article.source else "Unknown"
            sigma_service = SigmaGenerationService(config_models=agent_models)
            sigma_result = await sigma_service.generate_sigma_rules(
                article_title=article.title,
                article_content=content_to_use,
                source_name=source_name,
                url=article.canonical_url or "",
                ai_model='lmstudio'
            )
            
            sigma_rules = sigma_result.get('rules', [])
            sigma_errors = sigma_result.get('errors')
            sigma_metadata = sigma_result.get('metadata', {})
            
            # Store detailed error info in error_log for debugging
            error_log_entry = None
            if sigma_metadata.get('validation_results'):
                error_log_entry = {
                    'errors': sigma_errors,
                    'total_attempts': sigma_metadata.get('total_attempts', 0),
                    'validation_results': sigma_metadata.get('validation_results', []),
                    'conversation_log': sigma_metadata.get('conversation_log', []) if 'conversation_log' in sigma_metadata else None
                }
            
            # Update execution record
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                
                if execution:
                    execution.current_step = 'generate_sigma'
                    execution.sigma_rules = sigma_rules
                    
                    # Check if SIGMA validation failed (no valid rules generated)
                    # Check both errors field and metadata validation results
                    validation_failed = (
                        not sigma_rules and sigma_errors
                    ) or (
                        sigma_metadata.get('valid_rules', 0) == 0 and 
                        sigma_metadata.get('validation_results') and
                        not any(r.get('is_valid', False) for r in sigma_metadata.get('validation_results', []))
                    )
                    
                    # Always store error_log_entry if validation_results exist (for conversation log display)
                    if error_log_entry:
                        execution.error_log = {**(execution.error_log or {}), 'generate_sigma': error_log_entry}
                    
                    if validation_failed:
                        error_msg = sigma_errors or "SIGMA validation failed: No valid rules generated after all attempts"
                        execution.status = 'failed'
                        execution.error_message = error_msg
                        db_session.commit()
                        logger.error(f"[Workflow {execution_id}] SIGMA validation failed: {error_msg}")
                        
                        # CRITICAL: Raise exception to force workflow stop
                        # LangGraph will catch this and stop execution, preventing routing issues
                        raise ValueError(f"SIGMA validation failed: {error_msg}")
                    
                    db_session.commit()
            
            return {
                **state,
                'sigma_rules': sigma_rules,
                'current_step': 'generate_sigma',
                'status': 'running',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] SIGMA generation error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'generate_sigma': str(e)},
                'current_step': 'generate_sigma',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
        finally:
            db_session.close()
    
    async def similarity_search_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Step 4: Similarity search against existing SIGMA rules."""
        import yaml
        db_session = get_db_session()
        try:
            logger.info(f"[Workflow {state.get('execution_id')}] Step 4: Similarity Search")
            
            # Check if workflow already failed (e.g., SIGMA validation failed)
            if state.get('error') or state.get('status') == 'failed':
                logger.warning(f"[Workflow {state.get('execution_id')}] Workflow has error/failed status, skipping similarity search")
                execution_id = state.get('execution_id')
                if execution_id:
                    execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                        AgenticWorkflowExecutionTable.id == execution_id
                    ).first()
                    if execution and execution.status != 'failed':
                        execution.status = 'failed'
                        execution.current_step = state.get('current_step', 'generate_sigma')
                        execution.error_message = execution.error_message or state.get('error') or "SIGMA generation failed"
                        db_session.commit()
                
                return {
                    **state,
                    'similarity_results': [],
                    'max_similarity': 1.0,
                    'current_step': state.get('current_step', 'generate_sigma'),
                    'status': 'failed',
                    'termination_reason': state.get('termination_reason'),
                    'termination_details': state.get('termination_details')
                }
            
            # Lazy-load RAGService only when similarity search runs (to avoid loading embedding models at startup)
            rag_service = RAGService()
            
            sigma_rules = state.get('sigma_rules', [])
            
            if not sigma_rules or len(sigma_rules) == 0:
                logger.info(f"[Workflow {state.get('execution_id')}] No SIGMA rules generated; skipping similarity search")
                return {
                    **state,
                    'similarity_results': [],
                    'max_similarity': 0.0,
                    'current_step': 'similarity_search',
                    'status': state.get('status', 'running'),
                    'termination_reason': state.get('termination_reason'),
                    'termination_details': state.get('termination_details')
                }
            
            similarity_results = []
            
            for rule in sigma_rules:
                # Create query from rule title and description (as used in agentic_workflow.py)
                query_text = f"{rule.get('title', '')} {rule.get('description', '')}"
                similar = await rag_service.find_similar_sigma_rules(
                    query=query_text,
                    top_k=10
                )
                similarity_results.append({
                    'max_similarity': max([s.get('similarity', 0.0) for s in similar], default=0.0),
                    'similar_rules': similar
                })
            
            max_sim = max([r.get('max_similarity', 0.0) for r in similarity_results], default=0.0)
            
            # Update execution record
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                
                if execution:
                    # Only update current_step if workflow didn't fail earlier
                    if execution.status != 'failed':
                        execution.current_step = 'similarity_search'
                    execution.similarity_results = similarity_results
                    db_session.commit()
            
            return {
                **state,
                'similarity_results': similarity_results,
                'max_similarity': max_sim,
                'current_step': 'similarity_search',
                'status': 'running',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] Similarity search error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'similarity_search': str(e)},
                'current_step': 'similarity_search',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
        finally:
            db_session.close()
    
    async def generate_response_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Generate a chat-friendly response summarizing workflow results."""
        try:
            execution_id = state.get("execution_id")
            article_id = state.get("article_id")
            status = state.get("status", "unknown")
            termination_reason = state.get("termination_reason")
            termination_details = state.get("termination_details") or {}
            
            if status == "completed":
                if termination_reason == TERMINATION_REASON_RANK_THRESHOLD:
                    ranking_score = termination_details.get("ranking_score", state.get("ranking_score", 0))
                    ranking_threshold = termination_details.get("ranking_threshold", state.get("ranking_threshold", 6.0))
                    response_text = f"""⚠️ **Workflow completed early: article was below huntability threshold**

**Article #{article_id}** received a huntability score of **{ranking_score:.1f}/10**, below the configured threshold of **{ranking_threshold:.1f}/10**.

The workflow stopped after ranking (no extraction or SIGMA generation was attempted) and marked the execution as completed."""
                elif termination_reason == TERMINATION_REASON_NO_SIGMA_RULES:
                    response_text = f"""ℹ️ **Workflow completed without generating SIGMA rules**

No detection rules were produced for **article #{article_id}**. Review extraction output to confirm sufficient huntable behaviors are present before retrying.

The execution finished normally and recorded all intermediate results."""
                else:
                    # Build success summary
                    ranking_score = state.get("ranking_score", 0)
                    discrete_count = state.get("discrete_huntables_count", 0)
                    sigma_count = len(state.get("sigma_rules", []))
                    queued_count = len(state.get("queued_rules", []))
                    max_sim = state.get("max_similarity", 0)
                    
                    response_text = f"""✅ **Workflow completed for article #{article_id}**

**Results:**
- **Huntability Score**: {ranking_score:.1f}/10
- **Discrete Huntables**: {discrete_count}
- **SIGMA Rules Generated**: {sigma_count}
- **Rules Queued**: {queued_count}
- **Max Similarity**: {max_sim:.2%}

"""
                
                    if queued_count > 0:
                        response_text += f"🎯 **{queued_count} new rule(s) queued for human review.**\n\n"
                        response_text += "You can view and approve them in the Workflow > SIGMA Queue tab.\n"
                    elif sigma_count > 0:
                        response_text += f"⚠️ All {sigma_count} generated rule(s) were similar to existing rules (similarity > threshold).\n"
                    else:
                        response_text += "ℹ️ No SIGMA rules were generated.\n"
                
                response_text += f"\n**Execution ID**: {execution_id}\n"
                response_text += "View full details in the Workflow > Executions tab."
            
            elif status == "failed":
                # Generic error message for failures
                error_msg = state.get("error", "Unknown error")
                response_text = f"""❌ **Workflow failed for article #{article_id}**

**Error**: {error_msg}

**Execution ID**: {execution_id}
Check the Workflow > Executions tab for detailed error logs."""
            
            else:
                response_text = f"⏳ Workflow status: {status} for article #{article_id}"
            
            return {
                **state,
                "messages": [
                    *state.get("messages", []),
                    AIMessage(content=response_text)
                ]
            }
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {
                **state,
                "messages": [
                    *state.get("messages", []),
                    AIMessage(content=f"Error generating response: {str(e)}")
                ]
            }
    
    async def promote_to_queue_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Step 5: Promote low-similarity rules to queue."""
        import yaml
        db_session = get_db_session()
        try:
            logger.info(f"[Workflow {state.get('execution_id')}] Step 5: Promote to Queue")
            
            # CRITICAL: Stop early if workflow already failed (e.g., SIGMA validation failed)
            if state.get('error') or state.get('status') == 'failed':
                logger.warning(f"[Workflow {state.get('execution_id')}] Workflow has error/failed status, skipping queue promotion")
                execution_id = state.get('execution_id')
                if execution_id:
                    execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                        AgenticWorkflowExecutionTable.id == execution_id
                    ).first()
                    if execution and execution.status != 'failed':
                        execution.status = 'failed'
                        execution.current_step = state.get('current_step', 'promote_to_queue')
                        execution.error_message = execution.error_message or state.get('error') or "Workflow failed before queue promotion"
                        db_session.commit()
                
                return {
                    **state,
                    'queued_rules': [],
                    'current_step': state.get('current_step', 'promote_to_queue'),
                    'status': 'failed',
                    'termination_reason': state.get('termination_reason'),
                    'termination_details': state.get('termination_details')
                }
            
            article_id = state['article_id']
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                raise ValueError(f"Article {article_id} not found")
            
            sigma_rules = state.get('sigma_rules', [])
            similarity_results = state.get('similarity_results', [])
            similarity_threshold = state.get('similarity_threshold', 0.5)
            
            termination_reason = state.get('termination_reason')
            termination_details = state.get('termination_details')
            
            if not sigma_rules or len(sigma_rules) == 0:
                logger.info(f"[Workflow {state.get('execution_id')}] No SIGMA rules generated; completing without queue promotion")
                if termination_reason is None:
                    termination_reason = TERMINATION_REASON_NO_SIGMA_RULES
                if termination_details is None:
                    termination_details = {'generated_rules': 0}
            
            queued_rules = []
            
            # Queue each rule with low similarity
            for idx, rule in enumerate(sigma_rules):
                rule_similarity = similarity_results[idx] if idx < len(similarity_results) else {'max_similarity': 0.0}
                rule_max_sim = rule_similarity.get('max_similarity', 0.0)
                
                if rule_max_sim < similarity_threshold:
                    # Convert rule dict to YAML
                    rule_yaml = yaml.dump(rule, default_flow_style=False, sort_keys=False)
                    
                    # Create queue entry
                    queue_entry = SigmaRuleQueueTable(
                        article_id=article.id,
                        workflow_execution_id=state.get('execution_id'),
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
            logger.info(f"[Workflow {state.get('execution_id')}] Queued {len(queued_rules)} rules")
            
            # Update execution record to completed
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                
                if execution:
                    # Only update current_step and status if workflow didn't fail earlier
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
            logger.error(f"[Workflow {state.get('execution_id')}] Queue promotion error: {e}")
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                if execution:
                    execution.status = 'failed'
                    execution.error_message = str(e)
                    db_session.commit()
            
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'promote_to_queue': str(e)},
                'current_step': 'promote_to_queue',
                'status': 'failed',
                'termination_reason': state.get('termination_reason'),
                'termination_details': state.get('termination_details')
            }
        finally:
            db_session.close()
    
    def check_should_continue(state: ExposableWorkflowState) -> str:
        """Check if workflow should continue after ranking."""
        if state.get('should_continue', False) and state.get('status') != 'failed':
            return "extract_agent"
        else:
            return "end"
    
    # Build workflow graph
    workflow = StateGraph(ExposableWorkflowState)
    
    # Add nodes
    workflow.add_node("parse_input", parse_input_node)
    workflow.add_node("junk_filter", junk_filter_node)
    workflow.add_node("rank_article", rank_article_node)
    workflow.add_node("extract_agent", extract_agent_node)
    workflow.add_node("generate_sigma", generate_sigma_node)
    workflow.add_node("similarity_search", similarity_search_node)
    workflow.add_node("promote_to_queue", promote_to_queue_node)
    workflow.add_node("generate_response", generate_response_node)
    
    # Define edges
    workflow.set_entry_point("parse_input")
    
    # Route based on whether we have an article_id or conversational response
    def route_after_parse(state: ExposableWorkflowState) -> str:
        """Route after parsing: continue to workflow or end if conversational."""
        if state.get("current_step") == "conversational_response":
            return "end"
        if not state.get("article_id"):
            return "end"  # Error case - already handled in parse_input
        return "junk_filter"
    
    workflow.add_conditional_edges(
        "parse_input",
        route_after_parse,
        {
            "junk_filter": "junk_filter",
            "end": END
        }
    )
    workflow.add_edge("junk_filter", "rank_article")
    workflow.add_conditional_edges(
        "rank_article",
        check_should_continue,
        {
            "extract_agent": "extract_agent",
            "end": "generate_response"  # Route failed rankings to generate_response for chat-friendly error message
        }
    )
    def check_sigma_generation(state: ExposableWorkflowState) -> str:
        """Check if SIGMA generation succeeded or if workflow should stop."""
        execution_id = state.get('execution_id')
        
        # DEBUG: Log the state we're seeing
        logger.info(f"[Workflow {execution_id}] Routing check - State keys: {list(state.keys())}")
        logger.info(f"[Workflow {execution_id}] Routing check - sigma_rules: {state.get('sigma_rules')}, error: {state.get('error')}, status: {state.get('status')}")
        
        # Stop if there's an error
        if state.get('error'):
            logger.warning(f"[Workflow {execution_id}] Routing to generate_response due to error: {state.get('error')}")
            return "generate_response"  # Route to generate_response for error message
        
        # Stop if status is failed
        if state.get('status') == 'failed':
            logger.warning(f"[Workflow {execution_id}] Routing to generate_response due to failed status")
            return "generate_response"
        
        # CRITICAL: Check if no rules were generated
        # Handle both [] and None cases
        sigma_rules = state.get('sigma_rules')
        has_no_rules = (
            sigma_rules is None or 
            (isinstance(sigma_rules, list) and len(sigma_rules) == 0)
        )
        
        if has_no_rules:
            logger.warning(f"[Workflow {execution_id}] Routing to generate_response: No SIGMA rules generated (sigma_rules={sigma_rules})")
            # Also check database as fallback - if DB shows no rules, definitely fail
            try:
                db_session = get_db_session()
                try:
                    if execution_id:
                        execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                            AgenticWorkflowExecutionTable.id == execution_id
                        ).first()
                        if execution:
                            db_rules = execution.sigma_rules or []
                            if len(db_rules) == 0 and execution.error_log and 'generate_sigma' in execution.error_log:
                                logger.error(f"[Workflow {execution_id}] Database confirms no rules + error_log exists, routing to generate_response")
                                return "generate_response"
                finally:
                    db_session.close()
            except Exception as e:
                logger.warning(f"[Workflow {execution_id}] Error checking database in routing: {e}")
            
            return "generate_response"
        
        # Otherwise continue to similarity search
        logger.info(f"[Workflow {execution_id}] Routing to similarity_search: {len(sigma_rules)} rules found")
        return "similarity_search"
    
    workflow.add_edge("extract_agent", "generate_sigma")
    workflow.add_conditional_edges(
        "generate_sigma",
        check_sigma_generation,
        {
            "similarity_search": "similarity_search",
            "generate_response": "generate_response"
        }
    )
    workflow.add_edge("similarity_search", "promote_to_queue")
    workflow.add_edge("promote_to_queue", "generate_response")
    workflow.add_edge("generate_response", END)
    
    # Add checkpointing - use PostgreSQL if available, otherwise MemorySaver
    database_url = os.getenv("DATABASE_URL", "")
    if database_url and "postgresql" in database_url:
        try:
            # Convert asyncpg URL to psycopg2 for checkpointing
            checkpoint_url = database_url.replace("+asyncpg", "")
            # Remove password if present (we'll need to handle this securely)
            checkpoint = PostgresSaver.from_conn_string(checkpoint_url)
            logger.info("Using PostgreSQL checkpoint backend")
        except Exception as e:
            logger.warning(f"Failed to initialize PostgreSQL checkpoint, using MemorySaver: {e}")
            checkpoint = MemorySaver()
    else:
        checkpoint = MemorySaver()
        logger.info("Using MemorySaver checkpoint backend")
    
    # Enable debug mode for verbose logging of workflow execution
    return workflow.compile(checkpointer=checkpoint, debug=True)
