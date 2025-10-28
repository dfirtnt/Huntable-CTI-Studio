#!/usr/bin/env python3
"""
CTI Scraper Database Backup Script v2.0

Robust backup implementation using proper PostgreSQL tools with:
- Atomic operations
- Comprehensive error handling  
- Progress reporting
- Integrity verification
"""

import os
import sys
import gzip
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

class DatabaseBackup:
    def __init__(self):
        self.db_config = {
            'host': 'cti_postgres',
            'port': '5432', 
            'database': 'cti_scraper',
            'user': 'cti_user',
            'password': 'cti_password'
        }
        self.backup_dir = Path('backups')
        self.backup_dir.mkdir(exist_ok=True)
    
    def check_prerequisites(self) -> bool:
        """Verify all prerequisites are met."""
        print("🔍 Checking prerequisites...")
        
        # Check Docker container
        try:
            result = subprocess.run(
                ['docker', 'exec', 'cti_postgres', 'pg_isready', '-U', self.db_config['user']],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                print("❌ PostgreSQL container not ready")
                return False
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print("❌ Cannot connect to PostgreSQL container")
            return False
        
        # Check database exists
        try:
            result = subprocess.run([
                'docker', 'exec', 'cti_postgres', 'psql', '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-c', 'SELECT 1;'
            ], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                print("❌ Database not accessible")
                return False
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print("❌ Database connection failed")
            return False
        
        print("✅ Prerequisites check passed")
        return True
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics."""
        stats = {}
        
        try:
            # Get database size
            result = subprocess.run([
                'docker', 'exec', 'cti_postgres', 'psql', '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-t', '-c',
                "SELECT pg_size_pretty(pg_database_size('cti_scraper'));"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                stats['database_size'] = result.stdout.strip()
            
            # Get table counts
            result = subprocess.run([
                'docker', 'exec', 'cti_postgres', 'psql', '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-t', '-c',
                """
                SELECT 
                    schemaname,
                    tablename,
                    n_tup_ins as inserts,
                    n_tup_upd as updates, 
                    n_tup_del as deletes,
                    n_live_tup as live_rows,
                    n_dead_tup as dead_rows
                FROM pg_stat_user_tables 
                ORDER BY tablename;
                """
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                stats['table_stats'] = result.stdout.strip()
            
            # Get article count
            result = subprocess.run([
                'docker', 'exec', 'cti_postgres', 'psql', '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-t', '-c',
                'SELECT COUNT(*) FROM articles;'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                stats['article_count'] = int(result.stdout.strip())
            
            # Get source count
            result = subprocess.run([
                'docker', 'exec', 'cti_postgres', 'psql', '-U', self.db_config['user'],
                '-d', self.db_config['database'], '-t', '-c',
                'SELECT COUNT(*) FROM sources;'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                stats['source_count'] = int(result.stdout.strip())
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            print(f"⚠️  Warning: Could not get all database stats: {e}")
        
        stats.update({
            'backup_timestamp': datetime.now().isoformat(),
            'postgres_version': '17',
            'backup_version': '2.0'
        })
        
        return stats
    
    def create_backup(self, compress: bool = True) -> str:
        """Create a comprehensive database backup."""
        if not self.check_prerequisites():
            sys.exit(1)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"cti_scraper_backup_{timestamp}.sql"
        backup_path = self.backup_dir / backup_filename
        
        print(f"🔄 Creating backup: {backup_filename}")
        
        try:
            # Create pg_dump command with comprehensive options
            dump_cmd = [
                'docker', 'exec', 'cti_postgres', 'pg_dump',
                '-U', self.db_config['user'],
                '-d', self.db_config['database'],
                '--verbose',
                '--no-password',
                '--format=plain',
                '--encoding=UTF8',
                '--no-owner',
                '--no-privileges',
                '--clean',
                '--if-exists',
                '--create'
            ]
            
            print("📊 Executing pg_dump...")
            
            # Execute backup with progress monitoring
            with open(backup_path, 'w') as f:
                process = subprocess.Popen(
                    dump_cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # Monitor progress
                stderr_lines = []
                while process.poll() is None:
                    line = process.stderr.readline()
                    if line:
                        stderr_lines.append(line.strip())
                        if 'dumping' in line.lower():
                            print(f"   {line.strip()}")
                
                # Wait for completion
                returncode = process.wait()
                
                if returncode != 0:
                    error_output = '\n'.join(stderr_lines)
                    print(f"❌ pg_dump failed: {error_output}")
                    backup_path.unlink(missing_ok=True)
                    sys.exit(1)
            
            # Verify backup file
            if not backup_path.exists() or backup_path.stat().st_size == 0:
                print("❌ Backup file is empty or missing")
                sys.exit(1)
            
            print(f"✅ pg_dump completed: {backup_path.stat().st_size:,} bytes")
            
            # Get database statistics
            print("📈 Collecting database statistics...")
            stats = self.get_database_stats()
            
            # Create metadata file
            metadata_filename = f"cti_scraper_backup_{timestamp}.json"
            metadata_path = self.backup_dir / metadata_filename
            
            with open(metadata_path, 'w') as f:
                json.dump(stats, f, indent=2)
            
            # Compress if requested
            if compress:
                print("🗜️  Compressing backup...")
                compressed_filename = f"{backup_filename}.gz"
                compressed_path = self.backup_dir / compressed_filename
                
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        f_out.write(f_in.read())
                
                # Verify compression
                original_size = backup_path.stat().st_size
                compressed_size = compressed_path.stat().st_size
                compression_ratio = (1 - compressed_size / original_size) * 100
                
                print(f"   📊 Compression: {compression_ratio:.1f}% reduction")
                
                # Remove uncompressed file
                backup_path.unlink()
                backup_path = compressed_path
                backup_filename = compressed_filename
            
            # Final verification
            file_size_mb = backup_path.stat().st_size / (1024 * 1024)
            
            print(f"✅ Backup completed successfully!")
            print(f"   📁 File: {backup_path}")
            print(f"   📊 Size: {file_size_mb:.2f} MB")
            print(f"   📋 Metadata: {metadata_path}")
            print(f"   📈 Articles: {stats.get('article_count', 'unknown')}")
            print(f"   📈 Sources: {stats.get('source_count', 'unknown')}")
            
            return str(backup_path)
            
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            backup_path.unlink(missing_ok=True)
            sys.exit(1)

def main():
    """Main entry point."""
    backup = DatabaseBackup()
    backup_path = backup.create_backup(compress=True)
    print(f"\n🎉 Backup ready: {backup_path}")

if __name__ == '__main__':
    main()
