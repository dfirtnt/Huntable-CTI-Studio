"""Unit tests for the execute_sql and list_tables MCP tools."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.query import _format_results, _validate_readonly, register

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_tools(session_rows: list, columns: list[str] | None = None):
    """Build registered tools backed by a mock session.

    session_rows: rows returned by session.execute(...).fetchall()
    columns:      column names from session.execute(...).keys()
    """
    if columns is None:
        columns = ["col"]

    result_mock = MagicMock()
    result_mock.keys.return_value = columns
    result_mock.fetchall.return_value = session_rows

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock(return_value=result_mock)

    @asynccontextmanager
    async def _mock_session():
        yield session_mock

    db = MagicMock()
    db.get_session = _mock_session

    mcp = FastMCP("test-query")
    register(mcp, db)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    return tools, session_mock


# ── _validate_readonly ────────────────────────────────────────────────────────


class TestValidateReadonly:
    def test_plain_select_is_allowed(self):
        assert _validate_readonly("SELECT 1") is None

    def test_select_with_where_is_allowed(self):
        assert _validate_readonly("SELECT id, title FROM articles WHERE hunt_score > 50") is None

    def test_select_with_join_is_allowed(self):
        sql = "SELECT a.title, s.name FROM articles a JOIN sources s ON s.id = a.source_id"
        assert _validate_readonly(sql) is None

    def test_leading_whitespace_and_newlines_are_ok(self):
        assert _validate_readonly("\n  SELECT * FROM sources\n") is None

    def test_update_is_rejected(self):
        err = _validate_readonly("UPDATE articles SET title = 'x'")
        assert err is not None
        assert "Only SELECT" in err

    def test_insert_is_rejected(self):
        err = _validate_readonly("INSERT INTO articles (title) VALUES ('x')")
        assert err is not None

    def test_delete_is_rejected(self):
        err = _validate_readonly("DELETE FROM articles WHERE id = 1")
        assert err is not None

    def test_drop_is_rejected(self):
        err = _validate_readonly("DROP TABLE articles")
        assert err is not None

    def test_truncate_is_rejected(self):
        err = _validate_readonly("TRUNCATE articles")
        assert err is not None

    def test_alter_is_rejected(self):
        err = _validate_readonly("ALTER TABLE articles ADD COLUMN foo TEXT")
        assert err is not None

    def test_create_is_rejected(self):
        err = _validate_readonly("CREATE TABLE evil (id INT)")
        assert err is not None

    def test_select_then_drop_via_semicolon_is_rejected(self):
        err = _validate_readonly("SELECT 1; DROP TABLE articles")
        assert err is not None

    def test_double_select_via_semicolon_is_rejected(self):
        # Even harmless chaining is rejected to prevent any ambiguity.
        err = _validate_readonly("SELECT 1; SELECT 2")
        assert err is not None
        assert "semicolon" in err.lower()

    def test_comment_masking_write_keyword_is_stripped_before_check(self):
        # /* UPDATE */ before SELECT is stripped — the remaining query is valid.
        assert _validate_readonly("/* UPDATE */ SELECT 1") is None

    def test_inline_comment_before_select(self):
        assert _validate_readonly("-- ignore me\nSELECT 1") is None

    def test_drop_keyword_inside_string_literal_is_conservatively_rejected(self):
        # The validator cannot parse string literals, so 'DROP' in a LIKE pattern
        # is rejected. This is a known conservative false-positive.
        sql = "SELECT * FROM articles WHERE title LIKE '%DROP%'"
        err = _validate_readonly(sql)
        assert err is not None

    def test_uppercase_forbidden_keyword_is_rejected(self):
        assert _validate_readonly("DELETE FROM sources") is not None

    def test_mixed_case_forbidden_keyword_is_rejected(self):
        assert _validate_readonly("dElEtE FROM sources") is not None


# ── _format_results ────────────────────────────────────────────────────────


class TestFormatResults:
    def test_empty_rows_message(self):
        result = _format_results(["id"], [])
        assert result == "Query returned 0 rows."

    def test_single_row_singular_suffix(self):
        result = _format_results(["id"], [("1",)])
        assert "(1 row)" in result

    def test_multiple_rows_plural_suffix(self):
        result = _format_results(["id"], [("1",), ("2",), ("3",)])
        assert "(3 rows)" in result

    def test_column_header_appears_in_output(self):
        result = _format_results(["article_id", "title"], [("42", "Test Article")])
        assert "article_id" in result
        assert "title" in result

    def test_cell_values_appear_in_output(self):
        result = _format_results(["id", "name"], [("7", "Bleeping Computer")])
        assert "7" in result
        assert "Bleeping Computer" in result

    def test_none_cell_renders_as_empty_string(self):
        result = _format_results(["id", "value"], [("1", None)])
        # Should not raise and should not contain "None"
        assert "None" not in result

    def test_long_cell_is_truncated_with_ellipsis(self):
        long_val = "x" * 400
        result = _format_results(["col"], [(long_val,)])
        assert "…" in result
        # Truncated cell must not exceed 300 visible chars + ellipsis
        # Find the cell content in the table between pipes
        assert "x" * 300 in result
        assert "x" * 301 not in result

    def test_exactly_200_rows_no_truncation_note(self):
        rows = [(str(i),) for i in range(200)]
        result = _format_results(["id"], rows)
        assert "of 200 rows" not in result
        assert "(200 rows)" in result

    def test_201_rows_shows_truncation_note(self):
        rows = [(str(i),) for i in range(201)]
        result = _format_results(["id"], rows)
        assert "200 of 201 rows" in result

    def test_table_has_separator_lines(self):
        result = _format_results(["id"], [("1",)])
        assert "+" in result
        assert "|" in result

    def test_multi_column_row_renders_all_columns(self):
        result = _format_results(["a", "b", "c"], [("alpha", "beta", "gamma")])
        assert "alpha" in result
        assert "beta" in result
        assert "gamma" in result


# ── execute_sql tool ──────────────────────────────────────────────────────────


class TestExecuteSql:
    async def test_valid_select_returns_table(self):
        tools, _ = _make_tools([("42",)], ["id"])
        fn = tools["execute_sql"].fn

        result = await fn(sql="SELECT id FROM articles LIMIT 1")

        assert "id" in result
        assert "42" in result

    async def test_sets_transaction_read_only_before_query(self):
        tools, session_mock = _make_tools([], ["id"])
        fn = tools["execute_sql"].fn

        await fn(sql="SELECT 1")

        first_call_sql = str(session_mock.execute.call_args_list[0][0][0])
        assert "SET TRANSACTION READ ONLY" in first_call_sql

    async def test_write_query_is_rejected_before_db_call(self):
        tools, session_mock = _make_tools([])
        fn = tools["execute_sql"].fn

        result = await fn(sql="DELETE FROM articles WHERE id = 1")

        assert "Query rejected" in result
        session_mock.execute.assert_not_called()

    async def test_semicolon_query_is_rejected_before_db_call(self):
        tools, session_mock = _make_tools([])
        fn = tools["execute_sql"].fn

        result = await fn(sql="SELECT 1; SELECT 2")

        assert "Query rejected" in result
        session_mock.execute.assert_not_called()

    async def test_empty_result_returns_zero_rows_message(self):
        tools, _ = _make_tools([], ["id"])
        fn = tools["execute_sql"].fn

        result = await fn(sql="SELECT id FROM articles WHERE 1=0")

        assert "0 rows" in result

    async def test_db_exception_returns_error_string(self):
        result_mock = MagicMock()
        result_mock.keys.return_value = ["id"]
        result_mock.fetchall.return_value = [("1",)]

        session_mock = AsyncMock()
        session_mock.execute = AsyncMock(side_effect=RuntimeError("pg: connection lost"))

        @asynccontextmanager
        async def _failing_session():
            yield session_mock

        db = MagicMock()
        db.get_session = _failing_session

        mcp = FastMCP("test-query-err")
        register(mcp, db)
        fn = {t.name: t for t in mcp._tool_manager.list_tools()}["execute_sql"].fn

        result = await fn(sql="SELECT 1")

        assert "Query error" in result


# ── list_tables tool ──────────────────────────────────────────────────────────


class TestListTables:
    def _make_table_rows(self):
        return [
            ("articles", "id", "integer", "NO", "nextval('articles_id_seq')"),
            ("articles", "title", "text", "NO", None),
            ("articles", "summary", "text", "YES", None),
            ("sources", "id", "integer", "NO", "nextval('sources_id_seq')"),
            ("sources", "name", "text", "NO", None),
        ]

    async def test_groups_columns_by_table(self):
        tools, _ = _make_tools(
            self._make_table_rows(),
            ["table_name", "column_name", "data_type", "is_nullable", "column_default"],
        )
        fn = tools["list_tables"].fn

        result = await fn()

        assert "## articles" in result
        assert "## sources" in result

    async def test_not_null_columns_have_flag(self):
        tools, _ = _make_tools(
            self._make_table_rows(),
            ["table_name", "column_name", "data_type", "is_nullable", "column_default"],
        )
        fn = tools["list_tables"].fn

        result = await fn()

        # id and title are NOT NULL
        assert "NOT NULL" in result

    async def test_nullable_columns_omit_not_null(self):
        rows = [("articles", "summary", "text", "YES", None)]
        tools, _ = _make_tools(
            rows,
            ["table_name", "column_name", "data_type", "is_nullable", "column_default"],
        )
        fn = tools["list_tables"].fn

        result = await fn()

        assert "summary" in result
        assert "NOT NULL" not in result

    async def test_default_value_appears(self):
        rows = [("articles", "id", "integer", "NO", "nextval('articles_id_seq')")]
        tools, _ = _make_tools(
            rows,
            ["table_name", "column_name", "data_type", "is_nullable", "column_default"],
        )
        fn = tools["list_tables"].fn

        result = await fn()

        assert "DEFAULT" in result
        assert "nextval" in result

    async def test_empty_schema_returns_no_tables_message(self):
        tools, _ = _make_tools(
            [],
            ["table_name", "column_name", "data_type", "is_nullable", "column_default"],
        )
        fn = tools["list_tables"].fn

        result = await fn()

        assert "No tables found" in result

    async def test_sets_transaction_read_only(self):
        tools, session_mock = _make_tools(
            [],
            ["table_name", "column_name", "data_type", "is_nullable", "column_default"],
        )
        fn = tools["list_tables"].fn

        await fn()

        first_call_sql = str(session_mock.execute.call_args_list[0][0][0])
        assert "SET TRANSACTION READ ONLY" in first_call_sql

    async def test_db_exception_returns_error_string(self):
        session_mock = AsyncMock()
        session_mock.execute = AsyncMock(side_effect=RuntimeError("schema not found"))

        @asynccontextmanager
        async def _failing_session():
            yield session_mock

        db = MagicMock()
        db.get_session = _failing_session

        mcp = FastMCP("test-list-tables-err")
        register(mcp, db)
        fn = {t.name: t for t in mcp._tool_manager.list_tools()}["list_tables"].fn

        result = await fn()

        assert "Error listing tables" in result
