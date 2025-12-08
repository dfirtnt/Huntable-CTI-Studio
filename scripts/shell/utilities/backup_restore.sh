#!/bin/bash

# Database Backup and Restore Helper Script
# This script provides easy access to backup and restore functionality

set -e

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Please run this script from the CTI Scraper root directory."
    exit 1
fi

# Function to show usage
show_usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Database Backup & Restore Commands:"
    echo "  create [--backup-dir <dir>] [--no-compress]  - Create database backup"
    echo "  list [--backup-dir <dir>]                   - List available backups"
    echo "  restore <file> [--backup-dir <dir>] [--force] - Restore database"
    echo ""
    echo "Examples:"
    echo "  $0 create"
    echo "  $0 list"
    echo "  $0 restore cti_scraper_backup_20250907_134653.sql.gz"
    echo ""
    echo "Options:"
    echo "  --backup-dir <dir>    Backup directory (default: backups)"
    echo "  --no-compress         Skip compression"
    echo "  --force               Force restore without confirmation"
    echo "  --no-snapshot         Skip creating pre-restore snapshot"
}

# Check if command is provided
if [ $# -eq 0 ]; then
    show_usage
    exit 1
fi

# Set default backup directory
BACKUP_DIR="backups"

# Parse arguments
COMMAND="$1"
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --no-compress)
            NO_COMPRESS="--no-compress"
            shift
            ;;
        --force)
            FORCE="--force"
            shift
            ;;
        --no-snapshot)
            NO_SNAPSHOT="--no-snapshot"
            shift
            ;;
        *)
            if [ -z "$BACKUP_FILE" ]; then
                BACKUP_FILE="$1"
            fi
            shift
            ;;
    esac
done

# Execute commands
case "$COMMAND" in
    "create")
        echo "🔄 Creating database backup..."
        python3 scripts/backup_database.py --backup-dir "$BACKUP_DIR" $NO_COMPRESS
        ;;
    "list")
        echo "📋 Listing available backups..."
        python3 scripts/backup_database.py --list --backup-dir "$BACKUP_DIR"
        ;;
    "restore")
        if [ -z "$BACKUP_FILE" ]; then
            echo "❌ Error: backup restore requires <file>"
            show_usage
            exit 1
        fi
        echo "🔄 Restoring database from: $BACKUP_FILE"
        python3 scripts/restore_database.py "$BACKUP_FILE" --backup-dir "$BACKUP_DIR" $FORCE $NO_SNAPSHOT
        ;;
    *)
        echo "❌ Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac
