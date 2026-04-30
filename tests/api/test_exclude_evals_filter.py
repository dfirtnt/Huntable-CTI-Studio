"""
Regression test: exclude_evals filter on GET /api/workflow/executions.

Verifies that executions where config_snapshot->>'eval_run' IS 'true' are
excluded when exclude_evals=true is passed, and that:
  - normal executions (eval_run absent or false) are always returned
  - the stat counts also reflect the filtered set
  - executions without config_snapshot (NULL) are kept

Requires: TEST_DATABASE_URL set + USE_ASGI_CLIENT=1 (integration_full suite).
Falls back to skipping cleanly when no test DB is available.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sync_test_db_url() -> str | None:
    """Return sync Postgres URL for test DB, or None if not configured."""
    password = os.getenv("POSTGRES_PASSWORD", "cti_password")
    default = f"postgresql://cti_user:{password}@localhost:5433/cti_scraper_test"
    url = os.getenv("TEST_DATABASE_URL", default)
    return url.replace("+asyncpg", "")


def _skip_if_no_test_db():
    url = _sync_test_db_url()
    try:
        from sqlalchemy import create_engine, text

        eng = create_engine(url, connect_args={"connect_timeout": 2})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Test DB not reachable")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _TestData:
    """Container for IDs created in a test run so cleanup can target them."""

    def __init__(self):
        self.source_id: int | None = None
        self.article_id: int | None = None
        self.eval_exec_id: int | None = None
        self.normal_exec_id: int | None = None
        self.null_snapshot_exec_id: int | None = None


def _seed(session, uid: str) -> _TestData:
    """Insert a source, one article, and three executions into the test DB."""
    from src.database.models import AgenticWorkflowExecutionTable, ArticleTable, SourceTable

    td = _TestData()

    source = SourceTable(
        identifier=f"test-excl-evals-{uid}",
        name="Excl-Evals Test Source",
        url=f"https://test.invalid/excl-evals-{uid}",
        rss_url=None,
        check_frequency=86400,
        lookback_days=365,
        active=False,
        config={},
    )
    session.add(source)
    session.flush()
    td.source_id = source.id

    article = ArticleTable(
        source_id=source.id,
        canonical_url=f"https://test.invalid/excl-evals-article-{uid}",
        title=f"Excl-Evals Test Article {uid}",
        published_at=datetime.now(UTC),
        content="Test content for exclude_evals regression.",
        content_hash=f"excl-evals-hash-{uid}",
        article_metadata={},
        word_count=7,
    )
    session.add(article)
    session.flush()
    td.article_id = article.id

    # Eval execution — should be hidden with exclude_evals=true
    eval_exec = AgenticWorkflowExecutionTable(
        article_id=article.id,
        status="completed",
        current_step="extract_agent",
        config_snapshot={"eval_run": True, "test_uid": uid},
    )
    session.add(eval_exec)
    session.flush()
    td.eval_exec_id = eval_exec.id

    # Normal execution — should always appear
    normal_exec = AgenticWorkflowExecutionTable(
        article_id=article.id,
        status="completed",
        current_step="extract_agent",
        config_snapshot={"eval_run": False, "test_uid": uid},
    )
    session.add(normal_exec)
    session.flush()
    td.normal_exec_id = normal_exec.id

    # NULL config_snapshot execution — should appear (no eval_run key at all)
    null_exec = AgenticWorkflowExecutionTable(
        article_id=article.id,
        status="completed",
        current_step="extract_agent",
        config_snapshot=None,
    )
    session.add(null_exec)
    session.flush()
    td.null_snapshot_exec_id = null_exec.id

    session.commit()
    return td


def _cleanup(session, td: _TestData):
    """Remove all rows created by _seed."""
    from src.database.models import AgenticWorkflowExecutionTable, ArticleTable, SourceTable

    for exec_id in [td.eval_exec_id, td.normal_exec_id, td.null_snapshot_exec_id]:
        if exec_id:
            row = session.query(AgenticWorkflowExecutionTable).filter_by(id=exec_id).first()
            if row:
                session.delete(row)
    if td.article_id:
        row = session.query(ArticleTable).filter_by(id=td.article_id).first()
        if row:
            session.delete(row)
    if td.source_id:
        row = session.query(SourceTable).filter_by(id=td.source_id).first()
        if row:
            session.delete(row)
    session.commit()


# ---------------------------------------------------------------------------
# Integration tests (real DB)
# ---------------------------------------------------------------------------


@pytest.mark.integration_full
class TestExcludeEvalsFilter:
    """Verify exclude_evals filter correctly hides eval executions."""

    def _get_db(self):
        from src.database.manager import DatabaseManager

        return DatabaseManager(database_url=_sync_test_db_url())

    def setup_method(self):
        _skip_if_no_test_db()

    @pytest.mark.asyncio
    async def test_exclude_evals_hides_eval_executions(self):
        """With exclude_evals=true, executions with eval_run=True are absent."""
        uid = uuid.uuid4().hex[:8]
        db = self._get_db()
        session = db.get_session()
        td = _seed(session, uid)

        try:
            from src.web.routes.workflow_executions import list_workflow_executions

            with patch("src.web.routes.workflow_executions.get_db_manager", return_value=db):
                result = await list_workflow_executions(
                    request=MagicMock(spec=Request),
                    exclude_evals=True,
                    page=1,
                    limit=200,
                )

            returned_ids = {e.id for e in result.executions}
            assert td.eval_exec_id not in returned_ids, (
                f"Eval execution {td.eval_exec_id} should be excluded but was returned"
            )
            assert td.normal_exec_id in returned_ids, f"Normal execution {td.normal_exec_id} should be included"
            assert td.null_snapshot_exec_id in returned_ids, (
                f"NULL config_snapshot execution {td.null_snapshot_exec_id} should be included"
            )
        finally:
            _cleanup(session, td)

    @pytest.mark.asyncio
    async def test_without_filter_returns_all_executions(self):
        """Without exclude_evals, all executions including evals are returned."""
        uid = uuid.uuid4().hex[:8]
        db = self._get_db()
        session = db.get_session()
        td = _seed(session, uid)

        try:
            from src.web.routes.workflow_executions import list_workflow_executions

            with patch("src.web.routes.workflow_executions.get_db_manager", return_value=db):
                result = await list_workflow_executions(
                    request=MagicMock(spec=Request),
                    exclude_evals=False,
                    page=1,
                    limit=200,
                )

            returned_ids = {e.id for e in result.executions}
            for exec_id in [td.eval_exec_id, td.normal_exec_id, td.null_snapshot_exec_id]:
                assert exec_id in returned_ids, f"Execution {exec_id} should be present without exclude_evals filter"
        finally:
            _cleanup(session, td)

    @pytest.mark.asyncio
    async def test_exclude_evals_stat_counts_reflect_filter(self):
        """total count drops by at least 1 (the eval execution) when filter is on."""
        uid = uuid.uuid4().hex[:8]
        db = self._get_db()
        session = db.get_session()
        td = _seed(session, uid)

        try:
            from src.web.routes.workflow_executions import list_workflow_executions

            with patch("src.web.routes.workflow_executions.get_db_manager", return_value=db):
                unfiltered = await list_workflow_executions(
                    request=MagicMock(spec=Request),
                    exclude_evals=False,
                    page=1,
                    limit=1,
                )
                filtered = await list_workflow_executions(
                    request=MagicMock(spec=Request),
                    exclude_evals=True,
                    page=1,
                    limit=1,
                )

            assert filtered.total < unfiltered.total, (
                f"Filtered total ({filtered.total}) should be less than unfiltered total ({unfiltered.total})"
            )
        finally:
            _cleanup(session, td)
