#!/usr/bin/env python3
"""
Database Restore Script for CTI Scraper

This script restores PostgreSQL database from compressed backups
with validation and safety checks.
"""

import os
import sys
import gzip
import shutil
import subprocess
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

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

def validate_backup_file(backup_path: Path) -> Dict[str, Any]:
    """Validate backup file and extract metadata."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    
    # Check if compressed
    is_compressed = backup_path.suffix == '.gz'
    
    # Get file size
    file_size = backup_path.stat().st_size
    size_mb = file_size / (1024 * 1024)
    
    # Try to read first few lines to validate SQL
    try:
        if is_compressed:
            with gzip.open(backup_path, 'rt') as f:
                first_line = f.readline().strip()
        else:
            with open(backup_path, 'r') as f:
                first_line = f.readline().strip()
        
        if not first_line.startswith('-- PostgreSQL database dump') and not first_line.startswith('--'):
            raise ValueError("Invalid PostgreSQL backup file")
            
    except Exception as e:
        raise ValueError(f"Invalid backup file format: {e}")
    
    # Look for metadata file
    metadata_path = backup_path.parent / f"{backup_path.stem.replace('.sql', '')}.json"
    metadata = {}
    
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        except:
            pass
    
    return {
        'file_path': backup_path,
        'is_compressed': is_compressed,
        'file_size_mb': size_mb,
        'metadata': metadata,
        'valid': True
    }

def create_database_snapshot() -> str:
    """Create a snapshot of current database before restore."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    snapshot_filename = f"pre_restore_snapshot_{timestamp}.sql"
    snapshot_path = Path('backups') / snapshot_filename
    
    print(f"📸 Creating pre-restore snapshot: {snapshot_filename}")
    
    try:
        # Create snapshot directory
        snapshot_path.parent.mkdir(exist_ok=True)
        
        # Create pg_dump command
        dump_cmd = get_docker_exec_cmd(
            'cti_postgres',
            f"pg_dump -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} --verbose --no-password"
        )
        
        # Execute snapshot
        with open(snapshot_path, 'w') as f:
            result = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            print(f"⚠️  Snapshot creation failed: {result.stderr}")
            return None
        
        print(f"✅ Snapshot created: {snapshot_path}")
        return str(snapshot_path)
        
    except Exception as e:
        print(f"⚠️  Snapshot creation failed: {e}")
        return None

