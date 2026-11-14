"""Two workflow configs may run concurrently on the same article.

Before this, ``WorkflowTriggerService._workflow_eligibility`` blocked a new trigger
whenever *any* execution was pending/running for the article, regardless of which
config either run used -- so testing a new config against an article meant waiting
out or cancelling whatever config happened to be running already. The guard is now
keyed on config identity (``find_active_execution_for_config``, matched against the
dispatched execution's resolved ``config_id``/``config_version``): a different config
may proceed, a duplicate trigger on the *same* config is still blocked.
``run_workflow()`` no longer attaches to an existing run by article when called without an
``execution_id``, and an explicit id that names no row is an error, so a dispatch can only
ever run the execution it was handed.

These tests exercise that against the real test database; Celery dispatch is mocked
(no worker involved) and the LangGraph graph is replaced by a recording stub.
"""

import asyncio
import uuid
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import func

from src.database.manager import DatabaseManager
from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SourceTable,
)
from src.services.execution_snapshot_store import hydrate_snapshot
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.workflows.agentic_workflow import run_workflow

pytestmark = [pytest.mark.integration, pytest.mark.integration_full]


def _sync_test_db_url() -> str:
    import os

    password = os.getenv("POSTGRES_PASSWORD", "cti_password")
    default_url = f"postgresql+asyncpg://cti_user:{password}@localhost:5433/cti_scraper_test"
    url = os.getenv("TEST_DATABASE_URL", default_url)
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    return url


