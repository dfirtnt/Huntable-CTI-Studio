"""MCP tools for workflow execution and SIGMA queue status."""

import logging

from mcp.server.fastmcp import FastMCP
from sqlalchemy import desc, select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import (
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SigmaRuleQueueTable,
)

logger = logging.getLogger(__name__)


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
