#!/usr/bin/env python3
"""
Backup Retention Management Script for CTI Scraper

This script manages backup retention policies:
- Keep last 7 daily + 4 weekly + 3 monthly backups (default)
- Configurable retention rules
- Size-based cleanup
- Automatic cleanup of old backups

Features:
- Configurable retention policies
- Size-based cleanup (keep backups under X GB total)
- Dry-run mode
- Detailed reporting
- YAML configuration support
"""

import os
import sys
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import argparse

# Add src to path for imports
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

try:
    from utils.backup_config import get_backup_config_manager
except ImportError:
    # Fallback if config module not available
    def get_backup_config_manager():
        return None

# Default retention policy
DEFAULT_RETENTION = {
    'daily': 7,      # Keep last 7 daily backups
    'weekly': 4,     # Keep last 4 weekly backups
    'monthly': 3,    # Keep last 3 monthly backups
    'max_size_gb': 50  # Maximum total backup size in GB
}

def parse_backup_timestamp(backup_name: str) -> Optional[datetime]:
    """Parse timestamp from backup name."""
    try:
        # Handle system_backup_YYYYMMDD_HHMMSS format
        if backup_name.startswith('system_backup_'):
            timestamp_str = backup_name.replace('system_backup_', '')
            return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
        
        # Handle cti_scraper_backup_YYYYMMDD_HHMMSS format (legacy)
        elif backup_name.startswith('cti_scraper_backup_'):
            timestamp_str = backup_name.replace('cti_scraper_backup_', '')
            if timestamp_str.endswith('.sql'):
                timestamp_str = timestamp_str.replace('.sql', '')
            elif timestamp_str.endswith('.sql.gz'):
                timestamp_str = timestamp_str.replace('.sql.gz', '')
            return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
        
        # Handle pre_restore_snapshot_YYYYMMDD_HHMMSS format
        elif backup_name.startswith('pre_restore_snapshot_'):
            timestamp_str = backup_name.replace('pre_restore_snapshot_', '')
            if timestamp_str.endswith('.sql'):
                timestamp_str = timestamp_str.replace('.sql', '')
            return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
        
        return None
        
    except ValueError:
        return None

def get_backup_size(backup_path: Path) -> float:
    """Get backup size in MB."""
    if backup_path.is_file():
        return backup_path.stat().st_size / (1024 * 1024)
    elif backup_path.is_dir():
        total_size = 0
        for file_path in backup_path.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size / (1024 * 1024)
    return 0.0

def get_backup_metadata(backup_path: Path) -> Optional[Dict]:
    """Get backup metadata if available."""
    if backup_path.is_dir():
        metadata_file = backup_path / 'metadata.json'
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
    
    return None

def classify_backup_age(backup_timestamp: datetime, now: datetime) -> str:
    """Classify backup age (daily, weekly, monthly)."""
    age_days = (now - backup_timestamp).days
    
    if age_days < 7:
        return 'daily'
    elif age_days < 30:
        return 'weekly'
    else:
        return 'monthly'

def find_backups(backup_dir: Path) -> List[Tuple[Path, datetime, float, Optional[Dict]]]:
    """Find all backups in directory with metadata."""
    backups = []
    
    if not backup_dir.exists():
        return backups
    
    # Find system backup directories
    for item in backup_dir.iterdir():
        if item.is_dir() and item.name.startswith('system_backup_'):
            timestamp = parse_backup_timestamp(item.name)
            if timestamp:
                size_mb = get_backup_size(item)
                metadata = get_backup_metadata(item)
                backups.append((item, timestamp, size_mb, metadata))
    
    # Find legacy database backup files
    for item in backup_dir.iterdir():
        if item.is_file() and item.name.startswith('cti_scraper_backup_'):
            timestamp = parse_backup_timestamp(item.name)
            if timestamp:
                size_mb = get_backup_size(item)
                backups.append((item, timestamp, size_mb, None))
    
    # Find snapshot files
    for item in backup_dir.iterdir():
        if item.is_file() and item.name.startswith('pre_restore_snapshot_'):
            timestamp = parse_backup_timestamp(item.name)
            if timestamp:
                size_mb = get_backup_size(item)
                backups.append((item, timestamp, size_mb, None))
    
    # Sort by timestamp (newest first)
    backups.sort(key=lambda x: x[1], reverse=True)
    
    return backups

