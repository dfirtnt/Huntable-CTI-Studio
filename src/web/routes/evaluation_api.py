"""
API routes for agent evaluation management.
"""

import logging
import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from langfuse import Langfuse
from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgenticWorkflowExecutionTable, ArticleTable
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.worker.celery_app import trigger_agentic_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _get_langfuse_setting(key: str, env_key: str, default: Optional[str] = None) -> Optional[str]:
    """Get Langfuse setting from database first, then fall back to environment variable.
    
    Priority: database setting > environment variable > default
    """
    # Check database setting first (highest priority - user preference from UI)
    try:
        from src.database.manager import DatabaseManager
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            from src.database.models import AppSettingsTable
            setting = db_session.query(AppSettingsTable).filter(
                AppSettingsTable.key == key
            ).first()
            
            if setting and setting.value:
                logger.debug(f"Using {key} from database setting")
                return setting.value
        except Exception as e:
            logger.debug(f"Could not fetch {key} from database: {e}")
        finally:
            db_session.close()
    except Exception as e:
        logger.debug(f"Could not access database for {key}: {e}")
    
    # Fall back to environment variable (second priority)
    env_value = os.getenv(env_key)
    if env_value:
        logger.debug(f"Using {env_key} from environment")
        return env_value
    
    # Return default if provided
    return default


