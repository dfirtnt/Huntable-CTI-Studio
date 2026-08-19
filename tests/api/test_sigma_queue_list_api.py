"""API tests for SIGMA queue list endpoint (paginated)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.api
class TestSigmaQueueListAPI:
    """Test GET /api/sigma-queue/list returns paginated response."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_shape(self, async_client):
        """List endpoint returns items, total, limit, offset, and status_counts."""
        response = await async_client.get("/api/sigma-queue/list?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "status_counts" in data
        assert isinstance(data["items"], list)
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert isinstance(data["total"], int)
        assert data["total"] >= 0
        assert isinstance(data["status_counts"], dict)
        for v in data["status_counts"].values():
            assert isinstance(v, int) and v >= 0

    @pytest.mark.asyncio
    async def test_list_respects_limit_and_offset(self, async_client):
        """List endpoint respects limit and offset query params."""
        response = await async_client.get("/api/sigma-queue/list?limit=5&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 2
        assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_list_accepts_status_filter(self, async_client):
        """List endpoint accepts status query param and still returns status_counts."""
        response = await async_client.get("/api/sigma-queue/list?status=pending&limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "status_counts" in data
        assert isinstance(data["status_counts"], dict)

    @pytest.mark.asyncio
    async def test_list_accepts_keyword_filter(self, async_client):
        """List endpoint accepts keyword query param and returns only matching items."""
        response = await async_client.get("/api/sigma-queue/list?keyword=detection&limit=50&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        # Every returned item must contain the keyword in its rule_yaml (case-insensitive)
        for item in data["items"]:
            assert "detection" in (item.get("rule_yaml") or "").lower()

    @pytest.mark.asyncio
    async def test_list_keyword_no_match_returns_empty(self, async_client):
        """Keyword filter that matches nothing returns an empty items list with total=0."""
        response = await async_client.get("/api/sigma-queue/list?keyword=ZZZNOTAVALIDKEYWORD999&limit=50&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


def _make_list_session_mock(counts_rows, total=0, rules=None):
    """Build a DB session mock for list_queued_rules (mirrors status_counts helper).

    Query call order:
      1. query(SigmaRuleQueueTable)        -> base  (filtered for total)
      2. query(SigmaRuleQueueTable)        -> data  (filtered for items)
      3. query(status_col, count_col)      -> GROUP BY aggregation

    Returns (session, base_mock, data_mock) so tests can assert on the filter
    calls after the function runs (the side_effect list is consumed in place).
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
    return session, base_mock, data_mock


@pytest.mark.api
class TestSigmaQueueListJobFilter:
    """workflow_execution_id query param narrows the list to one job's rules."""

    def test_job_filter_applied_to_count_and_data_queries(self):
        """Both the total-count and data queries receive the execution-id filter."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import list_queued_rules

        session, base_mock, data_mock = _make_list_session_mock(counts_rows=[], total=0)
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            response = list_queued_rules(
                request=MagicMock(spec=Request),
                status=None,
                keyword=None,
                workflow_execution_id=42,
                limit=50,
                offset=0,
            )

        assert response.total == 0
        assert len(base_mock.filter.call_args_list) == 1
        assert len(data_mock.filter.call_args_list) == 1
        for call in base_mock.filter.call_args_list + data_mock.filter.call_args_list:
            assert "workflow_execution_id" in str(call.args[0])
            assert call.args[0].right.effective_value == 42

    def test_no_job_filter_applies_no_extra_filter(self):
        """Without workflow_execution_id the queries stay unfiltered by job."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import list_queued_rules

        session, base_mock, data_mock = _make_list_session_mock(counts_rows=[], total=0)
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = session
            response = list_queued_rules(
                request=MagicMock(spec=Request),
                status=None,
                keyword=None,
                workflow_execution_id=None,
                limit=50,
                offset=0,
            )

        assert response.total == 0
        assert base_mock.filter.call_count == 0
        assert data_mock.filter.call_count == 0
