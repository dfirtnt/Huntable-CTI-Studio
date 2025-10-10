# Automated Backup Configuration

## Overview

The CTI Scraper includes automated backup functionality that runs daily backups and weekly cleanup by default. This ensures your system is always protected with minimal manual intervention.

## Default Configuration

- **Daily Backup**: 2:00 AM (configurable)
- **Weekly Cleanup**: 3:00 AM on Sundays (configurable)
- **Retention Policy**: 7 daily + 4 weekly + 3 monthly backups
- **Max Size**: 50 GB total backup storage
- **Backup Type**: Full system backup (database + models + config + volumes)

## Setup Methods

### 1. Automated Setup (Recommended)

The automated setup script configures backups by default:

```bash
# Full setup with automated backups
./setup.sh

# Setup without automated backups
./setup.sh --no-backups

# Setup with custom backup time
./setup.sh --backup-time 1:30
```

### 2. Manual Setup

Use the dedicated backup setup script:

```bash
# Setup with default settings
./scripts/setup_automated_backups.sh

# Setup with custom settings
./scripts/setup_automated_backups.sh --backup-time 1:30 --daily 10 --weekly 5

# Setup with custom retention policy
./scripts/setup_automated_backups.sh --daily 7 --weekly 4 --monthly 3 --max-size-gb 100
```

## Configuration Options

### Backup Timing

```bash
# Custom backup time (24-hour format)
./scripts/setup_automated_backups.sh --backup-time 1:30

# Custom cleanup time
./scripts/setup_automated_backups.sh --cleanup-time 4:00
```

### Retention Policy

```bash
# Custom retention policy
./scripts/setup_automated_backups.sh --daily 10 --weekly 5 --monthly 2

# Size-based retention
./scripts/setup_automated_backups.sh --max-size-gb 100
```

### Backup Directory

```bash
# Custom backup directory
./scripts/setup_automated_backups.sh --backup-dir /path/to/backups
```

## Management Commands

### Check Status

```bash
# Show current backup status
./scripts/setup_automated_backups.sh --status
```

This shows:
- Whether automated backups are configured
- Recent backup activity
- Backup statistics and size
- Recent log entries

### Uninstall

```bash
# Remove automated backups
./scripts/setup_automated_backups.sh --uninstall
```

### Manual Backup Operations

```bash
# Create manual backup
./scripts/backup_restore.sh create

# List available backups
./scripts/backup_restore.sh list

# Verify backup integrity
./scripts/backup_restore.sh verify system_backup_YYYYMMDD_HHMMSS

# Restore from backup
./scripts/backup_restore.sh restore system_backup_YYYYMMDD_HHMMSS
```

## Cron Job Details

The automated backup system creates two cron jobs:

### Daily Backup Job

```bash
# Runs daily at 2:00 AM
0 2 * * * cd /path/to/CTIScraper && ./scripts/backup_restore.sh create --type full >> logs/backup.log 2>&1
```

### Weekly Cleanup Job

```bash
# Runs weekly on Sundays at 3:00 AM
0 3 * * 0 cd /path/to/CTIScraper && ./scripts/backup_restore.sh prune --daily 7 --weekly 4 --monthly 3 --max-size-gb 50 --force >> logs/backup.log 2>&1
```

## Monitoring and Logs

### Backup Logs

Backup activity is logged to `logs/backup.log`:

```bash
# View recent backup logs
tail -f logs/backup.log

# View all backup logs
cat logs/backup.log
```

### Log Rotation

Consider setting up log rotation for the backup log:

```bash
# Add to /etc/logrotate.d/cti-scraper
/path/to/CTIScraper/logs/backup.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
```

## Troubleshooting

### Common Issues

#### 1. Cron Jobs Not Running

**Symptoms**: No backup logs, no new backups created

**Solutions**:
- Check if cron service is running: `systemctl status cron`
- Verify cron jobs are installed: `crontab -l`
- Check cron logs: `journalctl -u cron`

#### 2. Permission Errors

**Symptoms**: Permission denied errors in backup logs

**Solutions**:
- Ensure scripts are executable: `chmod +x scripts/*.sh`
- Check file ownership: `ls -la scripts/`
- Run setup script as appropriate user