def get_langfuse_client() -> Langfuse:
    """Initialize Langfuse client from database settings or environment variables."""
    public_key = _get_langfuse_setting("LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY")
    secret_key = _get_langfuse_setting("LANGFUSE_SECRET_KEY", "LANGFUSE_SECRET_KEY")
    host = _get_langfuse_setting("LANGFUSE_HOST", "LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    if not public_key or not secret_key:
        raise ValueError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in Settings or environment variables")
    
    return Langfuse(public_key=public_key, secret_key=secret_key, host=host)


@router.get("/dataset/{dataset_name}/items")
async def get_dataset_items(request: Request, dataset_name: str):
    """Get items from Langfuse dataset."""
    try:
        client = get_langfuse_client()
        dataset = client.get_dataset(dataset_name)
        
        if not dataset:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' not found")
        
        items = []
        
        # Handle case where dataset.items might not be iterable
        if hasattr(dataset, "items") and dataset.items:
            try:
                for item in dataset.items:
                    expected_output = item.expected_output if hasattr(item, "expected_output") else {}
                    if isinstance(expected_output, dict):
                        expected_count = expected_output.get("expected_count")
                    else:
                        expected_count = None
                    
                    # Extract article_id from metadata or input (must be numeric)
                    article_id = None
                    
                    # Try metadata first
                    if hasattr(item, "metadata") and item.metadata:
                        if isinstance(item.metadata, dict):
                            article_id = item.metadata.get("article_id")
                        elif hasattr(item.metadata, "get"):
                            article_id = item.metadata.get("article_id")
                        else:
                            # Try accessing as attribute
                            article_id = getattr(item.metadata, "article_id", None)
                    
                    # Try input as fallback
                    if not article_id and hasattr(item, "input") and isinstance(item.input, dict):
                        article_id = item.input.get("article_id")
                    
                    # If still no article_id, try to extract from article_url
                    if not article_id and hasattr(item, "input") and isinstance(item.input, dict):
                        article_url = item.input.get("article_url", "")
                        if article_url and isinstance(article_url, str):
                            # Try to extract ID from URL patterns like "article://68" or similar
                            import re
                            match = re.search(r'/(\d+)(?:/|$)', article_url)
                            if match:
                                article_id = int(match.group(1))
                                logger.info(f"Extracted article_id {article_id} from article_url: {article_url}")
                    
                    # Last resort: lookup by article_text content (for dataset items without article_id)
                    if not article_id and hasattr(item, "input") and isinstance(item.input, dict):
                        article_text = item.input.get("article_text", "")
                        article_title = item.input.get("article_title", "")
                        article_url = item.input.get("article_url", "")
                        
                        if article_text and len(article_text) > 100:  # Only if substantial content
                            try:
                                from src.database.models import ArticleTable
                                db_manager = DatabaseManager()
                                db_session = db_manager.get_session()
                                try:
                                    # Strategy 1: Try matching by title first (more reliable)
                                    if article_title:
                                        article = db_session.query(ArticleTable).filter(
                                            ArticleTable.title.ilike(f"%{article_title[:100]}%")
                                        ).first()
                                        if article:
                                            article_id = article.id
                                            logger.info(f"Found article_id {article_id} by title matching: {article_title[:50]}")
                                    
                                    # Strategy 2: Try matching by URL if it contains article info
                                    if not article_id and article_url:
                                        # Try to extract ID from URL
                                        import re
                                        url_match = re.search(r'[^/](\d{2,})[^/]', article_url)
                                        if url_match:
                                            potential_id = int(url_match.group(1))
                                            article = db_session.query(ArticleTable).filter(
                                                ArticleTable.id == potential_id
                                            ).first()
                                            if article:
                                                article_id = article.id
                                                logger.info(f"Found article_id {article_id} by URL pattern: {article_url}")
                                    
                                    # Strategy 3: Try content matching with multiple snippet sizes
                                    if not article_id:
                                        for snippet_size in [500, 300, 200, 100]:
                                            content_snippet = article_text[:snippet_size].strip()
                                            if content_snippet:
                                                # Escape special characters for LIKE query
                                                content_snippet_escaped = content_snippet.replace('%', '\\%').replace('_', '\\_')
                                                article = db_session.query(ArticleTable).filter(
                                                    ArticleTable.content.like(f"%{content_snippet_escaped}%")
                                                ).first()
                                                if article:
                                                    article_id = article.id
                                                    logger.info(f"Found article_id {article_id} by content matching (snippet size: {snippet_size})")
                                                    break
                                    
                                    if not article_id:
                                        logger.warning(f"Could not find article_id for dataset item {item.id} - tried title, URL, and content matching")
                                finally:
                                    db_session.close()
                            except Exception as e:
                                logger.error(f"Error during article lookup: {e}", exc_info=True)
                    
                    # Debug logging with more detail
                    input_info = {}
                    if isinstance(item.input, dict):
                        input_info = {
                            "keys": list(item.input.keys()),
                            "has_article_text": bool(item.input.get("article_text")),
                            "has_article_title": bool(item.input.get("article_title")),
                            "has_article_url": bool(item.input.get("article_url")),
                            "article_title_preview": item.input.get("article_title", "")[:50] if item.input.get("article_title") else None,
                        }
                    logger.info(f"Dataset item {item.id}: input={input_info}, article_id={article_id}")
                    
                    # Convert to int if it's a string number
                    if article_id and isinstance(article_id, str) and article_id.isdigit():
                        article_id = int(article_id)
                    elif article_id and isinstance(article_id, (int, float)):
                        article_id = int(article_id)
                    elif article_id:
                        # If article_id exists but isn't numeric, log and set to None
                        logger.warning(f"Non-numeric article_id found: {article_id} (type: {type(article_id)})")
                        article_id = None
                    
                    # Include item even if article_id not found (for manual review)
                    items.append({
                        "id": item.id if hasattr(item, "id") else str(item),
                        "input": item.input if hasattr(item, "input") else {},
                        "expected_output": expected_output,
                        "expected_count": expected_count,
                        "metadata": item.metadata if hasattr(item, "metadata") else {},
                        "status": item.status if hasattr(item, "status") else "ACTIVE",
                        "article_id": article_id,
                        "lookup_failed": article_id is None,  # Flag for UI to show warning
                    })
            except Exception as iter_error:
                logger.error(f"Error iterating dataset items: {iter_error}")
                raise HTTPException(status_code=500, detail=f"Error reading dataset items: {str(iter_error)}")
        
        return {"dataset_name": dataset.name if hasattr(dataset, "name") else dataset_name, "items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dataset items: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow-configs")
async def get_workflow_configs(request: Request):
    """Get all workflow configurations (presets)."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            configs = db_session.query(AgenticWorkflowConfigTable).order_by(
                AgenticWorkflowConfigTable.version.desc()
            ).all()
            
            return {
                "configs": [
                    {
                        "id": c.id,
                        "version": c.version,
                        "description": c.description or f"Config v{c.version}",
                        "is_active": c.is_active,
                        "agent_models": c.agent_models or {},
                        "created_at": c.created_at.isoformat(),
                    }
                    for c in configs
                ]
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting workflow configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class EvaluationRunRequest(BaseModel):
    """Request to run evaluation."""
    article_ids: List[int]
    config_ids: List[int]  # Workflow config IDs to test


@router.post("/run")
async def run_evaluation(request: Request, eval_request: EvaluationRunRequest):
    """Run articles through workflows with different configs."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            executions = []
            
            for article_id in eval_request.article_ids:
                article = db_session.query(ArticleTable).filter(
                    ArticleTable.id == article_id
                ).first()
                
                if not article:
                    logger.warning(f"Article {article_id} not found")
                    continue
                
                for config_id in eval_request.config_ids:
                    config = db_session.query(AgenticWorkflowConfigTable).filter(
                        AgenticWorkflowConfigTable.id == config_id
                    ).first()
                    
                    if not config:
                        logger.warning(f"Config {config_id} not found")
                        continue
                    
                    # Create execution with config snapshot
                    # Note: Workflow uses active config, so we activate this config temporarily
                    # For proper eval support, workflow should be modified to use config_snapshot when present
                    original_active = db_session.query(AgenticWorkflowConfigTable).filter(
                        AgenticWorkflowConfigTable.is_active == True
                    ).first()
                    
                    # Temporarily activate eval config
                    if original_active and original_active.id != config.id:
                        original_active.is_active = False
                    config.is_active = True
                    db_session.commit()
                    
                    execution = AgenticWorkflowExecutionTable(
                        article_id=article_id,
                        status='pending',
                        config_snapshot={
                            'min_hunt_score': config.min_hunt_score,
                            'ranking_threshold': config.ranking_threshold,
                            'similarity_threshold': config.similarity_threshold,
                            'junk_filter_threshold': config.junk_filter_threshold,
                            'agent_models': config.agent_models or {},
                            'agent_prompts': config.agent_prompts or {},
                            'qa_enabled': config.qa_enabled or {},
                            'config_id': config.id,
                            'config_version': config.version,
                            'eval_run': True,
                            'original_config_id': original_active.id if original_active else None,
                        }
                    )
                    db_session.add(execution)
                    db_session.commit()
                    db_session.refresh(execution)
                    
                    # Trigger workflow via Celery (will use the now-active config)
                    trigger_agentic_workflow.delay(article_id)
                    
                    # Note: Config remains active - user should restore original manually
                    # Or implement proper config restoration after workflow completes
                    logger.info(f"Eval execution {execution.id}: Using config {config.id} (v{config.version})")
                    
                    executions.append({
                        "execution_id": execution.id,
                        "article_id": article_id,
                        "config_id": config_id,
                        "config_version": config.version,
                    })
            
            if len(executions) == 0:
                return {
                    "success": False,
                    "executions": [],
                    "message": "No executions were created. Check that articles and configs exist."
                }
            
            return {
                "success": True,
                "executions": executions,
                "message": f"Triggered {len(executions)} workflow executions"
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error running evaluation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}/results")
async def get_execution_results(request: Request, execution_id: int):
    """Get results for a specific execution."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == execution_id
            ).first()
            
            if not execution:
                raise HTTPException(status_code=404, detail="Execution not found")
            
            # Extract cmdline count from extraction result
            cmdline_count = 0
            extraction_result = execution.extraction_result
            if extraction_result and isinstance(extraction_result, dict):
                subresults = extraction_result.get("subresults", {})
                if isinstance(subresults, dict):
                    cmdline = subresults.get("cmdline", {})
                    if isinstance(cmdline, dict):
                        cmdline_count = cmdline.get("count", 0)
            
            return {
                "execution_id": execution.id,
                "article_id": execution.article_id,
                "status": execution.status,
                "cmdline_count": cmdline_count,
                "config_version": execution.config_snapshot.get("config_version") if execution.config_snapshot else None,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

