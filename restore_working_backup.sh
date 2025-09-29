#!/bin/bash

# Restore a working database backup
# Usage: sh restore_working_backup.sh <backup_file>

if [ -z "$1" ]; then
    echo "❌ Error: Please provide backup file path"
    echo "Usage: sh restore_working_backup.sh <backup_file>"
    echo "Example: sh restore_working_backup.sh /Users/starlord/Downloads/cti_scraper_backup_working_20250929.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "📦 Starting restore from: $BACKUP_FILE"

# Verify backup integrity
echo "🔍 Verifying backup integrity..."
if ! gunzip -t "$BACKUP_FILE" 2>/dev/null; then
    echo "❌ Backup file is corrupted!"
    exit 1
fi
echo "✅ Backup integrity verified"

echo "🔄 Restoring database..."

# Stop applications that might be using the database
echo "⏹️  Stopping applications..."
docker stop cti_worker cti_web 2>/dev/null || true

# Wait for connections to close
sleep 5

# Execute restore
gunzip -c "$BACKUP_FILE" | docker exec -i cti_postgres psql -U cti_user -d postgres

if [ $? -eq 0 ]; then
    echo "✅ Database restored successfully!"
    
    # Restart applications
    echo "🔄 Restarting applications..."
    docker start cti_worker cti_web 2>/dev/null || true
    
    # Verify restore
    echo "🔍 Verifying restore..."
    ARTICLE_COUNT=$(docker exec cti_postgres psql -U cti_user -d cti_scraper -t -c "SELECT COUNT(*) FROM articles;" 2>/dev/null | tr -d ' \n')
    SOURCE_COUNT=$(docker exec cti_postgres psql -U cti_user -d cti_scraper -t -c "SELECT COUNT(*) FROM sources;" 2>/dev/null | tr -d ' \n')
    
    echo "📊 Restore verification:"
    echo "   - Articles: $ARTICLE_COUNT"
    echo "   - Sources: $SOURCE_COUNT"
    
    echo "🎉 Restore completed successfully!"
    
else
    echo "❌ Restore failed"
    
    # Restart applications even if restore failed
    docker start cti_worker cti_web 2>/dev/null || true
    exit 1
fi
