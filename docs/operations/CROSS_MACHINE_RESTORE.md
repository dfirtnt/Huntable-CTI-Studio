# Cross-Machine Backup Restore

## Overview

Backups created on one computer can be restored on another computer. The backup format is portable and doesn't contain machine-specific paths.

## Prerequisites

1. **Docker containers running** on the target machine:
   ```bash
   docker compose up -d
   ```

2. **Backup file/directory** copied to the target machine

3. **Same Docker volume names** (default: `postgres_data`, `redis_data`)

## Restore Methods

### Method 1: Copy Backup to Default Location

1. **Copy backup directory** to the `backups/` folder:
   ```bash
   # From source machine
   scp -r system_backup_20260121_113825 user@target:/path/to/Huntable-CTI-Studio/backups/
   
   # Or use USB drive, network share, etc.
   ```

2. **Restore using backup name**:
   ```bash
   cd /path/to/Huntable-CTI-Studio
   python3 scripts/restore_system.py system_backup_20260121_113825
   ```

### Method 2: Restore from Absolute Path

If the backup is in a different location:

```bash
python3 scripts/restore_system.py /path/to/backup/system_backup_20260121_113825
```

### Method 3: Via Web UI

1. Copy backup directory to `backups/` folder
2. Open Settings → Backup Actions
3. Click "Restore from Backup"
4. Select the backup from the list

## What Gets Restored

### Portable Components (Cross-Machine Safe)

✅ **Database** - SQL dump (fully portable)  
✅ **Models** - ML model files (`.pkl`, `.joblib`, etc.)  
✅ **Config** - Configuration files (YAML, JSON)  
✅ **Outputs** - Training data and generated content  
✅ **Logs** - Application logs  

### Docker Volumes (Requires Matching Names)

⚠️ **Docker Volumes** - Restored if volume names match:
- `postgres_data` (default)
- `redis_data` (default)

**Note**: If your target machine uses different volume names, you can:
1. Restore without Docker volumes: `--components database,models,config`
2. Manually restore volumes after renaming them

## Important Considerations

### 1. Database Credentials

The restore script uses default credentials. If your target machine has different credentials:

**Option A**: Set environment variables before restore:
```bash
export POSTGRES_PASSWORD=your_password
python3 scripts/restore_system.py system_backup_20260121_113825
```

**Option B**: Edit `scripts/restore_system.py` DB_CONFIG section temporarily

### 2. Docker Container Names

The restore script expects:
- `cti_postgres` (PostgreSQL container)
- `cti_redis` (Redis container)

If your containers have different names, update `scripts/restore_system.py` or use `docker compose` which sets these names automatically.

### 3. Selective Restore

You can restore only specific components:

```bash
# Restore database and models only
python3 scripts/restore_system.py system_backup_20260121_113825 \
  --components database,models

# Restore everything except Docker volumes
python3 scripts/restore_system.py system_backup_20260121_113825 \
  --components database,models,config,outputs,logs
```

### 4. Backup Format Compatibility

- **Version 1.0** backups: ✅ Supported
- **Version 2.0** backups: ✅ Supported
- Older formats: May require migration

## Step-by-Step Example

### Source Machine (Computer A)

```bash
# Create backup
cd /path/to/Huntable-CTI-Studio
python3 scripts/backup_system.py

# Backup created: backups/system_backup_20260121_113825/
```

### Transfer Backup

```bash
# Option 1: SCP
scp -r backups/system_backup_20260121_113825 user@target:/path/to/Huntable-CTI-Studio/backups/

# Option 2: USB drive
# Copy entire backup directory to USB, then copy to target machine

# Option 3: Network share
# Copy to shared network location, then copy from target machine
```

### Target Machine (Computer B)

```bash
# 1. Ensure Docker containers are running
cd /path/to/Huntable-CTI-Studio
docker compose up -d

# 2. Verify backup is in place
ls -la backups/system_backup_20260121_113825/

# 3. Restore (with snapshot for safety)
python3 scripts/restore_system.py system_backup_20260121_113825

# 4. Verify restore
# Check web UI or run verification
```

## Troubleshooting

### "Backup directory not found"

**Solution**: Use absolute path:
```bash
python3 scripts/restore_system.py /full/path/to/system_backup_20260121_113825
```

### "PostgreSQL container not running"

**Solution**: Start containers:
```bash
docker compose up -d
```

### "Database restore failed: connection refused"

**Solution**: Check container name and credentials:
```bash
docker ps | grep postgres
# Should show: cti_postgres
```

### "Volume restore failed"

**Solution**: Restore without volumes first:
```bash
python3 scripts/restore_system.py system_backup_20260121_113825 \
  --components database,models,config,outputs,logs
```

### Verification Failures

If verification fails for empty directories (outputs/logs), this is normal - empty directories are valid. The restore succeeded.

## Best Practices

1. **Test restore first**: Use `--dry-run` to verify backup structure:
   ```bash
   python3 scripts/restore_system.py system_backup_20260121_113825 --dry-run
   ```

2. **Create snapshot**: Always create a snapshot before restore (default behavior):
   ```bash
   # Snapshot is created automatically unless --no-snapshot is used
   ```

3. **Verify backup integrity**: Check backup before transferring:
   ```bash
   python3 scripts/verify_backup.py system_backup_20260121_113825
   ```

4. **Selective restore**: Restore components incrementally if needed:
   ```bash
   # First: Database only
   python3 scripts/restore_system.py system_backup_20260121_113825 \
     --components database
   
   # Then: Models and config
   python3 scripts/restore_system.py system_backup_20260121_113825 \
     --components models,config
   ```

## Security Notes

- Backups may contain sensitive data (API keys, database passwords)
- Transfer backups securely (encrypted connection, secure storage)
- Verify backup source before restoring
- Consider encrypting backups for cross-machine transfer

## Summary

✅ **Cross-machine restore is fully supported**  
✅ **Backups are portable** (no machine-specific paths)  
✅ **Selective restore available** (choose components)  
✅ **Web UI and CLI both support** cross-machine restore  

The only requirement is that Docker containers are running with the expected names on the target machine.
