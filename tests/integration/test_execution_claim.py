"""``run_workflow`` claims its execution row atomically.

Measured 2026-09-04 on the dev worker: two Celery tasks carrying the same
``execution_id`` both loaded the row (one saw ``pending``, the next saw
``running``), both ran the graph to completion and both wrote results into the
same row. With worker concurrency 2 x 2, up to four tasks can collide, and on a
non-junk article that is double provider spend plus interleaved writes.

The fix is a conditional ``UPDATE ... WHERE status = 'pending'`` with a rowcount
check in ``run_workflow``: exactly one caller moves the row to ``running``; every
other caller sees zero rows affected, logs a skip and returns without invoking
the graph. These tests exercise that against the real test database with the
LangGraph pipeline replaced by a recording stub, so no LLM provider is touched.
"""

import asyncio
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import pytest

from src.database.manager import DatabaseManager
from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SourceTable,
)
from src.services.execution_snapshot_store import attach_snapshot
from src.services.workflow_config_snapshot import build_config_snapshot
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


class _RecordingGraph:
    """Stands in for the compiled LangGraph: records which executions it ran."""

    def __init__(self, hold_seconds: float = 0.0):
        self.calls: list[int] = []
        self._lock = threading.Lock()
        self._hold_seconds = hold_seconds

    async def ainvoke(self, state):
        with self._lock:
            self.calls.append(int(state["execution_id"]))
        if self._hold_seconds:
            await asyncio.sleep(self._hold_seconds)
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
    """Route run_workflow's graph construction and tracing to inert stand-ins."""
    with (
        patch("src.workflows.agentic_workflow.create_agentic_workflow", lambda _db: graph),
        patch("src.workflows.agentic_workflow.trace_workflow_execution", _noop_trace),
    ):
        yield


def _ensure_active_config(session) -> AgenticWorkflowConfigTable:
    config = (
        session.query(AgenticWorkflowConfigTable)
        .filter(AgenticWorkflowConfigTable.is_active == True)  # noqa: E712
        .order_by(AgenticWorkflowConfigTable.version.desc())
        .first()
    )
    if config is None:
        config = AgenticWorkflowConfigTable(
            min_hunt_score=97.0,
            ranking_threshold=6.0,
            similarity_threshold=0.5,
            junk_filter_threshold=0.8,
            version=1,
            is_active=True,
            description="Test default",
            agent_prompts={},
        )
        session.add(config)
        session.commit()
        session.refresh(config)
    return config


def _create_pending_execution(session) -> tuple[int, int]:
    """One article with one pending execution carrying a complete snapshot."""
    config = _ensure_active_config(session)
    uid = uuid.uuid4().hex[:8]
    source = SourceTable(
        identifier=f"test-execution-claim-source-{uid}",
        name="Execution claim source",
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
        canonical_url=f"https://example.com/execution-claim-{uid}",
        title="Execution claim article",
        published_at=datetime.now(),
        content="Windows PowerShell and registry content for detection.",
        content_hash=f"execution-claim-hash-{uid}",
        article_metadata={},
    )
    session.add(article)
    session.commit()
    session.refresh(article)

    execution = AgenticWorkflowExecutionTable(article_id=article.id, status="pending")
    session.add(execution)
    # Rank agent off so run_workflow never reaches the model context probe; the graph
    # itself is stubbed, so no other node runs.
    attach_snapshot(
        session,
        execution,
        build_config_snapshot(
            config,
            extra={"skip_rank_agent": True, "rank_agent_enabled": False, "agent_models": {}},
        ),
    )
    session.commit()
    session.refresh(execution)
    return article.id, execution.id


def _load(session, execution_id: int) -> AgenticWorkflowExecutionTable:
    session.expire_all()
    row = session.query(AgenticWorkflowExecutionTable).filter(AgenticWorkflowExecutionTable.id == execution_id).first()
    assert row is not None
    return row


def test_single_dispatch_moves_pending_to_running_to_terminal():
    """The normal path is unaffected: one task claims the row and runs it to completion."""
    db = DatabaseManager(database_url=_sync_test_db_url())
    session = db.get_session()
    graph = _RecordingGraph()
    try:
        article_id, execution_id = _create_pending_execution(session)

        with _graph_stub(graph):
            result = asyncio.run(run_workflow(article_id, session, execution_id=execution_id))

        assert graph.calls == [execution_id]
        assert result.get("skipped") is not True
        assert result["execution_id"] == execution_id

        row = _load(session, execution_id)
        assert row.status == "completed", row.status
        assert row.started_at is not None, "the claim must stamp started_at"
        assert row.completed_at is not None
    finally:
        session.close()


def test_already_claimed_row_is_skipped_without_invoking_the_graph():
    """A row another worker already holds is left alone: no graph run, no writes."""
    db = DatabaseManager(database_url=_sync_test_db_url())
    session = db.get_session()
    graph = _RecordingGraph()
    try:
        article_id, execution_id = _create_pending_execution(session)
        claimed_at = datetime.now()
        row = _load(session, execution_id)
        row.status = "running"
        row.started_at = claimed_at
        row.current_step = "extract_huntables"
        session.commit()

        with _graph_stub(graph):
            result = asyncio.run(run_workflow(article_id, session, execution_id=execution_id))

        assert graph.calls == [], "the loser must never invoke the graph"
        assert result["skipped"] is True
        assert result["success"] is False
        assert result["execution_id"] == execution_id
        assert "already claimed" in result["reason"]

        row = _load(session, execution_id)
        assert row.status == "running", "the loser must not touch the owner's row"
        assert row.current_step == "extract_huntables"
        assert row.started_at == claimed_at
    finally:
        session.close()


def test_two_dispatches_for_one_execution_run_it_exactly_once():
    """The measured collision: two workers, one execution_id, both start together.

    Each thread owns its own session, as two Celery fork-pool children would. The
    barrier releases both into ``run_workflow`` at once; the database decides the
    winner, so the outcome does not depend on scheduling luck.
    """
    db = DatabaseManager(database_url=_sync_test_db_url())
    setup_session = db.get_session()
    graph = _RecordingGraph(hold_seconds=0.5)
    try:
        article_id, execution_id = _create_pending_execution(setup_session)
    finally:
        setup_session.close()

    barrier = threading.Barrier(2)
    results: dict[str, dict] = {}
    errors: dict[str, BaseException] = {}

    def _worker(name: str) -> None:
        session = db.get_session()
        try:
            barrier.wait(timeout=10)
            results[name] = asyncio.run(run_workflow(article_id, session, execution_id=execution_id))
        except BaseException as exc:  # noqa: BLE001 -- surfaced by the assertion below
            errors[name] = exc
        finally:
            session.close()

    with _graph_stub(graph):
        threads = [threading.Thread(target=_worker, args=(name,), name=name) for name in ("worker-a", "worker-b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

    assert not errors, errors
    assert graph.calls == [execution_id], f"exactly one run expected, graph saw {graph.calls}"

    skipped = [name for name, result in results.items() if result.get("skipped") is True]
    ran = [name for name, result in results.items() if result.get("skipped") is not True]
    assert len(skipped) == 1 and len(ran) == 1, results
    assert results[skipped[0]]["execution_id"] == execution_id
    assert results[ran[0]]["execution_id"] == execution_id

    check_session = db.get_session()
    try:
        row = _load(check_session, execution_id)
        assert row.status == "completed", row.status
        assert row.started_at is not None
    finally:
        check_session.close()
