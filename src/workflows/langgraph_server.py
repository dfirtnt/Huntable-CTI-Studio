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
    llm_service = LLMService()
    rag_service = RAGService()
    sigma_generation_service = SigmaGenerationService()
    
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
                    "article_id": None  # No article processing needed
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
                
                # Create new execution
                execution = AgenticWorkflowExecutionTable(
                    article_id=article_id,
                    status='pending',
                    config_snapshot={
                        'min_hunt_score': config.min_hunt_score if config else 97.0,
                        'ranking_threshold': config.ranking_threshold if config else 6.0,
                        'similarity_threshold': config.similarity_threshold if config else 0.5,
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
                
                return {
                    **state,
                    "article_id": article_id,
                    "execution_id": execution_id,
                    "min_hunt_score": min_score,
                    "ranking_threshold": rank_threshold,
                    "similarity_threshold": sim_threshold,
                    "status": "pending",
                    "current_step": "parse_input",
                    "should_continue": True,
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
        """Step 0: Filter content using least aggressive junk filter."""
        db_session = get_db_session()
        try:
            logger.info(f"[Workflow {state.get('execution_id')}] Step 0: Junk Filter")
            
            article_id = state['article_id']
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                raise ValueError(f"Article {article_id} not found")
            
            # Use least aggressive filter (min_confidence=0.9)
            filter_result = content_filter.filter_content(
                article.content,
                min_confidence=0.9,  # Least aggressive
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
                # Create new execution
                execution = AgenticWorkflowExecutionTable(
                    article_id=article_id,
                    status='running',
                    started_at=datetime.utcnow(),
                    config_snapshot={
                        'min_hunt_score': state.get('min_hunt_score', 97.0),
                        'ranking_threshold': state.get('ranking_threshold', 6.0),
                        'similarity_threshold': state.get('similarity_threshold', 0.5)
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
                    'chunks_kept': len(filter_result.removed_chunks) if filter_result.removed_chunks else 0,
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
                'status': 'running'
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] Junk filter error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'junk_filter': str(e)},
                'current_step': 'junk_filter',
                'status': 'failed'
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
            
            # Update execution record
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                
                if execution:
                    execution.current_step = 'rank_article'
                    execution.ranking_score = ranking_score
                    execution.status = 'failed' if not should_continue else 'running'
                    db_session.commit()
            
            logger.info(f"[Workflow {execution_id}] Ranking: {ranking_score}/10 (threshold: {ranking_threshold}), continue: {should_continue}")
            
            return {
                **state,
                'ranking_score': ranking_score,
                'ranking_reasoning': ranking_result.get('reasoning'),
                'should_continue': should_continue,
                'current_step': 'rank_article',
                'status': 'failed' if not should_continue else 'running'
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] Ranking error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'rank_article': str(e)},
                'current_step': 'rank_article',
                'status': 'failed'
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
            # Use relative path that works both in Docker and local
            prompt_file = Path(__file__).parent.parent / "prompts" / "ExtractAgent"
            extract_agent_prompt_path = str(prompt_file)
            extraction_result = await llm_service.extract_behaviors(
                content=filtered_content,
                title=article.title,
                url=article.canonical_url or "",
                prompt_file_path=extract_agent_prompt_path
            )
            
            discrete_huntables = extraction_result.get('discrete_huntables_count', 0)
            
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
                'status': 'running'
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] Extract agent error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'extract_agent': str(e)},
                'current_step': 'extract_agent',
                'status': 'failed'
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
            
            # Generate SIGMA rules
            source_name = article.source.name if article.source else "Unknown"
            sigma_result = await sigma_generation_service.generate_sigma_rules(
                article_title=article.title,
                article_content=filtered_content,
                source_name=source_name,
                url=article.canonical_url or "",
                ai_model='lmstudio'
            )
            
            sigma_rules = sigma_result.get('rules', [])
            
            # Update execution record
            execution_id = state.get('execution_id')
            if execution_id:
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == execution_id
                ).first()
                
                if execution:
                    execution.current_step = 'generate_sigma'
                    execution.sigma_rules = sigma_rules
                    db_session.commit()
            
            return {
                **state,
                'sigma_rules': sigma_rules,
                'current_step': 'generate_sigma',
                'status': 'running'
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] SIGMA generation error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'generate_sigma': str(e)},
                'current_step': 'generate_sigma',
                'status': 'failed'
            }
        finally:
            db_session.close()
    
    async def similarity_search_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Step 4: Similarity search against existing SIGMA rules."""
        import yaml
        db_session = get_db_session()
        try:
            logger.info(f"[Workflow {state.get('execution_id')}] Step 4: Similarity Search")
            
            sigma_rules = state.get('sigma_rules', [])
            similarity_results = []
            
            for rule in sigma_rules:
                rule_yaml = yaml.dump(rule, default_flow_style=False, sort_keys=False)
                similar = await rag_service.find_similar_sigma_rules(
                    rule_yaml=rule_yaml,
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
                    execution.current_step = 'similarity_search'
                    execution.similarity_results = similarity_results
                    db_session.commit()
            
            return {
                **state,
                'similarity_results': similarity_results,
                'max_similarity': max_sim,
                'current_step': 'similarity_search',
                'status': 'running'
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state.get('execution_id')}] Similarity search error: {e}")
            return {
                **state,
                'error': str(e),
                'error_log': {**(state.get('error_log') or {}), 'similarity_search': str(e)},
                'current_step': 'similarity_search',
                'status': 'failed'
            }
        finally:
            db_session.close()
    
    async def generate_response_node(state: ExposableWorkflowState) -> ExposableWorkflowState:
        """Generate a chat-friendly response summarizing workflow results."""
        try:
            execution_id = state.get("execution_id")
            article_id = state.get("article_id")
            status = state.get("status", "unknown")
            
            if status == "completed":
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
            
            article_id = state['article_id']
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                raise ValueError(f"Article {article_id} not found")
            
            sigma_rules = state.get('sigma_rules', [])
            similarity_results = state.get('similarity_results', [])
            similarity_threshold = state.get('similarity_threshold', 0.5)
            
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
                    execution.current_step = 'promote_to_queue'
                    execution.status = 'completed'
                    execution.completed_at = datetime.utcnow()
                    db_session.commit()
            
            return {
                **state,
                'queued_rules': queued_rules,
                'current_step': 'promote_to_queue',
                'status': 'completed'
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
                'status': 'failed'
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
            "end": END
        }
    )
    workflow.add_edge("extract_agent", "generate_sigma")
    workflow.add_edge("generate_sigma", "similarity_search")
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
    
    return workflow.compile(checkpointer=checkpoint)

