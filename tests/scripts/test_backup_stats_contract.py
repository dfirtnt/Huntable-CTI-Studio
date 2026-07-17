"""End-to-end contract test for the prune_backups.py --stats -> /api/backup/list pipeline.

``tests/unit/test_backup_list_parsing.py`` pins ``_parse_backup_list()`` against a
FROZEN verbatim copy of the script's stdout. That can only catch drift on the
*consumer* side: if ``show_backup_stats()`` changes its heading or line layout, the
parser silently returns ``[]`` and the Settings page shows "No backups found." while
that test stays green (it never invokes the script). This is exactly the class of
regression commit 387b7907 fixed once already (a case-sensitive "Recent Backups"
heading match vs. the script's lowercase "Recent backups:").

This test runs the *real* script and feeds its *real* stdout through the *real*
parser, locking both ends of the contract together.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRUNE_SCRIPT = PROJECT_ROOT / "scripts" / "prune_backups.py"

# Imported the same way the endpoint uses it; kept at module scope so a collection
# error surfaces loudly if the route module is renamed/moved.
from src.web.routes.backup import _parse_backup_list  # noqa: E402


def _make_system_backup(backup_dir: Path, created_at: datetime, *, payload_mb: int, components: int) -> str:
    """Create a fixture ``system_backup_*`` directory find_backups() will discover."""
    name = f"system_backup_{created_at.strftime('%Y%m%d_%H%M%S')}"
    path = backup_dir / name
    path.mkdir(parents=True)
    (path / "metadata.json").write_text(json.dumps({"components": {f"c{i}": {} for i in range(components)}}))
    (path / "database.sql").write_bytes(b"x" * (payload_mb * 1024 * 1024))
    return name


def test_stats_output_round_trips_through_the_web_parser(tmp_path):
    """Real `prune_backups.py --stats` output must parse cleanly via `_parse_backup_list`."""
    now = datetime.now()
    newest = _make_system_backup(tmp_path, now - timedelta(days=1), payload_mb=2, components=5)
    middle = _make_system_backup(tmp_path, now - timedelta(days=2), payload_mb=1, components=7)
    oldest = _make_system_backup(tmp_path, now - timedelta(days=3), payload_mb=3, components=7)

    # cwd=PROJECT_ROOT mirrors how src/web/routes/backup.py invokes the script.
    result = subprocess.run(
        [sys.executable, str(PRUNE_SCRIPT), "--stats", "--backup-dir", str(tmp_path)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    parsed = _parse_backup_list(result.stdout.split("\n"))

    # If the heading or numbered-line format drifts, parsed is empty and this fails.
    assert [entry["name"] for entry in parsed] == [newest, middle, oldest], (
        f"parser did not round-trip the script output.\n--- stdout ---\n{result.stdout}"
    )

    # Sizes are scraped from the "Size: X MB" lookahead lines; guard that coupling too.
    sizes = {entry["name"]: entry["size_mb"] for entry in parsed}
    assert sizes[newest] > sizes[middle]  # 2 MB payload vs 1 MB payload
    assert sizes[oldest] > sizes[newest]  # 3 MB payload vs 2 MB payload


def test_stats_output_is_empty_list_when_no_backups(tmp_path):
    """Empty backup dir must produce output the parser reads as zero backups (not a crash)."""
    result = subprocess.run(
        [sys.executable, str(PRUNE_SCRIPT), "--stats", "--backup-dir", str(tmp_path)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    assert _parse_backup_list(result.stdout.split("\n")) == []
