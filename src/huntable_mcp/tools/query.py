"""MCP tools for read-only SQL queries against the CTI database."""

import logging
import re

from mcp.server.fastmcp import FastMCP
from sqlalchemy import text

from src.database.async_manager import AsyncDatabaseManager

logger = logging.getLogger(__name__)

_MAX_ROWS = 200
_MAX_CELL_LEN = 300

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE|CALL|EXECUTE|EXEC)\b",
    re.IGNORECASE,
)

_STRIP_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def _validate_readonly(sql: str) -> str | None:
    """Return an error message if the query is not a plain SELECT, else None."""
    clean = _STRIP_COMMENTS.sub("", sql).strip()
    if not clean.upper().startswith("SELECT"):
        return "Only SELECT statements are permitted."
    if _FORBIDDEN_KEYWORDS.search(clean):
        return "Query contains a forbidden write keyword."
    if ";" in clean:
        return "Multiple statements (semicolons) are not permitted."
    return None


def _format_results(columns: list[str], rows: list) -> str:
    if not rows:
        return "Query returned 0 rows."

    truncated = len(rows) > _MAX_ROWS
    display_rows = rows[:_MAX_ROWS]

    col_widths = [len(c) for c in columns]
    str_rows: list[list[str]] = []
    for row in display_rows:
        cells = []
        for i, val in enumerate(row):
            cell = "" if val is None else str(val)
            if len(cell) > _MAX_CELL_LEN:
                cell = cell[:_MAX_CELL_LEN] + "…"
            col_widths[i] = max(col_widths[i], len(cell))
            cells.append(cell)
        str_rows.append(cells)

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header = "|" + "|".join(f" {c:<{col_widths[i]}} " for i, c in enumerate(columns)) + "|"

    lines = [sep, header, sep]
    for cells in str_rows:
        lines.append("|" + "|".join(f" {c:<{col_widths[i]}} " for i, c in enumerate(cells)) + "|")
    lines.append(sep)

    note = (
        f"\n({len(display_rows)} of {len(rows)} rows shown — first {_MAX_ROWS} max)"
        if truncated
        else f"\n({len(display_rows)} row{'s' if len(display_rows) != 1 else ''})"
    )
    return "\n".join(lines) + note


def register(mcp: FastMCP, db: AsyncDatabaseManager) -> None:
    """Register read-only SQL query tools on the MCP server."""

    @mcp.tool()
    async def execute_sql(sql: str) -> str:
        """Execute a read-only SQL SELECT query against the CTI database.

        Only SELECT statements are permitted. Write operations (INSERT, UPDATE,
        DELETE, DROP, etc.), semicolons, and SQL comments that mask keywords
        are all rejected. Results are capped at 200 rows.

        Useful tables: articles, sources, article_annotations, sigma_rules,
        sigma_queue, workflow_executions, workflow_config.

        Args:
            sql: A SELECT statement to execute (no semicolons, no write keywords).
        """
        err = _validate_readonly(sql)
        if err:
            return f"Query rejected: {err}"

        try:
            async with db.get_session() as session:
                await session.execute(text("SET TRANSACTION READ ONLY"))
                result = await session.execute(text(sql))
                columns = list(result.keys())
                rows = result.fetchall()
                return _format_results(columns, rows)
        except Exception as e:
            logger.error(f"execute_sql failed: {e}")
            return f"Query error: {e}"

    @mcp.tool()
    async def list_tables() -> str:
        """List all tables in the CTI database with their columns and types.

        Use this to discover what you can query before writing a SELECT statement.
        """
        sql = """
            SELECT
                t.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default
            FROM information_schema.tables t
            JOIN information_schema.columns c
                ON c.table_schema = t.table_schema
               AND c.table_name  = t.table_name
            WHERE t.table_schema = 'public'
              AND t.table_type   = 'BASE TABLE'
            ORDER BY t.table_name, c.ordinal_position
        """
        try:
            async with db.get_session() as session:
                await session.execute(text("SET TRANSACTION READ ONLY"))
                result = await session.execute(text(sql))
                rows = result.fetchall()

            if not rows:
                return "No tables found in the public schema."

            current_table = None
            lines = []
            for table_name, col_name, data_type, nullable, default in rows:
                if table_name != current_table:
                    if current_table is not None:
                        lines.append("")
                    lines.append(f"## {table_name}")
                    current_table = table_name
                null_flag = "" if nullable == "YES" else " NOT NULL"
                default_str = f" DEFAULT {default}" if default else ""
                lines.append(f"  {col_name}  {data_type}{null_flag}{default_str}")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"list_tables failed: {e}")
            return f"Error listing tables: {e}"
