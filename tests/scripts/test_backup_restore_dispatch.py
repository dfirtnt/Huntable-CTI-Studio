"""Static guarantee that every backup caller only references scripts that exist.

Commit e48b9246 deleted scripts/prune_backups.py and scripts/backup_database.py
while callers still referenced them, so the weekly cron `prune` job failed with
"[Errno 2] No such file or directory" every Sunday until 387b7907 restored the
dispatcher paths. These references are resolved at *runtime* (shell exec / Python
Path.exists()), so a re-deletion stays invisible until an operator or cron job
actually hits the command. Assert them statically instead — across every caller
surface, not just the canonical shell dispatcher.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _shell_dispatch_targets(script_path: Path) -> set[Path]:
    """Collect every `python3 scripts/<name>.py` target a shell dispatcher execs."""
    targets: set[Path] = set()
    for raw_line in script_path.read_text().splitlines():
        line = raw_line.strip()
        if not line.startswith("python3 scripts/"):
            continue
        targets.add(PROJECT_ROOT / line.split()[1])
    return targets


def _assert_all_exist(referenced: set[Path]) -> None:
    assert referenced, "expected at least one referenced script; parser found none"
    missing = sorted(str(path) for path in referenced if not path.exists())
    assert missing == [], f"referenced backup scripts are missing: {missing}"


def test_backup_restore_python_dispatch_targets_exist():
    """Canonical dispatcher scripts/backup_restore.sh (drives the cron jobs)."""
    _assert_all_exist(_shell_dispatch_targets(PROJECT_ROOT / "scripts" / "backup_restore.sh"))


def test_utilities_backup_restore_dispatch_targets_exist():
    """The duplicate dispatcher under scripts/shell/utilities/ must stay consistent too."""
    dispatcher = PROJECT_ROOT / "scripts" / "shell" / "utilities" / "backup_restore.sh"
    if not dispatcher.exists():
        # The duplicate is not a hard requirement; only enforce it when present.
        return
    _assert_all_exist(_shell_dispatch_targets(dispatcher))


def test_backup_cli_referenced_scripts_exist():
    """src/cli/commands/backup.py builds paths as `"scripts" / "<name>.py"`.

    Those are only checked with .exists() when a subcommand actually runs, so a
    deleted script degrades to an error message rather than a caught test failure.
    The CLI references the most scripts of any caller (backup/restore/verify/prune),
    which makes it the highest-value surface to pin.
    """
    cli_source = (PROJECT_ROOT / "src" / "cli" / "commands" / "backup.py").read_text()
    referenced = {PROJECT_ROOT / "scripts" / name for name in re.findall(r'"scripts"\s*/\s*"([^"]+\.py)"', cli_source)}
    _assert_all_exist(referenced)