def restore_database(backup_path: Path, create_snapshot: bool = True, force: bool = False) -> bool:
    """Restore database from backup file."""
    
    # Validate backup file
    try:
        backup_info = validate_backup_file(backup_path)
        print(f"✅ Backup file validated: {backup_path.name}")
        print(f"   📊 Size: {backup_info['file_size_mb']:.2f} MB")
        print(f"   🗜️  Compressed: {backup_info['is_compressed']}")
    except Exception as e:
        print(f"❌ Backup validation failed: {e}")
        return False
    
    # Check if PostgreSQL container is running
    if not check_docker_container('cti_postgres'):
        print("❌ PostgreSQL container 'cti_postgres' is not running!")
        print("Please start the CTI Scraper stack first: docker-compose up -d")
        return False
    
    # Create snapshot if requested
    snapshot_path = None
    if create_snapshot and not force:
        snapshot_path = create_database_snapshot()
        if not snapshot_path:
            print("❌ Failed to create snapshot. Use --force to skip snapshot creation.")
            return False
    
    print(f"🔄 Restoring database from: {backup_path.name}")
    
    try:
        # Create temporary file for SQL content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as temp_file:
            temp_path = temp_file.name
            
            # Extract SQL content
            if backup_info['is_compressed']:
                with gzip.open(backup_path, 'rt') as f_in:
                    shutil.copyfileobj(f_in, temp_file)
            else:
                with open(backup_path, 'r') as f_in:
                    shutil.copyfileobj(f_in, temp_file)
        
        # Copy SQL file to container
        copy_cmd = ['docker', 'cp', temp_path, f'cti_postgres:/tmp/restore.sql']
        subprocess.run(copy_cmd, check=True)
        
        # Drop and recreate database
        print("🗑️  Dropping existing database...")
        drop_cmd = get_docker_exec_cmd(
            'cti_postgres',
            f"psql -U {DB_CONFIG['user']} -c 'DROP DATABASE IF EXISTS {DB_CONFIG['database']};'"
        )
        subprocess.run(drop_cmd, check=True)
        
        print("🆕 Creating new database...")
        create_cmd = get_docker_exec_cmd(
            'cti_postgres',
            f"psql -U {DB_CONFIG['user']} -c 'CREATE DATABASE {DB_CONFIG['database']};'"
        )
        subprocess.run(create_cmd, check=True)
        
        # Restore from backup
        print("📥 Restoring data...")
        restore_cmd = get_docker_exec_cmd(
            'cti_postgres',
            f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -f /tmp/restore.sql"
        )
        
        result = subprocess.run(restore_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Restore failed: {result.stderr}")
            
            # Try to restore from snapshot if available
            if snapshot_path and Path(snapshot_path).exists():
                print("🔄 Attempting to restore from snapshot...")
                restore_snapshot(Path(snapshot_path))
            
            return False
        
        # Clean up temporary file
        os.unlink(temp_path)
        
        # Remove SQL file from container
        cleanup_cmd = get_docker_exec_cmd('cti_postgres', 'rm -f /tmp/restore.sql')
        subprocess.run(cleanup_cmd)
        
        print("✅ Database restore completed successfully!")
        
        # Verify restore
        verify_restore(backup_info.get('metadata', {}))
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Restore failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        # Clean up temporary file if it exists
        try:
            if 'temp_path' in locals():
                os.unlink(temp_path)
        except:
            pass

def restore_snapshot(snapshot_path: Path) -> bool:
    """Restore from snapshot file."""
    print(f"🔄 Restoring from snapshot: {snapshot_path.name}")
    return restore_database(snapshot_path, create_snapshot=False, force=True)

def verify_restore(backup_metadata: Optional[Dict[str, Any]] = None) -> None:
    """Verify the restored database, including critical tables like ml_model_versions."""
    print("🔍 Verifying restore...")
    
    try:
        # Check database connection
        conn_cmd = get_docker_exec_cmd(
            'cti_postgres',
            f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c 'SELECT version();'"
        )
        result = subprocess.run(conn_cmd, capture_output=True, text=True, check=True)
        
        # Get table count
        tables_cmd = get_docker_exec_cmd(
            'cti_postgres',
            f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';\" -t"
        )
        tables_result = subprocess.run(tables_cmd, capture_output=True, text=True, check=True)
        table_count = tables_result.stdout.strip()
        
        print(f"✅ Database connection verified")
        print(f"📊 Tables restored: {table_count}")
        
        # Verify ml_model_versions table exists and has data
        try:
            ml_versions_cmd = get_docker_exec_cmd(
                'cti_postgres',
                f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM ml_model_versions;\" -t"
            )
            ml_versions_result = subprocess.run(ml_versions_cmd, capture_output=True, text=True, check=True)
            ml_versions_count = ml_versions_result.stdout.strip()
            
            print(f"🤖 ML Model Versions restored: {ml_versions_count}")
            
            # Compare with backup metadata if available
            if backup_metadata and 'ml_model_versions_count' in backup_metadata:
                expected_count = backup_metadata['ml_model_versions_count'].strip()
                if ml_versions_count == expected_count:
                    print(f"✅ ML model metric history verified: {ml_versions_count} versions match backup")
                else:
                    print(f"⚠️  ML model version count mismatch: restored {ml_versions_count}, expected {expected_count}")
        except subprocess.CalledProcessError:
            print("⚠️  Could not verify ml_model_versions table (table may not exist in backup)")
        except Exception as e:
            print(f"⚠️  Error verifying ml_model_versions: {e}")
        
        # Verify agent config tables
        try:
            # Check agentic_workflow_config
            agent_config_cmd = get_docker_exec_cmd(
                'cti_postgres',
                f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM agentic_workflow_config;\" -t"
            )
            agent_config_result = subprocess.run(agent_config_cmd, capture_output=True, text=True, check=True)
            agent_config_count = agent_config_result.stdout.strip()
            print(f"⚙️  Agent Workflow Config restored: {agent_config_count} configuration(s)")
            
            # Check agent_prompt_versions
            prompt_versions_cmd = get_docker_exec_cmd(
                'cti_postgres',
                f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM agent_prompt_versions;\" -t"
            )
            prompt_versions_result = subprocess.run(prompt_versions_cmd, capture_output=True, text=True, check=True)
            prompt_versions_count = prompt_versions_result.stdout.strip()
            print(f"📝 Agent Prompt Versions restored: {prompt_versions_count} version(s)")
            
            # Check app_settings
            app_settings_cmd = get_docker_exec_cmd(
                'cti_postgres',
                f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM app_settings;\" -t"
            )
            app_settings_result = subprocess.run(app_settings_cmd, capture_output=True, text=True, check=True)
            app_settings_count = app_settings_result.stdout.strip()
            print(f"🔧 Application Settings restored: {app_settings_count} setting(s)")
            
        except subprocess.CalledProcessError:
            print("⚠️  Could not verify agent config tables (tables may not exist in backup)")
        except Exception as e:
            print(f"⚠️  Error verifying agent config tables: {e}")
        
        # Verify source configurations
        try:
            # Check sources table
            sources_cmd = get_docker_exec_cmd(
                'cti_postgres',
                f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM sources;\" -t"
            )
            sources_result = subprocess.run(sources_cmd, capture_output=True, text=True, check=True)
            sources_count = sources_result.stdout.strip()
            
            # Check active sources
            active_sources_cmd = get_docker_exec_cmd(
                'cti_postgres',
                f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM sources WHERE active = true;\" -t"
            )
            active_sources_result = subprocess.run(active_sources_cmd, capture_output=True, text=True, check=True)
            active_sources_count = active_sources_result.stdout.strip()
            
            print(f"📰 Sources restored: {sources_count} source(s) ({active_sources_count} active)")
            
            # Check source_checks
            source_checks_cmd = get_docker_exec_cmd(
                'cti_postgres',
                f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM source_checks;\" -t"
            )
            source_checks_result = subprocess.run(source_checks_cmd, capture_output=True, text=True, check=True)
            source_checks_count = source_checks_result.stdout.strip()
            print(f"📊 Source Check History restored: {source_checks_count} check(s)")
            
        except subprocess.CalledProcessError:
            print("⚠️  Could not verify source tables (tables may not exist in backup)")
        except Exception as e:
            print(f"⚠️  Error verifying source tables: {e}")
        
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Verification failed: {e}")

def list_backups(backup_dir: str = 'backups') -> List[Path]:
    """List available backup files."""
    backup_path = Path(backup_dir)
    
    if not backup_path.exists():
        return []
    
    # Find all backup files (compressed and uncompressed)
    backups = []
    backups.extend(backup_path.glob('cti_scraper_backup_*.sql'))
    backups.extend(backup_path.glob('cti_scraper_backup_*.sql.gz'))
    
    return sorted(backups, reverse=True)  # Most recent first

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='CTI Scraper Database Restore Tool')
    parser.add_argument('backup_file', nargs='?', help='Backup file to restore')
    parser.add_argument('--backup-dir', default='backups', help='Backup directory (default: backups)')
    parser.add_argument('--no-snapshot', action='store_true', help='Skip creating pre-restore snapshot')
    parser.add_argument('--force', action='store_true', help='Force restore without confirmation')
    parser.add_argument('--list', action='store_true', help='List available backups')
    
    args = parser.parse_args()
    
    if args.list:
        backups = list_backups(args.backup_dir)
        if not backups:
            print("📁 No backups found.")
            return
        
        print("📋 Available backups:")
        print("-" * 80)
        
        for backup in backups:
            try:
                backup_info = validate_backup_file(backup)
                print(f"📄 {backup.name}")
                print(f"   📊 Size: {backup_info['file_size_mb']:.2f} MB")
                print(f"   🗜️  Compressed: {backup_info['is_compressed']}")
                
                if backup_info['metadata']:
                    timestamp = backup_info['metadata'].get('backup_timestamp', 'Unknown')
                    print(f"   📅 Created: {timestamp}")
                
                print()
            except Exception as e:
                print(f"📄 {backup.name} (invalid: {e})")
                print()
        
        return
    
    if not args.backup_file:
        print("❌ Please specify a backup file to restore.")
        print("Use --list to see available backups.")
        sys.exit(1)
    
    backup_path = Path(args.backup_file)
    
    # Confirm restore
    if not args.force:
        print(f"⚠️  WARNING: This will replace the current database!")
        print(f"   Backup file: {backup_path}")
        print(f"   Snapshot: {'No' if args.no_snapshot else 'Yes'}")
        
        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("❌ Restore cancelled.")
            sys.exit(0)
    
    # Perform restore
    success = restore_database(
        backup_path,
        create_snapshot=not args.no_snapshot,
        force=args.force
    )
    
    if success:
        print("🎉 Database restore completed successfully!")
    else:
        print("❌ Database restore failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()
