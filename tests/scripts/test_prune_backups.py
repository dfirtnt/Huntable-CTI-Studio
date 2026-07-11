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
