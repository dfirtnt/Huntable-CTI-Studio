"""MCP tools for testing one extraction sub-agent on one article.

The MCP twin of the workflow page's "Test <Agent>" button: it dispatches the same
``test_agents.test_sub_agent`` worker task as POST /api/workflow/config/test-subagent,
then reads the Celery result. No workflow execution or eval record is created.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from src.database.async_manager import AsyncDatabaseManager
from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.huntable_mcp.tools.write_support import MCP_SERVICE_ACTOR, record_mcp_audit
from src.services.audit_service import ACTION_DEBUG_ACTION_INVOKED
from src.services.subagent_eval_launch_service import (
    LOCAL_PROVIDERS,
    EvalDispatchError,
    ensure_broker_reachable,
    resolve_agent_provider_model,
)
from src.utils.subagent_utils import SUBAGENT_TO_EXTRACT_AGENT, normalize_subagent_name

logger = logging.getLogger(__name__)

# Dispatched by name so the MCP host never imports the worker module (and its LLM stack).
SUB_AGENT_TEST_TASK = "test_agents.test_sub_agent"
# The worker registers test tasks only in these environments (src/worker/celery_app.py).
_TEST_TASK_ENVIRONMENTS = ("development", "test")
# celeryconfig.result_expires: a finished test's result is gone after this.
_RESULT_TTL_SECONDS = 1800


def _json_response(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


def _new_sync_session():
    return DatabaseManager().get_session()


def _runtime_environment() -> str:
    from src.worker.celery_app import _runtime_environment as worker_runtime_environment

    return worker_runtime_environment()


def _active_config(session):
    from src.services.workflow_trigger_service import WorkflowTriggerService

    return WorkflowTriggerService(session).get_active_config()


def _resolve_effort(agent_models: dict[str, Any], agent_name: str) -> str | None:
    """Same lookup as LLMService.resolve_extract_effort: own effort, then ExtractAgent's."""
    for key in (f"{agent_name}_effort", "ExtractAgent_effort"):
        value = agent_models.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _validate_args(agent: str, article_id: int) -> tuple[str | None, dict[str, Any] | None]:
    """Return (extractor agent name, None) or (None, error payload) without touching the DB."""
    canonical = normalize_subagent_name(agent)
    if canonical not in SUBAGENT_TO_EXTRACT_AGENT:
        return None, {
            "error": f"Unsupported agent for a single-article test: {agent}",
            "supported_agents": sorted(SUBAGENT_TO_EXTRACT_AGENT.values()),
        }
    if isinstance(article_id, bool) or not isinstance(article_id, int) or article_id < 1:
        return None, {"error": "article_id must be a positive integer"}
    return SUBAGENT_TO_EXTRACT_AGENT[canonical], None


def _summarize_result(result: Any, include_debug: bool) -> dict[str, Any]:
    """Item-level view of the extraction; ``_``-prefixed debug fields only on request."""
    if not isinstance(result, dict):
        return {"result": result}
    if include_debug:
        return {"result": result}
    return {
        "result": {key: value for key, value in result.items() if not str(key).startswith("_")},
        "llm_response": result.get("_llm_response"),
    }