def select_backups_to_keep(backups: List[Tuple[Path, datetime, float, Optional[Dict]]], 
                          retention: Dict) -> List[Tuple[Path, datetime, float, Optional[Dict]]]:
    """Select backups to keep based on retention policy."""
    if not backups:
        return []
    
    now = datetime.now()
    backups_to_keep = []
    
    # Classify backups by age
    daily_backups = []
    weekly_backups = []
    monthly_backups = []
    
    for backup in backups:
        backup_path, timestamp, size_mb, metadata = backup
        age_class = classify_backup_age(timestamp, now)
        
        if age_class == 'daily':
            daily_backups.append(backup)
        elif age_class == 'weekly':
            weekly_backups.append(backup)
        else:
            monthly_backups.append(backup)
    
    # Select backups to keep
    # Keep most recent daily backups
    daily_keep = min(retention['daily'], len(daily_backups))
    backups_to_keep.extend(daily_backups[:daily_keep])
    
    # Keep most recent weekly backups
    weekly_keep = min(retention['weekly'], len(weekly_backups))
    backups_to_keep.extend(weekly_backups[:weekly_keep])
    
    # Keep most recent monthly backups
    monthly_keep = min(retention['monthly'], len(monthly_backups))
    backups_to_keep.extend(monthly_backups[:monthly_keep])
    
    return backups_to_keep

def apply_size_limit(backups_to_keep: List[Tuple[Path, datetime, float, Optional[Dict]]], 
                    max_size_gb: float) -> List[Tuple[Path, datetime, float, Optional[Dict]]]:
    """Apply size limit to backups to keep."""
    if not backups_to_keep:
        return backups_to_keep
    
    max_size_mb = max_size_gb * 1024
    current_size_mb = sum(backup[2] for backup in backups_to_keep)
    
    if current_size_mb <= max_size_mb:
        return backups_to_keep
    
    # Remove oldest backups until under size limit
    # Sort by timestamp (oldest first) for removal
    backups_sorted = sorted(backups_to_keep, key=lambda x: x[1])
    
    while current_size_mb > max_size_mb and backups_sorted:
        removed_backup = backups_sorted.pop(0)
        current_size_mb -= removed_backup[2]
    
    # Return remaining backups sorted by timestamp (newest first)
    return sorted(backups_sorted, key=lambda x: x[1], reverse=True)

