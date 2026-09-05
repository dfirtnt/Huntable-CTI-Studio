"""
API routes for agent evaluation management.
"""

import hashlib
import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.database.manager import DatabaseManager
from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SubagentEvaluationTable,
)
from src.services.audit_service import (
    ACTION_EVAL_BUNDLE_EXPORTED,
    ACTION_EVAL_RECORDS_BACKFILLED,
    ACTION_EVAL_RECORDS_CLEARED,
    ACTION_EVAL_RECORDS_RESCORED,
    ACTION_EVAL_RUN_REQUESTED,
    STATUS_SUCCESS,
    AuditEvent,
    AuditService,
    build_actor_context,
)
from src.services.eval_bundle_service import EvalBundleService, compute_sha256_json
from src.services.eval_item_scorer import calculate_f_beta
from src.services.execution_snapshot_store import attach_snapshot, hydrate_snapshot
from src.services.subagent_eval_launch_service import (
    EVAL_ARTICLES_DATA_DIR,
    EVAL_STAGGER_SECONDS,
    MAX_EVAL_EXECUTIONS_ENV,
    EvalLaunchCapExceededError,
    EvalLaunchError,
    NoActiveConfigError,
    launch_subagent_eval,
    load_static_eval_articles,
    plan_subagent_eval,
    resolve_article_ids_by_urls,
)
from src.services.subagent_eval_service import rescore_completed_record, update_subagent_eval_on_completion
from src.services.workflow_config_snapshot import build_config_snapshot
from src.utils.langfuse_client import LANGFUSE_DEFAULT_HOST
from src.utils.subagent_utils import SUBAGENT_TO_EXTRACT_AGENT, build_subagent_lookup_values, normalize_subagent_name
from src.worker.celery_app import trigger_agentic_workflow

# Broker-side stagger floor for eval dispatch; owned by the launch service and
# re-exported here because other routes and tests read it from this module.
_EVAL_STAGGER_SECONDS = EVAL_STAGGER_SECONDS

# Patterns that indicate a provider rate-limit / TPM throttling failure.
# Covers OpenAI ("429", "rate limit", "try again in N..."), Anthropic
# ("rate_limit_error", "overloaded_error"), and generic wordings.
_THROTTLE_PATTERNS = re.compile(
    r"429|rate[\s_]?limit|rate_limit_error|try again in|overloaded",
    re.IGNORECASE,
)

# Billing-quota exhaustion -- 429 but NOT a retriable rate limit.
# Must be checked before _THROTTLE_PATTERNS so "insufficient_quota" errors
# are not misclassified as TPM throttles.
_QUOTA_ERROR_PATTERNS = re.compile(r"insufficient_quota", re.IGNORECASE)


def _is_throttle_string(text: str) -> bool:
    """Return True only if text signals a retriable rate limit (not a billing cap)."""
    if _QUOTA_ERROR_PATTERNS.search(text):
        return False
    return bool(_THROTTLE_PATTERNS.search(text))


def _audit_eval(
    db_session,
    request: Request,
    action: str,
    target_id: str | None,
    summary: str,
    metadata: dict | None = None,
    *,
    status: str = STATUS_SUCCESS,
    mandatory: bool = False,
) -> None:
    """Record an evaluation audit event on the route's existing sync session.

    These endpoints already own a sync session, so the event joins it rather than
    opening its own. Pass ``mandatory=True`` when the route is about to commit a
    DB mutation of its own (clearing or backfilling eval records): the event is
    added to that same transaction so the mutation and its attribution commit or
    roll back together. Dispatch-only routes use the best-effort commit.

    Audit emission only: nothing here reads, re-scrapes, or mutates eval-article
    rows or the config/eval_articles_data fixtures.
    """
    event = AuditEvent(
        action=action,
        target_type="evaluation",
        target_id=target_id,
        status=status,
        summary=summary,
        actor=build_actor_context(getattr(request.state, "identity", None), request),
        metadata=metadata or {},
    )
    if mandatory:
        AuditService.record_mandatory(db_session, event)
    else:
        AuditService.record_best_effort(db_session, event)


# Matches LMStudio context-exceeded messages and the context_length_exceeded flag on raw subagent results.
_CONTEXT_OVERFLOW_PATTERNS = re.compile(
    r"context.{0,15}(size|length|window).{0,15}exceeded|context_length_exceeded",
    re.IGNORECASE,
)

# Covers LMStudio "not ready" / "no model loaded" transient infra errors.
_INFRA_NOT_READY_PATTERNS = re.compile(
    r"lmstudio is not ready|no model.{0,20}loaded|ensure lmstudio is running",
    re.IGNORECASE,
)


def _execution_is_throttled(
    error_message: str | None,
    error_log: dict | list | str | None,
) -> bool:
    # Checks both error_message (terminal 429) and error_log conversation entries
    # because a throttled extractor stamps the error inside error_log while the
    # workflow still reports status='completed' and actual_count=0.
    if error_message and _is_throttle_string(error_message):
        return True

    if not isinstance(error_log, dict):
        return False

    extract_agent = error_log.get("extract_agent")
    if not isinstance(extract_agent, dict):
        return False

    conversation_log = extract_agent.get("conversation_log")
    if not isinstance(conversation_log, list):
        return False

    for entry in conversation_log:
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        for field in ("error", "error_type", "error_details"):
            value = result.get(field)
            if isinstance(value, str) and _is_throttle_string(value):
                return True
    return False


def _execution_has_context_overflow(
    error_message: str | None,
    error_log: dict | list | str | None,
    extraction_result: dict | None,
    subagent_lookup: str | None = None,
) -> bool:
    if error_message and _CONTEXT_OVERFLOW_PATTERNS.search(error_message):
        return True

    if isinstance(error_log, dict):
        extract_agent = error_log.get("extract_agent")
        if isinstance(extract_agent, dict):
            conversation_log = extract_agent.get("conversation_log")
            if isinstance(conversation_log, list):
                for entry in conversation_log:
                    if not isinstance(entry, dict):
                        continue
                    result = entry.get("result")
                    if not isinstance(result, dict):
                        continue
                    for field in ("error", "error_type", "error_details"):
                        value = result.get(field)
                        if isinstance(value, str) and _CONTEXT_OVERFLOW_PATTERNS.search(value):
                            return True

    if isinstance(extraction_result, dict) and subagent_lookup:
        subresults = extraction_result.get("subresults", {})
        if isinstance(subresults, dict):
            subresult = subresults.get(subagent_lookup, {})
            raw = subresult.get("raw", {}) if isinstance(subresult, dict) else {}
            if isinstance(raw, dict) and raw.get("context_length_exceeded"):
                return True

    return False


def _execution_has_quota_error(
    error_message: str | None,
    error_log: dict | list | str | None,
) -> bool:
    """Return True when the execution failed due to billing quota exhaustion (not a retriable rate limit)."""
    if error_message and _QUOTA_ERROR_PATTERNS.search(error_message):
        return True

    if not isinstance(error_log, dict):
        return False

    extract_agent = error_log.get("extract_agent")
    if not isinstance(extract_agent, dict):
        return False

    conversation_log = extract_agent.get("conversation_log")
    if not isinstance(conversation_log, list):
        return False

    for entry in conversation_log:
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        for field in ("error", "error_type", "error_details"):
            value = result.get(field)
            if isinstance(value, str) and _QUOTA_ERROR_PATTERNS.search(value):
                return True

    return False


def _execution_infra_not_ready(
    error_message: str | None,
    error_log: dict | list | str | None,
    extraction_result: dict | None,
) -> bool:
    if error_message and _INFRA_NOT_READY_PATTERNS.search(error_message):
        return True

    if isinstance(error_log, dict):
        extract_agent = error_log.get("extract_agent")
        if isinstance(extract_agent, dict):
            conversation_log = extract_agent.get("conversation_log")
            if isinstance(conversation_log, list):
                for entry in conversation_log:
                    if not isinstance(entry, dict):
                        continue
                    result = entry.get("result")
                    if not isinstance(result, dict):
                        continue
                    for field in ("error", "error_type", "error_details"):
                        value = result.get(field)
                        if isinstance(value, str) and _INFRA_NOT_READY_PATTERNS.search(value):
                            return True

    if isinstance(extraction_result, dict):
        subresults = extraction_result.get("subresults", {})
        if isinstance(subresults, dict):
            for subresult in subresults.values():
                raw = subresult.get("raw", {}) if isinstance(subresult, dict) else {}
                if isinstance(raw, dict):
                    err = raw.get("error", "")
                    if isinstance(err, str) and _INFRA_NOT_READY_PATTERNS.search(err):
                        return True

    return False


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])