#### 3. Docker Container Issues

**Symptoms**: Backup fails with Docker errors

**Solutions**:
- Ensure Docker is running: `docker info`
- Check container status: `docker-compose ps`
- Verify container names match script expectations

#### 4. Disk Space Issues

**Symptoms**: Backup fails due to insufficient disk space

**Solutions**:
- Check available disk space: `df -h`
- Clean up old backups: `./scripts/backup_restore.sh prune --force`
- Increase retention policy size limit

### Debug Commands

```bash
# Check cron jobs
crontab -l

# Check cron service status
systemctl status cron

# View cron logs
journalctl -u cron -f

# Test backup manually
./scripts/backup_restore.sh create --type full

# Check backup status
./scripts/setup_automated_backups.sh --status

# View backup logs
tail -50 logs/backup.log
```

## Advanced Configuration

### Custom Backup Schedule

For more complex schedules, you can manually edit the cron jobs:

```bash
# Edit crontab
crontab -e

# Add custom schedule (e.g., every 6 hours)
0 */6 * * * cd /path/to/CTIScraper && ./scripts/backup_restore.sh create --type full >> logs/backup.log 2>&1
```

### Systemd Service (Alternative)

For systems without cron, you can use systemd timers:

```bash
# Create systemd service
sudo ./scripts/setup_automated_backups.sh --systemd

# Check timer status
systemctl status cti-scraper-backup.timer

# View timer logs
journalctl -u cti-scraper-backup.timer
```

### Backup Verification

Set up automated backup verification:

```bash
# Add to crontab for daily verification
30 2 * * * cd /path/to/CTIScraper && ./scripts/backup_restore.sh verify system_backup_$(date +\%Y\%m\%d) >> logs/backup.log 2>&1
```

## Security Considerations

### Backup Storage

- Store backups in secure locations
- Consider encrypting sensitive backups
- Implement proper access controls

### Log Security

- Monitor backup logs for security events
- Implement log rotation and retention
- Consider log aggregation for monitoring

### Network Security

- Use secure backup transfer methods
- Implement backup encryption for remote storage
- Monitor backup network traffic

## Performance Optimization

### Backup Performance

- Schedule backups during low-usage periods
- Monitor backup duration and optimize as needed
- Consider incremental backups for large datasets

### Storage Optimization

- Use compression for large backups
- Implement backup deduplication
- Monitor storage usage and cleanup

### Network Optimization

- Use local backup storage when possible
- Implement backup bandwidth throttling
- Consider backup streaming for remote storage

## Integration with Monitoring

### Health Checks

```bash
# Add to monitoring system
./scripts/setup_automated_backups.sh --status | grep -q "configured" && echo "OK" || echo "FAIL"
```

### Alerting

Set up alerts for:
- Backup failures
- Backup size exceeding limits
- Backup verification failures
- Disk space issues

### Metrics Collection

Collect metrics for:
- Backup duration
- Backup size
- Backup success rate
- Storage usage

## Best Practices

### Regular Maintenance

1. **Weekly**: Check backup status and logs
2. **Monthly**: Test restore procedures
3. **Quarterly**: Review retention policies
4. **Annually**: Update backup procedures

### Documentation

- Document custom configurations
- Maintain backup procedures
- Update disaster recovery plans

### Testing

- Regular restore testing
- Backup integrity verification
- Disaster recovery drills

## Support

For issues with automated backups:

1. Check the troubleshooting section above
2. Review backup logs for specific errors
3. Verify cron jobs are properly configured
4. Test manual backup operations
5. Check system resources (disk space, memory)

## Future Enhancements

### Planned Features

1. **Backup Encryption**: Encrypt sensitive backup data
2. **Remote Storage**: Cloud storage integration
3. **Incremental Backups**: Only backup changed files
4. **Backup Monitoring**: Web-based monitoring dashboard
5. **Alerting Integration**: Slack/Teams notifications

### Configuration Management

1. **Configuration Files**: YAML/JSON configuration
2. **Environment Variables**: Environment-based configuration
3. **Template System**: Backup configuration templates
4. **Validation**: Configuration validation and testing
