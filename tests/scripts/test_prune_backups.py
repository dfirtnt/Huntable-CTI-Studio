import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRUNE_SCRIPT = PROJECT_ROOT / "scripts" / "prune_backups.py"


spec = importlib.util.spec_from_file_location("prune_backups", PRUNE_SCRIPT)
prune_backups_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prune_backups_module)


def system_backup_dir(backup_dir: Path, created_at: datetime) -> Path:
    path = backup_dir / f"system_backup_{created_at.strftime('%Y%m%d_%H%M%S')}"
    path.mkdir(parents=True)
    (path / "metadata.json").write_text("{}")
    return path


def database_backup_file(backup_dir: Path, created_at: datetime) -> Path:
    path = backup_dir / f"cti_scraper_backup_{created_at.strftime('%Y%m%d_%H%M%S')}.sql.gz"
    path.write_text("backup")
    path.with_name(path.name.replace(".sql.gz", ".json")).write_text("{}")
    return path


def test_prune_backups_deletes_oldest_system_backup(tmp_path):
    now = datetime.now()
    newest = system_backup_dir(tmp_path, now - timedelta(days=1))
    oldest = system_backup_dir(tmp_path, now - timedelta(days=2))

    result = prune_backups_module.prune_backups(
        backup_dir=str(tmp_path),
        retention={"daily": 1, "weekly": 0, "monthly": 0, "max_size_gb": 50},
        force=True,
    )

    assert result["backups_deleted"] == 1
    assert newest.exists()
    assert not oldest.exists()


def test_prune_backups_removes_database_metadata_sidecar(tmp_path):
    now = datetime.now()
    newest = database_backup_file(tmp_path, now - timedelta(days=1))
    oldest = database_backup_file(tmp_path, now - timedelta(days=2))
    oldest_metadata = oldest.with_name(oldest.name.replace(".sql.gz", ".json"))

    result = prune_backups_module.prune_backups(
        backup_dir=str(tmp_path),
        retention={"daily": 1, "weekly": 0, "monthly": 0, "max_size_gb": 50},
        force=True,
    )

    assert result["backups_deleted"] == 1
    assert newest.exists()
    assert not oldest.exists()
    assert not oldest_metadata.exists()


def entry(name: str, age_days: float, size_mb: float = 1.0):
    """Build a BackupEntry tuple: (path, timestamp, size_mb, metadata)."""
    return (Path(name), datetime.now() - timedelta(days=age_days), size_mb, None)


# --- timestamp parsing -------------------------------------------------------


def test_parse_backup_timestamp_supports_every_known_prefix():
    expected = datetime(2026, 7, 6, 2, 0, 2)

    assert prune_backups_module.parse_backup_timestamp("system_backup_20260706_020002") == expected
    assert prune_backups_module.parse_backup_timestamp("cti_scraper_backup_20260706_020002.sql") == expected
    assert prune_backups_module.parse_backup_timestamp("cti_scraper_backup_20260706_020002.sql.gz") == expected
    assert prune_backups_module.parse_backup_timestamp("pre_restore_snapshot_20260706_020002.sql.gz") == expected


def test_parse_backup_timestamp_rejects_malformed_and_unknown_names():
    # Unparseable timestamps must return None so find_backups skips them rather
    # than crashing the prune run or, worse, treating them as ancient.
    assert prune_backups_module.parse_backup_timestamp("system_backup_not_a_timestamp") is None
    assert prune_backups_module.parse_backup_timestamp("system_backup_20260706") is None
    assert prune_backups_module.parse_backup_timestamp("cti_scraper_backup_20261306_020002.sql") is None
    assert prune_backups_module.parse_backup_timestamp("unrelated_file_20260706_020002.sql") is None
    assert prune_backups_module.parse_backup_timestamp("metadata.json") is None


# --- age classification ------------------------------------------------------


