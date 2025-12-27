"""
API routes for agent evaluation management.
"""

import logging
import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from langfuse import Langfuse
from src.database.manager import DatabaseManager
from src.database.models import (
    AgenticWorkflowConfigTable, 
    AgenticWorkflowExecutionTable, 
    ArticleTable,
    SubagentEvaluationTable
)
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.worker.celery_app import trigger_agentic_workflow
import yaml
from pathlib import Path
import yaml
from pathlib import Path

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


class PresetEvaluationRunRequest(BaseModel):
    """Request to run preset-based evaluation."""
    preset_id: Optional[int] = None  # Optional, defaults to active preset
    dataset_name: str = "cmdline_extractor_gt"  # Default dataset name


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


@router.post("/run-preset")
async def run_preset_evaluation(
    request: Request,
    eval_request: PresetEvaluationRunRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a preset-based evaluation run.
    
    Creates an immutable preset snapshot and starts background evaluation job.
    Uses FastAPI BackgroundTasks (best-effort execution).
    May be swapped for durable job runner (e.g., Celery) in future if reliability requirements increase.
    """
    from uuid import UUID
    from src.database.models import EvalRunTable
    from src.services.eval_preset_snapshot_service import EvalPresetSnapshotService
    from src.services.evaluation.eval_runner import EvalRunner
    
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Create preset snapshot
            snapshot_service = EvalPresetSnapshotService(db_session)
            snapshot_id = snapshot_service.create_snapshot(
                preset_id=eval_request.preset_id,
                description=f"Evaluation snapshot for dataset {eval_request.dataset_name}"
            )
            
            # Create eval run record
            eval_run = EvalRunTable(
                preset_snapshot_id=snapshot_id,
                dataset_name=eval_request.dataset_name,
                status='queued'
            )
            db_session.add(eval_run)
            db_session.commit()
            db_session.refresh(eval_run)
            
            eval_run_id = eval_run.id
            
            # Start background evaluation task
            background_tasks.add_task(
                _run_evaluation_background,
                str(eval_run_id),
                str(snapshot_id),
                eval_request.dataset_name
            )
            
            logger.info(f"Started evaluation run {eval_run_id} with snapshot {snapshot_id}")
            
            return {
                "eval_run_id": str(eval_run_id),
                "status": "queued",
                "preset_snapshot_id": str(snapshot_id)
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error starting preset evaluation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _run_evaluation_background(eval_run_id_str: str, snapshot_id_str: str, dataset_name: str):
    """
    Background task to run evaluation.
    
    Note: This uses FastAPI BackgroundTasks which is best-effort.
    May be swapped for durable job runner (e.g., Celery) if reliability requirements increase.
    """
    from src.database.manager import DatabaseManager
    from src.services.evaluation.eval_runner import EvalRunner
    from uuid import UUID
    
    try:
        eval_run_id = UUID(eval_run_id_str)
        snapshot_id = UUID(snapshot_id_str)
        
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            runner = EvalRunner(db_session)
            result = runner.run_evaluation(eval_run_id, snapshot_id, dataset_name)
            logger.info(f"Background evaluation completed: {result}")
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Background evaluation failed: {e}", exc_info=True)


@router.get("/runs/{eval_run_id}/status")
async def get_eval_run_status(request: Request, eval_run_id: str):
    """
    Get status and progress for an evaluation run.
    
    Args:
        eval_run_id: UUID of the evaluation run (as string)
    """
    from uuid import UUID
    from src.database.models import EvalRunTable
    
    try:
        eval_run_uuid = UUID(eval_run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid eval_run_id format (must be UUID)")
    
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            eval_run = db_session.query(EvalRunTable).filter(
                EvalRunTable.id == eval_run_uuid
            ).first()
            
            if not eval_run:
                raise HTTPException(status_code=404, detail="Evaluation run not found")
            
            return {
                "eval_run_id": str(eval_run.id),
                "status": eval_run.status,
                "completed_items": eval_run.completed_items,
                "total_items": eval_run.total_items,
                "progress": eval_run.completed_items / eval_run.total_items if eval_run.total_items > 0 else 0.0,
                "accuracy": eval_run.accuracy,
                "mean_count_diff": eval_run.mean_count_diff,
                "passed": eval_run.passed,
                "error_message": eval_run.error_message,
                "langfuse_experiment_id": eval_run.langfuse_experiment_id,
                "langfuse_experiment_name": eval_run.langfuse_experiment_name,
                "created_at": eval_run.created_at.isoformat() if eval_run.created_at else None,
                "started_at": eval_run.started_at.isoformat() if eval_run.started_at else None,
                "completed_at": eval_run.completed_at.isoformat() if eval_run.completed_at else None,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting eval run status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{eval_run_id}/debug-info")
async def get_eval_run_debug_info(request: Request, eval_run_id: str):
    """
    Get debug information for opening evaluation run in Langfuse.
    
    Similar to workflow execution debug-info endpoint.
    """
    from uuid import UUID
    from src.database.models import EvalRunTable
    
    try:
        eval_run_uuid = UUID(eval_run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid eval_run_id format (must be UUID)")
    
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            eval_run = db_session.query(EvalRunTable).filter(
                EvalRunTable.id == eval_run_uuid
            ).first()
            
            if not eval_run:
                raise HTTPException(status_code=404, detail="Evaluation run not found")
            
            # Get Langfuse settings (same pattern as workflow_executions)
            langfuse_host = _get_langfuse_setting(
                "LANGFUSE_HOST", 
                "LANGFUSE_HOST", 
                "https://cloud.langfuse.com"
            )
            langfuse_public_key = _get_langfuse_setting(
                "LANGFUSE_PUBLIC_KEY",
                "LANGFUSE_PUBLIC_KEY"
            )
            langfuse_project_id = _get_langfuse_setting(
                "LANGFUSE_PROJECT_ID",
                "LANGFUSE_PROJECT_ID"
            )
            
            # Build session ID for eval run
            session_id = f"eval_run_{eval_run_id}"
            
            # Normalize host URL
            langfuse_host = langfuse_host.rstrip('/') if langfuse_host else "https://cloud.langfuse.com"
            
            # Generate session URL (groups all traces for the eval run)
            if langfuse_project_id:
                agent_chat_url = f"{langfuse_host}/project/{langfuse_project_id}/sessions/{session_id}"
                search_url = f"{langfuse_host}/project/{langfuse_project_id}/traces?search={session_id}"
            else:
                agent_chat_url = f"{langfuse_host}/sessions/{session_id}"
                search_url = f"{langfuse_host}/traces?search={session_id}"
            
            instructions = (
                f"Evaluation run {eval_run_id} traces are grouped by session_id: {session_id}\n"
                f"If the session is not found, search for traces using session_id in Langfuse UI."
            )
            
            return {
                "eval_run_id": str(eval_run.id),
                "agent_chat_url": agent_chat_url,
                "session_id": session_id,
                "langfuse_host": langfuse_host,
                "langfuse_project_id": langfuse_project_id,
                "search_url": search_url,
                "instructions": instructions,
                "uses_langsmith": bool(langfuse_public_key)  # Keep field name for backwards compatibility
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting eval run debug info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def resolve_article_by_url(url: str) -> Optional[int]:
    """
    Resolve article ID from URL by querying articles table.
    
    Args:
        url: Full article URL
        
    Returns:
        Article ID if found, None otherwise
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Try exact match on canonical_url first
            article = db_session.query(ArticleTable).filter(
                ArticleTable.canonical_url == url
            ).first()
            
            if article:
                return article.id
            
            # Try partial match (URL might have query params or fragments)
            # Normalize URL by removing query params and fragments for comparison
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            normalized_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
            
            article = db_session.query(ArticleTable).filter(
                ArticleTable.canonical_url.like(f"{normalized_url}%")
            ).first()
            
            if article:
                return article.id
            
            return None
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error resolving article by URL {url}: {e}")
        return None


@router.get("/subagent-eval-articles")
async def get_subagent_eval_articles(
    request: Request,
    subagent: str = Query(..., description="Subagent name (cmdline, sigextract, etc.)")
):
    """Get eval articles for a specific subagent from config file."""
    try:
        # Load eval articles config (go up 4 levels from src/web/routes/ to project root)
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "eval_articles.yaml"
        
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="eval_articles.yaml config file not found")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        subagents = config.get('subagents', {})
        if subagent not in subagents:
            raise HTTPException(status_code=404, detail=f"Subagent '{subagent}' not found in config")
        
        articles = subagents[subagent]
        if not isinstance(articles, list):
            articles = []
        
        # Resolve article IDs for each URL
        results = []
        for article_def in articles:
            url = article_def.get('url')
            expected_count = article_def.get('expected_count', 0)
            
            if not url:
                continue
            
            article_id = resolve_article_by_url(url)
            
            results.append({
                'url': url,
                'expected_count': expected_count,
                'article_id': article_id,
                'found': article_id is not None
            })
        
        return {
            'subagent': subagent,
            'articles': results,
            'total': len(results)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading subagent eval articles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class SubagentEvalRunRequest(BaseModel):
    """Request to run subagent evaluation."""
    subagent_name: str
    article_urls: List[str]
    use_active_config: bool = True


@router.post("/run-subagent-eval")
async def run_subagent_eval(request: Request, eval_request: SubagentEvalRunRequest):
    """Run subagent evaluation against selected articles."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Get current active config
            active_config = db_session.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).order_by(AgenticWorkflowConfigTable.version.desc()).first()
            
            if not active_config:
                raise HTTPException(status_code=404, detail="No active workflow config found")
            
            # Resolve article URLs to IDs
            article_mappings = []
            for url in eval_request.article_urls:
                article_id = resolve_article_by_url(url)
                if not article_id:
                    logger.warning(f"Article not found for URL: {url}")
                    # Still create eval record but mark as failed
                    article_mappings.append({
                        'url': url,
                        'article_id': None,
                        'found': False
                    })
                else:
                    article_mappings.append({
                        'url': url,
                        'article_id': article_id,
                        'found': True
                    })
            
            # Get expected counts from config (go up 4 levels from src/web/routes/ to project root)
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "eval_articles.yaml"
            expected_counts = {}
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    subagent_articles = config.get('subagents', {}).get(eval_request.subagent_name, [])
                    for article_def in subagent_articles:
                        url = article_def.get('url')
                        expected_count = article_def.get('expected_count')
                        if url:
                            expected_counts[url] = expected_count
            
            # Create SubagentEvaluationTable records and workflow executions
            eval_records = []
            executions = []
            
            for mapping in article_mappings:
                url = mapping['url']
                article_id = mapping['article_id']
                expected_count = expected_counts.get(url, 0)
                
                if not article_id:
                    # Create eval record but mark as failed
                    eval_record = SubagentEvaluationTable(
                        subagent_name=eval_request.subagent_name,
                        article_url=url,
                        article_id=None,
                        expected_count=expected_count,
                        workflow_config_id=active_config.id,
                        workflow_config_version=active_config.version,
                        status='failed'
                    )
                    db_session.add(eval_record)
                    continue
                
                # Create workflow execution with skip_os_detection flag
                execution = AgenticWorkflowExecutionTable(
                    article_id=article_id,
                    status='pending',
                    config_snapshot={
                        'min_hunt_score': active_config.min_hunt_score,
                        'ranking_threshold': active_config.ranking_threshold,
                        'similarity_threshold': active_config.similarity_threshold,
                        'junk_filter_threshold': active_config.junk_filter_threshold,
                        'agent_models': active_config.agent_models or {},
                        'agent_prompts': active_config.agent_prompts or {},
                        'qa_enabled': active_config.qa_enabled or {},
                        'config_id': active_config.id,
                        'config_version': active_config.version,
                        'eval_run': True,
                        'skip_os_detection': True,  # Bypass OS detection for evals
                        'skip_rank_agent': True,  # Bypass rank agent for evals
                        'skip_sigma_generation': True,  # Skip SIGMA generation for evals
                        'subagent_eval': eval_request.subagent_name
                    }
                )
                db_session.add(execution)
                db_session.flush()  # Get execution.id
                
                # Create SubagentEvaluationTable record
                eval_record = SubagentEvaluationTable(
                    subagent_name=eval_request.subagent_name,
                    article_url=url,
                    article_id=article_id,
                    expected_count=expected_count,
                    workflow_execution_id=execution.id,
                    workflow_config_id=active_config.id,
                    workflow_config_version=active_config.version,
                    status='pending'
                )
                db_session.add(eval_record)
                eval_records.append(eval_record)
                executions.append({
                    'execution_id': execution.id,
                    'article_id': article_id,
                    'url': url,
                    'eval_record_id': eval_record.id
                })
            
            db_session.commit()
            
            # Trigger workflows one at a time (sequential batch)
            for exec_info in executions:
                trigger_agentic_workflow.delay(exec_info['article_id'])
                logger.info(f"Triggered workflow execution {exec_info['execution_id']} for article {exec_info['article_id']}")
            
            return {
                'success': True,
                'subagent': eval_request.subagent_name,
                'total_articles': len(eval_request.article_urls),
                'found_articles': sum(1 for m in article_mappings if m['found']),
                'executions': executions,
                'message': f"Triggered {len(executions)} workflow executions for {eval_request.subagent_name} evaluation"
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running subagent eval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subagent-eval-results")
async def get_subagent_eval_results(
    request: Request,
    subagent: str = Query(..., description="Subagent name"),
    eval_run_id: Optional[int] = Query(None, description="Optional: filter by eval record ID")
):
    """Get evaluation results for a subagent."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            query = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.subagent_name == subagent
            )
            
            if eval_run_id:
                query = query.filter(SubagentEvaluationTable.id == eval_run_id)
            
            eval_records = query.order_by(SubagentEvaluationTable.created_at.desc()).all()
            
            results = []
            for record in eval_records:
                # Calculate score if actual_count is set
                score = None
                if record.actual_count is not None:
                    score = record.actual_count - record.expected_count
                
                results.append({
                    'id': record.id,
                    'url': record.article_url,
                    'article_id': record.article_id,
                    'expected_count': record.expected_count,
                    'actual_count': record.actual_count,
                    'score': score,
                    'status': record.status,
                    'execution_id': record.workflow_execution_id,
                    'config_version': record.workflow_config_version,
                    'created_at': record.created_at.isoformat() if record.created_at else None,
                    'completed_at': record.completed_at.isoformat() if record.completed_at else None,
                    'workflow_config_id': record.workflow_config_id
                })
            
            return {
                'subagent': subagent,
                'results': results,
                'total': len(results)
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting subagent eval results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subagent-eval-status/{eval_record_id}")
async def get_subagent_eval_status(request: Request, eval_record_id: int):
    """Get status and progress for a subagent evaluation run."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            eval_record = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.id == eval_record_id
            ).first()
            
            if not eval_record:
                raise HTTPException(status_code=404, detail="Evaluation record not found")
            
            # Get all eval records for the same subagent and config version
            all_records = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.subagent_name == eval_record.subagent_name,
                SubagentEvaluationTable.workflow_config_version == eval_record.workflow_config_version
            ).all()
            
            total = len(all_records)
            completed = sum(1 for r in all_records if r.status == 'completed')
            failed = sum(1 for r in all_records if r.status == 'failed')
            pending = sum(1 for r in all_records if r.status == 'pending')
            
            # Calculate aggregate metrics
            completed_records = [r for r in all_records if r.status == 'completed' and r.score is not None]
            if completed_records:
                perfect_matches = sum(1 for r in completed_records if r.score == 0)
                accuracy = perfect_matches / len(completed_records) if completed_records else 0.0
                mean_score = sum(r.score for r in completed_records) / len(completed_records)
            else:
                accuracy = None
                mean_score = None
                perfect_matches = 0
            
            return {
                'eval_record_id': eval_record_id,
                'subagent': eval_record.subagent_name,
                'status': eval_record.status,
                'progress': {
                    'completed': completed,
                    'failed': failed,
                    'pending': pending,
                    'total': total
                },
                'metrics': {
                    'accuracy': accuracy,
                    'mean_score': mean_score,
                    'perfect_matches': perfect_matches
                },
                'current_record': {
                    'url': eval_record.article_url,
                    'expected_count': eval_record.expected_count,
                    'actual_count': eval_record.actual_count,
                    'score': eval_record.score
                }
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subagent eval status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/subagent-eval-clear-pending")
async def clear_pending_eval_records(
    request: Request,
    subagent: str = Query(..., description="Subagent name")
):
    """Delete all pending evaluation records for a subagent."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Find all pending records for this subagent
            pending_records = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.subagent_name == subagent,
                SubagentEvaluationTable.status == 'pending'
            ).all()
            
            deleted_count = len(pending_records)
            
            # Delete the records
            for record in pending_records:
                db_session.delete(record)
            
            db_session.commit()
            
            logger.info(f"Deleted {deleted_count} pending evaluation records for subagent {subagent}")
            
            return {
                'success': True,
                'deleted_count': deleted_count,
                'subagent': subagent,
                'message': f"Deleted {deleted_count} pending evaluation record(s)"
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error clearing pending eval records: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subagent-eval-backfill")
async def backfill_eval_records(
    request: Request,
    subagent: str = Query(..., description="Subagent name")
):
    """Backfill pending eval records for completed workflow executions."""
    try:
        from src.workflows.agentic_workflow import _update_subagent_eval_on_completion
        
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Find all pending eval records for this subagent
            pending_evals = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.subagent_name == subagent,
                SubagentEvaluationTable.status == 'pending'
            ).all()
            
            updated_count = 0
            failed_count = 0
            
            for eval_record in pending_evals:
                if not eval_record.workflow_execution_id:
                    continue
                    
                execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                    AgenticWorkflowExecutionTable.id == eval_record.workflow_execution_id
                ).first()
                
                if not execution or execution.status != 'completed':
                    continue
                
                # Use the existing update function
                try:
                    _update_subagent_eval_on_completion(execution, db_session)
                    # Check if it was updated
                    db_session.refresh(eval_record)
                    if eval_record.status == 'completed':
                        updated_count += 1
                    elif eval_record.status == 'failed':
                        failed_count += 1
                except Exception as e:
                    logger.warning(f"Error updating eval record {eval_record.id}: {e}")
                    failed_count += 1
            
            db_session.commit()
            
            logger.info(f"Backfilled {updated_count} eval records for subagent {subagent}")
            
            return {
                'success': True,
                'updated_count': updated_count,
                'failed_count': failed_count,
                'subagent': subagent,
                'message': f"Updated {updated_count} record(s), {failed_count} marked as failed"
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error backfilling eval records: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subagent-eval-aggregate")
async def get_subagent_eval_aggregate(
    request: Request,
    subagent: str = Query(..., description="Subagent name"),
    config_version: Optional[int] = Query(None, description="Optional: filter by config version")
):
    """Get aggregate scores per config version for a subagent."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            query = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.subagent_name == subagent
            )
            
            if config_version:
                query = query.filter(SubagentEvaluationTable.workflow_config_version == config_version)
            
            all_records = query.order_by(
                SubagentEvaluationTable.workflow_config_version.desc(),
                SubagentEvaluationTable.created_at.desc()
            ).all()
            
            # Group by config version
            by_config_version = {}
            for record in all_records:
                version = record.workflow_config_version
                if version not in by_config_version:
                    by_config_version[version] = []
                by_config_version[version].append(record)
            
            # Calculate aggregate metrics per config version
            aggregates = []
            for version, records in sorted(by_config_version.items(), reverse=True):
                completed_records = [r for r in records if r.status == 'completed' and r.score is not None]
                failed_records = [r for r in records if r.status == 'failed']
                pending_records = [r for r in records if r.status == 'pending']
                
                if not completed_records:
                    aggregates.append({
                        'config_version': version,
                        'total_articles': len(records),
                        'completed': len(completed_records),
                        'failed': len(failed_records),
                        'pending': len(pending_records),
                        'mean_score': None,
                        'mean_absolute_error': None,
                        'mean_squared_error': None,
                        'perfect_matches': 0,
                        'perfect_match_percentage': 0.0,
                        'score_distribution': {
                            'exact': 0,
                            'within_2': 0,
                            'over_2': 0
                        }
                    })
                    continue
                
                # Calculate metrics
                scores = [r.score for r in completed_records]
                mean_score = sum(scores) / len(scores)
                mean_absolute_error = sum(abs(s) for s in scores) / len(scores)
                mean_squared_error = sum(s * s for s in scores) / len(scores)
                perfect_matches = sum(1 for s in scores if s == 0)
                perfect_match_percentage = (perfect_matches / len(completed_records)) * 100
                
                # Score distribution
                exact = sum(1 for s in scores if s == 0)
                within_2 = sum(1 for s in scores if abs(s) <= 2 and s != 0)
                over_2 = sum(1 for s in scores if abs(s) > 2)
                
                aggregates.append({
                    'config_version': version,
                    'total_articles': len(records),
                    'completed': len(completed_records),
                    'failed': len(failed_records),
                    'pending': len(pending_records),
                    'mean_score': round(mean_score, 2),
                    'mean_absolute_error': round(mean_absolute_error, 2),
                    'mean_squared_error': round(mean_squared_error, 2),
                    'perfect_matches': perfect_matches,
                    'perfect_match_percentage': round(perfect_match_percentage, 1),
                    'score_distribution': {
                        'exact': exact,
                        'within_2': within_2,
                        'over_2': over_2
                    }
                })
            
            return {
                'subagent': subagent,
                'aggregates': aggregates,
                'total_config_versions': len(aggregates)
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting aggregate eval scores: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

