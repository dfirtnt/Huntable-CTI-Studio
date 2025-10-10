# Comprehensive Backup System

## Overview

The CTI Scraper comprehensive backup system provides complete system recovery capability, backing up not just the database but all critical components including ML models, training data, configuration files, and Docker volumes.

## Architecture

### Backup Components

The system backs up the following components:

1. **Database** - PostgreSQL dump with metadata
2. **ML Models** - Trained models (`models/` directory)
3. **Configuration** - Source configs and settings (`config/` directory)
4. **Training Data** - User feedback and training datasets (`outputs/` directory)
5. **Docker Volumes** - Persistent data volumes (postgres_data, redis_data, ollama_data)
6. **Logs** - Application logs (`logs/` directory)

### Backup Structure

```
/backups/system_backup_YYYYMMDD_HHMMSS/
├── database.sql.gz              # PostgreSQL dump
├── metadata.json                # Backup metadata and checksums
├── models/                      # ML models directory
│   └── content_filter.pkl
├── config/                      # Configuration files
│   └── sources.yaml
├── outputs/                     # Training data & feedback
│   ├── chunk_classification_feedback.csv
│   └── combined_training_data.csv
├── docker_volumes/              # Docker volume exports
│   ├── postgres_data.tar.gz
│   ├── redis_data.tar.gz
│   └── ollama_data.tar.gz
└── logs/                        # Application logs
    └── *.log
```

### Metadata Format

```json
{
  "timestamp": "2025-10-10T10:30:00",
  "version": "2.0",
  "backup_name": "system_backup_20251010_103000",
  "backup_path": "/path/to/backup",
  "components": {
    "database": {
      "filename": "database_20251010_103000.sql.gz",
      "size_mb": 45.2,
      "checksum": "sha256...",
      "database_size": "45 MB"
    },
    "models": {
      "files": 1,
      "size_mb": 0.5,
      "backup_dir": "/path/to/backup/models"
    },
    "config": {
      "files": 1,
      "size_mb": 0.04,
      "backup_dir": "/path/to/backup/config"
    },
    "outputs": {
      "files": 15,
      "size_mb": 2.3,
      "backup_dir": "/path/to/backup/outputs"
    },
    "docker_volume_postgres_data": {
      "filename": "postgres_data_20251010_103000.tar.gz",
      "size_mb": 45.2,
      "checksum": "sha256..."
    }
  },
  "total_size_mb": 93.04,
  "validation_errors": []
}
```

## Usage

### Command Line Interface

#### Create Backup

```bash
# Full system backup (default)
./scripts/backup_restore.sh create

# Database-only backup
./scripts/backup_restore.sh create --type database

# Files-only backup
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

#### Restore System

```bash
# Full system restore
./scripts/backup_restore.sh restore system_backup_20251010_103000

# Selective restore
./scripts/backup_restore.sh restore system_backup_20251010_103000 --components database,models

# Dry run
./scripts/backup_restore.sh restore system_backup_20251010_103000 --dry-run
```

#### Verify Backup

```bash
# Basic verification
./scripts/backup_restore.sh verify system_backup_20251010_103000

# With database restore test
./scripts/backup_restore.sh verify system_backup_20251010_103000 --test-restore
```

#### Prune Backups

```bash
# Show what would be pruned
./scripts/backup_restore.sh prune --dry-run

# Custom retention policy
./scripts/backup_restore.sh prune --daily 5 --weekly 2 --monthly 1 --max-size-gb 30

# Force prune without confirmation
./scripts/backup_restore.sh prune --force
```

### CLI Integration

```bash
# Create backup
python -m src.cli.main backup create

# Create database-only backup
python -m src.cli.main backup create --type database

# List backups
python -m src.cli.main backup list

# Restore system
python -m src.cli.main backup restore system_backup_20251010_103000

# Verify backup
python -m src.cli.main backup verify system_backup_20251010_103000

# Prune backups
python -m src.cli.main backup prune --dry-run

# Show statistics
python -m src.cli.main backup stats
```

## Retention Policy

### Default Policy

- **Daily**: Keep last 7 daily backups
- **Weekly**: Keep last 4 weekly backups  
- **Monthly**: Keep last 3 monthly backups
- **Size Limit**: Maximum 50 GB total backup size

### Configuration

Retention policies can be configured via:

1. **Command line options**:
   ```bash
   ./scripts/backup_restore.sh prune --daily 10 --weekly 5 --monthly 2 --max-size-gb 100
   ```

2. **Environment variables** (future enhancement):
   ```bash
   export BACKUP_RETENTION_DAILY=10
   export BACKUP_RETENTION_WEEKLY=5
   export BACKUP_RETENTION_MONTHLY=2
   export BACKUP_MAX_SIZE_GB=100
   ```

## Recovery Procedures

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

#### Automated Testing

```bash
# Test backup integrity
./scripts/backup_restore.sh verify system_backup_YYYYMMDD_HHMMSS --test-restore

