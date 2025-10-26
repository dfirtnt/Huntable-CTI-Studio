#!/usr/bin/env python3
"""
Database Backup Script for CTI Scraper

This script creates compressed backups of the PostgreSQL database
with timestamp and metadata information.
"""

import os
import sys
import gzip
import shutil
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': '5432',
    'database': 'cti_scraper',
    'user': 'cti_user',
    'password': 'cti_password'
}

def get_docker_exec_cmd(container_name: str, command: str) -> list:
    """Generate docker exec command for running commands in container."""
    return ['docker', 'exec', container_name, 'bash', '-c', command]

def check_docker_container(container_name: str) -> bool:
    """Check if Docker container is running."""
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', f'name={container_name}', '--format', '{{.Names}}'],
            capture_output=True,
            text=True,
            check=True
        )
        return container_name in result.stdout
    except subprocess.CalledProcessError:
        return False

def get_database_info() -> Dict[str, Any]:
    """Get database metadata and statistics."""
    try:
        # Get database size
        size_cmd = get_docker_exec_cmd(
            'cti_postgres',
            "psql -U cti_user -d cti_scraper -c \"SELECT pg_size_pretty(pg_database_size('cti_scraper'));\" -t"
        )
        size_result = subprocess.run(size_cmd, capture_output=True, text=True, check=True)
        db_size = size_result.stdout.strip()
        
        # Get table counts
        tables_cmd = get_docker_exec_cmd(
            'cti_postgres',
            "psql -U cti_user -d cti_scraper -c \"SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del FROM pg_stat_user_tables ORDER BY tablename;\" -t"
        )
        tables_result = subprocess.run(tables_cmd, capture_output=True, text=True, check=True)
        
        # Get ml_model_versions count
        model_versions_cmd = get_docker_exec_cmd(
            'cti_postgres',
            "psql -U cti_user -d cti_scraper -c \"SELECT COUNT(*) FROM ml_model_versions;\" -t"
        )
        model_versions_result = subprocess.run(model_versions_cmd, capture_output=True, text=True, check=True)
        model_versions_count = model_versions_result.stdout.strip()
        
        return {
            'database_size': db_size,
            'table_stats': tables_result.stdout.strip(),
            'ml_model_versions_count': model_versions_count,
            'backup_timestamp': datetime.now().isoformat(),
            'postgres_version': '15-alpine'
        }
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not get database info: {e}")
        return {
            'backup_timestamp': datetime.now().isoformat(),
            'postgres_version': '15-alpine'
        }

def create_backup(backup_dir: str = 'backups', compress: bool = True) -> str:
    """Create a database backup."""
    
    # Check if PostgreSQL container is running
    if not check_docker_container('cti_postgres'):
        print("❌ PostgreSQL container 'cti_postgres' is not running!")
        print("Please start the CTI Scraper stack first: docker-compose up -d")
        sys.exit(1)
    
    # Create backup directory
    backup_path = Path(backup_dir)
    backup_path.mkdir(exist_ok=True)
    
    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"cti_scraper_backup_{timestamp}.sql"
    backup_filepath = backup_path / backup_filename
    
    print(f"🔄 Creating database backup: {backup_filename}")
    
    try:
        # Create pg_dump command
        dump_cmd = get_docker_exec_cmd(
            'cti_postgres',
            f"pg_dump -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} --verbose --no-password"
        )
        
        # Execute backup
        with open(backup_filepath, 'w') as f:
            result = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            print(f"❌ Backup failed: {result.stderr}")
            sys.exit(1)
        
        # Get database metadata
        db_info = get_database_info()
        
        # Create metadata file
        metadata_filename = f"cti_scraper_backup_{timestamp}.json"
        metadata_filepath = backup_path / metadata_filename
        
        with open(metadata_filepath, 'w') as f:
            json.dump(db_info, f, indent=2)
        
        # Compress if requested
        if compress:
            print("🗜️  Compressing backup...")
            compressed_filename = f"{backup_filename}.gz"
            compressed_filepath = backup_path / compressed_filename
            
            with open(backup_filepath, 'rb') as f_in:
                with gzip.open(compressed_filepath, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove uncompressed file
            backup_filepath.unlink()
            backup_filepath = compressed_filepath
            backup_filename = compressed_filename
        
        # Get file size
        file_size = backup_filepath.stat().st_size
        size_mb = file_size / (1024 * 1024)
        
        print(f"✅ Backup completed successfully!")
        print(f"   📁 File: {backup_filepath}")
        print(f"   📊 Size: {size_mb:.2f} MB")
        print(f"   📋 Metadata: {metadata_filepath}")
        
        return str(backup_filepath)
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Backup failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

def list_backups(backup_dir: str = 'backups') -> None:
    """List available backups."""
    backup_path = Path(backup_dir)
    
    if not backup_path.exists():
        print("📁 No backup directory found.")
        return
    
    backups = list(backup_path.glob('cti_scraper_backup_*.sql*'))
    
    if not backups:
        print("📁 No backups found.")
        return
    
    print("📋 Available backups:")
    print("-" * 80)
    
    for backup in sorted(backups):
        stat = backup.stat()
        size_mb = stat.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stat.st_mtime)
        
        print(f"📄 {backup.name}")
        print(f"   📊 Size: {size_mb:.2f} MB")
        print(f"   📅 Modified: {modified.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Check for metadata file
        metadata_file = backup_path / f"{backup.stem}.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                if 'database_size' in metadata:
                    print(f"   💾 DB Size: {metadata['database_size']}")
                if 'ml_model_versions_count' in metadata:
                    print(f"   🤖 Model Versions: {metadata['ml_model_versions_count']}")
            except:
                pass
        
        print()

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='CTI Scraper Database Backup Tool')
    parser.add_argument('--backup-dir', default='backups', help='Backup directory (default: backups)')
    parser.add_argument('--no-compress', action='store_true', help='Skip compression')
    parser.add_argument('--list', action='store_true', help='List available backups')
    
    args = parser.parse_args()
    
    if args.list:
        list_backups(args.backup_dir)
    else:
        create_backup(args.backup_dir, compress=not args.no_compress)

if __name__ == '__main__':
    main()
