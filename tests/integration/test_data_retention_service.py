"""End-to-end tests for age-based retention.

These run against a real database on purpose. The two rules that matter most --
"never purge an execution referenced by the Sigma queue" and "never purge an eval
run" -- depend on a cascading foreign key and on JSONB containment, neither of
which a mocked session or SQLite can reproduce. A test that fakes the session can
pass while the live purge silently cascades reviewable Sigma rules out of the queue.

Each test builds a scratch database from models.py, seeds a fixed set of rows with
explicit ages, and asserts on what survives.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.models import (  # noqa: E402
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionSnapshotTable,
    AgenticWorkflowExecutionTable,
    AppSettingsTable,
    ArticleTable,
    Base,
    SigmaEvaluationTable,
    SigmaRuleQueueTable,
    SourceCheckTable,
    SourceTable,
    SubagentEvaluationTable,
)
from src.services.data_retention_service import (  # noqa: E402
    DEFAULT_STALE_EXECUTION_HOURS,
    RETENTION_POLICY_MAP,
    STALE_EXECUTION_SETTING_KEY,
    purgeable_execution_ids,
    reap_stale_executions,
    resolve_retention_days,
    run_retention,
)
from tests.utils.test_database_url import build_test_database_url  # noqa: E402

pytestmark = pytest.mark.integration

# Worker-scoped so a parallel run cannot have two workers dropping and creating the
# same database underneath each other.
SCRATCH_DB = "cti_scratch_retention_test_" + os.getenv("PYTEST_XDIST_WORKER", "main")

# Only the tables retention touches, plus their FK parents. Creating the full
# metadata would drag in unrelated pgvector indexes for no benefit here.
_TABLES = (
    SourceTable,
    ArticleTable,
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionSnapshotTable,
    AgenticWorkflowExecutionTable,
    SigmaRuleQueueTable,
    SubagentEvaluationTable,
    SigmaEvaluationTable,
    SourceCheckTable,
    AppSettingsTable,
)

NOW = datetime(2026, 8, 6, 12, 0, 0)


def _sync_base_url() -> str:
    """Base URL using the sync driver.

    build_test_database_url returns TEST_DATABASE_URL verbatim when it is set,
    ignoring asyncpg=False -- and the test harness sets it to the +asyncpg form.
    These tests use the sync Session/engine API, so force the driver here.
    """
    url = build_test_database_url(asyncpg=False)
    return url.replace("+asyncpg", "")


def _admin_engine():
    return create_engine(_sync_base_url(), isolation_level="AUTOCOMMIT")


@pytest.fixture()
def session():
    admin = _admin_engine()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    admin.dispose()

    scratch_url = _sync_base_url().rsplit("/", 1)[0] + f"/{SCRATCH_DB}"
    engine = create_engine(scratch_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(engine, tables=[model.__table__ for model in _TABLES])

    maker = sessionmaker(bind=engine)
    db = maker()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        admin2 = _admin_engine()
        with admin2.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin2.dispose()


def _seed_article(session) -> int:
    source = SourceTable(identifier="src", name="Source", url="http://example.test")
    session.add(source)
    session.flush()
    article = ArticleTable(
        source_id=source.id,
        title="t",
        canonical_url="http://example.test/a",
        published_at=NOW,
        content="c",
        content_hash="h",
    )
    session.add(article)
    session.flush()
    return article.id


def _add_execution(session, article_id: int, *, age_days: float, status: str = "completed", snapshot=None):
    execution = AgenticWorkflowExecutionTable(
        article_id=article_id,
        status=status,
        config_snapshot=snapshot,
        created_at=NOW - timedelta(days=age_days),
        updated_at=NOW - timedelta(days=age_days),
    )
    session.add(execution)
    session.flush()
    return execution


class TestExecutionPurgeGuards:
    """The exclusions that keep an age purge from destroying irreplaceable rows."""

    def test_old_unreferenced_execution_is_purgeable(self, session):
        article_id = _seed_article(session)
        old = _add_execution(session, article_id, age_days=120)

        assert purgeable_execution_ids(session, NOW - timedelta(days=90)) == [old.id]

    def test_eval_run_is_never_purged(self, session):
        article_id = _seed_article(session)
        _add_execution(session, article_id, age_days=365, snapshot={"eval_run": True})

        assert purgeable_execution_ids(session, NOW - timedelta(days=90)) == []

    def test_queue_referenced_execution_is_never_purged(self, session):
        """The load-bearing guard: this FK is ON DELETE CASCADE."""
        article_id = _seed_article(session)
        execution = _add_execution(session, article_id, age_days=365)
        session.add(
            SigmaRuleQueueTable(
                article_id=article_id,
                workflow_execution_id=execution.id,
                rule_yaml="title: t",
            )
        )
        session.flush()

        assert purgeable_execution_ids(session, NOW - timedelta(days=90)) == []

        # And the purge run itself must leave the queue row intact.
        run_retention(session, now=NOW)
        assert session.query(SigmaRuleQueueTable).count() == 1
        assert session.query(AgenticWorkflowExecutionTable).count() == 1

    @pytest.mark.parametrize(
        "model,column",
        [
            (SubagentEvaluationTable, "article_url"),
            (SigmaEvaluationTable, "article_url"),
        ],
    )
    def test_evaluation_referenced_execution_is_never_purged(self, session, model, column):
        article_id = _seed_article(session)
        execution = _add_execution(session, article_id, age_days=365)
        kwargs = {"workflow_execution_id": execution.id, column: "x"}
        if model is SubagentEvaluationTable:
            kwargs.update({"subagent_name": "cmdline", "expected_count": 1})
        if model is SigmaEvaluationTable:
            kwargs.update({"expected_rule_count": 1})
        session.add(model(**kwargs))
        session.flush()

        assert purgeable_execution_ids(session, NOW - timedelta(days=90)) == []

    def test_running_execution_is_never_purged_by_age(self, session):
        article_id = _seed_article(session)
        _add_execution(session, article_id, age_days=365, status="running")

        assert purgeable_execution_ids(session, NOW - timedelta(days=90)) == []

    def test_recent_execution_is_retained(self, session):
        article_id = _seed_article(session)
        _add_execution(session, article_id, age_days=10)

        assert purgeable_execution_ids(session, NOW - timedelta(days=90)) == []


class TestStaleExecutionReaping:
    def test_inert_running_execution_is_failed(self, session):
        article_id = _seed_article(session)
        stuck = _add_execution(session, article_id, age_days=38, status="running")

        assert reap_stale_executions(session, now=NOW) == 1
        session.refresh(stuck)
        assert stuck.status == "failed"
        assert stuck.completed_at == NOW
        assert "no activity" in stuck.error_message

    def test_recently_active_run_is_left_alone(self, session):
        """Staleness is measured on updated_at, so a long run still making progress survives."""
        article_id = _seed_article(session)
        execution = _add_execution(session, article_id, age_days=30, status="running")
        execution.updated_at = NOW - timedelta(minutes=5)
        session.flush()

        assert reap_stale_executions(session, now=NOW) == 0
        session.refresh(execution)
        assert execution.status == "running"

    def test_dry_run_counts_without_mutating(self, session):
        article_id = _seed_article(session)
        stuck = _add_execution(session, article_id, age_days=38, status="running")

        assert reap_stale_executions(session, dry_run=True, now=NOW) == 1
        session.refresh(stuck)
        assert stuck.status == "running"


class TestRetentionWindows:
    def test_defaults_apply_when_unset(self, session):
        policy = RETENTION_POLICY_MAP["source_checks"]
        assert resolve_retention_days(session, policy) == policy.default_days

    def test_setting_overrides_default(self, session):
        policy = RETENTION_POLICY_MAP["source_checks"]
        session.add(AppSettingsTable(key=policy.setting_key, value="30", category="retention"))
        session.flush()

        assert resolve_retention_days(session, policy) == 30

    @pytest.mark.parametrize("bad_value", ["", "not-a-number", "0", "-5"])
    def test_malformed_window_falls_back_to_default(self, session, bad_value):
        """A typo in a settings row must never be read as 'delete everything'."""
        policy = RETENTION_POLICY_MAP["source_checks"]
        session.add(AppSettingsTable(key=policy.setting_key, value=bad_value, category="retention"))
        session.flush()

        assert resolve_retention_days(session, policy) == policy.default_days

    def test_stale_hours_setting_is_honored(self, session):
        article_id = _seed_article(session)
        _add_execution(session, article_id, age_days=0.1, status="running")
        session.add(AppSettingsTable(key=STALE_EXECUTION_SETTING_KEY, value="1", category="retention"))
        session.flush()

        assert DEFAULT_STALE_EXECUTION_HOURS > 1
        assert reap_stale_executions(session, now=NOW) == 1


class TestRunRetention:
    def test_purges_source_checks_by_age(self, session):
        source = SourceTable(identifier="s", name="S", url="http://s.test")
        session.add(source)
        session.flush()
        session.add_all(
            [
                SourceCheckTable(
                    source_id=source.id,
                    check_time=NOW - timedelta(days=age),
                    success=True,
                    method="rss",
                    articles_found=0,
                    check_metadata={},
                )
                for age in (400, 200, 10)
            ]
        )
        session.flush()

        result = run_retention(session, now=NOW)

        # source_checks keeps 90 days.
        # Ages 400 and 200 both exceed the 90-day window, so two checks are purged.
        assert result.deleted["source_checks"] == 2
        assert session.query(SourceCheckTable).count() == 1

    def test_dry_run_reports_counts_and_deletes_nothing(self, session):
        article_id = _seed_article(session)
        _add_execution(session, article_id, age_days=120)

        result = run_retention(session, dry_run=True, now=NOW)

        assert result.dry_run is True
        assert result.deleted["workflow_executions"] == 1
        assert session.query(AgenticWorkflowExecutionTable).count() == 1

    def test_result_reports_zero_rather_than_bare_success(self, session):
        """The defect this replaced returned success while deleting nothing."""
        result = run_retention(session, now=NOW)

        assert result.as_dict()["total_deleted"] == 0
        assert set(result.deleted) == set(RETENTION_POLICY_MAP)
