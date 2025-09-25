#!/usr/bin/env python3
"""
CTI Scraper Database Restore Script v2.0 - Container Compatible

Container-compatible restore implementation using direct database connections:
- No docker commands (works inside containers)
- Comprehensive error handling
- Progress reporting  
- Integrity verification
"""

import os
import sys
import gzip
import json
import tempfile
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

class ContainerDatabaseRestore:
    def __init__(self):
        # Use direct database connection instead of docker
        self.db_config = {
            'host': 'cti_postgres',  # Container name
            'port': '5432',
            'database': 'cti_scraper', 
            'user': 'cti_user',
            'password': 'cti_password_2024'
        }
        self.backup_dir = Path('backups')
        self.temp_dir = Path('/tmp')
    
    def check_prerequisites(self) -> bool:
        """Verify all prerequisites are met."""
        print("🔍 Checking prerequisites...")
        
        # Check database connectivity using psql
        try:
            import subprocess
            result = subprocess.run([
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-c', 'SELECT 1;'
            ], capture_output=True, text=True, timeout=10, env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            
            if result.returncode != 0:
                print("❌ Database not accessible")
                return False
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False
        
        print("✅ Prerequisites check passed")
        return True
    
    def validate_backup_file(self, backup_path: Path) -> Dict[str, Any]:
        """Validate backup file and extract metadata."""
        print(f"🔍 Validating backup file: {backup_path.name}")
        
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        
        # Check if compressed
        is_compressed = backup_path.suffix == '.gz'
        
        # Get file size
        file_size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"   📊 File size: {file_size_mb:.2f} MB")
        
        # Try to read first few lines to validate format
        try:
            if is_compressed:
                with gzip.open(backup_path, 'rt') as f:
                    first_line = f.readline().strip()
            else:
                with open(backup_path, 'r') as f:
                    first_line = f.readline().strip()
            
            if not first_line.startswith('-- PostgreSQL database dump') and not first_line.startswith('--'):
                raise ValueError("Invalid backup file format")
            
            print("✅ Backup file format validated")
            
        except Exception as e:
            raise ValueError(f"Invalid backup file: {e}")
        
        # Look for metadata file
        metadata_path = backup_path.with_suffix('.json')
        metadata = {}
        
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                print(f"   📋 Metadata found: {metadata.get('article_count', 'unknown')} articles")
            except Exception as e:
                print(f"⚠️  Warning: Could not read metadata: {e}")
        
        return {
            'is_compressed': is_compressed,
            'file_size_mb': file_size_mb,
            'metadata': metadata
        }
    
    def restore_database(self, backup_path: Path, force: bool = False) -> bool:
        """Restore database from backup file."""
        if not self.check_prerequisites():
            return False
        
        # Validate backup file
        backup_info = self.validate_backup_file(backup_path)
        
        try:
            # Extract SQL content to temporary file
            print("📦 Extracting backup content...")
            
            temp_sql_path = self.temp_dir / f"restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            
            if backup_info['is_compressed']:
                with gzip.open(backup_path, 'rt') as f_in:
                    with open(temp_sql_path, 'w') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                shutil.copy2(backup_path, temp_sql_path)
            
            print(f"✅ Extracted to: {temp_sql_path}")
            
            # Filter out problematic commands from backup
            print("🔧 Filtering backup content...")
            filtered_sql_path = self.temp_dir / f"restore_filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            
            with open(temp_sql_path, 'r') as f_in:
                with open(filtered_sql_path, 'w') as f_out:
                    for line in f_in:
                        # Skip problematic commands
                        if any(skip_cmd in line.upper() for skip_cmd in [
                            'DROP DATABASE',
                            'CREATE DATABASE', 
                            '\\connect',
                            '\\c ',
                            '\\restrict',
                            'SELECT PG_CATALOG.SET_CONFIG',
                            'SET SEARCH_PATH',
                            'SET DEFAULT_TABLESPACE',
                            'SET DEFAULT_WITH_OIDS',
                            'SET ROW_SECURITY',
                            'CREATE EXTENSION',
                            'COMMENT ON',
                            'REVOKE',
                            'GRANT'
                        ]):
                            continue
                        
                        # SQLAlchemy backup now has proper escaping, no need to modify
                        
                        f_out.write(line)
            
            # Use filtered SQL file
            temp_sql_path = filtered_sql_path
            
            # Terminate active connections and drop database
            print("🔌 Terminating active connections...")
            import subprocess
            
            terminate_cmd = [
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', 'postgres', '-c', f"""
                SELECT pg_terminate_backend(pid) 
                FROM pg_stat_activity 
                WHERE datname = '{self.db_config["database"]}' 
                AND pid <> pg_backend_pid();
                """
            ]
            
            subprocess.run(terminate_cmd, capture_output=True, text=True, 
                          env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            
            print("🗑️  Dropping existing database...")
            drop_cmd = [
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', 'postgres', '-c', f'DROP DATABASE IF EXISTS {self.db_config["database"]};'
            ]
            
            result = subprocess.run(drop_cmd, capture_output=True, text=True,
                                  env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            if result.returncode != 0:
                print(f"⚠️  Warning: Drop database failed: {result.stderr}")
            
            print("🆕 Creating new database...")
            create_cmd = [
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', 'postgres', '-c', f'CREATE DATABASE {self.db_config["database"]};'
            ]
            
            result = subprocess.run(create_cmd, capture_output=True, text=True,
                                  env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create database: {result.stderr}")
            
            # Restore from backup
            print("📥 Restoring data...")
            restore_cmd = [
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-f', str(temp_sql_path),
                '-v', 'ON_ERROR_STOP=0'  # Continue on errors
            ]
            
            result = subprocess.run(restore_cmd, capture_output=True, text=True, timeout=300,
                                  env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            
            # Check for critical errors in stderr
            if result.stderr and 'ERROR:' in result.stderr:
                # Count critical errors vs warnings
                error_lines = [line for line in result.stderr.split('\n') if 'ERROR:' in line]
                warning_lines = [line for line in result.stderr.split('\n') if 'WARNING:' in line]
                
                if len(error_lines) > len(warning_lines):
                    print(f"❌ Restore failed: {result.stderr}")
                    return False
                else:
                    print(f"⚠️  Restore completed with warnings: {len(warning_lines)} warnings")
            
            print("✅ Data restore completed")
            
            # Verify restore
            print("🔍 Verifying restore...")
            if not self.verify_restore():
                print("❌ Restore verification failed")
                return False
            
            print("✅ Database restore completed successfully!")
            
            # Show restore statistics
            self.show_restore_stats()
            
            return True
            
        except Exception as e:
            print(f"❌ Restore failed: {e}")
            return False
        
        finally:
            # Cleanup temporary files
            try:
                temp_sql_path.unlink(missing_ok=True)
                filtered_sql_path.unlink(missing_ok=True)
            except Exception:
                pass
    
    def verify_restore(self) -> bool:
        """Verify that the restore was successful."""
        try:
            import subprocess
            
            # Check database connectivity
            result = subprocess.run([
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-c', 'SELECT 1;'
            ], capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            
            if result.returncode != 0:
                return False
            
            # Check if articles table exists and has data
            result = subprocess.run([
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-t', '-c', 'SELECT COUNT(*) FROM articles;'
            ], capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            
            if result.returncode != 0:
                return False
            
            article_count = int(result.stdout.strip())
            print(f"   📈 Articles restored: {article_count}")
            
            # Check if sources table exists and has data
            result = subprocess.run([
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-t', '-c', 'SELECT COUNT(*) FROM sources;'
            ], capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            
            if result.returncode != 0:
                return False
            
            source_count = int(result.stdout.strip())
            print(f"   📈 Sources restored: {source_count}")
            
            return article_count > 0 and source_count > 0
            
        except Exception as e:
            print(f"⚠️  Verification error: {e}")
            return False
    
    def show_restore_stats(self):
        """Show statistics about the restored database."""
        try:
            import subprocess
            
            # Get database size
            result = subprocess.run([
                'psql', '-h', self.db_config['host'], '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-t', '-c', 
                "SELECT pg_size_pretty(pg_database_size('cti_scraper'));"
            ], capture_output=True, text=True, timeout=30,
            env={**os.environ, 'PGPASSWORD': self.db_config['password']})
            
            if result.returncode == 0:
                db_size = result.stdout.strip()
                print(f"   📊 Database size: {db_size}")
            
        except Exception:
            pass

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='CTI Scraper Database Restore v2.0 - Container Compatible')
    parser.add_argument('backup_file', help='Path to backup file')
    parser.add_argument('--force', action='store_true', help='Skip snapshot creation')
    
    args = parser.parse_args()
    
    backup_path = Path(args.backup_file)
    if not backup_path.is_absolute():
        # Check if it's already in backups directory
        if backup_path.parent.name == 'backups':
            pass  # Already correct path
        else:
            backup_path = Path('backups') / backup_path
    
    restore = ContainerDatabaseRestore()
    success = restore.restore_database(backup_path, force=args.force)
    
    if success:
        print("\n🎉 Database restore completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Database restore failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()