# Article IDs excluded from eval results and aggregate calculations (e.g. duplicates removed from eval config)
EXCLUDED_EVAL_ARTICLE_IDS = frozenset({62})


def _resolve_subagent_query(subagent: str) -> tuple[str, list[str]]:
    """Return the canonical name plus matching candidates for a subagent."""
    canonical, lookup_values = build_subagent_lookup_values(subagent)
    if not lookup_values:
        normalized_raw = str(subagent).strip()
        lookup_values = {normalized_raw} if normalized_raw else {subagent}

    canonical_value = canonical or (next(iter(lookup_values)) if lookup_values else subagent)
    return canonical_value, list(lookup_values)


_ROOT = Path(__file__).parent.parent.parent.parent
_EVAL_ARTICLES_DATA_DIR = EVAL_ARTICLES_DATA_DIR

# Fixture loading (strict key allowlist + path-containment guard) lives in the
# launch service so the MCP launch tool inherits it; the private alias keeps
# this module's call sites and test patch targets stable.
_load_static_eval_articles = load_static_eval_articles


def _load_static_eval_fixture_by_url(article_url: str | None) -> str | None:
    """Return committed eval text for an article URL when the corpus contains it."""
    if not isinstance(article_url, str) or not article_url:
        return None

    for data_dir in _EVAL_ARTICLES_DATA_DIR.iterdir():
        if not data_dir.is_dir():
            continue
        entries = _load_static_eval_articles(data_dir.name)
        entry = entries.get(article_url)
        content = entry.get("content") if entry else None
        if isinstance(content, str) and content:
            return content
    return None


def _workflow_config_snapshot(config: AgenticWorkflowConfigTable) -> dict:
    """Capture every runtime workflow setting needed by an evaluation execution.

    Delegates to the shared snapshot builder so eval executions satisfy the same
    completeness contract as normal ones and are hashed the same way — an eval whose
    snapshot were incomplete would fall back to the live active config at run time,
    which is exactly the irreproducibility this is meant to remove.
    """
    return build_config_snapshot(config)


def _load_preset_expected_by_url(subagent: str) -> dict[str, int]:
    """Load predetermined expected_count by article_url from eval_articles.yaml."""
    config_path = _ROOT / "config" / "eval_articles.yaml"
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


