#!/bin/bash

# Comprehensive Backup and Restore Helper Script for CTI Scraper
# This script provides easy access to both legacy and comprehensive backup/restore functionality

set -e

# Function to check and start Docker on macOS
ensure_docker_running() {
    local max_wait=300  # 5 minutes max wait
    local wait_interval=5
    local elapsed=0
    
    # Ensure PATH includes common directories for cron
    export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
    
    # Check if Docker is already running
    if docker info > /dev/null 2>&1; then
        return 0
    fi
    
    # Try to start Docker Desktop on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "⚠️  Docker is not running. Attempting to start Docker Desktop..."
        
        # Try to start Docker Desktop (works even from cron if user is logged in)
        if [ -d "/Applications/Docker.app" ]; then
            /usr/bin/open -a Docker 2>/dev/null || true
        elif [ -d "/Applications/Docker Desktop.app" ]; then
            /usr/bin/open -a "Docker Desktop" 2>/dev/null || true
        else
            echo "⚠️  Docker Desktop not found in standard location. Please start it manually."
            # Try to find Docker Desktop in other locations
            local docker_path=$(mdfind "kMDItemKind == 'Application' && kMDItemDisplayName == 'Docker Desktop'" 2>/dev/null | head -1)
            if [ -n "$docker_path" ]; then
                /usr/bin/open -a "$docker_path" 2>/dev/null || true
            fi
        fi
        
        # Wait for Docker to become available
        echo "⏳ Waiting for Docker to start (max 5 minutes)..."
        while [ $elapsed -lt $max_wait ]; do
            if docker info > /dev/null 2>&1; then
                echo "✅ Docker is now running"
                # Additional wait for containers to be ready
                sleep 10
                return 0
            fi
            sleep $wait_interval
            elapsed=$((elapsed + wait_interval))
            if [ $((elapsed % 30)) -eq 0 ]; then
                echo "⏳ Still waiting for Docker... (${elapsed}s elapsed)"
            fi
        done
        
        echo "❌ Docker failed to start within ${max_wait} seconds"
        echo "⚠️  Note: Docker Desktop may require user login or manual start on macOS"
        return 1
    else
        echo "❌ Docker is not running. Please start Docker first."
        return 1
    fi
}

# Ensure Docker is running before proceeding
if ! ensure_docker_running; then
    echo "❌ Cannot proceed without Docker. Exiting."
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
    echo "Comprehensive System Backup & Restore Commands:"
    echo "  create [--type full|database|files] [--backup-dir <dir>] [--no-compress] [--no-verify]"
    echo "  restore <backup_name> [--components <list>] [--backup-dir <dir>] [--force] [--dry-run]"
    echo "  list [--backup-dir <dir>] [--show-details]"
    echo "  verify <backup_name> [--backup-dir <dir>] [--test-restore]"
    echo "  prune [--backup-dir <dir>] [--daily N] [--weekly N] [--monthly N] [--max-size-gb N] [--dry-run] [--force]"
    echo ""
    echo "Legacy Database-Only Commands (for backward compatibility):"
    echo "  db-create [--backup-dir <dir>] [--no-compress]  - Create database-only backup"
    echo "  db-restore <file> [--backup-dir <dir>] [--force] - Restore database-only backup"
    echo "  db-list [--backup-dir <dir>]                   - List database-only backups"
    echo ""
    echo "Examples:"
    echo "  $0 create                                    # Create full system backup"
    echo "  $0 create --type database                   # Create database-only backup"
    echo "  $0 list                                     # List all backups"
    echo "  $0 restore system_backup_20251010_143022    # Restore full system"
    echo "  $0 restore system_backup_20251010_143022 --components database,models  # Selective restore"
    echo "  $0 verify system_backup_20251010_143022     # Verify backup integrity"
    echo "  $0 prune --dry-run                          # Show what would be pruned"
    echo "  $0 prune --daily 5 --weekly 2 --monthly 1   # Custom retention policy"
    echo ""
    echo "Options:"
    echo "  --backup-dir <dir>      Backup directory (default: backups)"
    echo "  --type <type>           Backup type: full, database, files (default: full)"
    echo "  --components <list>     Comma-separated components to restore (default: all)"
    echo "  --no-compress           Skip compression"
    echo "  --no-verify             Skip file validation"
    echo "  --force                 Force operations without confirmation"
    echo "  --dry-run               Show what would be done without making changes"
    echo "  --test-restore          Test database restore during verification"
    echo "  --daily N               Keep last N daily backups (default: 7)"
    echo "  --weekly N              Keep last N weekly backups (default: 4)"
    echo "  --monthly N             Keep last N monthly backups (default: 3)"
    echo "  --max-size-gb N         Maximum total backup size in GB (default: 50)"
    echo "  --show-details          Show detailed backup information"
}