def test_classify_backup_age_bucket_boundaries():
    now = datetime(2026, 7, 6, 12, 0, 0)

    def bucket(age_days: int) -> str:
        return prune_backups_module.classify_backup_age(now - timedelta(days=age_days), now)

    assert bucket(0) == "daily"
    assert bucket(6) == "daily"
    assert bucket(7) == "weekly"
    assert bucket(29) == "weekly"
    assert bucket(30) == "monthly"
    assert bucket(365) == "monthly"


# --- retention selection -----------------------------------------------------


def test_select_backups_to_keep_honors_per_bucket_limits():
    backups = [
        entry("daily_1", 1),
        entry("daily_2", 2),
        entry("daily_3", 3),
        entry("weekly_1", 10),
        entry("weekly_2", 15),
        entry("weekly_3", 20),
        entry("monthly_1", 40),
        entry("monthly_2", 60),
    ]

    kept = prune_backups_module.select_backups_to_keep(
        backups, {"daily": 2, "weekly": 1, "monthly": 1, "max_size_gb": 50}
    )

    assert [path.name for path, *_ in kept] == ["daily_1", "daily_2", "weekly_1", "monthly_1"]


def test_select_backups_to_keep_takes_newest_first_within_each_bucket():
    # find_backups hands over a newest-first list; selection must preserve that
    # ordering assumption or retention silently keeps the oldest copies.
    backups = [entry("newest", 1), entry("middle", 2), entry("oldest", 3)]

    kept = prune_backups_module.select_backups_to_keep(
        backups, {"daily": 1, "weekly": 0, "monthly": 0, "max_size_gb": 50}
    )

    assert [path.name for path, *_ in kept] == ["newest"]


def test_select_backups_to_keep_with_zero_retention_keeps_nothing():
    backups = [entry("daily_1", 1), entry("weekly_1", 10), entry("monthly_1", 40)]

    kept = prune_backups_module.select_backups_to_keep(
        backups, {"daily": 0, "weekly": 0, "monthly": 0, "max_size_gb": 50}
    )

    assert kept == []


def test_select_backups_to_keep_tolerates_limits_larger_than_the_bucket():
    backups = [entry("daily_1", 1), entry("daily_2", 2)]

    kept = prune_backups_module.select_backups_to_keep(
        backups, {"daily": 7, "weekly": 4, "monthly": 3, "max_size_gb": 50}
    )

    assert [path.name for path, *_ in kept] == ["daily_1", "daily_2"]


# --- size limit --------------------------------------------------------------


def test_apply_size_limit_is_a_noop_under_the_limit():
    backups = [entry("daily_1", 1, size_mb=512.0), entry("daily_2", 2, size_mb=512.0)]

    assert prune_backups_module.apply_size_limit(backups, max_size_gb=50) == backups


def test_apply_size_limit_drops_oldest_first_until_under_limit():
    backups = [
        entry("newest", 1, size_mb=1024.0),
        entry("middle", 2, size_mb=1024.0),
        entry("oldest", 3, size_mb=1024.0),
    ]

    remaining = prune_backups_module.apply_size_limit(backups, max_size_gb=2)

    # 3 GB total against a 2 GB cap: the oldest goes, the two newest survive,
    # and the result stays newest-first for the caller.
    assert [path.name for path, *_ in remaining] == ["newest", "middle"]


def test_apply_size_limit_never_evicts_the_newest_backup():
    # Prune runs unattended with --force (src/services/backup_cron_service.py),
    # so a max_size_gb smaller than a single backup must not empty the retention
    # set. Staying over the limit is recoverable; having zero backups is not.
    backups = [entry("newest", 1, size_mb=3072.0)]

    assert prune_backups_module.apply_size_limit(backups, max_size_gb=2) == backups


def test_apply_size_limit_keeps_the_newest_even_when_every_backup_is_oversized():
    backups = [
        entry("newest", 1, size_mb=3072.0),
        entry("middle", 2, size_mb=3072.0),
        entry("oldest", 3, size_mb=3072.0),
    ]

    remaining = prune_backups_module.apply_size_limit(backups, max_size_gb=2)

    assert [path.name for path, *_ in remaining] == ["newest"]


