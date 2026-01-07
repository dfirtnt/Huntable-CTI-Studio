#!/usr/bin/env python3
"""
Database Backup Script for CTI Scraper

This script creates compressed backups of the PostgreSQL database
with timestamp and metadata information.

IMPORTANT: This backup includes ALL database tables, including:
- ml_model_versions: ML model version history with evaluation metrics
- All other application tables

The backup uses pg_dump which captures the complete database schema and data.
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
        
        # Get chunk_analysis_results count (for ML hunt comparison metrics)
        chunk_analysis_cmd = get_docker_exec_cmd(
            'cti_postgres',
            "psql -U cti_user -d cti_scraper -c \"SELECT COUNT(*) FROM chunk_analysis_results;\" -t"
        )
        chunk_analysis_result = subprocess.run(chunk_analysis_cmd, capture_output=True, text=True, check=True)
        chunk_analysis_count = chunk_analysis_result.stdout.strip()
        
        # Get model file paths from ml_model_versions (for model file tracking)
        model_files_cmd = get_docker_exec_cmd(
            'cti_postgres',
            "psql -U cti_user -d cti_scraper -c \"SELECT DISTINCT model_file_path FROM ml_model_versions WHERE model_file_path IS NOT NULL;\" -t"
        )
        model_files_result = subprocess.run(model_files_cmd, capture_output=True, text=True, check=True)
        model_file_paths = [line.strip() for line in model_files_result.stdout.strip().split('\n') if line.strip()]
        
        # Get counts for new tables (for restore verification)
        table_counts = {}
        new_tables = [
            'observable_model_metrics',
            'observable_evaluation_failures',
            'agent_evaluations',
            'agentic_workflow_executions',
            'sigma_rules',
            'article_sigma_matches',
            'sigma_rule_queue'
        ]
        
        for table in new_tables:
            try:
                count_cmd = get_docker_exec_cmd(
                    'cti_postgres',
                    f"psql -U cti_user -d cti_scraper -c \"SELECT COUNT(*) FROM {table};\" -t"
                )
                count_result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)
                table_counts[f'{table}_count'] = count_result.stdout.strip()
            except subprocess.CalledProcessError:
                # Table may not exist in older backups, skip silently
                pass
        
        metadata = {
            'database_size': db_size,
            'table_stats': tables_result.stdout.strip(),
            'ml_model_versions_count': model_versions_count,
            'chunk_analysis_results_count': chunk_analysis_count,
            'model_file_paths': model_file_paths,
            'backup_timestamp': datetime.now().isoformat(),
            'postgres_version': '15-alpine'
        }
        metadata.update(table_counts)
        
        return metadata
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
        # Note: pg_dump without --table or --exclude-table flags backs up ALL tables
        # This ensures all tables are included:
        # - ml_model_versions: ML model version history with evaluation metrics
        # - agentic_workflow_config: Agent workflow configuration (thresholds, agent models, prompts, QA settings)
        # - agent_prompt_versions: Agent prompt version history
        # - app_settings: Application settings (user preferences)
        # - sources: Source configurations (enabled status, lookback_days, check_frequency, config JSON)
        # - source_checks: Source check history and health metrics
        # - All other application tables
        dump_cmd = get_docker_exec_cmd(
            'cti_postgres',
            f"pg_dump -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} --verbose --no-password"
        )
        
        # Execute backup
        with open(backup_filepath, 'w') as f:
            result = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            print(f"❌ Backup failed: {result.stderr}")
            # Clean up empty backup file if it exists
            if backup_filepath.exists():
                backup_filepath.unlink()
            sys.exit(1)
        
        # Verify backup file was created and is not empty
        if not backup_filepath.exists():
            print("❌ Backup file was not created")
            sys.exit(1)
        
        backup_size = backup_filepath.stat().st_size
        if backup_size == 0:
            print("❌ Backup file is empty - backup may have failed silently")
            backup_filepath.unlink()
            sys.exit(1)
        
        print(f"✅ Backup file created: {backup_size:,} bytes")
        
        # Validate SQL content
        try:
            with open(backup_filepath, 'r') as f:
                first_line = f.readline().strip()
                # Read a bit more to check for SQL content
                content_sample = f.read(1000)
            
            # Check for PostgreSQL dump markers
            if not (first_line.startswith("-- PostgreSQL database dump") or 
                    first_line.startswith("--") or
                    "CREATE" in content_sample or
                    "COPY" in content_sample or
                    "INSERT" in content_sample):
                print("❌ Backup file does not appear to be a valid PostgreSQL dump")
                backup_filepath.unlink()
                sys.exit(1)
            
            print("✅ Backup file contains valid SQL content")
        except Exception as e:
            print(f"❌ Error validating backup content: {e}")
            backup_filepath.unlink()
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