def prune_backups(backup_dir: Optional[str] = None, retention: Optional[Dict] = None,
                 dry_run: bool = False, force: bool = False) -> Dict:
    """Prune backups based on retention policy."""
    
    # Load configuration
    config_manager = get_backup_config_manager()
    if config_manager:
        config = config_manager.get_config()
        backup_dir = backup_dir or config.backup_dir
        if retention is None:
            retention = config_manager.get_retention_policy()
    else:
        backup_dir = backup_dir or 'backups'
        if retention is None:
            retention = DEFAULT_RETENTION.copy()
    
    backup_path = Path(backup_dir)
    
    print(f"🧹 Pruning backups in: {backup_path}")
    print(f"📋 Retention policy:")
    print(f"   • Daily: {retention['daily']} backups")
    print(f"   • Weekly: {retention['weekly']} backups")
    print(f"   • Monthly: {retention['monthly']} backups")
    print(f"   • Max size: {retention['max_size_gb']} GB")
    
    if dry_run:
        print("🔍 [DRY RUN MODE] - No backups will be deleted")
    
    # Find all backups
    all_backups = find_backups(backup_path)
    
    if not all_backups:
        print("📁 No backups found to prune.")
        return {
            'total_backups': 0,
            'backups_kept': 0,
            'backups_deleted': 0,
            'space_freed_mb': 0.0,
            'total_size_mb': 0.0
        }
    
    print(f"📊 Found {len(all_backups)} backups")
    
    # Calculate total size
    total_size_mb = sum(backup[2] for backup in all_backups)
    print(f"📊 Total backup size: {total_size_mb:.2f} MB ({total_size_mb/1024:.2f} GB)")
    
    # Select backups to keep
    backups_to_keep = select_backups_to_keep(all_backups, retention)
    backups_to_keep = apply_size_limit(backups_to_keep, retention['max_size_gb'])
    
    # Determine backups to delete
    keep_paths = {backup[0] for backup in backups_to_keep}
    backups_to_delete = [backup for backup in all_backups if backup[0] not in keep_paths]
    
    print(f"📊 Backups to keep: {len(backups_to_keep)}")
    print(f"📊 Backups to delete: {len(backups_to_delete)}")
    
    if backups_to_delete:
        space_to_free_mb = sum(backup[2] for backup in backups_to_delete)
        print(f"📊 Space to free: {space_to_free_mb:.2f} MB ({space_to_free_mb/1024:.2f} GB)")
        
        print("\n🗑️  Backups to be deleted:")
        for backup_path, timestamp, size_mb, metadata in backups_to_delete:
            age_class = classify_backup_age(timestamp, datetime.now())
            print(f"   • {backup_path.name} ({age_class}, {size_mb:.2f} MB)")
        
        # Confirm deletion
        if not force and not dry_run:
            response = input(f"\nDelete {len(backups_to_delete)} backups? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                print("❌ Pruning cancelled.")
                return {
                    'total_backups': len(all_backups),
                    'backups_kept': len(backups_to_keep),
                    'backups_deleted': 0,
                    'space_freed_mb': 0.0,
                    'total_size_mb': total_size_mb
                }
    
    # Delete backups
    deleted_count = 0
    space_freed_mb = 0.0
    
    for backup_path, timestamp, size_mb, metadata in backups_to_delete:
        try:
            if not dry_run:
                if backup_path.is_file():
                    backup_path.unlink()
                elif backup_path.is_dir():
                    shutil.rmtree(backup_path)
                
                print(f"✅ Deleted: {backup_path.name}")
            else:
                print(f"🔍 [DRY RUN] Would delete: {backup_path.name}")
            
            deleted_count += 1
            space_freed_mb += size_mb
            
        except Exception as e:
            print(f"❌ Failed to delete {backup_path.name}: {e}")
    
    # Show final results
    if not dry_run:
        print(f"\n🎉 Pruning completed!")
        print(f"   📊 Backups deleted: {deleted_count}")
        print(f"   💾 Space freed: {space_freed_mb:.2f} MB ({space_freed_mb/1024:.2f} GB)")
        print(f"   📊 Backups remaining: {len(backups_to_keep)}")
    else:
        print(f"\n🔍 [DRY RUN] Pruning simulation completed!")
        print(f"   📊 Would delete: {deleted_count} backups")
        print(f"   💾 Would free: {space_freed_mb:.2f} MB ({space_freed_mb/1024:.2f} GB)")
        print(f"   📊 Would keep: {len(backups_to_keep)} backups")
    
    return {
        'total_backups': len(all_backups),
        'backups_kept': len(backups_to_keep),
        'backups_deleted': deleted_count,
        'space_freed_mb': space_freed_mb,
        'total_size_mb': total_size_mb
    }

def show_backup_stats(backup_dir: str = 'backups') -> None:
    """Show detailed backup statistics."""
    backup_path = Path(backup_dir)
    
    if not backup_path.exists():
        print("📁 No backup directory found.")
        return
    
    backups = find_backups(backup_path)
    
    if not backups:
        print("📁 No backups found.")
        return
    
    print("📊 Backup Statistics")
    print("=" * 80)
    
    # Overall stats
    total_size_mb = sum(backup[2] for backup in backups)
    print(f"Total backups: {len(backups)}")
    print(f"Total size: {total_size_mb:.2f} MB ({total_size_mb/1024:.2f} GB)")
    
    # Age classification
    now = datetime.now()
    daily_count = 0
    weekly_count = 0
    monthly_count = 0
    
    for backup_path, timestamp, size_mb, metadata in backups:
        age_class = classify_backup_age(timestamp, now)
        if age_class == 'daily':
            daily_count += 1
        elif age_class == 'weekly':
            weekly_count += 1
        else:
            monthly_count += 1
    
    print(f"\nAge Distribution:")
    print(f"  Daily (< 7 days): {daily_count} backups")
    print(f"  Weekly (7-30 days): {weekly_count} backups")
    print(f"  Monthly (> 30 days): {monthly_count} backups")
    
    # Show recent backups
    print(f"\nRecent Backups (last 10):")
    print("-" * 80)
    
    for i, (backup_path, timestamp, size_mb, metadata) in enumerate(backups[:10]):
        age_class = classify_backup_age(timestamp, now)
        age_days = (now - timestamp).days
        
        print(f"{i+1:2d}. {backup_path.name}")
        print(f"     📅 {timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({age_days} days ago, {age_class})")
        print(f"     📊 {size_mb:.2f} MB")
        
        if metadata:
            version = metadata.get('version', '1.0')
            components = len(metadata.get('components', {}))
            print(f"     🧩 Version {version}, {components} components")
        
        print()

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='CTI Scraper Backup Retention Management')
    parser.add_argument('--backup-dir', default='backups', help='Backup directory (default: backups)')
    parser.add_argument('--daily', type=int, default=7, help='Keep last N daily backups (default: 7)')
    parser.add_argument('--weekly', type=int, default=4, help='Keep last N weekly backups (default: 4)')
    parser.add_argument('--monthly', type=int, default=3, help='Keep last N monthly backups (default: 3)')
    parser.add_argument('--max-size-gb', type=float, default=50, help='Maximum total backup size in GB (default: 50)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without making changes')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompts')
    parser.add_argument('--stats', action='store_true', help='Show backup statistics')
    
    args = parser.parse_args()
    
    if args.stats:
        show_backup_stats(args.backup_dir)
        return
    
    # Build retention policy
    retention = {
        'daily': args.daily,
        'weekly': args.weekly,
        'monthly': args.monthly,
        'max_size_gb': args.max_size_gb
    }
    
    # Prune backups
    result = prune_backups(
        backup_dir=args.backup_dir,
        retention=retention,
        dry_run=args.dry_run,
        force=args.force
    )
    
    # Exit with error if no backups were processed
    if result['total_backups'] == 0:
        sys.exit(1)

if __name__ == '__main__':
    main()
