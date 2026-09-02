"""
Regression test: the "(unset)" step filter bucket on GET /api/workflow/executions.

`agentic_workflow_executions.current_step` has rows with NULL and rows with ''
depending on when they were written. Before this fix those rows were simply
unreachable by the Step filter dropdown. `step=__unset__` (the
`UNSET_STEP_FILTER_VALUE` sentinel) must match both NULL and empty-string rows,
and must not match rows with a real step value.

Requires: TEST_DATABASE_URL set (integration_full suite).
Falls back to skipping cleanly when no test DB is available.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from tests.api.test_exclude_evals_filter import _skip_if_no_test_db, _sync_test_db_url

pytestmark = pytest.mark.api


class _TestData:
    def __init__(self):
        self.source_id: int | None = None
        self.article_id: int | None = None
        self.null_step_exec_id: int | None = None
        self.empty_step_exec_id: int | None = None
        self.real_step_exec_id: int | None = None


def _seed(session, uid: str) -> _TestData:
    from src.database.models import AgenticWorkflowExecutionTable, ArticleTable, SourceTable

    td = _TestData()

    source = SourceTable(
        identifier=f"test-unset-step-{uid}",
        name="Unset-Step Test Source",
        url=f"https://test.invalid/unset-step-{uid}",
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
        canonical_url=f"https://test.invalid/unset-step-article-{uid}",
        title=f"Unset-Step Test Article {uid}",
        published_at=datetime.now(UTC),
        content="Test content for unset-step-filter regression.",
        content_hash=f"unset-step-hash-{uid}",
        article_metadata={},
        word_count=6,
    )
    session.add(article)
    session.flush()
    td.article_id = article.id

    null_exec = AgenticWorkflowExecutionTable(article_id=article.id, status="failed", current_step=None)
    session.add(null_exec)
    session.flush()
    td.null_step_exec_id = null_exec.id

    empty_exec = AgenticWorkflowExecutionTable(article_id=article.id, status="failed", current_step="")
    session.add(empty_exec)
    session.flush()
    td.empty_step_exec_id = empty_exec.id

    real_exec = AgenticWorkflowExecutionTable(article_id=article.id, status="completed", current_step="extract_agent")
    session.add(real_exec)
    session.flush()
    td.real_step_exec_id = real_exec.id

    session.commit()
    return td


def _cleanup(session, td: _TestData):
    from src.database.models import AgenticWorkflowExecutionTable, ArticleTable, SourceTable

    for exec_id in [td.null_step_exec_id, td.empty_step_exec_id, td.real_step_exec_id]:
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


@pytest.mark.integration_full
class TestUnsetStepFilter:
    """Verify step=__unset__ matches NULL/'' current_step rows and only those."""

    def _get_db(self):
        from src.database.manager import DatabaseManager

        return DatabaseManager(database_url=_sync_test_db_url())

    def setup_method(self):
        _skip_if_no_test_db()

    @pytest.mark.asyncio
    async def test_unset_sentinel_matches_null_and_empty_but_not_real_steps(self):
        uid = uuid.uuid4().hex[:8]
        db = self._get_db()
        session = db.get_session()
        td = _seed(session, uid)

        try:
            from src.web.routes.workflow_executions import UNSET_STEP_FILTER_VALUE, list_workflow_executions

            with patch("src.web.routes.workflow_executions.get_db_manager", return_value=db):
                result = list_workflow_executions(
                    request=MagicMock(spec=Request),
                    step=UNSET_STEP_FILTER_VALUE,
                    article_id=td.article_id,
                    page=1,
                    limit=200,
                )

            returned_ids = {e.id for e in result.executions}
            assert td.null_step_exec_id in returned_ids
            assert td.empty_step_exec_id in returned_ids
            assert td.real_step_exec_id not in returned_ids
        finally:
            _cleanup(session, td)

    @pytest.mark.asyncio
    async def test_real_step_filter_still_excludes_unset_rows(self):
        """A concrete step value must not accidentally match NULL/'' rows."""
        uid = uuid.uuid4().hex[:8]
        db = self._get_db()
        session = db.get_session()
        td = _seed(session, uid)

        try:
            from src.web.routes.workflow_executions import list_workflow_executions

            with patch("src.web.routes.workflow_executions.get_db_manager", return_value=db):
                result = list_workflow_executions(
                    request=MagicMock(spec=Request),
                    step="extract_agent",
                    article_id=td.article_id,
                    page=1,
                    limit=200,
                )

            returned_ids = {e.id for e in result.executions}
            assert td.real_step_exec_id in returned_ids
            assert td.null_step_exec_id not in returned_ids
            assert td.empty_step_exec_id not in returned_ids
        finally:
            _cleanup(session, td)
