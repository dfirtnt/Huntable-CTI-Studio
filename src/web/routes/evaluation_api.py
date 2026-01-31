"""
API routes for agent evaluation management.
"""

import logging
import os
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from langfuse import Langfuse
from pydantic import BaseModel, Field

from src.database.manager import DatabaseManager
from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SubagentEvaluationTable,
)
from src.services.eval_bundle_service import EvalBundleService
from src.utils.subagent_utils import build_subagent_lookup_values, normalize_subagent_name
from src.worker.celery_app import trigger_agentic_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _resolve_subagent_query(subagent: str) -> tuple[str, list[str]]:
    """Return the canonical name plus matching candidates for a subagent."""
    canonical, lookup_values = build_subagent_lookup_values(subagent)
    if not lookup_values:
        normalized_raw = str(subagent).strip()
        lookup_values = {normalized_raw} if normalized_raw else {subagent}

    canonical_value = canonical or (next(iter(lookup_values)) if lookup_values else subagent)
    return canonical_value, list(lookup_values)


def _load_preset_expected_by_url(subagent: str) -> dict[str, int]:
    """Load predetermined expected_count by article_url from eval_articles.yaml."""
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "eval_articles.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
    subagents = config.get("subagents", {})
    canonical, _ = _resolve_subagent_query(subagent)
    key = canonical if canonical in subagents else subagent
    articles = subagents.get(key, [])
    if not isinstance(articles, list):
        return {}
    out = {}
    for a in articles:
        url = a.get("url")
        if url is not None:
            out[url] = a.get("expected_count", 0) if a.get("expected_count") is not None else 0
    return out