def register(mcp: FastMCP, db: AsyncDatabaseManager) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    async def test_subagent_on_article(agent: str, article_id: int, confirmed_by_user: bool = False) -> str:
        """Plan, then run, one extraction sub-agent on one article with the active config.

        The MCP equivalent of the workflow page's "Test <Agent>" button: one
        agent, one article (any article, not only eval fixtures), no workflow
        execution, no eval record. Content is junk-filtered at the active
        config's threshold, as the button does.

        Caller-attested call that spends provider tokens. Call it first with
        confirmed_by_user=false: it returns the plan (article, config version,
        provider, model, effort, billing line) and dispatches nothing. Show the
        plan to the user, obtain explicit approval for this run, then call again
        with confirmed_by_user=true. Approval never carries over: every run needs
        its own confirmed_by_user=true. Tokens are billed to the agent's
        configured provider unless it is lmstudio.

        After a run, poll get_subagent_test_result with the returned task_id.
        Results expire 30 minutes after the task finishes.

        Args:
            agent: Extractor name (CmdlineExtract, ProcTreeExtract,
                HuntQueriesExtract, RegistryExtract, ServicesExtract,
                ScheduledTasksExtract, NetworkIndicatorExtract) or its alias
                (cmdline, process_lineage, hunt_queries, ...).
            article_id: Database article ID (the Article ID search results report).
            confirmed_by_user: True only after explicit approval for this run.
        """
        agent_name, invalid = _validate_args(agent, article_id)
        if invalid is not None:
            return _json_response({**invalid, "dispatched": False})
        assert agent_name is not None

        db_session = _new_sync_session()
        try:
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if article is None:
                return _json_response({"error": f"Article {article_id} not found", "dispatched": False})
            config = _active_config(db_session)
            if config is None:
                return _json_response({"error": "No active workflow configuration found", "dispatched": False})

            agent_models = config.agent_models or {}
            provider, model = resolve_agent_provider_model(agent_models, agent_name)
            is_local_provider = (provider or "").strip().lower() in LOCAL_PROVIDERS
            threshold = config.junk_filter_threshold if config.junk_filter_threshold is not None else 0.8
            plan: dict[str, Any] = {
                "schema_version": "mcp_subagent_test_v1",
                "agent_name": agent_name,
                "article_id": article.id,
                "article_title": article.title,
                "article_url": article.canonical_url,
                "config_id": config.id,
                "config_version": config.version,
                "provider": provider,
                "model": model,
                "effort": _resolve_effort(agent_models, agent_name),
                "use_junk_filter": True,
                "junk_filter_threshold": float(threshold),
                "billing": (
                    f"Provider {provider} is local; this test bills no tokens."
                    if is_local_provider
                    else f"Tokens WILL be billed to provider {provider or 'unknown'} (model {model or 'unknown'}) "
                    "for one extractor run."
                ),
            }
        finally:
            db_session.close()

        if not confirmed_by_user:
            return _json_response(
                {
                    **plan,
                    "dispatched": False,
                    "confirmation_required": True,
                    "message": (
                        "Explicit user confirmation is required before running this test. "
                        f"{plan['billing']} Show the plan to the user; after approval, retry once with "
                        "confirmed_by_user=true."
                    ),
                }
            )

        environment = _runtime_environment()
        if environment not in _TEST_TASK_ENVIRONMENTS:
            return _json_response(
                {
                    **plan,
                    "dispatched": False,
                    "error": (
                        f"The worker registers agent test tasks only in {'/'.join(_TEST_TASK_ENVIRONMENTS)}; "
                        f"this environment is {environment!r}, so nothing would consume the task."
                    ),
                }
            )

        try:
            ensure_broker_reachable()
        except EvalDispatchError as e:
            return _json_response({**plan, "dispatched": False, "error": str(e)})

        from src.worker.celery_app import celery_app

        try:
            async_result = celery_app.send_task(
                SUB_AGENT_TEST_TASK,
                kwargs={
                    "agent_name": agent_name,
                    "article_id": article_id,
                    "use_junk_filter": plan["use_junk_filter"],
                    "junk_filter_threshold": plan["junk_filter_threshold"],
                },
            )
        except Exception as e:
            logger.error("MCP test_subagent_on_article dispatch failed for %s: %s", agent_name, e, exc_info=True)
            return _json_response({**plan, "dispatched": False, "error": f"Dispatch failed: {e}"})

        audit_error: str | None = None
        try:
            async with db.get_session() as session:
                await record_mcp_audit(
                    session,
                    ACTION_DEBUG_ACTION_INVOKED,
                    "agent_test",
                    agent_name,
                    f"Dispatched {agent_name} test on article {article_id} via MCP",
                    {
                        "task_id": async_result.id,
                        "article_id": article_id,
                        "config_version": plan["config_version"],
                        "provider": plan["provider"],
                        "model": plan["model"],
                        "confirmation_attested_by_caller": True,
                    },
                )
                await session.commit()
        except Exception as e:
            audit_error = str(e)
            logger.critical("Could not audit MCP agent test %s on article %s: %s", agent_name, article_id, e)

        payload: dict[str, Any] = {
            **plan,
            "dispatched": True,
            "task_id": async_result.id,
            "initiated_by": MCP_SERVICE_ACTOR,
            "confirmation_attested_by_caller": True,
            "next_steps": (
                f"Poll get_subagent_test_result(task_id='{async_result.id}') until status is completed or failed. "
                f"The result expires {_RESULT_TTL_SECONDS // 60} minutes after the task finishes."
            ),
        }
        if audit_error:
            payload["audit_error"] = audit_error
        return _json_response(payload)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_subagent_test_result(task_id: str, include_debug: bool = False) -> str:
        """Status and result of a test started by test_subagent_on_article.

        Returns status pending, completed or failed. A completed test returns
        the extractor's items and count plus the raw model response text.
        include_debug=true also returns the prompt messages and provider payload
        (large). Celery keeps a finished result for 30 minutes; an unknown or
        expired task_id reports pending, because Celery cannot tell the two
        apart. Read-only.

        Args:
            task_id: The task_id test_subagent_on_article returned.
            include_debug: Include ``_``-prefixed debug fields (prompt, payload).
        """
        if not isinstance(task_id, str) or not task_id.strip():
            return _json_response({"error": "task_id is required"})
        task_id = task_id.strip()

        from celery.result import AsyncResult

        from src.worker.celery_app import celery_app

        try:
            task_result = AsyncResult(task_id, app=celery_app)
            if not task_result.ready():
                return _json_response(
                    {
                        "task_id": task_id,
                        "status": "pending",
                        "message": (
                            "Still running, or the task_id is unknown or its result expired "
                            f"({_RESULT_TTL_SECONDS // 60} minutes after finishing). Poll again shortly."
                        ),
                    }
                )
            if not task_result.successful():
                return _json_response({"task_id": task_id, "status": "failed", "error": str(task_result.result)})

            outcome = task_result.result if isinstance(task_result.result, dict) else {}
            base = {
                "task_id": task_id,
                "agent_name": outcome.get("agent_name"),
                "article_id": outcome.get("article_id"),
            }
            # The task catches its own errors and returns success=false instead of raising.
            if not outcome.get("success"):
                return _json_response(
                    {**base, "status": "failed", "error": outcome.get("error") or "Test task reported failure"}
                )
            return _json_response(
                {**base, "status": "completed", **_summarize_result(outcome.get("result"), include_debug)}
            )
        except Exception as e:
            logger.error("MCP get_subagent_test_result failed for %s: %s", task_id, e, exc_info=True)
            return _json_response({"task_id": task_id, "error": str(e)})
