"""MCP tools for workflow execution and SIGMA queue status."""

import logging
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from sqlalchemy import desc, select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SigmaRuleQueueTable,
)
from src.huntable_mcp.tools.write_support import record_mcp_audit
from src.services.audit_service import ACTION_WORKFLOW_CANCELLED, ACTION_WORKFLOW_RETRIED

logger = logging.getLogger(__name__)


def _enqueue_workflow_retry(article_id: int, execution_id: int) -> None:
    """Enqueue a workflow retry in Celery."""
    from src.worker.celery_app import trigger_agentic_workflow

    trigger_agentic_workflow.delay(article_id, execution_id)


def register(mcp: FastMCP, db: AsyncDatabaseManager) -> None:
    """Register workflow and queue tools on the MCP server."""

    @mcp.tool()
    async def list_workflow_executions(
        status: str | None = None,
        limit: int = 20,
    ) -> str:
        """List recent workflow executions.

        Shows the agentic workflow pipeline runs: which articles were processed,
        their status, current step, and any errors.

        Args:
            status: Filter by status (pending, running, completed, failed). Omit for all.
            limit: Maximum results (default 20)
        """
        try:
            async with db.get_session() as session:
                query = (
                    select(
                        AgenticWorkflowExecutionTable.id,
                        AgenticWorkflowExecutionTable.status,
                        AgenticWorkflowExecutionTable.current_step,
                        AgenticWorkflowExecutionTable.ranking_score,
                        AgenticWorkflowExecutionTable.error_message,
                        AgenticWorkflowExecutionTable.started_at,
                        AgenticWorkflowExecutionTable.completed_at,
                        AgenticWorkflowExecutionTable.created_at,
                        ArticleTable.title.label("article_title"),
                        ArticleTable.id.label("article_id"),
                    )
                    .join(ArticleTable, AgenticWorkflowExecutionTable.article_id == ArticleTable.id)
                    .order_by(desc(AgenticWorkflowExecutionTable.created_at))
                    .limit(limit)
                )

                if status:
                    query = query.where(AgenticWorkflowExecutionTable.status == status)

                result = await session.execute(query)
                rows = result.fetchall()

            if not rows:
                return f"No workflow executions found{f' with status={status}' if status else ''}."

            lines = [f"Workflow executions ({len(rows)}):\n"]
            for r in rows:
                created = r.created_at.isoformat() if r.created_at else "N/A"
                error = f"\n   Error: {r.error_message[:100]}..." if r.error_message else ""
                lines.append(
                    f"- **Execution #{r.id}** — {(r.status or 'unknown').upper()}\n"
                    f"  Article: [{r.article_id}] {r.article_title}\n"
                    f"  Step: {r.current_step or 'N/A'} | "
                    f"Ranking: {r.ranking_score or 'N/A'}\n"
                    f"  Created: {created}{error}\n"
                )
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Failed to list workflow executions: {e}")
            return f"Error listing workflow executions: {e}"

    @mcp.tool()
    async def retry_workflow_execution(execution_id: int) -> str:
        """Retry a failed or completed workflow execution.

        Risk tier: auto-executable. This creates a new pending execution for the
        same article and enqueues the worker task.

        Args:
            execution_id: Workflow execution ID from list_workflow_executions.
        """
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(AgenticWorkflowExecutionTable).where(AgenticWorkflowExecutionTable.id == execution_id)
                )
                execution = result.scalar_one_or_none()
                if execution is None:
                    return f"Workflow execution {execution_id} not found."
                if execution.status not in ["failed", "completed"]:
                    return (
                        f"Cannot retry execution {execution_id} with status '{execution.status}'. "
                        "Only failed or completed executions can be retried."
                    )

                new_config_snapshot = dict(execution.config_snapshot or {})
                config_result = await session.execute(
                    select(AgenticWorkflowConfigTable)
                    .where(AgenticWorkflowConfigTable.is_active)
                    .order_by(AgenticWorkflowConfigTable.version.desc())
                    .limit(1)
                )
                current_config = config_result.scalar_one_or_none()
                if current_config and current_config.agent_models:
                    new_config_snapshot["agent_models"] = dict(current_config.agent_models)
                if current_config and hasattr(current_config, "rank_agent_enabled"):
                    new_config_snapshot["rank_agent_enabled"] = bool(current_config.rank_agent_enabled)
                elif "rank_agent_enabled" not in new_config_snapshot:
                    new_config_snapshot["rank_agent_enabled"] = True
                else:
                    new_config_snapshot["rank_agent_enabled"] = bool(
                        new_config_snapshot.get("rank_agent_enabled", True)
                    )

                article_id = execution.article_id
                new_execution = AgenticWorkflowExecutionTable(
                    article_id=article_id,
                    status="pending",
                    config_snapshot=new_config_snapshot,
                    retry_count=(execution.retry_count or 0) + 1,
                )
                session.add(new_execution)
                await session.flush()
                new_execution_id = new_execution.id
                await record_mcp_audit(
                    session,
                    ACTION_WORKFLOW_RETRIED,
                    "workflow_execution",
                    execution_id,
                    f"Retried workflow execution {execution_id}",
                    {"new_execution_id": new_execution_id, "article_id": article_id},
                )
                await session.commit()

            _enqueue_workflow_retry(article_id, new_execution_id)
            return f"Retry initiated for workflow execution {execution_id}. New execution ID: {new_execution_id}."
        except Exception as e:
            logger.error(f"retry_workflow_execution failed: {e}")
            return f"Error retrying workflow execution {execution_id}: {e}"

    @mcp.tool()
    async def cancel_workflow_execution(execution_id: int) -> str:
        """Cancel a running or pending workflow execution.

        Risk tier: auto-executable. This marks the execution failed with a
        cancellation message; the worker task may continue until it notices.

        Args:
            execution_id: Workflow execution ID from list_workflow_executions.
        """
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(AgenticWorkflowExecutionTable).where(AgenticWorkflowExecutionTable.id == execution_id)
                )
                execution = result.scalar_one_or_none()
                if execution is None:
                    return f"Workflow execution {execution_id} not found."
                if execution.status not in ["running", "pending"]:
                    return (
                        f"Cannot cancel execution {execution_id} with status '{execution.status}'. "
                        "Only running or pending executions can be cancelled."
                    )

                previous_status = execution.status
                execution.status = "failed"
                execution.error_message = f"Execution cancelled by MCP (was {previous_status})"
                execution.completed_at = datetime.now()
                await record_mcp_audit(
                    session,
                    ACTION_WORKFLOW_CANCELLED,
                    "workflow_execution",
                    execution_id,
                    f"Cancelled workflow execution {execution_id}",
                    {"previous_status": previous_status},
                )
                await session.commit()

            return f"Workflow execution {execution_id} cancelled successfully."
        except Exception as e:
            logger.error(f"cancel_workflow_execution failed: {e}")
            return f"Error cancelling workflow execution {execution_id}: {e}"

    @mcp.tool()
    async def list_sigma_queue(
        status: str | None = None,
        limit: int = 20,
    ) -> str:
        """List SIGMA rules in the review queue.

        Shows AI-generated SIGMA detection rules pending human review,
        their similarity to existing rules, and review status.

        Args:
            status: Filter by status (pending, approved, rejected, submitted). Omit for all.
            limit: Maximum results (default 20)
        """
        try:
            async with db.get_session() as session:
                query = (
                    select(
                        SigmaRuleQueueTable.id,
                        SigmaRuleQueueTable.status,
                        SigmaRuleQueueTable.rule_metadata,
                        SigmaRuleQueueTable.max_similarity,
                        SigmaRuleQueueTable.review_notes,
                        SigmaRuleQueueTable.pr_url,
                        SigmaRuleQueueTable.created_at,
                        ArticleTable.title.label("article_title"),
                        ArticleTable.id.label("article_id"),
                    )
                    .join(ArticleTable, SigmaRuleQueueTable.article_id == ArticleTable.id)
                    .order_by(desc(SigmaRuleQueueTable.created_at))
                    .limit(limit)
                )

                if status:
                    query = query.where(SigmaRuleQueueTable.status == status)

                result = await session.execute(query)
                rows = result.fetchall()

            if not rows:
                return f"No SIGMA queue items found{f' with status={status}' if status else ''}."

            lines = [f"SIGMA rule queue ({len(rows)}):\n"]
            for r in rows:
                meta = r.rule_metadata or {}
                rule_title = meta.get("title", "Untitled rule")
                created = r.created_at.isoformat() if r.created_at else "N/A"
                similarity = f"{r.max_similarity:.2f}" if r.max_similarity is not None else "N/A"
                notes = f"\n   Notes: {r.review_notes}" if r.review_notes else ""
                pr = f"\n   PR: {r.pr_url}" if r.pr_url else ""
                lines.append(
                    f"- **Queue #{r.id}** — {(r.status or 'unknown').upper()}\n"
                    f"  Rule: {rule_title}\n"
                    f"  Source article: [{r.article_id}] {r.article_title}\n"
                    f"  Max similarity to existing: {similarity}\n"
                    f"  Created: {created}{notes}{pr}\n"
                )
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Failed to list sigma queue: {e}")
            return f"Error listing sigma queue: {e}"

    @mcp.tool()
    async def get_queue_rule(queue_number: int) -> str:
        """Get full YAML, status, similarity scores, and reviewer notes for a SIGMA queue item.

        Use the queue number shown in list_sigma_queue output (e.g. Queue #264 -> queue_number=264).

        Args:
            queue_number: Integer queue ID from list_sigma_queue (the number after "Queue #").
        """
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(
                        SigmaRuleQueueTable.id,
                        SigmaRuleQueueTable.status,
                        SigmaRuleQueueTable.rule_yaml,
                        SigmaRuleQueueTable.rule_metadata,
                        SigmaRuleQueueTable.similarity_scores,
                        SigmaRuleQueueTable.max_similarity,
                        SigmaRuleQueueTable.review_notes,
                        SigmaRuleQueueTable.reviewed_by,
                        SigmaRuleQueueTable.reviewed_at,
                        SigmaRuleQueueTable.pr_url,
                        SigmaRuleQueueTable.created_at,
                        ArticleTable.title.label("article_title"),
                        ArticleTable.id.label("article_id"),
                    )
                    .join(ArticleTable, SigmaRuleQueueTable.article_id == ArticleTable.id)
                    .where(SigmaRuleQueueTable.id == queue_number)
                )
                row = result.fetchone()

            if row is None:
                return f"No queue item found with queue_number={queue_number}."

            meta = row.rule_metadata or {}
            rule_title = meta.get("title", "Untitled rule")
            created = row.created_at.isoformat() if row.created_at else "N/A"
            reviewed_at = row.reviewed_at.isoformat() if row.reviewed_at else "N/A"
            max_sim = f"{row.max_similarity:.4f}" if row.max_similarity is not None else "N/A"

            # Format similarity scores
            scores = row.similarity_scores or []
            if scores:
                sim_lines = "\n".join(
                    f"  - {s.get('title', 'Unknown')} [{s.get('rule_id', '?')}]: {s.get('similarity', 0):.4f}"
                    for s in sorted(scores, key=lambda x: x.get("similarity", 0), reverse=True)[:10]
                )
            else:
                sim_lines = "  (none computed)"

            review_section = ""
            if row.review_notes or row.reviewed_by:
                review_section = (
                    f"\n## Reviewer Notes\n"
                    f"**Reviewed by:** {row.reviewed_by or 'N/A'} | **At:** {reviewed_at}\n"
                    f"{row.review_notes or '(no notes)'}\n"
                )

            pr_section = f"\n**PR:** {row.pr_url}" if row.pr_url else ""

            return (
                f"# Queue #{row.id} — {(row.status or 'unknown').upper()}\n\n"
                f"**Rule:** {rule_title}\n"
                f"**Source article:** [{row.article_id}] {row.article_title}\n"
                f"**Created:** {created}{pr_section}\n\n"
                f"## Similarity to Existing Rules\n"
                f"**Max similarity:** {max_sim}\n"
                f"{sim_lines}\n"
                f"{review_section}\n"
                f"## Detection Rule (YAML)\n```yaml\n{row.rule_yaml or '(no YAML stored)'}\n```\n"
            )

        except Exception as e:
            logger.error(f"Failed to get queue rule {queue_number}: {e}")
            return f"Error retrieving queue item {queue_number}: {e}"