def _get_langfuse_setting(key: str, env_key: str, default: str | None = None) -> str | None:
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

            setting = db_session.query(AppSettingsTable).filter(AppSettingsTable.key == key).first()

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
                        if isinstance(item.metadata, dict) or hasattr(item.metadata, "get"):
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

                            match = re.search(r"/(\d+)(?:/|$)", article_url)
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
                                        article = (
                                            db_session.query(ArticleTable)
                                            .filter(ArticleTable.title.ilike(f"%{article_title[:100]}%"))
                                            .first()
                                        )
                                        if article:
                                            article_id = article.id
                                            logger.info(
                                                f"Found article_id {article_id} by title matching: {article_title[:50]}"
                                            )

                                    # Strategy 2: Try matching by URL if it contains article info
                                    if not article_id and article_url:
                                        # Try to extract ID from URL
                                        import re

                                        url_match = re.search(r"[^/](\d{2,})[^/]", article_url)
                                        if url_match:
                                            potential_id = int(url_match.group(1))
                                            article = (
                                                db_session.query(ArticleTable)
                                                .filter(ArticleTable.id == potential_id)
                                                .first()
                                            )
                                            if article:
                                                article_id = article.id
                                                logger.info(
                                                    f"Found article_id {article_id} by URL pattern: {article_url}"
                                                )

                                    # Strategy 3: Try content matching with multiple snippet sizes
                                    if not article_id:
                                        for snippet_size in [500, 300, 200, 100]:
                                            content_snippet = article_text[:snippet_size].strip()
                                            if content_snippet:
                                                # Escape special characters for LIKE query
                                                content_snippet_escaped = content_snippet.replace("%", "\\%").replace(
                                                    "_", "\\_"
                                                )
                                                article = (
                                                    db_session.query(ArticleTable)
                                                    .filter(ArticleTable.content.like(f"%{content_snippet_escaped}%"))
                                                    .first()
                                                )
                                                if article:
                                                    article_id = article.id
                                                    logger.info(
                                                        f"Found article_id {article_id} by content matching (snippet size: {snippet_size})"
                                                    )
                                                    break

                                    if not article_id:
                                        logger.warning(
                                            f"Could not find article_id for dataset item {item.id} - tried title, URL, and content matching"
                                        )
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
                            "article_title_preview": item.input.get("article_title", "")[:50]
                            if item.input.get("article_title")
                            else None,
                        }
                    logger.info(f"Dataset item {item.id}: input={input_info}, article_id={article_id}")

                    # Convert to int if it's a string number
                    if (
                        (article_id and isinstance(article_id, str) and article_id.isdigit())
                        or article_id
                        and isinstance(article_id, (int, float))
                    ):
                        article_id = int(article_id)
                    elif article_id:
                        # If article_id exists but isn't numeric, log and set to None
                        logger.warning(f"Non-numeric article_id found: {article_id} (type: {type(article_id)})")
                        article_id = None

                    # Include item even if article_id not found (for manual review)
                    items.append(
                        {
                            "id": item.id if hasattr(item, "id") else str(item),
                            "input": item.input if hasattr(item, "input") else {},
                            "expected_output": expected_output,
                            "expected_count": expected_count,
                            "metadata": item.metadata if hasattr(item, "metadata") else {},
                            "status": item.status if hasattr(item, "status") else "ACTIVE",
                            "article_id": article_id,
                            "lookup_failed": article_id is None,  # Flag for UI to show warning
                        }
                    )
            except Exception as iter_error:
                logger.error(f"Error iterating dataset items: {iter_error}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error reading dataset items: {str(iter_error)}",
                )

        return {
            "dataset_name": dataset.name if hasattr(dataset, "name") else dataset_name,
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dataset items: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class EvaluationRunRequest(BaseModel):
    """Request to run evaluation."""

    article_ids: list[int]
    config_ids: list[int]  # Workflow config IDs to test


@router.post("/run")
async def run_evaluation(request: Request, eval_request: EvaluationRunRequest):
    """Run articles through workflows with different configs."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            executions = []

            for article_id in eval_request.article_ids:
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()

                if not article:
                    logger.warning(f"Article {article_id} not found")
                    continue

                for config_id in eval_request.config_ids:
                    config = (
                        db_session.query(AgenticWorkflowConfigTable)
                        .filter(AgenticWorkflowConfigTable.id == config_id)
                        .first()
                    )

                    if not config:
                        logger.warning(f"Config {config_id} not found")
                        continue

                    # Create execution with config snapshot
                    # Note: Workflow uses active config, so we activate this config temporarily
                    # For proper eval support, workflow should be modified to use config_snapshot when present
                    original_active = (
                        db_session.query(AgenticWorkflowConfigTable)
                        .filter(AgenticWorkflowConfigTable.is_active == True)
                        .first()
                    )

                    # Temporarily activate eval config
                    if original_active and original_active.id != config.id:
                        original_active.is_active = False
                    config.is_active = True
                    db_session.commit()

                    execution = AgenticWorkflowExecutionTable(
                        article_id=article_id,
                        status="pending",
                        config_snapshot={
                            "min_hunt_score": config.min_hunt_score,
                            "ranking_threshold": config.ranking_threshold,
                            "similarity_threshold": config.similarity_threshold,
                            "junk_filter_threshold": config.junk_filter_threshold,
                            "agent_models": config.agent_models or {},
                            "agent_prompts": config.agent_prompts or {},
                            "qa_enabled": config.qa_enabled or {},
                            "rank_agent_enabled": config.rank_agent_enabled
                            if hasattr(config, "rank_agent_enabled")
                            else True,
                            "config_id": config.id,
                            "config_version": config.version,
                            "eval_run": True,
                            "skip_rank_agent": True,  # Bypass rank agent for evals
                            "original_config_id": original_active.id if original_active else None,
                        },
                    )
                    db_session.add(execution)
                    db_session.commit()
                    db_session.refresh(execution)

                    # Trigger workflow via Celery (will use the now-active config)
                    trigger_agentic_workflow.delay(article_id, execution.id)

                    # Note: Config remains active - user should restore original manually
                    # Or implement proper config restoration after workflow completes
                    logger.info(f"Eval execution {execution.id}: Using config {config.id} (v{config.version})")

                    executions.append(
                        {
                            "execution_id": execution.id,
                            "article_id": article_id,
                            "config_id": config_id,
                            "config_version": config.version,
                        }
                    )

            if len(executions) == 0:
                return {
                    "success": False,
                    "executions": [],
                    "message": "No executions were created. Check that articles and configs exist.",
                }

            return {
                "success": True,
                "executions": executions,
                "message": f"Triggered {len(executions)} workflow executions",
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
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(status_code=404, detail="Execution not found")

            # Extract cmdline count from extraction result
            cmdline_count = 0
            warnings = []
            extraction_result = execution.extraction_result
            if extraction_result and isinstance(extraction_result, dict):
                subresults = extraction_result.get("subresults", {})
                if isinstance(subresults, dict):
                    cmdline = subresults.get("cmdline", {})
                    if isinstance(cmdline, dict):
                        cmdline_count = cmdline.get("count", 0)

                # Extract truncation warnings if any
                if "warnings" in extraction_result:
                    extraction_warnings = extraction_result.get("warnings")
                    if isinstance(extraction_warnings, list):
                        warnings.extend(extraction_warnings)

            return {
                "execution_id": execution.id,
                "article_id": execution.article_id,
                "status": execution.status,
                "cmdline_count": cmdline_count,
                "config_version": execution.config_snapshot.get("config_version")
                if execution.config_snapshot
                else None,
                "warnings": warnings if warnings else None,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execution/{execution_id}/commandlines")
async def get_execution_commandlines(
    request: Request,
    execution_id: int,
):
    """Get commandlines extracted from a workflow execution."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(status_code=404, detail="Execution not found")

            # Check if this is a subagent eval and which subagent
            config_snapshot = execution.config_snapshot or {}
            raw_subagent_eval = config_snapshot.get("subagent_eval")
            normalized_subagent_eval = normalize_subagent_name(raw_subagent_eval)

            # Determine which results to return based on subagent_eval
            result_key = normalized_subagent_eval or "cmdline"

            commandlines = []
            extraction_result = execution.extraction_result

            if extraction_result and isinstance(extraction_result, dict):
                # Check observables list first
                observables = extraction_result.get("observables", [])
                if isinstance(observables, list):
                    if result_key == "cmdline":
                        commandlines = [
                            obs.get("value", str(obs))
                            for obs in observables
                            if obs.get("type") == "cmdline" or obs.get("type") == "commandline"
                        ]
                    elif result_key == "process_lineage":
                        commandlines = [
                            obs.get("value", str(obs)) for obs in observables if obs.get("type") == "process_lineage"
                        ]
                    elif result_key == "hunt_queries":
                        commandlines = [
                            obs.get("value", str(obs)) for obs in observables if obs.get("type") == "hunt_queries"
                        ]

                # Also check subresults
                if not commandlines:
                    subresults = extraction_result.get("subresults", {})
                    if isinstance(subresults, dict):
                        # Get results for the appropriate subagent
                        if result_key == "cmdline":
                            cmdline_result = subresults.get("cmdline", {}) or subresults.get("CmdlineExtract", {})
                            if isinstance(cmdline_result, dict):
                                items = cmdline_result.get("items", [])
                                if items:
                                    commandlines = items if isinstance(items, list) else [items]
                        elif result_key == "process_lineage":
                            proc_tree_result = subresults.get("process_lineage", {}) or subresults.get(
                                "ProcTreeExtract", {}
                            )
                            if isinstance(proc_tree_result, dict):
                                items = proc_tree_result.get("items", [])
                                if items:
                                    commandlines = items if isinstance(items, list) else [items]
                        elif result_key == "hunt_queries":
                            hunt_queries_result = subresults.get("hunt_queries", {}) or subresults.get(
                                "HuntQueriesExtract", {}
                            )
                            if isinstance(hunt_queries_result, dict):
                                # For hunt_queries, we want to return both EDR queries and SIGMA rules separately
                                # but also include items for backward compatibility
                                items = hunt_queries_result.get("items", [])
                                if items:
                                    commandlines = items if isinstance(items, list) else [items]

            # Extract truncation warnings if any
            warnings = []
            if extraction_result and isinstance(extraction_result, dict):
                if "warnings" in extraction_result:
                    extraction_warnings = extraction_result.get("warnings")
                    if isinstance(extraction_warnings, list):
                        warnings.extend(extraction_warnings)

            response_data = {
                "execution_id": execution_id,
                "article_id": execution.article_id,
                "commandlines": commandlines,
                "count": len(commandlines),
                "subagent_eval": normalized_subagent_eval or (raw_subagent_eval or ""),
                "result_type": result_key,
                "warnings": warnings if warnings else None,
            }

            return response_data
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution commandlines: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def resolve_article_by_url(url: str) -> int | None:
    """
    Resolve article ID from URL by querying articles table.

    Args:
        url: Full article URL

    Returns:
        Article ID if found, None otherwise
    """
    try:
        import re
        from urllib.parse import urlparse

        # Handle localhost/article ID URLs (e.g., http://127.0.0.1:8001/articles/1523)
        parsed = urlparse(url)
        if parsed.netloc in ("127.0.0.1:8001", "localhost:8001", "127.0.0.1", "localhost"):
            # Extract article ID from path like /articles/1523
            match = re.match(r"/articles/(\d+)", parsed.path)
            if match:
                article_id = int(match.group(1))
                # Verify article exists in database
                db_manager = DatabaseManager()
                db_session = db_manager.get_session()
                try:
                    article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                    if article:
                        return article.id
                finally:
                    db_session.close()

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            # Try exact match on canonical_url first
            article = db_session.query(ArticleTable).filter(ArticleTable.canonical_url == url).first()

            if article:
                return article.id

            # Try partial match (URL might have query params or fragments)
            # Normalize URL by removing query params and fragments for comparison
            from urllib.parse import urlunparse

            parsed = urlparse(url)
            normalized_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

            article = (
                db_session.query(ArticleTable).filter(ArticleTable.canonical_url.like(f"{normalized_url}%")).first()
            )

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
    subagent: str = Query(..., description="Subagent name (cmdline, hunt_queries, etc.)"),
):
    """Get eval articles for a specific subagent from config file."""
    try:
        # Load eval articles config (go up 4 levels from src/web/routes/ to project root)
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "eval_articles.yaml"

        if not config_path.exists():
            raise HTTPException(status_code=404, detail="eval_articles.yaml config file not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        subagents = config.get("subagents", {})
        canonical_subagent, _ = _resolve_subagent_query(subagent)
        subagent_key = canonical_subagent if canonical_subagent in subagents else subagent
        if subagent_key not in subagents:
            raise HTTPException(status_code=404, detail=f"Subagent '{subagent}' not found in config")

        articles = subagents.get(subagent_key, [])
        if not isinstance(articles, list):
            articles = []

        # Resolve article IDs for each URL
        results = []
        for article_def in articles:
            url = article_def.get("url")

            if not url:
                continue

            article_id = resolve_article_by_url(url)

            # Standard single-count format for all subagents
            expected_count = article_def.get("expected_count", 0)
            results.append(
                {
                    "url": url,
                    "expected_count": expected_count,
                    "article_id": article_id,
                    "found": article_id is not None,
                }
            )

        return {"subagent": subagent, "articles": results, "total": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading subagent eval articles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class SubagentEvalRunRequest(BaseModel):
    """Request to run subagent evaluation."""

    subagent_name: str
    article_urls: list[str]
    use_active_config: bool = True


@router.post("/run-subagent-eval")
async def run_subagent_eval(request: Request, eval_request: SubagentEvalRunRequest):
    """Run subagent evaluation against selected articles."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            # Get current active config
            active_config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .first()
            )

            if not active_config:
                raise HTTPException(status_code=404, detail="No active workflow config found")

            # Resolve article URLs to IDs
            article_mappings = []
            for url in eval_request.article_urls:
                article_id = resolve_article_by_url(url)
                if not article_id:
                    logger.warning(f"Article not found for URL: {url}")
                    # Still create eval record but mark as failed
                    article_mappings.append({"url": url, "article_id": None, "found": False})
                else:
                    article_mappings.append({"url": url, "article_id": article_id, "found": True})

            raw_subagent_name = str(eval_request.subagent_name or "").strip()
            canonical_subagent_name = normalize_subagent_name(raw_subagent_name)
            if not canonical_subagent_name:
                canonical_subagent_name = raw_subagent_name
            if not canonical_subagent_name:
                canonical_subagent_name = eval_request.subagent_name

            # Get expected counts from config (go up 4 levels from src/web/routes/ to project root)
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "eval_articles.yaml"
            expected_counts = {}
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    subagent_articles = config.get("subagents", {}).get(canonical_subagent_name, [])
                    for article_def in subagent_articles:
                        url = article_def.get("url")
                        expected_count = article_def.get("expected_count")
                        if url:
                            expected_counts[url] = expected_count if expected_count is not None else 0

            # Create SubagentEvaluationTable records and workflow executions
            eval_records = []
            executions = []

            for mapping in article_mappings:
                url = mapping["url"]
                article_id = mapping["article_id"]
                expected_count = expected_counts.get(url, 0)

                if not article_id:
                    # Create eval record but mark as failed
                    eval_record = SubagentEvaluationTable(
                        subagent_name=canonical_subagent_name,
                        article_url=url,
                        article_id=None,
                        expected_count=expected_count,
                        workflow_config_id=active_config.id,
                        workflow_config_version=active_config.version,
                        status="failed",
                    )
                    db_session.add(eval_record)
                    eval_records.append(eval_record)
                    continue

                # Create workflow execution
                execution = AgenticWorkflowExecutionTable(
                    article_id=article_id,
                    status="pending",
                    config_snapshot={
                        "min_hunt_score": active_config.min_hunt_score,
                        "ranking_threshold": active_config.ranking_threshold,
                        "similarity_threshold": active_config.similarity_threshold,
                        "junk_filter_threshold": active_config.junk_filter_threshold,
                        "agent_models": active_config.agent_models or {},
                        "agent_prompts": active_config.agent_prompts or {},
                        "qa_enabled": active_config.qa_enabled or {},
                        "config_id": active_config.id,
                        "config_version": active_config.version,
                        "eval_run": True,
                        "skip_os_detection": True,  # Bypass OS detection for evals
                        "skip_rank_agent": True,  # Bypass rank agent for evals
                        "skip_sigma_generation": True,  # Skip SIGMA generation for evals
                        "subagent_eval": canonical_subagent_name,
                    },
                )
                db_session.add(execution)
                db_session.flush()  # Get execution.id

                # Create SubagentEvaluationTable record
                eval_record = SubagentEvaluationTable(
                    subagent_name=canonical_subagent_name,
                    article_url=url,
                    article_id=article_id,
                    expected_count=expected_count,
                    workflow_execution_id=execution.id,
                    workflow_config_id=active_config.id,
                    workflow_config_version=active_config.version,
                    status="pending",
                )
                db_session.add(eval_record)
                eval_records.append(eval_record)
                executions.append(
                    {
                        "execution_id": execution.id,
                        "article_id": article_id,
                        "url": url,
                        "eval_record_id": eval_record.id,
                    }
                )

            db_session.commit()

            # Trigger workflows one at a time (sequential batch)
            for exec_info in executions:
                trigger_agentic_workflow.delay(exec_info["article_id"], exec_info["execution_id"])
                logger.info(
                    f"Triggered workflow execution {exec_info['execution_id']} for article {exec_info['article_id']}"
                )

            return {
                "success": True,
                "subagent": canonical_subagent_name,
                "total_articles": len(eval_request.article_urls),
                "found_articles": sum(1 for m in article_mappings if m["found"]),
                "executions": executions,
                "message": f"Triggered {len(executions)} workflow executions for {canonical_subagent_name} evaluation",
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
    eval_run_id: int | None = Query(None, description="Optional: filter by eval record ID"),
):
    """Get evaluation results for a subagent."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            canonical_subagent, lookup_values = _resolve_subagent_query(subagent)

            # For hunt_queries, include historical hunt_queries_edr records to show previous EDR results
            if canonical_subagent == "hunt_queries":
                lookup_values = set(lookup_values) if lookup_values else set()
                lookup_values.add("hunt_queries_edr")
                lookup_values = list(lookup_values)

            query = db_session.query(SubagentEvaluationTable)
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))

            if eval_run_id:
                query = query.filter(SubagentEvaluationTable.id == eval_run_id)

            eval_records = query.order_by(SubagentEvaluationTable.created_at.desc()).all()

            results = []
            for record in eval_records:
                actual_count = record.actual_count
                warnings = []

                if record.workflow_execution_id:
                    execution = (
                        db_session.query(AgenticWorkflowExecutionTable)
                        .filter(AgenticWorkflowExecutionTable.id == record.workflow_execution_id)
                        .first()
                    )

                    if execution and execution.extraction_result and isinstance(execution.extraction_result, dict):
                        # Extract warnings
                        if "warnings" in execution.extraction_result:
                            extraction_warnings = execution.extraction_result.get("warnings")
                            if isinstance(extraction_warnings, list):
                                warnings.extend(extraction_warnings)

                # Calculate score if actual_count is set
                score = None
                if actual_count is not None:
                    score = actual_count - record.expected_count

                results.append(
                    {
                        "id": record.id,
                        "url": record.article_url,
                        "article_id": record.article_id,
                        "subagent_name": record.subagent_name,  # Include subagent_name for filtering
                        "expected_count": record.expected_count,
                        "actual_count": actual_count,
                        "score": score,
                        "status": record.status,
                        "execution_id": record.workflow_execution_id,
                        "config_version": record.workflow_config_version,
                        "created_at": record.created_at.isoformat() if record.created_at else None,
                        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
                        "workflow_config_id": record.workflow_config_id,
                        "warnings": warnings if warnings else None,
                    }
                )

            return {"subagent": canonical_subagent, "results": results, "total": len(results)}
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
            eval_record = (
                db_session.query(SubagentEvaluationTable).filter(SubagentEvaluationTable.id == eval_record_id).first()
            )

            if not eval_record:
                raise HTTPException(status_code=404, detail="Evaluation record not found")

            # Get all eval records for the same subagent and config version
            all_records = (
                db_session.query(SubagentEvaluationTable)
                .filter(
                    SubagentEvaluationTable.subagent_name == eval_record.subagent_name,
                    SubagentEvaluationTable.workflow_config_version == eval_record.workflow_config_version,
                )
                .all()
            )

            total = len(all_records)
            completed = sum(1 for r in all_records if r.status == "completed")
            failed = sum(1 for r in all_records if r.status == "failed")
            pending = sum(1 for r in all_records if r.status == "pending")

            # Calculate aggregate metrics
            completed_records = [r for r in all_records if r.status == "completed" and r.score is not None]
            if completed_records:
                perfect_matches = sum(1 for r in completed_records if r.score == 0)
                accuracy = perfect_matches / len(completed_records) if completed_records else 0.0
                mean_score = sum(r.score for r in completed_records) / len(completed_records)
            else:
                accuracy = None
                mean_score = None
                perfect_matches = 0

            return {
                "eval_record_id": eval_record_id,
                "subagent": eval_record.subagent_name,
                "status": eval_record.status,
                "progress": {
                    "completed": completed,
                    "failed": failed,
                    "pending": pending,
                    "total": total,
                },
                "metrics": {
                    "accuracy": accuracy,
                    "mean_score": mean_score,
                    "perfect_matches": perfect_matches,
                },
                "current_record": {
                    "url": eval_record.article_url,
                    "expected_count": eval_record.expected_count,
                    "actual_count": eval_record.actual_count,
                    "score": eval_record.score,
                },
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subagent eval status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/subagent-eval-clear-pending")
async def clear_pending_eval_records(request: Request, subagent: str = Query(..., description="Subagent name")):
    """Delete all pending evaluation records for a subagent."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            canonical_subagent, lookup_values = _resolve_subagent_query(subagent)

            # Find all pending records for this subagent
            pending_records = (
                db_session.query(SubagentEvaluationTable)
                .filter(
                    SubagentEvaluationTable.subagent_name.in_(lookup_values),
                    SubagentEvaluationTable.status == "pending",
                )
                .all()
            )

            deleted_count = len(pending_records)

            # Delete the records
            for record in pending_records:
                db_session.delete(record)

            db_session.commit()

            logger.info(f"Deleted {deleted_count} pending evaluation records for subagent {canonical_subagent}")

            return {
                "success": True,
                "deleted_count": deleted_count,
                "subagent": canonical_subagent,
                "message": f"Deleted {deleted_count} pending evaluation record(s)",
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error clearing pending eval records: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subagent-eval-backfill")
async def backfill_eval_records(request: Request, subagent: str = Query(..., description="Subagent name")):
    """Backfill pending eval records for completed workflow executions."""
    try:
        from src.workflows.agentic_workflow import _update_subagent_eval_on_completion

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            canonical_subagent, lookup_values = _resolve_subagent_query(subagent)

            # Find all pending eval records for this subagent
            pending_evals = (
                db_session.query(SubagentEvaluationTable)
                .filter(
                    SubagentEvaluationTable.subagent_name.in_(lookup_values),
                    SubagentEvaluationTable.status == "pending",
                )
                .all()
            )

            updated_count = 0
            failed_count = 0

            for eval_record in pending_evals:
                if not eval_record.workflow_execution_id:
                    continue

                execution = (
                    db_session.query(AgenticWorkflowExecutionTable)
                    .filter(AgenticWorkflowExecutionTable.id == eval_record.workflow_execution_id)
                    .first()
                )

                if not execution or execution.status != "completed":
                    continue

                # Use the existing update function
                try:
                    _update_subagent_eval_on_completion(execution, db_session)
                    # Check if it was updated
                    db_session.refresh(eval_record)
                    if eval_record.status == "completed":
                        updated_count += 1
                    elif eval_record.status == "failed":
                        failed_count += 1
                except Exception as e:
                    logger.warning(f"Error updating eval record {eval_record.id}: {e}")
                    failed_count += 1

            db_session.commit()

            logger.info(f"Backfilled {updated_count} eval records for subagent {canonical_subagent}")

            return {
                "success": True,
                "updated_count": updated_count,
                "failed_count": failed_count,
                "subagent": canonical_subagent,
                "message": f"Updated {updated_count} record(s), {failed_count} marked as failed",
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
    config_version: int | None = Query(None, description="Optional: filter by config version"),
):
    """Get aggregate scores per config version for a subagent."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            canonical_subagent, lookup_values = _resolve_subagent_query(subagent)

            # For hunt_queries, include historical hunt_queries_edr records for aggregate calculations
            if canonical_subagent == "hunt_queries":
                lookup_values = set(lookup_values) if lookup_values else set()
                lookup_values.add("hunt_queries_edr")
                lookup_values = list(lookup_values)

            query = db_session.query(SubagentEvaluationTable)
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))

            if config_version:
                query = query.filter(SubagentEvaluationTable.workflow_config_version == config_version)

            all_records = query.order_by(
                SubagentEvaluationTable.workflow_config_version.desc(),
                SubagentEvaluationTable.created_at.desc(),
            ).all()

            # Predetermined expected_count by article_url from eval_articles.yaml
            preset_expected_by_url = _load_preset_expected_by_url(subagent)

            # Group by config version
            by_config_version = {}
            for record in all_records:
                version = record.workflow_config_version
                if version not in by_config_version:
                    by_config_version[version] = []
                by_config_version[version].append(record)

            # Calculate aggregate metrics per config version using preset expected
            aggregates = []
            for version, records in sorted(by_config_version.items(), reverse=True):
                completed_records = [r for r in records if r.status == "completed" and r.actual_count is not None]
                failed_records = [r for r in records if r.status == "failed"]
                pending_records = [r for r in records if r.status == "pending"]

                if not completed_records:
                    aggregates.append(
                        {
                            "config_version": version,
                            "total_articles": len(records),
                            "completed": len(completed_records),
                            "failed": len(failed_records),
                            "pending": len(pending_records),
                            "mean_score": None,
                            "mean_absolute_error": None,
                            "raw_mae": None,
                            "mean_expected_count": None,
                            "mean_squared_error": None,
                            "perfect_matches": 0,
                            "perfect_match_percentage": 0.0,
                            "score_distribution": {
                                "exact": 0,
                                "within_2": 0,
                                "over_2": 0,
                            },
                        }
                    )
                    continue

                # Score = actual - preset_expected (fallback to record.expected_count if url not in preset)
                scores = []
                expected_counts = []
                for r in completed_records:
                    expected = preset_expected_by_url.get(r.article_url)
                    if expected is None:
                        expected = r.expected_count if r.expected_count is not None else 0
                    expected_counts.append(expected)
                    scores.append((r.actual_count or 0) - expected)

                mean_score = sum(scores) / len(scores)
                mean_absolute_error = sum(abs(s) for s in scores) / len(scores)
                mean_expected_count = sum(expected_counts) / len(expected_counts) if expected_counts else 1.0
                divisor = max(mean_expected_count, 1.0)
                nmae_raw = mean_absolute_error / divisor if divisor > 0 else None
                normalized_mean_absolute_error = min(nmae_raw, 1.0) if nmae_raw is not None else None
                mean_squared_error = sum(s * s for s in scores) / len(scores)
                perfect_matches = sum(1 for s in scores if s == 0)
                perfect_match_percentage = (perfect_matches / len(completed_records)) * 100
                exact = sum(1 for s in scores if s == 0)
                within_2 = sum(1 for s in scores if abs(s) <= 2 and s != 0)
                over_2 = sum(1 for s in scores if abs(s) > 2)

                aggregates.append(
                    {
                        "config_version": version,
                        "total_articles": len(records),
                        "completed": len(completed_records),
                        "failed": len(failed_records),
                        "pending": len(pending_records),
                        "mean_score": round(mean_score, 2),
                        "mean_absolute_error": round(normalized_mean_absolute_error, 4)
                        if normalized_mean_absolute_error is not None
                        else None,
                        "raw_mae": round(mean_absolute_error, 4),
                        "mean_expected_count": round(mean_expected_count, 4),
                        "mean_squared_error": round(mean_squared_error, 2),
                        "perfect_matches": perfect_matches,
                        "perfect_match_percentage": round(perfect_match_percentage, 1),
                        "score_distribution": {
                            "exact": exact,
                            "within_2": within_2,
                            "over_2": over_2,
                        },
                    }
                )

            return {
                "subagent": subagent,
                "aggregates": aggregates,
                "total_config_versions": len(aggregates),
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting aggregate eval scores: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config-versions-models")
async def get_config_versions_models(
    request: Request,
    config_versions: str = Query("1", description="Comma-separated list of config version numbers"),
):
    """Get agent models for specified config versions."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            version_list = [int(v.strip()) for v in config_versions.split(",") if v.strip()]

            if not version_list:
                return {"models_by_version": {}}

            configs = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.version.in_(version_list))
                .all()
            )

            models_by_version = {}
            for config in configs:
                agent_models = config.agent_models or {}
                qa_enabled = config.qa_enabled or {}
                agent_prompts = config.agent_prompts or {}

                # Get disabled extract agents (same logic as frontend)
                extract_settings = agent_prompts.get("ExtractAgentSettings") or agent_prompts.get("ExtractAgent") or {}
                disabled_raw = (
                    extract_settings.get("disabled_agents") or extract_settings.get("disabled_sub_agents") or []
                )

                disabled_set = set()
                if isinstance(disabled_raw, list):
                    disabled_set = set(disabled_raw)
                elif isinstance(disabled_raw, dict):
                    disabled_set = {
                        key
                        for key, value in disabled_raw.items()
                        if value is False or value == 0 or (isinstance(value, str) and value.lower() == "false")
                    }

                # Build model list (same format as frontend)
                model_list = []

                # Main agents (only if QA enabled)
                if agent_models.get("SigmaAgent") and qa_enabled.get("SigmaAgent"):
                    provider = agent_models.get("SigmaAgent_provider") or "lmstudio"
                    model_list.append(f"SIGMA: {agent_models['SigmaAgent']} ({provider})")

                # Sub-agents (only if enabled and has model)
                for agent in ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract"]:
                    model_key = f"{agent}_model"
                    if agent_models.get(model_key) and agent not in disabled_set:
                        provider = agent_models.get(f"{agent}_provider") or "lmstudio"
                        model_list.append(f"{agent}: {agent_models[model_key]} ({provider})")

                models_by_version[config.version] = {
                    "agent_models": agent_models,
                    "qa_enabled": qa_enabled,
                    "display_text": "\n".join(model_list) if model_list else "No models configured",
                }

            return {"models_by_version": models_by_version}
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting config versions models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ExportBundleRequest(BaseModel):
    """Request model for eval bundle export."""

    agent_name: str = Field(..., description="Agent name (e.g., 'CmdlineExtract', 'rank_article')")
    attempt: int | None = Field(None, description="Attempt number (1-indexed). If None, uses last attempt.")
    inline_large_text: bool = Field(False, description="Whether to inline large text fields")
    max_inline_chars: int = Field(200000, description="Maximum characters to inline before truncation")


@router.post("/evals/{execution_id}/export-bundle")
async def export_eval_bundle(request: Request, execution_id: int, export_request: ExportBundleRequest):
    """
    Export evaluation bundle for a specific LLM call within a workflow execution.

    Returns eval_bundle_v1 JSON with all inputs, outputs, and provenance data.
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            bundle_service = EvalBundleService(db_session)
            try:
                bundle = bundle_service.generate_bundle(
                    execution_id=execution_id,
                    agent_name=export_request.agent_name,
                    attempt=export_request.attempt,
                    inline_large_text=export_request.inline_large_text,
                    max_inline_chars=export_request.max_inline_chars,
                )
            except AttributeError as e:
                logger.error(f"AttributeError in bundle generation: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error accessing data structure: {str(e)}. This may indicate a data format issue in the execution record.",
                )

            # Workflow metadata already set by service (includes actual attempt used)

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
        logger.error(f"Execution not found: {execution_id} - {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting eval bundle for execution {execution_id}: {e}", exc_info=True)
        error_detail = str(e)
        # Add more context if it's a missing data error
        if "not found" in error_detail.lower() or "missing" in error_detail.lower():
            error_detail = f"{error_detail}. Check that the execution has error_log data for the specified agent."
        raise HTTPException(status_code=500, detail=error_detail)


@router.get("/evals/{execution_id}/export-bundle")
async def get_eval_bundle_metadata(
    request: Request,
    execution_id: int,
    agent_name: str | None = Query(None, description="Agent name (optional, defaults to first available)"),
    attempt: int = Query(1, description="Attempt number (defaults to 1)"),
):
    """
    Get metadata for the most recent eval bundle or regenerate on demand.

    Query params:
    - agent_name: Agent name (optional, defaults to first available)
    - attempt: Attempt number (defaults to 1)
    """
    try:
        db_manager = DatabaseManager()
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
                # Filter out non-agent keys
                agent_keys = ["rank_article", "extract_agent", "generate_sigma", "os_detection"]
                available_agents = [k for k in error_log.keys() if k in agent_keys]
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
        raise HTTPException(status_code=500, detail=str(e))
