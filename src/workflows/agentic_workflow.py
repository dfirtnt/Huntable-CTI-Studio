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
    llm_service = LLMService()
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
                'current_step': 'junk_filter'
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
                'status': 'failed'
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
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"
            
            # Rank article using LLM
            ranking_result = await llm_service.rank_article(
                title=article.title,
                content=filtered_content,
                source=source_name,
                url=article.canonical_url or ""
            )
            
            ranking_score = ranking_result['score']
            ranking_threshold = state['config'].get('ranking_threshold', 6.0) if state.get('config') else 6.0
            should_continue = ranking_score >= ranking_threshold
            
            # Update execution record with ranking results
            if execution:
                execution.ranking_score = ranking_score
                execution.status = 'failed' if not should_continue else 'running'
                db_session.commit()
            
            logger.info(f"[Workflow {state['execution_id']}] Ranking: {ranking_score}/10 (threshold: {ranking_threshold}), continue: {should_continue}")
            
            return {
                **state,
                'ranking_score': ranking_score,
                'ranking_reasoning': ranking_result.get('reasoning'),
                'should_continue': should_continue,
                'current_step': 'rank_article'
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
                'current_step': 'rank_article'
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
            # Use relative path that works both in Docker and local
            prompt_file = Path(__file__).parent.parent / "prompts" / "ExtractAgent"
            extract_agent_prompt_path = str(prompt_file)
            extraction_result = await llm_service.extract_behaviors(
                content=filtered_content,
                title=article.title,
                url=article.canonical_url or "",
                prompt_file_path=extract_agent_prompt_path
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
                'current_step': 'extract_agent'
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Extraction error: {e}")
            return {
                **state,
                'error': str(e),
                'current_step': 'extract_agent'
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
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"
            
            # Generate SIGMA rules using service
            sigma_service = SigmaGenerationService()
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
            
            # Update execution record with SIGMA results
            if execution:
                execution.sigma_rules = sigma_rules
                db_session.commit()
            
            logger.info(f"[Workflow {state['execution_id']}] Generated {len(sigma_rules)} SIGMA rules")
            
            return {
                **state,
                'sigma_rules': sigma_rules,
                'current_step': 'generate_sigma'
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
                'current_step': 'generate_sigma'
            }
    
    async def similarity_search_node(state: WorkflowState) -> WorkflowState:
        """Step 4: Search for similar SIGMA rules."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 4: Similarity Search")
            
            sigma_rules = state.get('sigma_rules', [])
            if not sigma_rules:
                logger.warning(f"[Workflow {state['execution_id']}] No SIGMA rules to search")
                return {
                    **state,
                    'similarity_results': [],
                    'max_similarity': 0.0,
                    'current_step': 'similarity_search'
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
                execution.current_step = 'similarity_search'
                execution.similarity_results = similarity_results
                db_session.commit()
            
            logger.info(f"[Workflow {state['execution_id']}] Similarity: max={max_similarity:.2f}")
            
            return {
                **state,
                'similarity_results': similarity_results,
                'max_similarity': max_similarity,
                'current_step': 'similarity_search'
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Similarity search error: {e}")
            return {
                **state,
                'error': str(e),
                'current_step': 'similarity_search'
            }
    
    def promote_to_queue_node(state: WorkflowState) -> WorkflowState:
        """Step 5: Promote rules to queue if similarity is low."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 5: Promote to Queue")
            
            sigma_rules = state.get('sigma_rules', [])
            similarity_results = state.get('similarity_results', [])
            max_similarity = state.get('max_similarity', 1.0)
            similarity_threshold = state['config'].get('similarity_threshold', 0.5) if state.get('config') else 0.5
            
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
                execution.current_step = 'promote_to_queue'
                execution.status = 'completed'
                execution.completed_at = datetime.utcnow()
                db_session.commit()
            
            return {
                **state,
                'queued_rules': queued_rules,
                'current_step': 'promote_to_queue'
            }
            
        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Queue promotion error: {e}")
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
                'current_step': 'promote_to_queue'
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
    workflow.add_edge("generate_sigma", "similarity_search")
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
            'current_step': 'junk_filter'
        }
        
        # Set execution context for LLM service tracing
        llm_service = LLMService()
        llm_service._current_execution_id = execution.id
        llm_service._current_article_id = article_id
        
        # Create and run workflow with LangFuse tracing
        with trace_workflow_execution(execution_id=execution.id, article_id=article_id) as trace:
            workflow_graph = create_agentic_workflow(db_session)
            final_state = await workflow_graph.ainvoke(initial_state)
            
            # Log workflow completion
            if trace:
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
        
        return {
            'success': final_state.get('error') is None,
            'execution_id': execution.id,
            'final_state': final_state,
            'error': final_state.get('error')
        }
        
    except Exception as e:
        logger.error(f"Workflow execution error for article {article_id}: {e}")
        if execution:
            execution.status = 'failed'
            execution.error_message = str(e)
            db_session.commit()
        raise

