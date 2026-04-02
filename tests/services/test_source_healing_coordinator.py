"""Tests for source_healing_coordinator.scan_and_trigger_healing() — grace period logic."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_source_row(
    *,
    source_id: int = 1,
    name: str = "Failing Source",
    consecutive_failures: int = 200,
    active: bool = True,
    healing_exhausted: bool = False,
    last_success: datetime | None = None,
):
    """Build a mock SourceTable row."""
    row = MagicMock()
    row.id = source_id
    row.name = name
    row.consecutive_failures = consecutive_failures
    row.active = active
    row.healing_exhausted = healing_exhausted
    row.last_success = last_success
    return row


@pytest.fixture
def _mock_config():
    """Patch SourceHealingConfig.load() to return an enabled config."""
    with patch("src.services.source_healing_coordinator.SourceHealingConfig") as cls:
        cfg = MagicMock()
        cfg.enabled = True
        cfg.threshold = 100
        cls.load.return_value = cfg
        yield cfg


@pytest.fixture
def _mock_db():
    """Patch AsyncDatabaseManager to return a controllable session."""
    with patch("src.services.source_healing_coordinator.AsyncDatabaseManager") as cls:
        db = MagicMock()
        session = AsyncMock()
        db.get_session.return_value.__aenter__ = AsyncMock(return_value=session)
        db.get_session.return_value.__aexit__ = AsyncMock(return_value=False)
        cls.return_value = db
        yield session


@pytest.fixture
def _mock_heal_task():
    """Patch the heal_source Celery task (imported lazily inside the function)."""
    with patch("src.worker.celery_app.heal_source") as task:
        task.delay = MagicMock()
        yield task


class TestGracePeriodFiltering:
    """Verify that sources with a recent last_success are skipped."""

    @pytest.mark.asyncio
    async def test_source_within_grace_period_is_skipped(self, _mock_config, _mock_db, _mock_heal_task):
        """A source that succeeded 2 hours ago should NOT be dispatched for healing."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        source = _make_source_row(last_success=datetime.now() - timedelta(hours=2))

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [source]
        _mock_db.execute.return_value = result_mock

        await scan_and_trigger_healing()

        _mock_heal_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_source_outside_grace_period_is_dispatched(self, _mock_config, _mock_db, _mock_heal_task):
        """A source that succeeded 48 hours ago should be dispatched."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        source = _make_source_row(last_success=datetime.now() - timedelta(hours=48))

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [source]
        _mock_db.execute.return_value = result_mock

        await scan_and_trigger_healing()

        _mock_heal_task.delay.assert_called_once_with(source.id)

    @pytest.mark.asyncio
    async def test_source_with_no_last_success_is_dispatched(self, _mock_config, _mock_db, _mock_heal_task):
        """A source that has never succeeded (last_success=None) should be dispatched."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        source = _make_source_row(last_success=None)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [source]
        _mock_db.execute.return_value = result_mock

        await scan_and_trigger_healing()

        _mock_heal_task.delay.assert_called_once_with(source.id)

    @pytest.mark.asyncio
    async def test_mixed_sources_filters_correctly(self, _mock_config, _mock_db, _mock_heal_task):
        """Only sources outside the grace period or with no last_success are dispatched."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        recent = _make_source_row(source_id=1, name="Recent OK", last_success=datetime.now() - timedelta(hours=1))
        stale = _make_source_row(source_id=2, name="Stale", last_success=datetime.now() - timedelta(hours=48))
        never = _make_source_row(source_id=3, name="Never OK", last_success=None)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [recent, stale, never]
        _mock_db.execute.return_value = result_mock

        await scan_and_trigger_healing()

        dispatched_ids = [call.args[0] for call in _mock_heal_task.delay.call_args_list]
        assert 1 not in dispatched_ids  # recent — skipped
        assert 2 in dispatched_ids  # stale — dispatched
        assert 3 in dispatched_ids  # never — dispatched

    @pytest.mark.asyncio
    async def test_source_exactly_at_grace_period_boundary_is_dispatched(self, _mock_config, _mock_db, _mock_heal_task):
        """A source exactly 24 hours stale should be dispatched because only newer successes are skipped."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        source = _make_source_row(last_success=datetime.now() - timedelta(hours=24))

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [source]
        _mock_db.execute.return_value = result_mock

        await scan_and_trigger_healing()

        _mock_heal_task.delay.assert_called_once_with(source.id)


class TestDisabledHealing:
    @pytest.mark.asyncio
    async def test_disabled_config_returns_early(self, _mock_db, _mock_heal_task):
        """When healing is disabled, no DB query or dispatch occurs."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        with patch("src.services.source_healing_coordinator.SourceHealingConfig") as cls:
            cfg = MagicMock()
            cfg.enabled = False
            cls.load.return_value = cfg

            await scan_and_trigger_healing()

        _mock_db.execute.assert_not_called()
        _mock_heal_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sources_above_threshold(self, _mock_config, _mock_db, _mock_heal_task):
        """When the query returns no sources, nothing is dispatched."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        _mock_db.execute.return_value = result_mock

        await scan_and_trigger_healing()

        _mock_heal_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_failure_returns_without_dispatch(self, _mock_config, _mock_db, _mock_heal_task):
        """Database query failures should be swallowed so the scheduler loop stays alive."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        _mock_db.execute.side_effect = RuntimeError("db unavailable")

        await scan_and_trigger_healing()

        _mock_heal_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_failure_on_one_source_does_not_block_remaining_sources(
        self, _mock_config, _mock_db, _mock_heal_task
    ):
        """A failed queue dispatch should not prevent later sources from being scheduled."""
        from src.services.source_healing_coordinator import scan_and_trigger_healing

        first = _make_source_row(source_id=1, name="First", last_success=None)
        second = _make_source_row(source_id=2, name="Second", last_success=None)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [first, second]
        _mock_db.execute.return_value = result_mock
        _mock_heal_task.delay.side_effect = [RuntimeError("queue down"), None]

        await scan_and_trigger_healing()

        assert _mock_heal_task.delay.call_count == 2
        dispatched_ids = [call.args[0] for call in _mock_heal_task.delay.call_args_list]
        assert dispatched_ids == [1, 2]