# Test restore to temporary environment
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --dry-run
```

#### Manual Testing

1. **Create test environment**:
   ```bash
   # Copy backup to test location
   cp -r backups/system_backup_YYYYMMDD_HHMMSS /tmp/test_restore/
   
   # Restore to test environment
   ./scripts/restore_system.py /tmp/test_restore/system_backup_YYYYMMDD_HHMMSS --dry-run
   ```

2. **Verify components**:
   - Database connectivity and data integrity
   - ML model loading and functionality
   - Configuration file validity
   - Docker volume data accessibility

## Backup Testing Procedures

### Pre-Production Testing

1. **Create test backup**:
   ```bash
   ./scripts/backup_restore.sh create --type full
   ```

2. **Verify backup integrity**:
   ```bash
   ./scripts/backup_restore.sh verify system_backup_YYYYMMDD_HHMMSS --test-restore
   ```

3. **Test selective restore**:
   ```bash
   ./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS --components database --dry-run
   ```

### Production Validation

1. **Monthly full restore test**:
   - Restore to isolated environment
   - Verify all components function correctly
   - Document any issues or improvements

2. **Quarterly disaster recovery drill**:
   - Simulate complete system failure
   - Test full recovery procedure
   - Measure RTO/RPO performance

## Monitoring and Alerting

### Backup Health Monitoring

```bash
# Check backup status
./scripts/backup_restore.sh list

# Show backup statistics
./scripts/backup_restore.sh stats

# Verify latest backup
LATEST_BACKUP=$(./scripts/backup_restore.sh list | grep "system_backup_" | head -1 | awk '{print $2}')
./scripts/backup_restore.sh verify $LATEST_BACKUP
```

### Automated Monitoring (Future Enhancement)

1. **Daily backup verification**:
   - Automated backup creation
   - Integrity verification
   - Alert on failures

2. **Retention policy enforcement**:
   - Automated pruning
   - Size monitoring
   - Alert on policy violations

## Troubleshooting

### Common Issues

#### 1. Backup Creation Fails

**Symptoms**: Backup script exits with error
**Solutions**:
- Check Docker containers are running
- Verify disk space availability
- Check file permissions
- Review logs for specific errors

#### 2. Restore Fails

**Symptoms**: Restore process fails or hangs
**Solutions**:
- Verify backup integrity first
- Check Docker container status
- Ensure sufficient disk space
- Try selective component restore

#### 3. Checksum Validation Fails

**Symptoms**: Backup verification reports checksum mismatches
**Solutions**:
- Recreate backup from source
- Check for file corruption
- Verify backup storage integrity

### Debug Commands

```bash
# Check Docker containers
docker ps

# Check Docker volumes
docker volume ls

# Check disk space
df -h

# Check backup directory permissions
ls -la backups/

# Verbose backup creation
python3 scripts/backup_system.py --backup-dir backups --no-compress --no-verify
```

## Security Considerations

### Backup Encryption

- Backups are stored unencrypted by default
- Consider encrypting sensitive backups for long-term storage
- Use secure backup storage locations

### Access Control

- Restrict backup directory access
- Use secure backup transfer methods
- Implement backup access logging

### Data Privacy

- Ensure backups comply with data retention policies
- Consider data anonymization for test environments
- Implement secure backup disposal procedures

## Performance Optimization

### Backup Performance

- Use parallel backup execution (default)
- Consider backup timing during low-usage periods
- Monitor backup duration and optimize as needed

### Storage Optimization

- Use compression for large backups (default)
- Implement incremental backups (future enhancement)
- Consider backup deduplication (future enhancement)

### Network Optimization

- Use local backup storage when possible
- Consider backup streaming for remote storage
- Implement backup bandwidth throttling if needed

## Future Enhancements

### Planned Features

1. **Incremental Backups**
   - Only backup changed files
   - Reduce backup time and storage

2. **Backup Encryption**
   - Encrypt sensitive backup data
   - Key management integration

3. **Remote Backup Storage**
   - Cloud storage integration
   - Multi-region backup replication

4. **Automated Scheduling**
   - Cron-based backup scheduling
   - Configurable backup frequency

5. **Backup Monitoring Dashboard**
   - Web-based backup status
   - Alerting and notification system

### Integration Opportunities

1. **CI/CD Integration**
   - Automated backup testing
   - Deployment rollback capabilities

2. **Monitoring Integration**
   - Prometheus metrics
   - Grafana dashboards

3. **Notification Integration**
   - Slack/Teams notifications
   - Email alerts

## Support and Maintenance

### Regular Maintenance Tasks

1. **Weekly**:
   - Verify backup integrity
   - Check backup storage usage
   - Review backup logs

2. **Monthly**:
   - Test restore procedures
   - Review retention policies
   - Update documentation

3. **Quarterly**:
   - Disaster recovery drill
   - Performance optimization review
   - Security audit

### Documentation Updates

- Keep this document current with system changes
- Update recovery procedures based on testing results
- Document any custom configurations or procedures

### Support Contacts

- **System Administrator**: For backup system issues
- **Database Administrator**: For database-specific restore issues
- **DevOps Team**: For Docker and infrastructure issues
