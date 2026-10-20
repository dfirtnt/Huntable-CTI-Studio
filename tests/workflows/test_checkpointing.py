"""Unit tests for LangGraph checkpoint wiring.

Covers the pure helpers (thread id, DSN normalisation, the opt-in flag) and the
degradation contract: a missing package, a missing DSN or a switched-off flag
must all yield ``None`` so the workflow still runs.
"""

import pytest

from src.workflows import checkpointing
from src.workflows.checkpointing import (
    checkpoint_thread_id,
    checkpointing_enabled,
    open_checkpointer,
    psycopg_dsn,
)

pytestmark = pytest.mark.unit


class TestThreadId:
    def test_thread_id_is_stable_per_execution(self):
        assert checkpoint_thread_id(42) == checkpoint_thread_id(42)

    def test_thread_id_differs_between_executions(self):
        assert checkpoint_thread_id(1) != checkpoint_thread_id(2)

    def test_thread_id_prefix_matches_langfuse_session_convention(self):
        assert checkpoint_thread_id(7) == "workflow_exec_7"


class TestPsycopgDsn:
    def test_strips_asyncpg_dialect_prefix(self):
        dsn = psycopg_dsn("postgresql+asyncpg://u:p@localhost:5433/cti_scraper")
        assert dsn == "postgresql://u:p@localhost:5433/cti_scraper"

    def test_strips_psycopg2_dialect_prefix(self):
        dsn = psycopg_dsn("postgresql+psycopg2://u:p@db:5432/cti")
        assert dsn == "postgresql://u:p@db:5432/cti"

    def test_accepts_plain_dsn_unchanged(self):
        assert psycopg_dsn("postgresql://u:p@db:5432/cti") == "postgresql://u:p@db:5432/cti"

    def test_rewrites_legacy_postgres_scheme(self):
        assert psycopg_dsn("postgres://u:p@db:5432/cti") == "postgresql://u:p@db:5432/cti"

    def test_missing_url_returns_none(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert psycopg_dsn() is None

    def test_empty_url_returns_none(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "   ")
        assert psycopg_dsn() is None

    def test_uses_environment_when_no_argument(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5433/d")
        assert psycopg_dsn() == "postgresql://u:p@h:5433/d"


class TestEnabledFlag:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", "enabled", " true "])
    def test_truthy_values_enable(self, monkeypatch, value):
        monkeypatch.setenv("LANGGRAPH_CHECKPOINT_ENABLED", value)
        assert checkpointing_enabled() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "random"])
    def test_other_values_disable(self, monkeypatch, value):
        monkeypatch.setenv("LANGGRAPH_CHECKPOINT_ENABLED", value)
        assert checkpointing_enabled() is False

    def test_default_is_disabled(self, monkeypatch):
        monkeypatch.delenv("LANGGRAPH_CHECKPOINT_ENABLED", raising=False)
        assert checkpointing_enabled() is False


class TestOpenCheckpointerDegradation:
    """Checkpointing must never be able to stop the pipeline."""

    async def test_disabled_yields_none(self, monkeypatch):
        monkeypatch.delenv("LANGGRAPH_CHECKPOINT_ENABLED", raising=False)
        async with open_checkpointer() as saver:
            assert saver is None

    async def test_enabled_without_dsn_yields_none(self, monkeypatch):
        monkeypatch.setenv("LANGGRAPH_CHECKPOINT_ENABLED", "1")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        async with open_checkpointer() as saver:
            assert saver is None

    async def test_missing_package_yields_none(self, monkeypatch):
        monkeypatch.setenv("LANGGRAPH_CHECKPOINT_ENABLED", "1")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")

        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("langgraph.checkpoint.postgres"):
                raise ImportError("simulated missing package")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        async with open_checkpointer() as saver:
            assert saver is None

    async def test_unreachable_database_yields_none(self, monkeypatch):
        pytest.importorskip("langgraph.checkpoint.postgres.aio")
        monkeypatch.setenv("LANGGRAPH_CHECKPOINT_ENABLED", "1")
        # Port 1 is reserved and nothing listens there.
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/nope")
        async with open_checkpointer() as saver:
            assert saver is None


class TestCompileWiring:
    """create_agentic_workflow must forward the checkpointer to compile()."""

    def test_checkpointer_is_forwarded(self, monkeypatch):
        from unittest.mock import Mock, patch

        from src.workflows.agentic_workflow import create_agentic_workflow

        sentinel = object()
        fake_graph = Mock()
        fake_graph.compile = Mock(return_value="compiled")

        with (
            patch("src.workflows.agentic_workflow.StateGraph", return_value=fake_graph),
            patch("src.workflows.agentic_workflow.ContentFilter"),
            patch("src.workflows.agentic_workflow.WorkflowTriggerService"),
        ):
            result = create_agentic_workflow(Mock(), checkpointer=sentinel)

        assert result == "compiled"
        fake_graph.compile.assert_called_once_with(checkpointer=sentinel)

    def test_compile_without_checkpointer_uses_no_kwargs(self):
        from unittest.mock import Mock, patch

        from src.workflows.agentic_workflow import create_agentic_workflow

        fake_graph = Mock()
        fake_graph.compile = Mock(return_value="compiled")

        with (
            patch("src.workflows.agentic_workflow.StateGraph", return_value=fake_graph),
            patch("src.workflows.agentic_workflow.ContentFilter"),
            patch("src.workflows.agentic_workflow.WorkflowTriggerService"),
        ):
            create_agentic_workflow(Mock())

        fake_graph.compile.assert_called_once_with()
