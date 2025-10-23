# Database Backup and Restore Guide

This guide covers the database backup and restore functionality for the CTI Scraper application.

## Overview

The CTI Scraper includes comprehensive database backup and restore capabilities that allow you to:
- Create compressed backups with metadata
- List and validate existing backups
- Restore databases with safety checks and snapshots
- Use both command-line scripts and CLI integration

> **Note**: This document covers the legacy database-only backup system. For comprehensive system backups including ML models, configuration files, and Docker volumes, see [BACKUP_SYSTEM.md](development/BACKUP_SYSTEM.md).

## Quick Start

### Using the Helper Script (Recommended)

```bash
# Create a database-only backup
./scripts/backup_restore.sh db-create

# List available database backups
./scripts/backup_restore.sh db-list

# Restore from database backup
./scripts/backup_restore.sh db-restore cti_scraper_backup_20250907_134653.sql.gz
```

### Using the Comprehensive System Backup (Recommended)

```bash
# Create a full system backup (includes database + models + config + volumes)
./scripts/backup_restore.sh create

# List all backups
./scripts/backup_restore.sh list

# Restore full system
./scripts/backup_restore.sh restore system_backup_20251010_103000
```

### Using Direct Scripts

```bash
# Create a backup
python3 scripts/backup_database.py

# List backups
python3 scripts/backup_database.py --list

# Restore database
python3 scripts/restore_database.py cti_scraper_backup_20250907_134653.sql.gz
```

## Backup Features

### Automatic Compression
- Backups are automatically compressed using gzip
- Reduces file size by ~70-80%
- Use `--no-compress` to skip compression

### Metadata Tracking
- Each backup includes a JSON metadata file
- Contains database size, table statistics, and timestamp
- Helps with backup validation and management

### Timestamped Filenames
- Format: `cti_scraper_backup_YYYYMMDD_HHMMSS.sql.gz`
- Easy to identify and sort backups chronologically

### Docker Integration
- Works seamlessly with Docker containers
- Automatically detects running PostgreSQL container
- Uses `docker exec` for database operations

## Restore Features

### Safety Checks
- Validates backup file format before restore
- Creates pre-restore snapshots by default
- Confirms restore operation (unless `--force` is used)

### Snapshot Protection
- Automatically creates snapshot before restore
- Can restore from snapshot if main restore fails
- Use `--no-snapshot` to skip snapshot creation

### Database Verification
- Verifies database connection after restore
- Reports table count and basic statistics
- Ensures restore completed successfully

## Command Reference

### Backup Commands

#### Create Backup
```bash
# Basic backup
./scripts/backup_restore.sh create

# Custom backup directory
./scripts/backup_restore.sh create --backup-dir /path/to/backups

# Uncompressed backup
./scripts/backup_restore.sh create --no-compress
```

#### List Backups
```bash
# List all backups
./scripts/backup_restore.sh list

# List from specific directory
./scripts/backup_restore.sh list --backup-dir /path/to/backups
```

### Restore Commands

#### Restore Database
```bash
# Basic restore
./scripts/backup_restore.sh restore cti_scraper_backup_20250907_134653.sql.gz

# Force restore without confirmation
./scripts/backup_restore.sh restore cti_scraper_backup_20250907_134653.sql.gz --force

# Skip snapshot creation
./scripts/backup_restore.sh restore cti_scraper_backup_20250907_134653.sql.gz --no-snapshot

# Custom backup directory
./scripts/backup_restore.sh restore backup.sql.gz --backup-dir /path/to/backups
```

## File Structure

```
backups/
├── cti_scraper_backup_20250907_134653.sql.gz    # Compressed backup
├── cti_scraper_backup_20250907_134653.json      # Metadata file
├── cti_scraper_backup_20250907_140201.sql.gz    # Another backup
└── cti_scraper_backup_20250907_140201.json      # Another metadata file
```

## Metadata File Format

```json
{
  "database_size": "15.2 MB",
  "table_stats": "table_name | inserts | updates | deletes",
  "backup_timestamp": "2025-09-07T13:46:53.394736",
  "postgres_version": "15-alpine"
}
```

## Best Practices

### Regular Backups
- Create backups before major updates
- Schedule regular backups (daily/weekly)
- Keep multiple backup versions

### Backup Management
- Monitor backup directory size
- Clean up old backups periodically
- Test restore procedures regularly

### Safety Measures
- Always create snapshots before restore
- Verify backups after creation
- Test restore in non-production environment first

## Troubleshooting

### Common Issues

#### Container Not Running
```
❌ PostgreSQL container 'cti_postgres' is not running!
```
**Solution**: Start the CTI Scraper stack first:
```bash
docker-compose up -d
```

#### Invalid Backup File
```
❌ Invalid PostgreSQL backup file
```
**Solution**: Ensure the file is a valid PostgreSQL dump created by pg_dump

#### Permission Denied
```
❌ Permission denied
```
**Solution**: Make scripts executable:
```bash
chmod +x scripts/backup_database.py scripts/restore_database.py
chmod +x backup_restore.sh
```

### Recovery Procedures

#### Restore from Snapshot
If a restore fails, the system automatically attempts to restore from the pre-restore snapshot:
```bash
# The restore script will automatically try to restore from snapshot
# Check the backup directory for snapshot files
ls backups/pre_restore_snapshot_*.sql
```

#### Manual Recovery
If automatic recovery fails, you can manually restore from snapshot:
```bash
python3 scripts/restore_database.py backups/pre_restore_snapshot_20250907_140201.sql --force
```

## Integration with CI/CD

### Automated Backups
```bash
#!/bin/bash
# Add to your CI/CD pipeline
./scripts/backup_restore.sh create --backup-dir /backups/ci
```

### Backup Validation
```bash
#!/bin/bash
# Validate backup integrity
python3 scripts/restore_database.py --list --backup-dir /backups/ci
```

## Security Considerations

- Backup files contain sensitive data
- Store backups in secure locations
- Use appropriate file permissions
- Consider encryption for long-term storage

## Performance Notes

- Backup size depends on database content
- Compression reduces file size significantly
- Restore time varies with database size
- Consider disk space for backup storage

## Migration to Comprehensive Backup System

### Why Migrate?

The comprehensive backup system provides:
- **Complete system recovery**: Database + ML models + configuration + Docker volumes
- **Better organization**: Structured backup directories with metadata
- **Enhanced verification**: Checksum validation and integrity testing
- **Selective restore**: Restore only the components you need
- **Retention management**: Automated cleanup of old backups

### Migration Steps

1. **Create your first comprehensive backup**:
   ```bash
   ./scripts/backup_restore.sh create
   ```

2. **Verify the backup**:
   ```bash
   ./scripts/backup_restore.sh verify system_backup_YYYYMMDD_HHMMSS
   ```

3. **Test restore**:
   ```bash
   ./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --dry-run
   ```

4. **Keep legacy backups**: The old database-only backups remain compatible and can be restored using the legacy commands.

### Legacy Command Mapping

| Legacy Command | New Command | Notes |
|----------------|-------------|-------|
| `./scripts/backup_restore.sh create` | `./scripts/backup_restore.sh db-create` | Database-only backup |
| `./scripts/backup_restore.sh list` | `./scripts/backup_restore.sh db-list` | Database-only backups |
| `./scripts/backup_restore.sh restore` | `./scripts/backup_restore.sh db-restore` | Database-only restore |

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify Docker containers are running
3. Check file permissions and paths
4. Review backup file integrity
5. For comprehensive backup issues, see [BACKUP_SYSTEM.md](development/BACKUP_SYSTEM.md)
