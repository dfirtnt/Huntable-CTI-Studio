#!/usr/bin/env python3
"""Backup retention management for system and database backups."""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

try:
    from utils.backup_config import get_backup_config_manager
except ImportError:

    def get_backup_config_manager():
        return None


DEFAULT_RETENTION = {
    "daily": 7,
    "weekly": 4,
    "monthly": 3,
    "max_size_gb": 50,
}


BackupEntry = tuple[Path, datetime, float, dict[str, Any] | None]


def parse_backup_timestamp(name: str) -> datetime | None:
    """Parse known backup timestamp formats."""
    candidates = {
        "system_backup_": ("",),
        "cti_scraper_backup_": (".sql.gz", ".sql"),
        "pre_restore_snapshot_": (".sql.gz", ".sql"),
    }

    for prefix, suffixes in candidates.items():
        if not name.startswith(prefix):
            continue
        timestamp = name.removeprefix(prefix)
        for suffix in suffixes:
            if suffix and timestamp.endswith(suffix):
                timestamp = timestamp.removesuffix(suffix)
                break
        try:
            return datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
        except ValueError:
            return None

    return None


def get_backup_size(path: Path) -> float:
    """Return backup size in MB."""
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    if path.is_dir():
        total_size = sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
        return total_size / (1024 * 1024)
    return 0.0