# Check if command is provided
if [ $# -eq 0 ]; then
    show_usage
    exit 1
fi

# Set default values
BACKUP_DIR="backups"
BACKUP_TYPE="full"
COMPONENTS=""
NO_COMPRESS=""
NO_VERIFY=""
FORCE=""
DRY_RUN=""
TEST_RESTORE=""
DAILY=""
WEEKLY=""
MONTHLY=""
MAX_SIZE_GB=""
SHOW_DETAILS=""

# Parse arguments
COMMAND="$1"
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-dir)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --type)
            BACKUP_TYPE="$2"
            shift 2
            ;;
        --components)
            COMPONENTS="--components $2"
            shift 2
            ;;
        --no-compress)
            NO_COMPRESS="--no-compress"
            shift
            ;;
        --no-verify)
            NO_VERIFY="--no-verify"
            shift
            ;;
        --force)
            FORCE="--force"
            shift
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --test-restore)
            TEST_RESTORE="--test-restore"
            shift
            ;;
        --daily)
            DAILY="--daily $2"
            shift 2
            ;;
        --weekly)
            WEEKLY="--weekly $2"
            shift 2
            ;;
        --monthly)
            MONTHLY="--monthly $2"
            shift 2
            ;;
        --max-size-gb)
            MAX_SIZE_GB="--max-size-gb $2"
            shift 2
            ;;
        --show-details)
            SHOW_DETAILS="--show-details"
            shift
            ;;
        *)
            if [ -z "$BACKUP_NAME" ]; then
                BACKUP_NAME="$1"
            fi
            shift
            ;;
    esac
done

# Execute commands
case "$COMMAND" in
    "create")
        echo "🚀 Creating comprehensive system backup..."
        case "$BACKUP_TYPE" in
            "full")
                python3 scripts/backup_system.py --backup-dir "$BACKUP_DIR" $NO_COMPRESS $NO_VERIFY
                ;;
            "database")
                echo "📊 Creating database-only backup..."
                python3 scripts/backup_database.py --backup-dir "$BACKUP_DIR" $NO_COMPRESS
                ;;
            "files")
                echo "📁 Creating files-only backup..."
                python3 scripts/backup_system.py --backup-dir "$BACKUP_DIR" $NO_COMPRESS $NO_VERIFY
                ;;
            *)
                echo "❌ Invalid backup type: $BACKUP_TYPE"
                echo "Valid types: full, database, files"
                exit 1
                ;;
        esac
        ;;
    
    "restore")
        if [ -z "$BACKUP_NAME" ]; then
            echo "❌ Error: restore requires <backup_name>"
            show_usage
            exit 1
        fi
        echo "🔄 Restoring system from: $BACKUP_NAME"
        python3 scripts/restore_system.py "$BACKUP_NAME" --backup-dir "$BACKUP_DIR" $COMPONENTS $FORCE $DRY_RUN
        ;;
    
    "list")
        echo "📋 Listing available backups..."
        if [ -n "$SHOW_DETAILS" ]; then
            echo "📊 System backups:"
            python3 scripts/backup_system.py --list --backup-dir "$BACKUP_DIR"
            echo ""
            echo "📊 Database-only backups:"
            python3 scripts/backup_database.py --list --backup-dir "$BACKUP_DIR"
        else
            python3 scripts/backup_system.py --list --backup-dir "$BACKUP_DIR"
        fi
        ;;
    
    "verify")
        if [ -z "$BACKUP_NAME" ]; then
            echo "❌ Error: verify requires <backup_name>"
            show_usage
            exit 1
        fi
        echo "🔍 Verifying backup: $BACKUP_NAME"
        python3 scripts/verify_backup.py "$BACKUP_NAME" --backup-dir "$BACKUP_DIR" $TEST_RESTORE
        ;;
    
    "prune")
        echo "🧹 Pruning old backups..."
        python3 scripts/prune_backups.py --backup-dir "$BACKUP_DIR" $DAILY $WEEKLY $MONTHLY $MAX_SIZE_GB $DRY_RUN $FORCE
        ;;
    
    # Legacy database-only commands for backward compatibility
    "db-create")
        echo "📊 Creating database-only backup..."
        python3 scripts/backup_database.py --backup-dir "$BACKUP_DIR" $NO_COMPRESS
        ;;
    
    "db-restore")
        if [ -z "$BACKUP_NAME" ]; then
            echo "❌ Error: db-restore requires <file>"
            show_usage
            exit 1
        fi
        echo "🔄 Restoring database from: $BACKUP_NAME"
        python3 scripts/restore_database.py "$BACKUP_NAME" --backup-dir "$BACKUP_DIR" $FORCE
        ;;
    
    "db-list")
        echo "📋 Listing database-only backups..."
        python3 scripts/backup_database.py --list --backup-dir "$BACKUP_DIR"
        ;;
    
    *)
        echo "❌ Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac
