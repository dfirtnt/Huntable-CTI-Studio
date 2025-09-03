#!/usr/bin/env python3
"""
Complete Database Reset Script for CTI Scraper
This will delete the existing database and create a fresh one
"""

import os
import sys
import shutil
from pathlib import Path

def main():
    print("🗑️  CTI Scraper Database Reset")
    print("=" * 50)
    
    # Database file path
    db_file = "threat_intel.db"
    
    # Check if database exists
    if not os.path.exists(db_file):
        print(f"✅ No existing database found at {db_file}")
        print("Ready to initialize fresh database!")
        return True
    
    # Show database info
    db_size = os.path.getsize(db_file) / (1024 * 1024)  # MB
    print(f"📊 Current database: {db_file}")
    print(f"📏 Size: {db_size:.2f} MB")
    
    # Confirmation
    print("\n⚠️  WARNING: This will permanently delete all collected data!")
    print("This includes:")
    print("  • All collected articles")
    print("  • Source configurations")
    print("  • TTP analysis results")
    print("  • Collection history")
    
    response = input("\n🤔 Are you sure you want to continue? (yes/no): ").lower().strip()
    
    if response not in ['yes', 'y']:
        print("❌ Database reset cancelled")
        return False
    
    # Backup the old database (optional)
    backup_response = input("\n💾 Create backup of current database? (yes/no): ").lower().strip()
    
    if backup_response in ['yes', 'y']:
        backup_file = f"{db_file}.backup.{int(os.time.time())}"
        try:
            shutil.copy2(db_file, backup_file)
            print(f"✅ Database backed up to: {backup_file}")
        except Exception as e:
            print(f"⚠️  Backup failed: {e}")
            print("Continuing without backup...")
    
    # Delete the database
    try:
        os.remove(db_file)
        print(f"✅ Database {db_file} deleted successfully")
        
        # Also remove any SQLite journal files
        journal_file = f"{db_file}-journal"
        if os.path.exists(journal_file):
            os.remove(journal_file)
            print(f"✅ Journal file removed")
        
        # Remove any WAL files
        wal_file = f"{db_file}-wal"
        if os.path.exists(wal_file):
            os.remove(wal_file)
            print(f"✅ WAL file removed")
        
        print("\n🎉 Database reset complete!")
        print("\n📋 Next steps:")
        print("1. Run: ./threat-intel init")
        print("2. Run: ./threat-intel collect")
        print("3. Start web server: ./start_web.sh")
        
        return True
        
    except Exception as e:
        print(f"❌ Error deleting database: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