def get_langfuse_client():
    """Initialize Langfuse client from database settings or environment variables."""
    from langfuse import Langfuse

    public_key = _get_langfuse_setting("LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY")
    secret_key = _get_langfuse_setting("LANGFUSE_SECRET_KEY", "LANGFUSE_SECRET_KEY")
    host = _get_langfuse_setting("LANGFUSE_HOST", "LANGFUSE_HOST", LANGFUSE_DEFAULT_HOST)

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
                                                        "Found article_id %s by content matching (snippet size: %s)",
                                                        article_id,
                                                        snippet_size,
                                                    )
                                                    break

                                    if not article_id:
                                        logger.warning(
                                            "Could not find article_id for dataset item %s - "
                                            "tried title, URL, and content matching",
                                            item.id,
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
                    if (article_id and isinstance(article_id, str) and article_id.isdigit()) or (
                        article_id and isinstance(article_id, (int, float))
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
                ) from iter_error

        return {
            "dataset_name": dataset.name if hasattr(dataset, "name") else dataset_name,
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dataset items: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
            stagger_idx = 0

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

                    config_snapshot = _workflow_config_snapshot(config)
                    config_snapshot.update(
                        {
                            "eval_run": True,
                            "skip_rank_agent": True,
                        }
                    )
                    fixture_content = _load_static_eval_fixture_by_url(article.canonical_url)
                    if fixture_content is not None:
                        config_snapshot["eval_fixture_content"] = fixture_content
                        config_snapshot["eval_fixture_content_sha256"] = hashlib.sha256(
                            fixture_content.encode("utf-8")
                        ).hexdigest()

                    execution = AgenticWorkflowExecutionTable(
                        article_id=article_id,
                        status="pending",
                    )
                    db_session.add(execution)
                    attach_snapshot(db_session, execution, config_snapshot)
                    db_session.commit()
                    db_session.refresh(execution)

                    # Trigger workflow via Celery. The execution snapshot is the
                    # complete configuration authority for this eval.
                    trigger_agentic_workflow.apply_async(
                        args=[article_id, execution.id],
                        countdown=stagger_idx * _EVAL_STAGGER_SECONDS,
                    )
                    stagger_idx += 1

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

            _audit_eval(
                db_session,
                request,
                ACTION_EVAL_RUN_REQUESTED,
                None,
                f"Triggered {len(executions)} evaluation workflow executions",
                {
                    "eval_kind": "workflow",
                    "executions_count": len(executions),
                    "execution_ids": [e["execution_id"] for e in executions],
                    "config_ids": sorted({e["config_id"] for e in executions}),
                },
            )

            return {
                "success": True,
                "executions": executions,
                "message": f"Triggered {len(executions)} workflow executions",
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error running evaluation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
                "config_version": hydrate_snapshot(execution).get("config_version"),
                "warnings": warnings if warnings else None,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution results: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


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

            # Check if this is a subagent eval and which subagent. Externalized
            # rows carry only {"snapshot_id": N}; hydrate to reach subagent_eval.
            config_snapshot = hydrate_snapshot(execution)
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
                    elif result_key == "registry_artifacts":
                        commandlines = [
                            obs.get("value", str(obs)) for obs in observables if obs.get("type") == "registry_artifacts"
                        ]
                    elif result_key == "windows_services":
                        commandlines = [
                            obs.get("value", str(obs)) for obs in observables if obs.get("type") == "windows_services"
                        ]
                    elif result_key == "scheduled_tasks":
                        commandlines = [
                            obs.get("value", str(obs)) for obs in observables if obs.get("type") == "scheduled_tasks"
                        ]
                    elif result_key == "network_indicators":
                        commandlines = [
                            obs.get("value", str(obs)) for obs in observables if obs.get("type") == "network_indicators"
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
                        elif result_key == "registry_artifacts":
                            registry_result = subresults.get("registry_artifacts", {}) or subresults.get(
                                "RegistryExtract", {}
                            )
                            if isinstance(registry_result, dict):
                                items = registry_result.get("items", [])
                                if items:
                                    commandlines = items if isinstance(items, list) else [items]
                        elif result_key == "windows_services":
                            services_result = subresults.get("windows_services", {}) or subresults.get(
                                "ServicesExtract", {}
                            )
                            if isinstance(services_result, dict):
                                items = services_result.get("items", [])
                                if items:
                                    commandlines = items if isinstance(items, list) else [items]
                        elif result_key == "scheduled_tasks":
                            sched_result = subresults.get("scheduled_tasks", {}) or subresults.get(
                                "ScheduledTasksExtract", {}
                            )
                            if isinstance(sched_result, dict):
                                items = sched_result.get("items", [])
                                if items:
                                    commandlines = items if isinstance(items, list) else [items]
                        elif result_key == "network_indicators":
                            network_result = subresults.get("network_indicators", {}) or subresults.get(
                                "NetworkIndicatorExtract", {}
                            )
                            if isinstance(network_result, dict):
                                items = network_result.get("items", [])
                                if items:
                                    commandlines = items if isinstance(items, list) else [items]

            # Extract truncation warnings if any
            warnings = []
            if extraction_result and isinstance(extraction_result, dict) and "warnings" in extraction_result:
                extraction_warnings = extraction_result.get("warnings")
                if isinstance(extraction_warnings, list):
                    warnings.extend(extraction_warnings)

            # Check if the relevant subagent hit a context length overflow
            context_length_exceeded = False
            if extraction_result and isinstance(extraction_result, dict):
                subresults = extraction_result.get("subresults", {})
                subresult = subresults.get(result_key, {}) if isinstance(subresults, dict) else {}
                raw = subresult.get("raw", {}) if isinstance(subresult, dict) else {}
                if isinstance(raw, dict) and raw.get("context_length_exceeded"):
                    context_length_exceeded = True

            # Article title and URL for display
            article_title = ""
            article_url = ""
            if execution.article_id is not None:
                article = db_session.query(ArticleTable).filter(ArticleTable.id == execution.article_id).first()
                if article:
                    article_title = (article.title or "").strip()
                    article_url = article.canonical_url or ""

            return {
                "execution_id": execution_id,
                "article_id": execution.article_id,
                "article_title": article_title or None,
                "article_url": article_url or None,
                "commandlines": commandlines,
                "count": len(commandlines),
                "subagent_eval": normalized_subagent_eval or (raw_subagent_eval or ""),
                "result_type": result_key,
                "warnings": warnings if warnings else None,
                "context_length_exceeded": context_length_exceeded,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution commandlines: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


def resolve_articles_by_urls(urls: list[str]) -> dict[str, int]:
    """Resolve article URLs to IDs on a route-owned session; errors log and yield {}.

    The batch lookup itself lives in the launch service so the MCP launch tool
    can resolve on its own session.
    """
    if not urls:
        return {}
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            return resolve_article_ids_by_urls(db_session, urls)
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error resolving articles by URLs: {e}")
        return {}


@router.get("/subagent-eval-articles")
async def get_subagent_eval_articles(
    request: Request,
    subagent: str = Query(..., description="Subagent name (cmdline, hunt_queries, etc.)"),
):
    """Get eval articles for a specific subagent from config file."""
    try:
        config_path = _ROOT / "config" / "eval_articles.yaml"
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

        urls = [a.get("url") for a in articles if a.get("url")]
        url_to_id = resolve_articles_by_urls(urls) if urls else {}
        url_to_static = _load_static_eval_articles(subagent_key)

        # Batch-fetch titles for DB-resolved articles
        article_ids = [url_to_id[u] for u in urls if url_to_id.get(u)]
        id_to_title: dict[int, str] = {}
        if article_ids:
            try:
                db_manager = DatabaseManager()
                db_session = db_manager.get_session()
                try:
                    rows = (
                        db_session.query(ArticleTable.id, ArticleTable.title)
                        .filter(ArticleTable.id.in_(article_ids))
                        .all()
                    )
                    id_to_title = {r[0]: (r[1] or "") for r in rows}
                finally:
                    db_session.close()
            except Exception as e:
                logger.warning("Could not fetch article titles for eval list: %s", e)

        results = []
        for article_def in articles:
            url = article_def.get("url")
            if not url:
                continue
            article_id = url_to_id.get(url)
            from_static = url in url_to_static
            found = article_id is not None or from_static
            expected_count = article_def.get("expected_count", 0)
            expected_items = article_def.get("expected_items")
            acceptable_items = article_def.get("acceptable_items")
            # Also pull expected_items from static snapshot when present
            if not expected_items and from_static and url in url_to_static:
                expected_items = url_to_static[url].get("expected_items")
                acceptable_items = url_to_static[url].get("acceptable_items")
            title = ""
            if from_static and url in url_to_static:
                title = (url_to_static[url].get("title") or "").strip()
            if not title and article_id is not None:
                title = (id_to_title.get(article_id) or "").strip()
            results.append(
                {
                    "url": url,
                    "title": title or None,
                    "expected_count": expected_count,
                    "expected_items": expected_items,
                    "acceptable_items": acceptable_items,
                    "article_id": article_id,
                    "found": found,
                    "from_static": from_static,
                }
            )

        return {"subagent": subagent, "articles": results, "total": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading subagent eval articles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


class SubagentEvalRunRequest(BaseModel):
    """Request to run subagent evaluation against the active workflow config.

    The run always targets the active config; the legacy ``use_active_config``
    flag some clients still send is ignored.
    """

    subagent_name: str
    article_urls: list[str]
    concurrency_throttle_seconds: float = Field(default=5.0, ge=0.0, le=60.0)


def _request_initiated_by(request: Request) -> str:
    """Provenance label stored in eval snapshot extras and the audit payload."""
    identity = getattr(getattr(request, "state", None), "identity", None)
    if identity is None or not getattr(identity, "is_authenticated", False):
        return "web"
    actor = getattr(identity, "user_id", None) or getattr(identity, "email", None)
    return f"user:{actor}" if actor else "web"


@router.post("/run-subagent-eval")
async def run_subagent_eval(request: Request, eval_request: SubagentEvalRunRequest):
    """Run subagent evaluation against selected articles.

    Thin wrapper over ``subagent_eval_launch_service``: the service plans and
    writes, this route maps plan outcomes to HTTP status codes and records the
    audit event with the request's actor. The response shape is a contract for
    the Agent Evals page and ``scripts/run_eval_loop.py``.
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            urls_list = list(eval_request.article_urls)
            logger.info(
                "run_subagent_eval subagent=%s received %s article URL(s)",
                eval_request.subagent_name,
                len(urls_list),
            )
            try:
                plan = plan_subagent_eval(
                    db_session,
                    eval_request.subagent_name,
                    article_urls=urls_list,
                    replicates=1,
                    allow_inline_execution=True,
                )
            except NoActiveConfigError as e:
                raise HTTPException(status_code=404, detail="No active workflow config found") from e
            except EvalLaunchError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e

            # Eval article snapshots are versioned test inputs.  A live DB row
            # supplies the workflow/article identity, but must never replace the
            # committed content being scored.
            missing_fixture_urls = plan.missing_fixture_urls
            if missing_fixture_urls:
                raise HTTPException(
                    status_code=422,
                    detail=f"No committed eval fixture content for URL: {missing_fixture_urls[0]}",
                )
            if plan.exceeds_cap:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Requested {plan.total_executions} eval executions; "
                        f"{MAX_EVAL_EXECUTIONS_ENV}={plan.max_executions} caps a single launch"
                    ),
                )

            try:
                result = await launch_subagent_eval(
                    db_session,
                    plan,
                    concurrency_throttle_seconds=eval_request.concurrency_throttle_seconds,
                    initiated_by=_request_initiated_by(request),
                )
            except EvalLaunchCapExceededError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e

            _audit_eval(
                db_session,
                request,
                ACTION_EVAL_RUN_REQUESTED,
                plan.subagent,
                f"Triggered {len(result.executions)} subagent eval executions for {plan.subagent}",
                result.audit_metadata(),
            )

            return {
                "success": True,
                "subagent": plan.subagent,
                "total_articles": len(urls_list),
                "found_articles": result.found_articles,
                "executions": result.executions,
                "message": result.message,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running subagent eval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/subagent-eval-version-articles")
async def get_subagent_eval_version_articles(
    request: Request,
    subagent: str = Query(..., description="Subagent name"),
    config_version: int = Query(..., description="Config version to look up"),
):
    """Return the distinct article URLs that were run in a specific config version."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            _, lookup_values = _resolve_subagent_query(subagent)
            query = db_session.query(SubagentEvaluationTable.article_url).distinct()
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
            query = query.filter(
                SubagentEvaluationTable.workflow_config_version == config_version,
                SubagentEvaluationTable.article_url.isnot(None),
            )
            if EXCLUDED_EVAL_ARTICLE_IDS:
                query = query.filter(
                    SubagentEvaluationTable.article_id.notin_(EXCLUDED_EVAL_ARTICLE_IDS)
                    | SubagentEvaluationTable.article_id.is_(None)
                )
            rows = query.all()
            urls = [r[0] for r in rows if r[0]]
            return {"config_version": config_version, "urls": urls, "count": len(urls)}
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching version articles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/subagent-eval-results")
async def get_subagent_eval_results(
    request: Request,
    subagent: str = Query(..., description="Subagent name"),
    eval_run_id: int | None = Query(None, description="Optional: filter by eval record ID"),
    counts_only: bool = Query(
        False,
        description="Return only aggregate status counts (cheap GROUP BY) instead of the full per-record payload. Used by the run progress poller.",
    ),
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

            # Fast path for the run progress poller: it only needs status counts, not the
            # full per-record payload. Building that payload meant loading every row (1900+)
            # plus title/execution enrichment on a 2s poll loop, which pinned the web worker.
            # A single GROUP BY answers the poller cheaply. Counts MUST apply the same
            # subagent + excluded-article filters as the full path so totals match exactly.
            if counts_only:
                from sqlalchemy import func, or_

                count_query = db_session.query(SubagentEvaluationTable.status, func.count())
                if lookup_values:
                    count_query = count_query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
                if eval_run_id:
                    count_query = count_query.filter(SubagentEvaluationTable.id == eval_run_id)
                if EXCLUDED_EVAL_ARTICLE_IDS:
                    # Mirror the full path: drop excluded article_ids but keep NULL article_id rows.
                    count_query = count_query.filter(
                        or_(
                            SubagentEvaluationTable.article_id.is_(None),
                            SubagentEvaluationTable.article_id.notin_(EXCLUDED_EVAL_ARTICLE_IDS),
                        )
                    )
                counts = {"completed": 0, "pending": 0, "failed": 0}
                for status_value, n in count_query.group_by(SubagentEvaluationTable.status).all():
                    counts[status_value] = counts.get(status_value, 0) + n
                total = sum(counts.values())
                return {"subagent": canonical_subagent, "counts": counts, "results": [], "total": total}

            query = db_session.query(SubagentEvaluationTable)
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))

            if eval_run_id:
                query = query.filter(SubagentEvaluationTable.id == eval_run_id)

            eval_records = query.order_by(SubagentEvaluationTable.created_at.desc()).all()

            # Batch-fetch article titles for records with article_id
            article_ids = [
                r.article_id
                for r in eval_records
                if r.article_id is not None and r.article_id not in EXCLUDED_EVAL_ARTICLE_IDS
            ]
            id_to_title: dict[int, str] = {}
            if article_ids:
                rows = (
                    db_session.query(ArticleTable.id, ArticleTable.title).filter(ArticleTable.id.in_(article_ids)).all()
                )
                id_to_title = {r[0]: (r[1] or "") for r in rows}

            # For static evals (article_id null), get title from static data
            url_to_static = _load_static_eval_articles(canonical_subagent)

            def _title_for_record(rec: SubagentEvaluationTable) -> str:
                # Prefer static (committed JSON) so results table matches repo titles
                if rec.article_url and rec.article_url in url_to_static:
                    t = (url_to_static[rec.article_url].get("title") or "").strip()
                    if t:
                        return t
                if rec.article_id is not None:
                    return (id_to_title.get(rec.article_id) or "").strip()
                return ""

            # Batch-fetch all executions in one query to avoid N+1 round-trips.
            execution_ids = [r.workflow_execution_id for r in eval_records if r.workflow_execution_id]
            executions_by_id: dict[int, AgenticWorkflowExecutionTable] = {}
            if execution_ids:
                exec_rows = (
                    db_session.query(AgenticWorkflowExecutionTable)
                    .filter(AgenticWorkflowExecutionTable.id.in_(execution_ids))
                    .all()
                )
                executions_by_id = {e.id: e for e in exec_rows}

            results = []
            for record in eval_records:
                if record.article_id is not None and record.article_id in EXCLUDED_EVAL_ARTICLE_IDS:
                    continue
                actual_count = record.actual_count
                warnings = []
                execution_error_message = None
                throttled = False
                context_length_exceeded = False
                infra_not_ready = False
                quota_exceeded = False

                if record.workflow_execution_id:
                    execution = executions_by_id.get(record.workflow_execution_id)

                    if execution:
                        if (
                            execution.extraction_result
                            and isinstance(execution.extraction_result, dict)
                            and "warnings" in execution.extraction_result
                        ):
                            extraction_warnings = execution.extraction_result.get("warnings")
                            if isinstance(extraction_warnings, list):
                                warnings.extend(extraction_warnings)
                        if execution.error_message:
                            execution_error_message = execution.error_message
                        if _execution_has_quota_error(execution.error_message, execution.error_log):
                            quota_exceeded = True
                        elif _execution_is_throttled(execution.error_message, execution.error_log):
                            throttled = True
                        if _execution_has_context_overflow(
                            execution.error_message,
                            execution.error_log,
                            execution.extraction_result,
                            record.subagent_name,
                        ):
                            context_length_exceeded = True
                        if _execution_infra_not_ready(
                            execution.error_message,
                            execution.error_log,
                            execution.extraction_result,
                        ):
                            infra_not_ready = True

                # Calculate score if actual_count is set
                score = None
                if actual_count is not None:
                    score = actual_count - record.expected_count

                results.append(
                    {
                        "id": record.id,
                        "url": record.article_url,
                        "title": _title_for_record(record) or None,
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
                        "error_message": execution_error_message,
                        "throttled": throttled,
                        "context_length_exceeded": context_length_exceeded,
                        "infra_not_ready": infra_not_ready,
                        "quota_exceeded": quota_exceeded,
                        # Item-level fields (present when expected_items was set)
                        "expected_items": record.expected_items,
                        "acceptable_items": record.acceptable_items,
                        "actual_items": record.actual_items,
                        "matched_count": record.matched_count,
                        "missed_count": record.missed_count,
                        "extra_count": record.extra_count,
                        "neutral_count": record.neutral_count,
                    }
                )

            return {"subagent": canonical_subagent, "results": results, "total": len(results)}
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting subagent eval results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
        raise HTTPException(status_code=500, detail="Internal server error") from e


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

            # Same transaction as the deletes, so attribution cannot outlive or
            # fall behind the mutation it describes.
            _audit_eval(
                db_session,
                request,
                ACTION_EVAL_RECORDS_CLEARED,
                canonical_subagent,
                f"Cleared {deleted_count} pending eval record(s) for {canonical_subagent}",
                {
                    "subagent": canonical_subagent,
                    "deleted_count": deleted_count,
                    "deleted_ids": [r.id for r in pending_records],
                },
                mandatory=True,
            )

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
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/subagent-eval-backfill")
async def backfill_eval_records(request: Request, subagent: str = Query(..., description="Subagent name")):
    """Backfill pending eval records for completed workflow executions."""
    try:
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
                    update_subagent_eval_on_completion(execution, db_session)
                    # Check if it was updated
                    db_session.refresh(eval_record)
                    if eval_record.status == "completed":
                        updated_count += 1
                    elif eval_record.status == "failed":
                        failed_count += 1
                except Exception as e:
                    logger.warning(f"Error updating eval record {eval_record.id}: {e}")
                    failed_count += 1

            _audit_eval(
                db_session,
                request,
                ACTION_EVAL_RECORDS_BACKFILLED,
                canonical_subagent,
                f"Backfilled {updated_count} eval record(s) for {canonical_subagent}",
                {
                    "subagent": canonical_subagent,
                    "updated_count": updated_count,
                    "failed_count": failed_count,
                    "pending_considered": len(pending_evals),
                },
                mandatory=True,
            )

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
        raise HTTPException(status_code=500, detail="Internal server error") from e


# Canonical agents whose completed count-only records can be repaired from
# retained extractor output without re-running a paid LLM.
_RESCORABLE_SUBAGENTS = (
    "cmdline",
    "process_lineage",
    "registry_artifacts",
    "windows_services",
    "scheduled_tasks",
    "network_indicators",
    "hunt_queries",
)


@router.post("/subagent-eval-rescore")
async def rescore_eval_records(
    request: Request,
    subagent: str = Query(..., description="Subagent name, or 'all' for every supported agent"),
    apply: bool = Query(False, description="When false (default) run a dry-run that writes nothing"),
):
    """Repair completed count-only records that have ground truth but no score.

    Restores item-level precision/recall for records that were completed before
    item scoring supported the agent's output schema. It scores each record's
    *retained* extractor output against the ground truth stored on the record,
    so it never re-runs a paid LLM and never reloads ground truth from disk
    (no silent ground-truth drift).

    Dry-run by default: reports, per agent, how many records are candidates,
    scorable, or unrepairable (no retained output), and writes nothing. Pass
    ``apply=true`` to persist. Idempotent -- scope is restricted to completed
    records with non-empty ``expected_items`` and a null ``matched_count``, so a
    second apply updates nothing. Records without item-level ground truth are
    never touched, preserving legitimate count-only behavior.
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            raw = (subagent or "").strip().lower()
            if raw in ("all", "*"):
                targets = list(_RESCORABLE_SUBAGENTS)
                canonical_label = "all"
            else:
                canonical = normalize_subagent_name(subagent)
                if not canonical:
                    raise HTTPException(status_code=422, detail=f"Unknown subagent: {subagent}")
                targets = [canonical]
                canonical_label = canonical

            per_agent: dict[str, dict] = {}
            totals = {"candidates": 0, "scorable": 0, "unrepairable_no_output": 0, "updated": 0}

            for canonical in targets:
                _, lookup_values = build_subagent_lookup_values(canonical)
                records = (
                    db_session.query(SubagentEvaluationTable)
                    .filter(
                        SubagentEvaluationTable.subagent_name.in_(list(lookup_values) or [canonical]),
                        SubagentEvaluationTable.status == "completed",
                        SubagentEvaluationTable.matched_count.is_(None),
                    )
                    .all()
                )

                stats = {"candidates": 0, "scorable": 0, "unrepairable_no_output": 0, "updated": 0}
                for rec in records:
                    # Skip records with no item-level ground truth -- legitimately count-only.
                    if not isinstance(rec.expected_items, list) or len(rec.expected_items) == 0:
                        continue
                    stats["candidates"] += 1

                    execution = None
                    if rec.workflow_execution_id:
                        execution = (
                            db_session.query(AgenticWorkflowExecutionTable)
                            .filter(AgenticWorkflowExecutionTable.id == rec.workflow_execution_id)
                            .first()
                        )

                    computed = rescore_completed_record(rec, execution)
                    if computed is None:
                        stats["unrepairable_no_output"] += 1
                        continue

                    stats["scorable"] += 1
                    if apply:
                        rec.actual_items = computed["actual_items"]
                        rec.matched_count = computed["matched_count"]
                        rec.missed_count = computed["missed_count"]
                        rec.extra_count = computed["extra_count"]
                        rec.neutral_count = computed["neutral_count"]
                        stats["updated"] += 1

                per_agent[canonical] = stats
                for k in totals:
                    totals[k] += stats[k]

            verb = "Rescored" if apply else "Dry-run rescore of"
            _audit_eval(
                db_session,
                request,
                ACTION_EVAL_RECORDS_RESCORED,
                canonical_label,
                f"{verb} {totals['scorable']} completed record(s) for {canonical_label}",
                {"subagent": canonical_label, "apply": apply, **totals, "per_agent": per_agent},
                mandatory=apply,
            )

            if apply:
                db_session.commit()

            logger.info(
                "Rescore (%s) for %s: candidates=%d scorable=%d unrepairable=%d updated=%d",
                "apply" if apply else "dry-run",
                canonical_label,
                totals["candidates"],
                totals["scorable"],
                totals["unrepairable_no_output"],
                totals["updated"],
            )

            return {
                "success": True,
                "subagent": canonical_label,
                "apply": apply,
                "dry_run": not apply,
                **totals,
                "per_agent": per_agent,
                "message": (
                    f"Updated {totals['updated']} record(s)"
                    if apply
                    else f"{totals['scorable']} record(s) would be updated ({totals['unrepairable_no_output']} lack retained output)"
                ),
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rescoring eval records: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/subagent-eval-aggregate")
async def get_subagent_eval_aggregate(
    request: Request,
    subagent: str = Query(..., description="Subagent name"),
    config_version: int | None = Query(None, description="Optional: filter by config version"),
    model: str | None = Query(
        None,
        description="Optional: filter to config versions where this subagent used the given model",
    ),
):
    """Get aggregate scores per config version for a subagent.

    When ``model`` is provided, restricts results to config versions where the
    subagent's configured model matches. This is used by the Evaluation Metrics
    Over Time chart to plot a single model's trajectory across config snapshots.
    """
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

            # Hoisted above the model-filter early-return so eval_set_total is
            # always populated in the response, regardless of which return path fires.
            preset_expected_by_url = _load_preset_expected_by_url(subagent)
            eval_set_total = len(preset_expected_by_url)

            query = db_session.query(SubagentEvaluationTable)
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))

            if config_version:
                query = query.filter(SubagentEvaluationTable.workflow_config_version == config_version)

            # If a model filter is supplied, narrow to config versions where the subagent
            # used that model. We do this by joining on the workflow config table and
            # inspecting agent_models[<AgentName>_model].
            agent_name_for_model = _SUBAGENT_TO_BUNDLE_AGENT.get(canonical_subagent)
            if model and agent_name_for_model:
                model_key = f"{agent_name_for_model}_model"
                matching_versions = (
                    db_session.query(AgenticWorkflowConfigTable.version)
                    .filter(AgenticWorkflowConfigTable.agent_models[model_key].astext == model)
                    .all()
                )
                version_set = {v for (v,) in matching_versions}
                if not version_set:
                    return {
                        "subagent": subagent,
                        "aggregates": [],
                        "total_config_versions": 0,
                        "eval_set_total": eval_set_total,
                    }
                query = query.filter(SubagentEvaluationTable.workflow_config_version.in_(version_set))

            all_records = query.order_by(
                SubagentEvaluationTable.workflow_config_version.desc(),
                SubagentEvaluationTable.created_at.desc(),
            ).all()

            # Batch-fetch execution rows to avoid N+1 queries when counting throttled/quota runs.
            execution_ids = [r.workflow_execution_id for r in all_records if r.workflow_execution_id]
            throttled_execution_ids: set[int] = set()
            quota_exceeded_execution_ids: set[int] = set()
            if execution_ids:
                execution_rows = (
                    db_session.query(
                        AgenticWorkflowExecutionTable.id,
                        AgenticWorkflowExecutionTable.error_message,
                        AgenticWorkflowExecutionTable.error_log,
                    )
                    .filter(AgenticWorkflowExecutionTable.id.in_(execution_ids))
                    .all()
                )
                for exec_id, err_msg, err_log in execution_rows:
                    if _execution_has_quota_error(err_msg, err_log):
                        quota_exceeded_execution_ids.add(exec_id)
                    elif _execution_is_throttled(err_msg, err_log):
                        throttled_execution_ids.add(exec_id)

            # Group by config version (exclude articles in EXCLUDED_EVAL_ARTICLE_IDS)
            by_config_version = {}
            for record in all_records:
                if record.article_id is not None and record.article_id in EXCLUDED_EVAL_ARTICLE_IDS:
                    continue
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
                throttled_count = sum(1 for r in records if r.workflow_execution_id in throttled_execution_ids)
                quota_exceeded_count = sum(
                    1 for r in records if r.workflow_execution_id in quota_exceeded_execution_ids
                )

                if not completed_records:
                    aggregates.append(
                        {
                            "config_version": version,
                            "total_articles": len(records),
                            "completed": len(completed_records),
                            "failed": len(failed_records),
                            "pending": len(pending_records),
                            "throttled": throttled_count,
                            "quota_exceeded": quota_exceeded_count,
                            "mean_score": None,
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
                            # Item-level metrics: macro-averaged precision/recall and
                            # derived F0.5 across articles annotated with expected_items.
                            "mean_precision": None,
                            "mean_recall": None,
                            "mean_f05": None,
                            "scored_articles": 0,
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
                mean_squared_error = sum(s * s for s in scores) / len(scores)
                perfect_matches = sum(1 for s in scores if s == 0)
                perfect_match_percentage = (perfect_matches / len(completed_records)) * 100
                exact = sum(1 for s in scores if s == 0)
                within_2 = sum(1 for s in scores if abs(s) <= 2 and s != 0)
                over_2 = sum(1 for s in scores if abs(s) > 2)

                # Item-level macro precision/recall (only over articles that have item-level
                # scoring -- i.e. expected_items was set and matched_count was populated).
                scored_records = [
                    r
                    for r in completed_records
                    if r.matched_count is not None and r.missed_count is not None and r.extra_count is not None
                ]
                if scored_records:
                    per_article_precision = []
                    per_article_recall = []
                    for r in scored_records:
                        m = r.matched_count or 0
                        miss = r.missed_count or 0
                        ex = r.extra_count or 0
                        precision_denom = m + ex
                        recall_denom = m + miss
                        per_article_precision.append(m / precision_denom if precision_denom > 0 else 0.0)
                        per_article_recall.append(m / recall_denom if recall_denom > 0 else 0.0)
                    mean_precision = sum(per_article_precision) / len(per_article_precision)
                    mean_recall = sum(per_article_recall) / len(per_article_recall)
                    mean_f05 = calculate_f_beta(mean_precision, mean_recall)
                else:
                    mean_precision = None
                    mean_recall = None
                    mean_f05 = None

                aggregates.append(
                    {
                        "config_version": version,
                        "total_articles": len(records),
                        "completed": len(completed_records),
                        "failed": len(failed_records),
                        "pending": len(pending_records),
                        "throttled": throttled_count,
                        "quota_exceeded": quota_exceeded_count,
                        "mean_score": round(mean_score, 2),
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
                        # Item-level metrics (null when no annotated articles in this version).
                        "mean_precision": round(mean_precision, 4) if mean_precision is not None else None,
                        "mean_recall": round(mean_recall, 4) if mean_recall is not None else None,
                        "mean_f05": round(mean_f05, 4) if mean_f05 is not None else None,
                        "scored_articles": len(scored_records),
                    }
                )

            return {
                "subagent": subagent,
                "aggregates": aggregates,
                "total_config_versions": len(aggregates),
                "eval_set_total": eval_set_total,
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting aggregate eval scores: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/subagent-eval-models")
async def get_subagent_eval_models(
    request: Request,
    subagent: str = Query(..., description="Subagent name"),
):
    """List models that have been used for the given subagent across configs with eval data.

    Powers the model dropdown on the Evaluation Metrics Over Time chart. We only
    surface models that are *both* configured for this subagent in some config
    version *and* have at least one eval record under that version -- otherwise
    the chart would be empty for that selection.
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            canonical_subagent, lookup_values = _resolve_subagent_query(subagent)
            if canonical_subagent == "hunt_queries":
                lookup_values = set(lookup_values) if lookup_values else set()
                lookup_values.add("hunt_queries_edr")
                lookup_values = list(lookup_values)

            agent_name = _SUBAGENT_TO_BUNDLE_AGENT.get(canonical_subagent)
            if not agent_name:
                return {"subagent": subagent, "models": []}

            # Versions that actually have eval rows for this subagent.
            eval_query = db_session.query(SubagentEvaluationTable.workflow_config_version).distinct()
            if lookup_values:
                eval_query = eval_query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
            versions_with_evals = {v for (v,) in eval_query.all() if v is not None}
            if not versions_with_evals:
                return {"subagent": subagent, "models": []}

            # Pull the configured model per version, intersect with versions_with_evals.
            model_key = f"{agent_name}_model"
            configs = (
                db_session.query(
                    AgenticWorkflowConfigTable.version,
                    AgenticWorkflowConfigTable.agent_models,
                )
                .filter(AgenticWorkflowConfigTable.version.in_(versions_with_evals))
                .all()
            )
            models_seen: dict[str, int] = {}
            for version, agent_models in configs:
                if not isinstance(agent_models, dict):
                    continue
                model_name = agent_models.get(model_key)
                if not model_name:
                    continue
                models_seen[model_name] = models_seen.get(model_name, 0) + 1

            # Sort: most-used first, then alphabetical for stability.
            sorted_models = sorted(
                models_seen.items(),
                key=lambda kv: (-kv[1], kv[0]),
            )
            return {
                "subagent": subagent,
                "models": [{"name": name, "config_count": count} for name, count in sorted_models],
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error("Error listing eval models for subagent: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/subagent-eval-compare")
async def get_subagent_eval_compare(
    request: Request,
    subagent: str = Query(...),
    version_a: int = Query(..., description="Baseline config version"),
    version_b: int = Query(..., description="Candidate config version"),
):
    """Side-by-side comparison of two config versions for a subagent."""
    logger.info(
        "subagent-eval-compare: subagent=%s version_a=%s version_b=%s",
        subagent,
        version_a,
        version_b,
    )
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            canonical_subagent, lookup_values = _resolve_subagent_query(subagent)

            # For hunt_queries include historical edr records
            if canonical_subagent == "hunt_queries":
                lookup_values = set(lookup_values) if lookup_values else set()
                lookup_values.add("hunt_queries_edr")
                lookup_values = list(lookup_values)

            query = db_session.query(SubagentEvaluationTable)
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
            query = query.filter(SubagentEvaluationTable.workflow_config_version.in_([version_a, version_b]))
            all_records = query.order_by(
                SubagentEvaluationTable.workflow_config_version.desc(),
                SubagentEvaluationTable.created_at.desc(),
            ).all()

            # Batch-fetch article titles
            article_ids = [
                r.article_id
                for r in all_records
                if r.article_id is not None and r.article_id not in EXCLUDED_EVAL_ARTICLE_IDS
            ]
            id_to_title: dict[int, str] = {}
            if article_ids:
                title_rows = (
                    db_session.query(ArticleTable.id, ArticleTable.title).filter(ArticleTable.id.in_(article_ids)).all()
                )
                id_to_title = {r[0]: (r[1] or "") for r in title_rows}

            url_to_static = _load_static_eval_articles(canonical_subagent)

            def _title_for(rec: SubagentEvaluationTable) -> str:
                if rec.article_url and rec.article_url in url_to_static:
                    t = (url_to_static[rec.article_url].get("title") or "").strip()
                    if t:
                        return t
                if rec.article_id is not None:
                    return (id_to_title.get(rec.article_id) or "").strip()
                return ""

            preset_expected_by_url = _load_preset_expected_by_url(subagent)

            # Build per-(url, version) latest-record map (most recent by
            # created_at, tie-broken by id DESC so the choice is deterministic
            # across page refreshes -- replicate runs queued together can share
            # a created_at timestamp at microsecond precision).
            # Also count attempts per (url, version) so the UI can surface
            # replicate variance instead of silently collapsing it.
            latest: dict[tuple[str | None, int], SubagentEvaluationTable] = {}
            attempt_counts: dict[tuple[str | None, int], int] = {}
            # Sums for averaging across all completed replicate attempts.
            # The per-article "improvement" badge and the IMPROVED/REGRESSED
            # tallies derive from these averages -- single-attempt comparisons
            # were misleading on stochastic LLM output (a lucky/unlucky latest
            # attempt could fabricate or hide a direction-of-change).
            sum_actual: dict[tuple[str | None, int], float] = {}
            sum_abs_err: dict[tuple[str | None, int], float] = {}
            completed_counts: dict[tuple[str | None, int], int] = {}
            for record in all_records:
                if record.article_id is not None and record.article_id in EXCLUDED_EVAL_ARTICLE_IDS:
                    continue
                key = (record.article_url, record.workflow_config_version)
                attempt_counts[key] = attempt_counts.get(key, 0) + 1
                # Accumulate per-key averaging stats for completed attempts only;
                # failed/missing attempts must not bias the average toward zero.
                if record.status == "completed" and record.actual_count is not None:
                    expected_val = preset_expected_by_url.get(record.article_url)
                    if expected_val is None:
                        expected_val = record.expected_count if record.expected_count is not None else 0
                    sum_actual[key] = sum_actual.get(key, 0.0) + float(record.actual_count)
                    sum_abs_err[key] = sum_abs_err.get(key, 0.0) + float(abs(record.actual_count - expected_val))
                    completed_counts[key] = completed_counts.get(key, 0) + 1
                existing = latest.get(key)
                if existing is None:
                    latest[key] = record
                    continue
                rec_ts = record.created_at
                ext_ts = existing.created_at
                rec_id = record.id or 0
                ext_id = existing.id or 0
                if rec_ts is not None and (ext_ts is None or rec_ts > ext_ts) or rec_ts == ext_ts and rec_id > ext_id:
                    latest[key] = record

            # Collect all unique URLs seen in either version
            all_urls: dict[str | None, str] = {}  # url -> title
            for (url, _ver), rec in latest.items():
                if url not in all_urls or not all_urls[url]:
                    all_urls[url] = _title_for(rec)

            def _make_result(rec: SubagentEvaluationTable | None) -> dict | None:
                if rec is None:
                    return None
                actual = rec.actual_count
                expected = preset_expected_by_url.get(rec.article_url)
                if expected is None:
                    expected = rec.expected_count if rec.expected_count is not None else 0
                score = (actual - expected) if actual is not None else None
                return {
                    "actual_count": actual,
                    "score": score,
                    "status": rec.status or "unknown",
                    "execution_id": rec.workflow_execution_id,
                }

            def _compute_aggregate(records: list[SubagentEvaluationTable], version: int) -> dict:
                completed = [r for r in records if r.status == "completed" and r.actual_count is not None]
                if not completed:
                    return {
                        "config_version": version,
                        "total_articles": len(records),
                        "completed": 0,
                        "raw_mae": None,
                        "perfect_matches": 0,
                        "perfect_match_percentage": 0.0,
                    }
                scores = []
                expected_counts = []
                for r in completed:
                    expected = preset_expected_by_url.get(r.article_url)
                    if expected is None:
                        expected = r.expected_count if r.expected_count is not None else 0
                    expected_counts.append(expected)
                    scores.append((r.actual_count or 0) - expected)
                mean_absolute_error = sum(abs(s) for s in scores) / len(scores)
                perfect_matches = sum(1 for s in scores if s == 0)
                perfect_match_pct = (perfect_matches / len(completed)) * 100
                return {
                    "config_version": version,
                    "total_articles": len(records),
                    "completed": len(completed),
                    "raw_mae": round(mean_absolute_error, 4),
                    "perfect_matches": perfect_matches,
                    "perfect_match_percentage": round(perfect_match_pct, 1),
                }

            # Aggregate over ALL completed attempts per version so the MAE here
            # matches the "MAE by Config Version" chart. Using only the latest
            # attempt per article would silently discard replicates and inflate
            # single-run LLM variance.
            def _allowed(r: SubagentEvaluationTable) -> bool:
                return r.article_id is None or r.article_id not in EXCLUDED_EVAL_ARTICLE_IDS

            records_a = [r for r in all_records if r.workflow_config_version == version_a and _allowed(r)]
            records_b = [r for r in all_records if r.workflow_config_version == version_b and _allowed(r)]

            aggregate_a = _compute_aggregate(records_a, version_a)
            aggregate_b = _compute_aggregate(records_b, version_b)

            def _avg_for(key: tuple[str | None, int]) -> dict | None:
                """Per-key averaged actual and abs_err across completed attempts."""
                n = completed_counts.get(key, 0)
                if n == 0:
                    return None
                return {
                    "avg_actual": round(sum_actual[key] / n, 2),
                    "avg_abs_err": round(sum_abs_err[key] / n, 2),
                    "completed_attempts": n,
                }

            # Build per-article rows
            articles = []
            for url, title in all_urls.items():
                rec_a = latest.get((url, version_a))
                rec_b = latest.get((url, version_b))
                result_a = _make_result(rec_a)
                result_b = _make_result(rec_b)
                avg_a = _avg_for((url, version_a))
                avg_b = _avg_for((url, version_b))

                expected_count = preset_expected_by_url.get(url)
                if expected_count is None:
                    rec_any = rec_a or rec_b
                    if rec_any:
                        expected_count = rec_any.expected_count
                if expected_count is None:
                    expected_count = 0

                # Improvement is the reduction in averaged abs_err from A -> B.
                # Positive means B is closer to expected on average; negative
                # means B drifted further away. Averaging across replicate
                # attempts smooths LLM stochasticity so the badge reflects a
                # statistically meaningful change instead of one lucky sample.
                improvement: float | None = None
                if avg_a is not None and avg_b is not None:
                    improvement = round(avg_a["avg_abs_err"] - avg_b["avg_abs_err"], 2)

                articles.append(
                    {
                        "url": url,
                        "title": title or None,
                        "expected_count": expected_count,
                        "result_a": result_a,
                        "result_b": result_b,
                        "improvement": improvement,
                        "attempts_a": attempt_counts.get((url, version_a), 0),
                        "attempts_b": attempt_counts.get((url, version_b), 0),
                        "avg_a": avg_a,
                        "avg_b": avg_b,
                    }
                )

            # Sort: biggest changes first (most improved or most regressed), nulls at end
            articles.sort(
                key=lambda a: (
                    a["improvement"] is None,
                    -abs(a["improvement"]) if a["improvement"] is not None else 0,
                )
            )

            # Magnitude-weighted summary so the panel does not mislead when a
            # single large win is offset by multiple small losses (or vice
            # versa). Unweighted counts (1 improved vs 2 regressed) can look
            # like a regression while the aggregate MAE actually went down.
            total_improvement = round(
                sum(a["improvement"] for a in articles if a["improvement"] is not None and a["improvement"] > 0),
                2,
            )
            total_regression = round(
                sum(a["improvement"] for a in articles if a["improvement"] is not None and a["improvement"] < 0),
                2,
            )
            net_change = round(total_improvement + total_regression, 2)

            return {
                "subagent": canonical_subagent,
                "version_a": version_a,
                "version_b": version_b,
                "aggregate_a": aggregate_a,
                "aggregate_b": aggregate_b,
                "articles": articles,
                "net_change": net_change,
                "total_improvement_magnitude": total_improvement,
                "total_regression_magnitude": total_regression,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in subagent-eval-compare: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/config-versions-models")
async def get_config_versions_models(
    request: Request,
    config_versions: str = Query("1", description="Comma-separated list of config version numbers"),
):
    """Get agent models for specified config versions.

    ``config_versions`` is length-capped rather than paginated: the caller
    (the model-comparison table) needs the full id set in one response, and
    the query string is what carries it. nginx's default header buffer is
    8KB; ``_MAX_CONFIG_VERSIONS_PARAM_LENGTH`` stays well under that so a
    caller with more ids gets a clear 400 instead of the request failing
    opaquely at the proxy.
    """
    try:
        _MAX_CONFIG_VERSIONS_PARAM_LENGTH = 4000
        if len(config_versions) > _MAX_CONFIG_VERSIONS_PARAM_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"config_versions is {len(config_versions)} characters, exceeding the "
                    f"{_MAX_CONFIG_VERSIONS_PARAM_LENGTH}-character cap. Request a smaller set of "
                    "config versions."
                ),
            )

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

                # Sub-agents (only if enabled and has model)
                for agent in [
                    "CmdlineExtract",
                    "ProcTreeExtract",
                    "HuntQueriesExtract",
                    "RegistryExtract",
                    "ServicesExtract",
                    "ScheduledTasksExtract",
                    "NetworkIndicatorExtract",
                ]:
                    model_key = f"{agent}_model"
                    if agent_models.get(model_key) and agent not in disabled_set:
                        provider = agent_models.get(f"{agent}_provider") or ""
                        model_list.append(f"{agent}: {agent_models[model_key]} ({provider or 'not configured'})")

                models_by_version[config.version] = {
                    "agent_models": agent_models,
                    "display_text": "\n".join(model_list) if model_list else "No models configured",
                    "cmdline_attention_preprocessor_enabled": config.cmdline_attention_preprocessor_enabled,
                    "proc_tree_attention_preprocessor_enabled": config.proc_tree_attention_preprocessor_enabled,
                }

            return {"models_by_version": models_by_version}
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting config versions models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
                    detail=f"Error accessing data structure: {str(e)}. "
                    "This may indicate a data format issue in the execution record.",
                ) from e

            # Workflow metadata already set by service (includes actual attempt used)

            # Recompute bundle_sha256 with updated workflow metadata
            bundle_for_hash = bundle.copy()
            bundle_for_hash["integrity"] = {"bundle_sha256": "", "warnings": bundle["integrity"]["warnings"]}

            bundle_sha256 = compute_sha256_json(bundle_for_hash)
            bundle["integrity"]["bundle_sha256"] = bundle_sha256

            _audit_eval(
                db_session,
                request,
                ACTION_EVAL_BUNDLE_EXPORTED,
                str(execution_id),
                f"Exported eval bundle for execution {execution_id}",
                {
                    "execution_id": execution_id,
                    "agent_name": export_request.agent_name,
                    "attempt": export_request.attempt,
                    "bundle_id": bundle.get("bundle_id"),
                    "bundle_sha256": bundle_sha256,
                },
            )

            return bundle
        finally:
            db_session.close()

    except ValueError as e:
        logger.error(f"Execution not found: {execution_id} - {e}")
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error exporting eval bundle for execution {execution_id}: {e}", exc_info=True)
        error_detail = str(e)
        # Add more context if it's a missing data error
        if "not found" in error_detail.lower() or "missing" in error_detail.lower():
            error_detail = f"{error_detail}. Check that the execution has error_log data for the specified agent."
        raise HTTPException(status_code=500, detail=error_detail) from e


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
                available_agents = [k for k in error_log if k in agent_keys]
                agent_name = available_agents[0] if available_agents else "extract_agent"

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
        raise HTTPException(status_code=500, detail="Internal server error") from e


# Eval diagnosis is authored by an MCP client agent, not by a server-side LLM
# call -- see the huntable-eval-diagnosis skill and the get_eval_diagnosis_context
# / save_eval_diagnosis MCP tools. The endpoints below are read-only views over
# the diagnoses that flow persists to data/diagnoses.


@router.get("/evals/{execution_id}/diagnosis")
async def get_saved_diagnosis(execution_id: int):
    """
    Return the most recent saved diagnosis for an execution, or 404 if none exists.
    """
    from src.services.eval_diagnosis_service import load_saved_diagnoses

    entries = load_saved_diagnoses(execution_id)
    if not entries:
        raise HTTPException(status_code=404, detail="No diagnosis found")

    return entries[0][1]


@router.get("/evals/diagnosis-counts")
async def get_diagnosis_counts():
    """
    Return a dict of {execution_id: count} for every execution that has at least
    one saved diagnosis.  Uses a single directory scan (no file reads) so it is
    cheap to call on every page load.
    """
    from collections import defaultdict

    from src.services.eval_diagnosis_service import DIAGNOSES_DIR

    counts: dict[int, int] = defaultdict(int)
    if DIAGNOSES_DIR.exists():
        for p in DIAGNOSES_DIR.glob("*.json"):
            # filename format: {exec_id}_{agent}_{short_id}.json
            parts = p.stem.split("_", 1)
            if parts and parts[0].isdigit():
                counts[int(parts[0])] += 1
    return dict(counts)


@router.get("/evals/{execution_id}/diagnoses")
async def list_saved_diagnoses(execution_id: int):
    """
    Return all saved diagnoses for an execution, newest first.
    Returns an empty list (not 404) when none exist.
    """
    from src.services.eval_diagnosis_service import load_saved_diagnoses

    return [diagnosis for _path, diagnosis in load_saved_diagnoses(execution_id)]


# Map subagent canonical names to agent names used in eval bundles
# Bundle/eval agent names keyed by subagent alias; hunt_queries_edr is a legacy
# alias of the HuntQueries extractor that still appears in stored eval rows.
_SUBAGENT_TO_BUNDLE_AGENT = {**SUBAGENT_TO_EXTRACT_AGENT, "hunt_queries_edr": "HuntQueriesExtract"}


@router.get("/evals/export-bundles-by-config-version")
async def export_bundles_by_config_version(
    request: Request,
    config_version: int = Query(..., description="Workflow config version"),
    subagent: str = Query(..., description="Subagent name (cmdline, process_lineage, hunt_queries)"),
    include_langfuse: bool = Query(False, description="Fetch Langfuse data for each bundle before export"),
    slim: bool = Query(False, description="Strip redundant data to reduce token consumption for AI review"),
):
    """
    Export eval bundles for all articles evaluated under a given config version.

    Returns a ZIP file with one JSON bundle per eval record (article_{article_id}_{record_id}.json).
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            include_langfuse_data = include_langfuse is True
            slim_mode = slim is True
            canonical_subagent, lookup_values = _resolve_subagent_query(subagent)
            if canonical_subagent == "hunt_queries":
                lookup_values = set(lookup_values) if lookup_values else set()
                lookup_values.add("hunt_queries_edr")
                lookup_values = list(lookup_values)
            agent_name = _SUBAGENT_TO_BUNDLE_AGENT.get(canonical_subagent or "")
            if not agent_name:
                agent_name = "CmdlineExtract"  # fallback for unknown subagents

            records = (
                db_session.query(SubagentEvaluationTable)
                .filter(
                    SubagentEvaluationTable.subagent_name.in_(lookup_values),
                    SubagentEvaluationTable.workflow_config_version == config_version,
                    SubagentEvaluationTable.workflow_execution_id.isnot(None),
                    SubagentEvaluationTable.status == "completed",
                )
                .order_by(SubagentEvaluationTable.article_id.asc())
                .all()
            )

            if not records:
                raise HTTPException(
                    status_code=404,
                    detail=f"No completed eval records for config version {config_version} and subagent {subagent}",
                )

            bundle_service = EvalBundleService(db_session)
            buffer = io.BytesIO()
            # Track shared prompts across bundles for the slim manifest
            shared_prompts: dict[str, str] = {}  # sha256 -> prompt text

            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
                for record in records:
                    try:
                        bundle = bundle_service.generate_bundle(
                            execution_id=record.workflow_execution_id,
                            agent_name=agent_name,
                            attempt=None,
                            fetch_langfuse=include_langfuse_data,
                            slim=slim_mode,
                        )
                        # Collect shared prompts before they get stripped (for slim manifest)
                        if slim_mode:
                            for inp in bundle.get("inputs", []):
                                if (
                                    isinstance(inp, dict)
                                    and inp.get("name") == "system_prompt"
                                    and inp.get("sha256")
                                    and inp.get("text")
                                ):
                                    shared_prompts[inp["sha256"]] = inp["text"]
                                    # Replace prompt text with SHA ref in the bundle
                                    inp["text"] = None
                                    inp["_slim_ref"] = f"see _prompts.json#{inp['sha256'][:12]}"

                        filename = f"article_{record.article_id or record.id}_{record.id}.json"
                        zf.writestr(filename, json.dumps(bundle, indent=2, ensure_ascii=False))
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Skipping bundle for execution {record.workflow_execution_id}: {e}")
                        zf.writestr(
                            f"article_{record.article_id or record.id}_{record.id}_error.txt",
                            f"Bundle generation failed: {e}",
                        )

                # Write shared prompt manifest for slim ZIPs
                if slim_mode and shared_prompts:
                    manifest = {
                        "description": "Shared prompts extracted from slim bundles. "
                        "Each bundle references these by SHA256 prefix.",
                        "prompts": {sha[:12]: {"sha256": sha, "text": text} for sha, text in shared_prompts.items()},
                    }
                    zf.writestr("_prompts.json", json.dumps(manifest, indent=2, ensure_ascii=False))

            buffer.seek(0)
            suffix = "_slim" if slim_mode else ""
            return StreamingResponse(
                buffer,
                media_type="application/zip",
                headers={
                    "Content-Disposition": (
                        f"attachment; filename=eval_bundles_v{config_version}"
                        f"_{canonical_subagent or subagent}{suffix}.zip"
                    )
                },
            )
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error exporting bundles for config version {config_version}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e
