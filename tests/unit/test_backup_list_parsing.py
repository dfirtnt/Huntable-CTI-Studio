"""Regression tests for /api/backup parsing of prune_backups.py --stats output.

Both /api/backup/list and /api/backup/status screen-scrape the script's stdout;
commit 387b7907 rewrote the script with a lowercase "Recent backups:" heading,
which the old case-sensitive parsers never matched — the settings UI showed
"No backups found." (list) and a null last-backup date (status) despite backups
on disk. Both endpoints now share _parse_backup_list().
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.web.routes import backup as backup_module
from src.web.routes.backup import _backup_freshness, _parse_backup_list

pytestmark = pytest.mark.unit

# Verbatim excerpt of `prune_backups.py --stats` output (2026-07-06 rewrite).
STATS_OUTPUT = """Backup Statistics
================================================================================
Total backups: 6
Total size: 1617.03 MB (1.58 GB)
Age distribution:
   Daily (< 7 days): 3
   Weekly (7-30 days): 3
   Monthly (> 30 days): 0
Recent backups:
 1. system_backup_20260706_130821
    Created: 2026-07-06 13:08:21 (0 days ago)
    Size: 398.35 MB
    Components: 5
 2. system_backup_20260706_020002
    Created: 2026-07-06 02:00:02 (0 days ago)
    Size: 384.91 MB
    Components: 7
 3. system_backup_20260705_020004
    Created: 2026-07-05 02:00:04 (1 days ago)
    Size: 382.45 MB
    Components: 7
"""


def test_parses_lowercase_recent_backups_heading():
    backups = _parse_backup_list(STATS_OUTPUT.split("\n"))
    assert [b["name"] for b in backups] == [
        "system_backup_20260706_130821",
        "system_backup_20260706_020002",
        "system_backup_20260705_020004",
    ]


def test_parses_sizes_from_lookahead_lines():
    backups = _parse_backup_list(STATS_OUTPUT.split("\n"))
    assert backups[0]["size_mb"] == pytest.approx(398.35)
    assert backups[1]["size_mb"] == pytest.approx(384.91)


def test_legacy_titlecase_heading_still_parses():
    legacy = STATS_OUTPUT.replace("Recent backups:", "Recent Backups")
    backups = _parse_backup_list(legacy.split("\n"))
    assert len(backups) == 3


def test_empty_output_returns_empty_list():
    assert _parse_backup_list([]) == []
    assert _parse_backup_list(["Total backups: 0"]) == []


def test_backup_freshness_marks_backup_stale_after_three_days():
    now = datetime(2026, 9, 3, 12, 0, 0)

    freshness = _backup_freshness("system_backup_20260830_115959", now=now)

    assert freshness == {
        "last_backup_at": "2026-08-30 11:59:59",
        "backup_age_days": pytest.approx(4.0),
        "backup_stale": True,
    }


def test_backup_freshness_does_not_warn_for_recent_backup():
    now = datetime(2026, 9, 3, 12, 0, 0)

    freshness = _backup_freshness("system_backup_20260902_115959", now=now)

    assert freshness["backup_age_days"] == pytest.approx(1.0)
    assert freshness["backup_stale"] is False


def test_status_endpoint_reports_last_backup_from_stats():
    """/api/backup/status must surface the newest backup, not null.

    Regression: the status endpoint had its own case-sensitive "Recent Backups"
    parser that never matched the rewritten script, leaving last_backup null even
    with backups on disk. It now delegates to _parse_backup_list().
    """
    stats_result = MagicMock(returncode=0, stdout=STATS_OUTPUT)
    cron_state = {"automated": True, "cron_available": False, "managed_jobs": []}

    with (
        patch.object(backup_module.subprocess, "run", return_value=stats_result),
        patch.object(backup_module, "_get_cron_state", return_value=cron_state),
    ):
        result = asyncio.run(backup_module.api_backup_status())

    assert result["last_backup"] == "system_backup_20260706_130821"
    assert result["total_backups"] == 6
