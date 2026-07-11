"""Regression tests for /api/backup/list parsing of prune_backups.py --stats output.

The endpoint screen-scrapes the script's stdout; commit 387b7907 rewrote the
script with a lowercase "Recent backups:" heading, which the old case-sensitive
parser never matched — the settings UI showed "No backups found." despite six
backups on disk.
"""

import pytest

from src.web.routes.backup import _parse_backup_list

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
