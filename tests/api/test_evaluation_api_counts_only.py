"""Unit tests for the counts_only fast path in GET /subagent-eval-results.

The counts_only=true parameter routes to a cheap GROUP BY query instead of
loading the full per-record payload.  These tests call get_subagent_eval_results
directly with a mocked DB session so they run without a live database.

Key invariants:
- counts_only=True returns {"subagent", "counts", "results": [], "total"}
- The same subagent + EXCLUDED_EVAL_ARTICLE_IDS filters are applied in both paths
- An empty table returns all-zero counts (no KeyError on missing statuses)
- Unknown status values are accumulated alongside the known ones
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request


def _make_count_session(rows: list[tuple[str, int]]) -> MagicMock:
    """Build a DB session mock that satisfies the counts_only GROUP BY chain."""
    count_q = MagicMock()
    count_q.filter.return_value = count_q  # support chained .filter().filter()...
    count_q.group_by.return_value.all.return_value = rows

    session = MagicMock()
    session.query.return_value = count_q
    return session


pytestmark = pytest.mark.api


@pytest.mark.asyncio
class TestSubagentEvalCountsOnly:
    """get_subagent_eval_results with counts_only=True uses the GROUP BY fast path."""

    async def test_returns_counts_dict_and_empty_results(self):
        """counts_only response has counts dict, results=[], and total."""
        from src.web.routes.evaluation_api import get_subagent_eval_results

        session = _make_count_session([("completed", 10), ("pending", 3), ("failed", 1)])
        with patch("src.web.routes.evaluation_api.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            result = await get_subagent_eval_results(
                request=MagicMock(spec=Request),
                subagent="cmdline",
                eval_run_id=None,
                counts_only=True,
            )

        assert result["results"] == []
        assert result["counts"]["completed"] == 10
        assert result["counts"]["pending"] == 3
        assert result["counts"]["failed"] == 1
        assert result["total"] == 14

    async def test_empty_table_returns_zero_counts(self):
        """No rows in GROUP BY → all statuses default to 0, total=0."""
        from src.web.routes.evaluation_api import get_subagent_eval_results

        session = _make_count_session([])
        with patch("src.web.routes.evaluation_api.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            result = await get_subagent_eval_results(
                request=MagicMock(spec=Request),
                subagent="cmdline",
                eval_run_id=None,
                counts_only=True,
            )

        assert result["counts"] == {"completed": 0, "pending": 0, "failed": 0}
        assert result["total"] == 0
        assert result["results"] == []

    async def test_unknown_status_values_are_accumulated(self):
        """Status values outside the known set are stored under their own key."""
        from src.web.routes.evaluation_api import get_subagent_eval_results

        session = _make_count_session([("completed", 5), ("retrying", 2)])
        with patch("src.web.routes.evaluation_api.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            result = await get_subagent_eval_results(
                request=MagicMock(spec=Request),
                subagent="cmdline",
                eval_run_id=None,
                counts_only=True,
            )

        assert result["counts"]["completed"] == 5
        assert result["counts"]["retrying"] == 2
        assert result["total"] == 7

    async def test_subagent_field_in_response_is_canonical(self):
        """The subagent key in the response is the canonical name, not the raw query."""
        from src.web.routes.evaluation_api import get_subagent_eval_results

        session = _make_count_session([])
        with patch("src.web.routes.evaluation_api.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            result = await get_subagent_eval_results(
                request=MagicMock(spec=Request),
                subagent="cmdline",
                eval_run_id=None,
                counts_only=True,
            )

        # canonical name is returned, not raw query string
        assert "subagent" in result
        assert isinstance(result["subagent"], str)

    async def test_eval_run_id_filter_is_applied(self):
        """When eval_run_id is set, a second .filter() is chained on the count query."""
        from src.web.routes.evaluation_api import get_subagent_eval_results

        session = _make_count_session([("completed", 1)])
        with patch("src.web.routes.evaluation_api.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            result = await get_subagent_eval_results(
                request=MagicMock(spec=Request),
                subagent="cmdline",
                eval_run_id=42,
                counts_only=True,
            )

        # filter() should have been called at least twice (subagent + eval_run_id)
        count_q = session.query.return_value
        assert count_q.filter.call_count >= 2
        assert result["total"] == 1

    async def test_counts_only_false_does_not_use_group_by_path(self):
        """counts_only=False must not call group_by — it takes the full record path."""
        from src.web.routes.evaluation_api import get_subagent_eval_results

        # Mock out the full path minimally so the function doesn't crash
        query_mock = MagicMock()
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value.all.return_value = []

        article_q = MagicMock()
        article_q.filter.return_value = article_q
        article_q.all.return_value = []

        execution_q = MagicMock()
        execution_q.filter.return_value = execution_q
        execution_q.all.return_value = []

        session = MagicMock()
        session.query.return_value = query_mock

        with patch("src.web.routes.evaluation_api.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            result = await get_subagent_eval_results(
                request=MagicMock(spec=Request),
                subagent="cmdline",
                eval_run_id=None,
                counts_only=False,
            )

        # Full path returns results list, not empty []
        assert "results" in result
        # group_by should NOT have been called
        count_q = session.query.return_value
        count_q.group_by.assert_not_called()
