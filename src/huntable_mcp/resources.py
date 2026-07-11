"""MCP resources for ambient Huntable runtime context."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import desc, func, select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import AgenticWorkflowConfigTable, ArticleTable, SigmaRuleQueueTable

logger = logging.getLogger(__name__)

_RECENT_RULE_LIMIT = 10


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _queue_row(row: Any) -> dict[str, Any]:
    metadata = row.rule_metadata or {}
    return {
        "queue_number": row.id,
        "status": row.status,
        "title": metadata.get("title", "Untitled rule"),
        "article_id": row.article_id,
        "article_title": row.article_title,
        "max_similarity": row.max_similarity,
        "behavioral_matches_found": row.behavioral_matches_found,
        "total_candidates_evaluated": row.total_candidates_evaluated,
        "pr_url": row.pr_url,
        "created_at": _iso(row.created_at),
    }


def _active_config_payload(config: AgenticWorkflowConfigTable | None) -> dict[str, Any]:
    if config is None:
        return {
            "resource": "huntable://workflow/active-config",
            "active": False,
            "config": None,
        }

    return {
        "resource": "huntable://workflow/active-config",
        "active": True,
        "config": {
            "id": config.id,
            "version": config.version,
            "description": config.description,
            "updated_at": _iso(config.updated_at),
            "thresholds": {
                "min_hunt_score": config.min_hunt_score,
                "ranking_threshold": config.ranking_threshold,
                "similarity_threshold": config.similarity_threshold,
                "junk_filter_threshold": config.junk_filter_threshold,
                "auto_trigger_hunt_score_threshold": config.auto_trigger_hunt_score_threshold,
            },
            "toggles": {
                "rank_agent_enabled": config.rank_agent_enabled,
                "sigma_fallback_enabled": config.sigma_fallback_enabled,
                "cmdline_attention_preprocessor_enabled": config.cmdline_attention_preprocessor_enabled,
                "proc_tree_attention_preprocessor_enabled": config.proc_tree_attention_preprocessor_enabled,
            },
            "agent_models": config.agent_models or {},
            "prompt_agents": sorted((config.agent_prompts or {}).keys()),
        },
    }


def register(mcp: FastMCP, db: AsyncDatabaseManager) -> None:
    """Register read-only ambient context resources on the MCP server."""

    @mcp.resource(
        "huntable://sigma-queue/status",
        name="sigma_queue_status",
        title="Sigma Queue Status",
        description="Global status counts for the AI-generated Sigma review queue.",
        mime_type="application/json",
    )
    async def sigma_queue_status() -> dict[str, Any]:
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(SigmaRuleQueueTable.status, func.count(SigmaRuleQueueTable.id))
                    .group_by(SigmaRuleQueueTable.status)
                    .order_by(SigmaRuleQueueTable.status)
                )
                counts = {status or "unknown": count for status, count in result.fetchall()}

            return {
                "resource": "huntable://sigma-queue/status",
                "total": sum(counts.values()),
                "status_counts": counts,
            }
        except Exception as e:
            logger.error("Failed to read sigma queue status resource: %s", e)
            return {"resource": "huntable://sigma-queue/status", "error": str(e)}

    @mcp.resource(
        "huntable://sigma-queue/recent-rules",
        name="sigma_queue_recent_rules",
        title="Recent Sigma Queue Rules",
        description="Most recent AI-generated Sigma review queue entries with status and source article.",
        mime_type="application/json",
    )
    async def sigma_queue_recent_rules() -> dict[str, Any]:
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(
                        SigmaRuleQueueTable.id,
                        SigmaRuleQueueTable.status,
                        SigmaRuleQueueTable.rule_metadata,
                        SigmaRuleQueueTable.max_similarity,
                        SigmaRuleQueueTable.behavioral_matches_found,
                        SigmaRuleQueueTable.total_candidates_evaluated,
                        SigmaRuleQueueTable.pr_url,
                        SigmaRuleQueueTable.created_at,
                        ArticleTable.id.label("article_id"),
                        ArticleTable.title.label("article_title"),
                    )
                    .outerjoin(ArticleTable, SigmaRuleQueueTable.article_id == ArticleTable.id)
                    .order_by(desc(SigmaRuleQueueTable.created_at))
                    .limit(_RECENT_RULE_LIMIT)
                )
                rows = result.fetchall()

            return {
                "resource": "huntable://sigma-queue/recent-rules",
                "limit": _RECENT_RULE_LIMIT,
                "count": len(rows),
                "rules": [_queue_row(row) for row in rows],
            }
        except Exception as e:
            logger.error("Failed to read recent sigma queue rules resource: %s", e)
            return {"resource": "huntable://sigma-queue/recent-rules", "error": str(e)}

    @mcp.resource(
        "huntable://workflow/active-config",
        name="workflow_active_config",
        title="Active Workflow Config",
        description="Current active workflow config version, thresholds, toggles, and model assignments.",
        mime_type="application/json",
    )
    async def workflow_active_config() -> dict[str, Any]:
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(AgenticWorkflowConfigTable)
                    .where(AgenticWorkflowConfigTable.is_active)
                    .order_by(AgenticWorkflowConfigTable.version.desc())
                    .limit(1)
                )
                config = result.scalar_one_or_none()
            return _active_config_payload(config)
        except Exception as e:
            logger.error("Failed to read active workflow config resource: %s", e)
            return {"resource": "huntable://workflow/active-config", "error": str(e)}