def test_prune_over_the_size_limit_still_leaves_one_backup_on_disk(tmp_path):
    now = datetime.now()
    newest = system_backup_dir(tmp_path, now - timedelta(days=1))
    oldest = system_backup_dir(tmp_path, now - timedelta(days=2))

    # max_size_gb is far below the size of even an empty backup directory once
    # the limit is set to effectively zero, which is what a mistyped settings
    # value looks like in production.
    result = prune_backups_module.prune_backups(
        backup_dir=str(tmp_path),
        retention={"daily": 7, "weekly": 4, "monthly": 3, "max_size_gb": 0.000000001},
        force=True,
    )

    assert result["backups_kept"] == 1
    assert newest.exists()
    assert not oldest.exists()


# --- discovery ---------------------------------------------------------------


def test_find_backups_ignores_unrelated_entries_and_returns_newest_first(tmp_path):
    now = datetime.now()
    older = system_backup_dir(tmp_path, now - timedelta(days=3))
    newer = database_backup_file(tmp_path, now - timedelta(days=1))
    (tmp_path / "notes.txt").write_text("not a backup")
    (tmp_path / "system_backup_bogus").mkdir()
    (tmp_path / "logs").mkdir()

    found = prune_backups_module.find_backups(tmp_path)

    assert [path.name for path, *_ in found] == [newer.name, older.name]


def test_find_backups_on_missing_directory_returns_empty(tmp_path):
    assert prune_backups_module.find_backups(tmp_path / "does_not_exist") == []


# --- prune orchestration -----------------------------------------------------


def test_prune_dry_run_reports_deletions_without_touching_the_filesystem(tmp_path):
    now = datetime.now()
    kept = system_backup_dir(tmp_path, now - timedelta(days=1))
    doomed_a = system_backup_dir(tmp_path, now - timedelta(days=2))
    doomed_b = system_backup_dir(tmp_path, now - timedelta(days=3))

    result = prune_backups_module.prune_backups(
        backup_dir=str(tmp_path),
        retention={"daily": 1, "weekly": 0, "monthly": 0, "max_size_gb": 50},
        dry_run=True,
        force=True,
    )

    assert result["backups_deleted"] == 2
    assert result["backups_kept"] == 1
    assert kept.exists()
    assert doomed_a.exists()
    assert doomed_b.exists()


def test_prune_on_empty_directory_returns_zeroed_stats(tmp_path):
    result = prune_backups_module.prune_backups(
        backup_dir=str(tmp_path),
        retention={"daily": 7, "weekly": 4, "monthly": 3, "max_size_gb": 50},
        force=True,
    )

    assert result == {
        "total_backups": 0,
        "backups_kept": 0,
        "backups_deleted": 0,
        "space_freed_mb": 0.0,
        "total_size_mb": 0.0,
    }


def test_prune_retains_one_backup_per_configured_bucket(tmp_path):
    now = datetime.now()
    survivors = {
        system_backup_dir(tmp_path, now - timedelta(days=1)).name,
        system_backup_dir(tmp_path, now - timedelta(days=10)).name,
        system_backup_dir(tmp_path, now - timedelta(days=40)).name,
    }
    system_backup_dir(tmp_path, now - timedelta(days=2))
    system_backup_dir(tmp_path, now - timedelta(days=20))
    system_backup_dir(tmp_path, now - timedelta(days=60))

    result = prune_backups_module.prune_backups(
        backup_dir=str(tmp_path),
        retention={"daily": 1, "weekly": 1, "monthly": 1, "max_size_gb": 50},
        force=True,
    )

    assert result["total_backups"] == 6
    assert result["backups_kept"] == 3
    assert result["backups_deleted"] == 3
    assert {path.name for path in tmp_path.iterdir()} == survivors
