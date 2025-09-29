#!/bin/bash

# Create a working database backup script
# This creates clean backups that can be restored without foreign key issues

echo "📦 Creating working CTI Scraper backup..."

# Set timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/Users/starlord/Downloads/cti_scraper_backup_working_$TIMESTAMP.sql.gz"

echo "🔄 Generating backup: $BACKUP_FILE"

# Create backup with proper options
docker exec cti_postgres pg_dump \
    -U cti_user \
    -d cti_scraper \
    --clean \
    --if-exists \
    --create \
    --disable-triggers \
    --no-owner \
    --no-privileges \
    --verbose \
  | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Backup created successfully!"
    echo "📁 Location: $BACKUP_FILE"
    
    # Show file size
    FILE_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
    echo "📏 Size: $FILE_SIZE"
    
    # Test extract to verify integrity
    echo "🔍 Testing backup integrity..."
    if gunzip -t "$BACKUP_FILE" 2>/dev/null; then
        echo "✅ Backup integrity verified"
    else
        echo "❌ Backup integrity check failed"
        rm "$BACKUP_FILE"
        exit 1
    fi
    
else
    echo "❌ Backup failed"
    exit 1
fi

echo "🎉 Working backup ready!"
echo ""
echo "To restore this backup:"
echo "1. sh restore_working_backup.sh $BACKUP_FILE"
