"""Regression: Source.should_check() must exist and gate scheduling.

Root cause being fixed: the ``should_check()`` method was dropped from the
``Source`` model during a history re-import, but two live callers survived --
``SourceManager.get_sources_due_for_check`` (src/core/source_manager.py) and the
``collect`` CLI command (src/cli/commands/collect.py). Every non-force run
through either path raised ``AttributeError: 'Source' object has no attribute
'should_check'``. These tests lock the method back onto the model and pin the
active/last_check/check_frequency semantics the callers depend on.
"""

from datetime import datetime, timedelta

import pytest

from src.models.source import Source

pytestmark = pytest.mark.unit


def _source(*, active=True, last_check=None, check_frequency=3600) -> Source:
    """Build a fully-populated Source with schedule-relevant fields overridable."""
    now = datetime.now()
    return Source(
        id=1,
        identifier="feed-a",
        name="Feed A",
        url="https://feed-a.example",
        rss_url=None,
        check_frequency=check_frequency,
        lookback_days=180,
        active=active,
        config={},
        last_check=last_check,
        last_success=None,
        consecutive_failures=0,
        total_articles=0,
        average_response_time=0.0,
        created_at=now,
        updated_at=now,
    )


def test_inactive_source_is_never_due():
    # An inactive source must never be collected, even if never checked.
    assert _source(active=False, last_check=None).should_check() is False


def test_never_checked_active_source_is_due():
    # last_check is None -> the source has never run and is due immediately.
    assert _source(active=True, last_check=None).should_check() is True


def test_recently_checked_source_is_not_due():
    # Checked 10s ago with a 1h frequency -> not yet due.
    recent = datetime.now() - timedelta(seconds=10)
    assert _source(active=True, last_check=recent, check_frequency=3600).should_check() is False


def test_stale_source_is_due():
    # Checked 2h ago with a 1h frequency -> overdue.
    stale = datetime.now() - timedelta(hours=2)
    assert _source(active=True, last_check=stale, check_frequency=3600).should_check() is True


def test_boundary_at_exactly_check_frequency_is_due():
    # time_since_check >= check_frequency is due (inclusive boundary).
    boundary = datetime.now() - timedelta(seconds=3600)
    assert _source(active=True, last_check=boundary, check_frequency=3600).should_check() is True


def test_caller_comprehension_does_not_raise():
    """Guards the exact filter both live callers use against AttributeError."""
    sources = [
        _source(active=True, last_check=None),  # due
        _source(active=False, last_check=None),  # inactive
        _source(active=True, last_check=datetime.now(), check_frequency=3600),  # not due
    ]
    due = [s for s in sources if s.should_check()]
    assert len(due) == 1