def _activate_new_config(session) -> tuple[int, int]:
    """Deactivate every currently-active config and activate a fresh version.

    Returns (config_id, config_version) as plain values -- callers hold onto these
    across commits elsewhere in the test rather than the ORM object, which a later
    ``session.expire_all()`` (inside ``_pending_executions``) would otherwise force
    to reload lazily and can surface as a stale/detached read.

    Mirrors the pattern in ``test_lmstudio_e2e.py``: ``is_active`` is a single
    global flag on this table, so a test that wants to switch "the" active config
    must explicitly deactivate whatever else is active first, and pick a version
    higher than anything already in the (shared) test database.
    """
    session.query(AgenticWorkflowConfigTable).filter(
        AgenticWorkflowConfigTable.is_active == True  # noqa: E712
    ).update({"is_active": False})
    session.commit()

    max_version = session.query(func.max(AgenticWorkflowConfigTable.version)).scalar() or 0
    config = AgenticWorkflowConfigTable(
        min_hunt_score=97.0,
        ranking_threshold=6.0,
        similarity_threshold=0.5,
        junk_filter_threshold=0.8,
        version=max_version + 1,
        is_active=True,
        description="Concurrent-runs test config",
        agent_prompts={},
        # Off so a dispatched run never reaches the model context probe (no LLM
        # provider is configured in this test environment) -- matches
        # ``test_execution_claim.py``'s ``_create_pending_execution``.
        rank_agent_enabled=False,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config.id, config.version


def _create_article(session) -> int:
    uid = uuid.uuid4().hex[:8]
    source = SourceTable(
        identifier=f"test-concurrent-runs-source-{uid}",
        name="Concurrent runs source",
        url="https://example.com",
        rss_url="https://example.com/feed.xml",
        check_frequency=3600,
        lookback_days=180,
        active=True,
    )
    session.add(source)
    session.commit()
    session.refresh(source)

    article = ArticleTable(
        source_id=source.id,
        canonical_url=f"https://example.com/concurrent-runs-{uid}",
        title="Concurrent runs article",
        published_at=datetime.now(),
        content="Windows PowerShell and registry content for detection.",
        content_hash=f"concurrent-runs-hash-{uid}",
        article_metadata={},
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return article.id


def _pending_executions(session, article_id: int) -> list[AgenticWorkflowExecutionTable]:
    session.expire_all()
    return (
        session.query(AgenticWorkflowExecutionTable)
        .filter(
            AgenticWorkflowExecutionTable.article_id == article_id,
            AgenticWorkflowExecutionTable.status == "pending",
        )
        .order_by(AgenticWorkflowExecutionTable.created_at.asc())
        .all()
    )


def _config_identity(execution: AgenticWorkflowExecutionTable) -> tuple[int | None, int | None]:
    snapshot = hydrate_snapshot(execution)
    return snapshot.get("config_id"), snapshot.get("config_version")


def test_second_config_triggers_while_first_is_still_pending():
    """A different config may start even while the article has a pending run."""
    db = DatabaseManager(database_url=_sync_test_db_url())
    session = db.get_session()
    try:
        article_id = _create_article(session)
        config_a_id, config_a_version = _activate_new_config(session)

        with patch("src.worker.celery_app.trigger_agentic_workflow") as dispatched:
            triggered_a, reason_a = WorkflowTriggerService(session).trigger_workflow(article_id, force=True)
        assert triggered_a is True, reason_a
        dispatched.delay.assert_called_once()

        config_b_id, config_b_version = _activate_new_config(session)
        assert config_b_id != config_a_id

        with patch("src.worker.celery_app.trigger_agentic_workflow") as dispatched_b:
            triggered_b, reason_b = WorkflowTriggerService(session).trigger_workflow(article_id, force=True)
        assert triggered_b is True, reason_b
        dispatched_b.delay.assert_called_once()

        rows = _pending_executions(session, article_id)
        assert len(rows) == 2, [r.id for r in rows]
        assert _config_identity(rows[0]) == (config_a_id, config_a_version)
        assert _config_identity(rows[1]) == (config_b_id, config_b_version)
    finally:
        session.close()


def test_duplicate_trigger_on_the_same_config_is_still_blocked():
    """The guard still refuses a second trigger for the config already running."""
    db = DatabaseManager(database_url=_sync_test_db_url())
    session = db.get_session()
    try:
        article_id = _create_article(session)
        _activate_new_config(session)

        with patch("src.worker.celery_app.trigger_agentic_workflow") as dispatched:
            triggered_1, reason_1 = WorkflowTriggerService(session).trigger_workflow(article_id, force=True)
        assert triggered_1 is True, reason_1
        dispatched.delay.assert_called_once()

        with patch("src.worker.celery_app.trigger_agentic_workflow") as dispatched_dup:
            triggered_2, reason_2 = WorkflowTriggerService(session).trigger_workflow(article_id, force=True)
        assert triggered_2 is False
        assert "already has an active workflow execution" in (reason_2 or "")
        dispatched_dup.delay.assert_not_called()

        rows = _pending_executions(session, article_id)
        assert len(rows) == 1, [r.id for r in rows]
    finally:
        session.close()


class _RecordingGraph:
    """Stands in for the compiled LangGraph: records which execution it ran."""

    def __init__(self):
        self.calls: list[int] = []

    async def ainvoke(self, state):
        self.calls.append(int(state["execution_id"]))
        return {
            **state,
            "current_step": "generate_sigma",
            "status": "running",
            "error": None,
            "sigma_rules": [],
            "queued_rules": [],
        }


@contextmanager
def _noop_trace(*_args, **_kwargs):
    yield None


@contextmanager
def _graph_stub(graph: _RecordingGraph):
    with (
        patch("src.workflows.agentic_workflow.create_agentic_workflow", lambda _db: graph),
        patch("src.workflows.agentic_workflow.trace_workflow_execution", _noop_trace),
    ):
        yield


def _two_pending_runs(session) -> tuple[int, int, int]:
    """One article with a pending run for each of two configs; returns (article, old, new)."""
    article_id = _create_article(session)
    config_old_id, _ = _activate_new_config(session)
    with patch("src.worker.celery_app.trigger_agentic_workflow"):
        WorkflowTriggerService(session).trigger_workflow(article_id, force=True)
    config_new_id, _ = _activate_new_config(session)
    with patch("src.worker.celery_app.trigger_agentic_workflow"):
        WorkflowTriggerService(session).trigger_workflow(article_id, force=True)
    rows = _pending_executions(session, article_id)
    assert len(rows) == 2
    old_id = next(r.id for r in rows if _config_identity(r)[0] == config_old_id)
    new_id = next(r.id for r in rows if _config_identity(r)[0] == config_new_id)
    return article_id, old_id, new_id


def test_explicit_execution_ids_each_update_their_own_record():
    """With two runs in flight, each dispatch touches only the row it was given."""
    db = DatabaseManager(database_url=_sync_test_db_url())
    session = db.get_session()
    graph = _RecordingGraph()
    try:
        article_id, old_id, new_id = _two_pending_runs(session)

        with _graph_stub(graph):
            first = asyncio.run(run_workflow(article_id, session, execution_id=old_id))
            session.expire_all()
            new_row = session.get(AgenticWorkflowExecutionTable, new_id)
            assert new_row.status == "pending", "running the older config must not touch the other run"
            second = asyncio.run(run_workflow(article_id, session, execution_id=new_id))

        assert graph.calls == [old_id, new_id]
        assert first.get("execution_id") == old_id
        assert second.get("execution_id") == new_id
    finally:
        session.close()


def test_bare_dispatch_never_attaches_to_an_existing_run():
    """A dispatch without an execution_id must not pick one of the in-flight runs.

    Both rows belong to configs that are (or were) in flight on the article, so the
    fallback has no way to know which was meant. It creates nothing (the active config
    already has a run, so eligibility refuses) and leaves both rows alone.
    """
    db = DatabaseManager(database_url=_sync_test_db_url())
    session = db.get_session()
    graph = _RecordingGraph()
    try:
        article_id, old_id, new_id = _two_pending_runs(session)

        with _graph_stub(graph):
            result = asyncio.run(run_workflow(article_id, session, execution_id=None))

        assert graph.calls == []
        assert result.get("skipped") is True
        rows = _pending_executions(session, article_id)
        assert sorted(r.id for r in rows) == sorted([old_id, new_id])
    finally:
        session.close()


def test_unknown_execution_id_is_an_error_not_a_substitute_run():
    """An explicit id that names no row must fail rather than run some other execution."""
    db = DatabaseManager(database_url=_sync_test_db_url())
    session = db.get_session()
    graph = _RecordingGraph()
    try:
        article_id, _old_id, _new_id = _two_pending_runs(session)
        missing_id = (session.query(func.max(AgenticWorkflowExecutionTable.id)).scalar() or 0) + 1000

        with _graph_stub(graph), pytest.raises(ValueError, match="not found"):
            asyncio.run(run_workflow(article_id, session, execution_id=missing_id))

        assert graph.calls == []
        assert len(_pending_executions(session, article_id)) == 2
    finally:
        session.close()
