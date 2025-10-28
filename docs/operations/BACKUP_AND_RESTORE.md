# Backup and Restore System

Comprehensive guide for CTI Scraper backup and restore operations, including database-only backups, full system backups, and automated backup configuration.

## Table of Contents

1. [Quick Start](#quick-start)
2. [System Overview](#system-overview)
3. [Database-Only Backups](#database-only-backups)
4. [Full System Backups](#full-system-backups)
5. [Automated Backups](#automated-backups)
6. [Restore Procedures](#restore-procedures)
7. [Disaster Recovery](#disaster-recovery)
8. [Retention & Pruning](#retention--pruning)
9. [Monitoring & Troubleshooting](#monitoring--troubleshooting)

---

## Quick Start

### Create Backup

```bash
# Full system backup (recommended)
./scripts/backup_restore.sh create

# Database-only backup
./scripts/backup_restore.sh db-create
```

### Restore System

```bash
# Restore full system
./scripts/backup_restore.sh restore system_backup_20251010_103000

# Restore database only
./scripts/backup_restore.sh db-restore cti_scraper_backup_20250907_134653.sql.gz
```

### List Backups

```bash
# List all backups
./scripts/backup_restore.sh list

# List database-only backups
./scripts/backup_restore.sh db-list
```

---

## System Overview

### Backup Types

| Type | Components | Use Case | Speed |
|------|------------|----------|-------|
| **Database-Only** | PostgreSQL dump | Quick DB snapshot | Fast (~1-2 min) |
| **Full System** | Database + Models + Config + Volumes | Complete recovery | Slow (~5-10 min) |

### Components Backed Up

#### Database-Only Backup
- PostgreSQL database dump (compressed)
- Metadata JSON file

#### Full System Backup
1. **Database** - PostgreSQL dump with metadata
2. **ML Models** - Trained models (`models/` directory)
3. **Configuration** - Source configs and settings (`config/` directory)
4. **Training Data** - User feedback and training datasets (`outputs/` directory)
5. **Docker Volumes** - Persistent data (postgres_data, redis_data, ollama_data)
6. **Logs** - Application logs (`logs/` directory)

### Backup Structure

**Database-Only:**
```
backups/
├── cti_scraper_backup_20250907_134653.sql.gz
└── cti_scraper_backup_20250907_134653.json
```

**Full System:**
```
backups/system_backup_20251010_103000/
├── database.sql.gz
├── metadata.json
├── models/
├── config/
├── outputs/
├── docker_volumes/
│   ├── postgres_data.tar.gz
│   ├── redis_data.tar.gz
│   └── ollama_data.tar.gz
└── logs/
```

---

## Database-Only Backups

### Features

- **Automatic Compression**: gzip compression (~70-80% reduction)
- **Metadata Tracking**: JSON metadata with database stats
- **Timestamped Filenames**: `cti_scraper_backup_YYYYMMDD_HHMMSS.sql.gz`
- **Docker Integration**: Seamless container integration
- **Safety Checks**: Pre-restore validation and snapshots

### Commands

#### Create Backup
```bash
# Basic backup
python3 scripts/backup_database.py

# Using helper script
./scripts/backup_restore.sh db-create

# Custom location
python3 scripts/backup_database.py --backup-dir /path/to/backups

# Skip compression
python3 scripts/backup_database.py --no-compress
```

#### List Backups
```bash
./scripts/backup_restore.sh db-list
python3 scripts/backup_database.py --list
```

#### Restore Database
```bash
# Basic restore
./scripts/backup_restore.sh db-restore cti_scraper_backup_20250907_134653.sql.gz

# Force restore without confirmation
python3 scripts/restore_database.py backup.sql.gz --force

# Skip pre-restore snapshot
python3 scripts/restore_database.py backup.sql.gz --no-snapshot
```

### Metadata Format

```json
{
  "database_size": "15.2 MB",
  "table_stats": "table_name | inserts | updates | deletes",
  "backup_timestamp": "2025-09-07T13:46:53.394736",
  "postgres_version": "15-alpine"
}
```

---

## Full System Backups

### Architecture

Full system backups provide complete system recovery capability, backing up all critical components for disaster recovery.

### Metadata Format

```json
{
  "timestamp": "2025-10-10T10:30:00",
  "version": "2.0",
  "backup_name": "system_backup_20251010_103000",
  "components": {
    "database": {
      "filename": "database_20251010_103000.sql.gz",
      "size_mb": 45.2,
      "checksum": "sha256..."
    },
    "models": {
      "files": 1,
      "size_mb": 0.5
    },
    "config": {
      "files": 1,
      "size_mb": 0.04
    }
  },
  "total_size_mb": 93.04
}
```

### Commands

#### Create Backup

```bash
# Full system backup (default)
./scripts/backup_restore.sh create

# Database-only
./scripts/backup_restore.sh create --type database

# Files-only
./scripts/backup_restore.sh create --type files

# Custom options
./scripts/backup_restore.sh create --no-compress --no-verify
```

#### List Backups

```bash
# List all backups
./scripts/backup_restore.sh list

# Show detailed information
./scripts/backup_restore.sh list --show-details
```

#### Verify Backup

```bash
# Basic verification
./scripts/backup_restore.sh verify system_backup_20251010_103000

# With database restore test
./scripts/backup_restore.sh verify system_backup_20251010_103000 --test-restore
```

#### Restore System

```bash
# Full system restore
./scripts/backup_restore.sh restore system_backup_20251010_103000

# Selective restore
./scripts/backup_restore.sh restore system_backup_20251010_103000 --components database,models

# Dry run
./scripts/backup_restore.sh restore system_backup_20251010_103000 --dry-run
```

### CLI Integration

```bash
# Create backup
python -m src.cli.main backup create

# List backups
python -m src.cli.main backup list

# Restore system
python -m src.cli.main backup restore system_backup_20251010_103000

# Verify backup
python -m src.cli.main backup verify system_backup_20251010_103000

# Show statistics
python -m src.cli.main backup stats
```

---

## Automated Backups

### Default Configuration

- **Daily Backup**: 2:00 AM (configurable)
- **Weekly Cleanup**: 3:00 AM on Sundays (configurable)
- **Retention Policy**: 7 daily + 4 weekly + 3 monthly backups
- **Max Size**: 50 GB total backup storage
- **Backup Type**: Full system backup

### Setup Methods

#### Automated Setup (Recommended)

```bash
# Full setup with automated backups
./setup.sh

# Setup without automated backups
./setup.sh --no-backups

# Setup with custom backup time
./setup.sh --backup-time 1:30
```

#### Manual Setup

```bash
# Setup with default settings
./scripts/setup_automated_backups.sh

# Setup with custom settings
./scripts/setup_automated_backups.sh --backup-time 1:30 --daily 10 --weekly 5

# Setup with custom retention policy
./scripts/setup_automated_backups.sh --daily 7 --weekly 4 --monthly 3 --max-size-gb 100
```

### Configuration Options

#### Backup Timing

```bash
# Custom backup time (24-hour format)
./scripts/setup_automated_backups.sh --backup-time 1:30

# Custom cleanup time
./scripts/setup_automated_backups.sh --cleanup-time 4:00
```

#### Retention Policy

```bash
# Custom retention policy
./scripts/setup_automated_backups.sh --daily 10 --weekly 5 --monthly 2

# Size-based retention
./scripts/setup_automated_backups.sh --max-size-gb 100
```

#### Backup Directory

```bash
# Custom backup directory
./scripts/setup_automated_backups.sh --backup-dir /path/to/backups
```

### Management Commands

#### Check Status

```bash
# Show current backup status
./scripts/setup_automated_backups.sh --status
```

This shows:
- Whether automated backups are configured
- Recent backup activity
- Backup statistics and size
- Recent log entries

#### Uninstall

```bash
# Remove automated backups
./scripts/setup_automated_backups.sh --uninstall
```

### Cron Job Details

The automated backup system creates two cron jobs:

**Daily Backup Job:**
```bash
# Runs daily at 2:00 AM
0 2 * * * cd /path/to/CTIScraper && ./scripts/backup_restore.sh create --type full >> logs/backup.log 2>&1
```

**Weekly Cleanup Job:**
```bash
# Runs weekly on Sundays at 3:00 AM
0 3 * * 0 cd /path/to/CTIScraper && ./scripts/backup_restore.sh prune --daily 7 --weekly 4 --monthly 3 --max-size-gb 50 --force >> logs/backup.log 2>&1
```

### Monitoring Logs

```bash
# View recent backup logs
tail -f logs/backup.log

# View all backup logs
cat logs/backup.log
```

---

## Restore Procedures

### Database-Only Restore

#### Safety Features

- Validates backup file format before restore
- Creates pre-restore snapshots by default
- Confirms restore operation (unless `--force` is used)
- Verifies database connection after restore

#### Restore Steps

```bash
# 1. List available backups
./scripts/backup_restore.sh db-list

# 2. Restore from specific backup
./scripts/backup_restore.sh db-restore cti_scraper_backup_20250907_134653.sql.gz

# 3. Verify database
docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "SELECT COUNT(*) FROM articles;"
```

#### Restore from Snapshot

If a restore fails, restore from pre-restore snapshot:

```bash
# List snapshot files
ls backups/pre_restore_snapshot_*.sql

# Restore from snapshot
python3 scripts/restore_database.py backups/pre_restore_snapshot_20250907_140201.sql --force
```

### Full System Restore

#### Selective Component Restore

```bash
# Database only
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --components database

# ML models only
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --components models

# Config files only
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --components config

# Multiple components
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --components database,models,config
```

#### Verify After Restore

```bash
# Verify database
docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "SELECT COUNT(*) FROM articles;"

# Verify models
ls -la models/
python -c "import pickle; pickle.load(open('models/content_filter.pkl', 'rb'))"

# Verify config
cat config/sources.yaml

# Verify containers
docker-compose ps
```

---

## Disaster Recovery

### RTO/RPO Targets

- **Recovery Time Objective (RTO)**: < 30 minutes
- **Recovery Point Objective (RPO)**: < 24 hours (daily backups)

### Disaster Recovery Playbook

#### 1. Full System Recovery

```bash
# 1. Stop all services
docker-compose down

# 2. Restore from latest backup
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS

# 3. Start services
docker-compose up -d

# 4. Verify system health
./scripts/backup_restore.sh verify system_backup_YYYYMMDD_HHMMSS
```

#### 2. Database-Only Recovery

```bash
# 1. Restore database component only
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --components database

# 2. Verify database
docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "SELECT COUNT(*) FROM articles;"
```

#### 3. ML Model Recovery

```bash
# 1. Restore models component only
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --components models

# 2. Verify models
ls -la models/
python -c "import pickle; pickle.load(open('models/content_filter.pkl', 'rb'))"
```

### Recovery Testing

#### Pre-Production Testing

```bash
# 1. Create test backup
./scripts/backup_restore.sh create --type full

# 2. Verify backup integrity
./scripts/backup_restore.sh verify system_backup_YYYYMMDD_HHMMSS --test-restore

# 3. Test selective restore
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --components database --dry-run
```

#### Production Validation

1. **Monthly full restore test**: Restore to isolated environment
2. **Quarterly disaster recovery drill**: Simulate complete system failure

---

## Retention & Pruning

### Default Retention Policy

- **Daily**: Keep last 7 daily backups
- **Weekly**: Keep last 4 weekly backups  
- **Monthly**: Keep last 3 monthly backups
- **Size Limit**: Maximum 50 GB total backup size

### Pruning Commands

```bash
# Show what would be pruned (dry run)
./scripts/backup_restore.sh prune --dry-run

# Custom retention policy
./scripts/backup_restore.sh prune --daily 5 --weekly 2 --monthly 1 --max-size-gb 30

# Force prune without confirmation
./scripts/backup_restore.sh prune --force
```

### Manual Cleanup

```bash
# List old backups
./scripts/backup_restore.sh list

# Remove specific backup
rm -rf backups/system_backup_20251001_103000

# Remove database-only backup
rm -f backups/cti_scraper_backup_20250901_*.{sql.gz,json}
```

---

## Monitoring & Troubleshooting

### Health Checks

```bash
# Check backup status
./scripts/backup_restore.sh list

# Show backup statistics
./scripts/backup_restore.sh stats

# Verify latest backup
LATEST_BACKUP=$(./scripts/backup_restore.sh list | grep "system_backup_" | head -1 | awk '{print $2}')
./scripts/backup_restore.sh verify $LATEST_BACKUP
```

### Common Issues

#### 1. Container Not Running

**Error**: `PostgreSQL container 'cti_postgres' is not running!`

**Solution**:
```bash
docker-compose up -d
docker-compose ps
```

#### 2. Permission Denied

**Error**: `Permission denied`

**Solution**:
```bash
chmod +x scripts/*.sh scripts/*.py
```

#### 3. Disk Space Issues

**Error**: `No space left on device`

**Solution**:
```bash
# Check disk space
df -h

# Clean up old backups
./scripts/backup_restore.sh prune --force

# Remove Docker resources
docker system prune -a
```

#### 4. Backup Creation Fails

**Solutions**:
- Check Docker containers: `docker-compose ps`
- Verify disk space: `df -h`
- Check file permissions: `ls -la scripts/`
- Review logs: `tail -50 logs/backup.log`

#### 5. Restore Fails

**Solutions**:
- Verify backup integrity first
- Check Docker container status
- Ensure sufficient disk space
- Try selective component restore

#### 6. Checksum Validation Fails

**Solutions**:
- Recreate backup from source
- Check for file corruption
- Verify backup storage integrity

#### 7. Cron Jobs Not Running

**Solutions**:
- Check cron service: `systemctl status cron`
- Verify cron jobs: `crontab -l`
- Check cron logs: `journalctl -u cron`

### Debug Commands

```bash
# Check Docker containers
docker ps

# Check Docker volumes
docker volume ls

# Check disk space
df -h

# Check backup directory
ls -la backups/

# Check cron jobs
crontab -l

# View backup logs
tail -50 logs/backup.log

# Test backup manually
./scripts/backup_restore.sh create --type full
```

### Log Monitoring

```bash
# View recent backup logs
tail -f logs/backup.log

# Search for errors
grep -i error logs/backup.log

# Search for specific backup
grep "system_backup_20251010" logs/backup.log
```

---

## Best Practices

### Regular Backups

- Create backups before major updates
- Schedule regular automated backups (daily recommended)
- Keep multiple backup versions
- Test restore procedures regularly

### Backup Management

- Monitor backup directory size
- Clean up old backups periodically with retention policies
- Verify backup integrity regularly
- Store backups in secure locations

### Safety Measures

- Always create snapshots before restore
- Test restore in non-production environment first
- Use `--dry-run` for testing restore operations
- Keep legacy backups for rollback options

### Security

- Backup files contain sensitive data
- Use appropriate file permissions (600 or 640)
- Consider encryption for long-term storage
- Implement secure backup transfer methods

### Performance

- Schedule backups during low-usage periods (default: 2:00 AM)
- Use compression for large backups (enabled by default)
- Monitor backup duration and optimize as needed
- Consider incremental backups for very large datasets

### Regular Maintenance Tasks

**Weekly**:
- Check backup status and logs
- Verify backup integrity
- Monitor storage usage

**Monthly**:
- Test restore procedures
- Review retention policies
- Update documentation

**Quarterly**:
- Disaster recovery drill
- Performance optimization review
- Security audit

---

## Migration from Database-Only to Full System

### Why Migrate?

Full system backups provide:
- Complete system recovery (Database + ML models + config + volumes)
- Better organization with metadata
- Enhanced verification with checksum validation
- Selective component restore
- Automated retention management

### Migration Steps

```bash
# 1. Create first comprehensive backup
./scripts/backup_restore.sh create

# 2. Verify backup
./scripts/backup_restore.sh verify system_backup_YYYYMMDD_HHMMSS

# 3. Test restore
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --dry-run

# 4. Setup automated backups
./scripts/setup_automated_backups.sh
```

### Legacy Command Mapping

| Legacy Command | New Command | Notes |
|----------------|-------------|-------|
| `./scripts/backup_restore.sh create` | `./scripts/backup_restore.sh db-create` | Database-only backup |
| `./scripts/backup_restore.sh list` | `./scripts/backup_restore.sh db-list` | Database-only backups |
| `./scripts/backup_restore.sh restore` | `./scripts/backup_restore.sh db-restore` | Database-only restore |

---

## Future Enhancements

### Planned Features

1. **Incremental Backups**: Only backup changed files to reduce time and storage
2. **Backup Encryption**: Encrypt sensitive backup data with key management
3. **Remote Storage**: Cloud storage integration (S3, Azure, GCS)
4. **Multi-Region Replication**: Backup replication across regions
5. **Backup Monitoring Dashboard**: Web-based status and alerting
6. **Automated Scheduling**: Enhanced cron/systemd-based scheduling
7. **Notification Integration**: Slack/Teams/Email alerts

### Integration Opportunities

1. **CI/CD Integration**: Automated backup testing, deployment rollback
2. **Monitoring Integration**: Prometheus metrics, Grafana dashboards
3. **Notification Integration**: Real-time backup status alerts

---

## Support

For issues with backups:

1. Check troubleshooting section above
2. Review backup logs: `tail -50 logs/backup.log`
3. Verify Docker containers are running: `docker-compose ps`
4. Test manual backup operations
5. Check system resources (disk space, memory)

---

**Last Updated**: January 2025  
**Version**: 2.0

