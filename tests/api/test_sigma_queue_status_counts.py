"""Unit tests for status_counts global aggregation in the sigma-queue list endpoint.

These tests call list_queued_rules directly with a mocked DB session so they run
without a live database.  The key invariant: status_counts always reflects global
DB totals, independent of the status filter applied to items/total.
"""

from unittest.mock import MagicMock, patch

import pytest


def _make_session_mock(counts_rows, total=0, rules=None):
    """Build a DB session mock that returns the given aggregation data.

    Query call order inside list_queued_rules:
      1. query(SigmaRuleQueueTable)        -> base  (filtered for total)
      2. query(SigmaRuleQueueTable)        -> data  (filtered for items)
      3. query(ArticleTable) per rule      -> article lookup (skipped when rules=[])
      4. query(status_col, count_col)      -> GROUP BY aggregation
    """
    rules = rules or []

    base_mock = MagicMock()
    base_mock.filter.return_value = base_mock  # chained filter returns self
    base_mock.with_entities.return_value.scalar.return_value = total

    data_mock = MagicMock()
    data_mock.filter.return_value = data_mock
    data_mock.order_by.return_value.offset.return_value.limit.return_value.all.return_value = rules

    counts_mock = MagicMock()
    counts_mock.group_by.return_value.all.return_value = counts_rows

    session = MagicMock()
    session.query.side_effect = [base_mock, data_mock, counts_mock]
    return session


@pytest.mark.api
class TestSigmaQueueStatusCounts:
    """list_queued_rules always populates status_counts from a global GROUP BY query."""

    @pytest.mark.asyncio
    async def test_status_counts_present_in_response(self):
        """Response includes status_counts key with dict value."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import list_queued_rules

        session = _make_session_mock(
            counts_rows=[("pending", 3), ("approved", 1)],
            total=4,
        )
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            response = await list_queued_rules(
                request=MagicMock(spec=Request),
                status=None,
                limit=50,
                offset=0,
            )

        assert hasattr(response, "status_counts")
        assert isinstance(response.status_counts, dict)

    @pytest.mark.asyncio
    async def test_status_counts_values_match_aggregation(self):
        """status_counts reflects the GROUP BY result from the DB."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import list_queued_rules

        session = _make_session_mock(
            counts_rows=[("pending", 5), ("approved", 2), ("rejected", 1), ("submitted", 3)],
            total=11,
        )
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            response = await list_queued_rules(
                request=MagicMock(spec=Request),
                status=None,
                limit=50,
                offset=0,
            )

        assert response.status_counts == {"pending": 5, "approved": 2, "rejected": 1, "submitted": 3}

    @pytest.mark.asyncio
    async def test_status_counts_global_even_when_filter_applied(self):
        """When status='pending' narrows total to 5, status_counts still shows all statuses."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import list_queued_rules

        # The DB returns total=5 for the filtered query, but counts show global breakdown
        session = _make_session_mock(
            counts_rows=[("pending", 5), ("approved", 2), ("rejected", 0)],
            total=5,  # filtered total for status=pending
        )
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            response = await list_queued_rules(
                request=MagicMock(spec=Request),
                status="pending",
                limit=50,
                offset=0,
            )

        assert response.total == 5  # filtered
        # status_counts comes from the unfiltered GROUP BY
        assert response.status_counts.get("approved") == 2
        assert response.status_counts.get("pending") == 5

    @pytest.mark.asyncio
    async def test_status_counts_empty_queue(self):
        """status_counts is an empty dict when the queue is empty."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import list_queued_rules

        session = _make_session_mock(counts_rows=[], total=0)
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            response = await list_queued_rules(
                request=MagicMock(spec=Request),
                status=None,
                limit=50,
                offset=0,
            )

        assert response.status_counts == {}
        assert response.total == 0

    @pytest.mark.asyncio
    async def test_status_counts_excludes_null_status_rows(self):
        """Rows with None status are excluded from status_counts."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import list_queued_rules

        # The DB returns a row with None key (data quality issue)
        session = _make_session_mock(
            counts_rows=[(None, 1), ("pending", 4)],
            total=5,
        )
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            response = await list_queued_rules(
                request=MagicMock(spec=Request),
                status=None,
                limit=50,
                offset=0,
            )

        assert None not in response.status_counts
        assert response.status_counts.get("pending") == 4


@pytest.mark.api
class TestQueuedRuleListResponseModel:
    """Contract: QueuedRuleListResponse includes status_counts with default empty dict."""

    def test_model_has_status_counts_field(self):
        from src.web.routes.sigma_queue import QueuedRuleListResponse

        resp = QueuedRuleListResponse(items=[], total=0, limit=10, offset=0)
        assert hasattr(resp, "status_counts")
        assert resp.status_counts == {}

    def test_model_accepts_status_counts_dict(self):
        from src.web.routes.sigma_queue import QueuedRuleListResponse

        counts = {"pending": 3, "approved": 1}
        resp = QueuedRuleListResponse(items=[], total=4, limit=10, offset=0, status_counts=counts)
        assert resp.status_counts == counts