def get_backup_metadata(path: Path) -> dict[str, Any] | None:
    """Read system backup metadata when available."""
    metadata_file = path / "metadata.json" if path.is_dir() else None
    if not metadata_file or not metadata_file.exists():
        return None

    try:
        with open(metadata_file) as f:
            metadata = json.load(f)
        return metadata if isinstance(metadata, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def classify_backup_age(timestamp: datetime, now: datetime) -> str:
    """Classify a backup by age bucket."""
    age_days = (now - timestamp).days
    if age_days < 7:
        return "daily"
    if age_days < 30:
        return "weekly"
    return "monthly"


def find_backups(backup_dir: Path) -> list[BackupEntry]:
    """Find prunable backup artifacts."""
    if not backup_dir.exists():
        return []

    backups: list[BackupEntry] = []
    for item in backup_dir.iterdir():
        is_backup = item.is_dir() and item.name.startswith("system_backup_")
        is_backup = is_backup or (
            item.is_file()
            and item.name.endswith((".sql", ".sql.gz"))
            and (item.name.startswith("cti_scraper_backup_") or item.name.startswith("pre_restore_snapshot_"))
        )
        if not is_backup:
            continue

        timestamp = parse_backup_timestamp(item.name)
        if timestamp is None:
            continue

        backups.append((item, timestamp, get_backup_size(item), get_backup_metadata(item)))

    return sorted(backups, key=lambda backup: backup[1], reverse=True)


def select_backups_to_keep(backups: list[BackupEntry], retention: dict[str, int | float]) -> list[BackupEntry]:
    """Select backups retained by daily, weekly, and monthly limits."""
    now = datetime.now()
    buckets = {"daily": [], "weekly": [], "monthly": []}

    for backup in backups:
        buckets[classify_backup_age(backup[1], now)].append(backup)

    keep: list[BackupEntry] = []
    keep.extend(buckets["daily"][: int(retention["daily"])])
    keep.extend(buckets["weekly"][: int(retention["weekly"])])
    keep.extend(buckets["monthly"][: int(retention["monthly"])])
    return keep


def apply_size_limit(backups: list[BackupEntry], max_size_gb: float) -> list[BackupEntry]:
    """Drop oldest retained backups until total size is under the limit."""
    max_size_mb = max_size_gb * 1024
    current_size_mb = sum(backup[2] for backup in backups)
    if current_size_mb <= max_size_mb:
        return backups

    remaining = sorted(backups, key=lambda backup: backup[1])
    while current_size_mb > max_size_mb and remaining:
        removed = remaining.pop(0)
        current_size_mb -= removed[2]

    return sorted(remaining, key=lambda backup: backup[1], reverse=True)


def load_defaults(
    backup_dir: str | None, retention: dict[str, int | float] | None
) -> tuple[str, dict[str, int | float]]:
    """Load backup directory and retention defaults from config when available."""
    config_manager = get_backup_config_manager()
    if config_manager:
        config = config_manager.get_config()
        resolved_backup_dir = backup_dir or config.backup_dir
        resolved_retention = retention or config_manager.get_retention_policy()
        return resolved_backup_dir, resolved_retention

    return backup_dir or "backups", retention or DEFAULT_RETENTION.copy()


def delete_backup(path: Path) -> None:
    """Delete a backup artifact and its metadata sidecar when present."""
    if path.is_file():
        metadata_path = path.with_name(path.name.replace(".sql.gz", ".json").replace(".sql", ".json"))
        path.unlink()
        if metadata_path.exists():
            metadata_path.unlink()
        return

    if path.is_dir():
        shutil.rmtree(path)


def prune_backups(
    backup_dir: str | None = None,
    retention: dict[str, int | float] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, float | int]:
    """Prune backups according to retention policy."""
    backup_dir, retention = load_defaults(backup_dir, retention)
    backup_path = Path(backup_dir)

    print(f"Pruning backups in: {backup_path}")
    print("Retention policy:")
    print(f"   Daily: {retention['daily']} backups")
    print(f"   Weekly: {retention['weekly']} backups")
    print(f"   Monthly: {retention['monthly']} backups")
    print(f"   Max size: {retention['max_size_gb']} GB")

    if dry_run:
        print("[DRY RUN] No backups will be deleted")

    backups = find_backups(backup_path)
    if not backups:
        print("No backups found to prune.")
        return {
            "total_backups": 0,
            "backups_kept": 0,
            "backups_deleted": 0,
            "space_freed_mb": 0.0,
            "total_size_mb": 0.0,
        }

    total_size_mb = sum(backup[2] for backup in backups)
    backups_to_keep = apply_size_limit(select_backups_to_keep(backups, retention), float(retention["max_size_gb"]))
    keep_paths = {backup[0] for backup in backups_to_keep}
    backups_to_delete = [backup for backup in backups if backup[0] not in keep_paths]

    print(f"Found backups: {len(backups)}")
    print(f"Total backup size: {total_size_mb:.2f} MB ({total_size_mb / 1024:.2f} GB)")
    print(f"Backups to keep: {len(backups_to_keep)}")
    print(f"Backups to delete: {len(backups_to_delete)}")

    if backups_to_delete:
        print("Backups selected for deletion:")
        now = datetime.now()
        for path, timestamp, size_mb, _metadata in backups_to_delete:
            age_class = classify_backup_age(timestamp, now)
            print(f"   {path.name} ({age_class}, {size_mb:.2f} MB)")

        if not dry_run and not force:
            response = input(f"Delete {len(backups_to_delete)} backups? (yes/no): ")
            if response.lower() not in {"yes", "y"}:
                print("Pruning cancelled.")
                return {
                    "total_backups": len(backups),
                    "backups_kept": len(backups_to_keep),
                    "backups_deleted": 0,
                    "space_freed_mb": 0.0,
                    "total_size_mb": total_size_mb,
                }

    deleted_count = 0
    space_freed_mb = 0.0

    for path, _timestamp, size_mb, _metadata in backups_to_delete:
        if dry_run:
            print(f"[DRY RUN] Would delete: {path.name}")
        elif path.is_file() or path.is_dir():
            delete_backup(path)
            print(f"Deleted: {path.name}")
        deleted_count += 1
        space_freed_mb += size_mb

    if dry_run:
        print("Dry-run pruning completed.")
    else:
        print("Pruning completed.")
    print(f"Backups deleted: {deleted_count}")
    print(f"Space freed: {space_freed_mb:.2f} MB ({space_freed_mb / 1024:.2f} GB)")
    print(f"Backups remaining: {len(backups_to_keep)}")

    return {
        "total_backups": len(backups),
        "backups_kept": len(backups_to_keep),
        "backups_deleted": deleted_count,
        "space_freed_mb": space_freed_mb,
        "total_size_mb": total_size_mb,
    }


def show_backup_stats(backup_dir: str = "backups") -> None:
    """Show backup statistics."""
    backups = find_backups(Path(backup_dir))
    if not backups:
        print("No backups found.")
        return

    total_size_mb = sum(backup[2] for backup in backups)
    now = datetime.now()

    print("Backup Statistics")
    print("=" * 80)
    print(f"Total backups: {len(backups)}")
    print(f"Total size: {total_size_mb:.2f} MB ({total_size_mb / 1024:.2f} GB)")

    counts = {"daily": 0, "weekly": 0, "monthly": 0}
    for _path, timestamp, _size_mb, _metadata in backups:
        counts[classify_backup_age(timestamp, now)] += 1

    print("Age distribution:")
    print(f"   Daily (< 7 days): {counts['daily']}")
    print(f"   Weekly (7-30 days): {counts['weekly']}")
    print(f"   Monthly (> 30 days): {counts['monthly']}")

    print("Recent backups:")
    for index, (path, timestamp, size_mb, metadata) in enumerate(backups[:10], start=1):
        age_days = (now - timestamp).days
        print(f"{index:2d}. {path.name}")
        print(f"    Created: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({age_days} days ago)")
        print(f"    Size: {size_mb:.2f} MB")
        if metadata:
            print(f"    Components: {len(metadata.get('components', {}))}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="CTI Scraper Backup Retention Management")
    parser.add_argument("--backup-dir", default=None, help="Backup directory")
    parser.add_argument("--daily", type=int, default=None, help="Keep last N daily backups")
    parser.add_argument("--weekly", type=int, default=None, help="Keep last N weekly backups")
    parser.add_argument("--monthly", type=int, default=None, help="Keep last N monthly backups")
    parser.add_argument("--max-size-gb", type=float, default=None, help="Maximum total backup size in GB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without making changes")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--stats", action="store_true", help="Show backup statistics")
    return parser.parse_args()


def main() -> int:
    """Run backup pruning."""
    args = parse_args()
    backup_dir, defaults = load_defaults(args.backup_dir, None)

    if args.stats:
        show_backup_stats(backup_dir)
        return 0

    retention = {
        "daily": args.daily if args.daily is not None else defaults["daily"],
        "weekly": args.weekly if args.weekly is not None else defaults["weekly"],
        "monthly": args.monthly if args.monthly is not None else defaults["monthly"],
        "max_size_gb": args.max_size_gb if args.max_size_gb is not None else defaults["max_size_gb"],
    }

    prune_backups(backup_dir=backup_dir, retention=retention, dry_run=args.dry_run, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
