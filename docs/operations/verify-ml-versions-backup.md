# ML Model Versions Backup/Restore Verification Plan

## Overview

This document describes a safe verification process to confirm that ML model versions (`ml_model_versions` table) are properly backed up and can be restored, **without any risk to production data**.

## Safety Guarantees

✅ **Production database is never modified**  
✅ **Uses isolated test database** (`cti_scraper_test`)  
✅ **All test artifacts are cleaned up**  
✅ **Read-only access to production data**

## Verification Process

The automated scripts that once ran this process (`utils/temp/verify_backup_restore_*.sh`) were removed; the manual steps below are the supported procedure. They create an isolated `cti_scraper_test` database, copy the table, back it up, restore it, and verify integrity.

### Step 1: Create Test Database
```bash
docker exec cti_postgres psql -U cti_user -d postgres -c "CREATE DATABASE cti_scraper_test;"
```

### Step 2: Copy Table Structure
```bash
docker exec cti_postgres pg_dump -U cti_user -d cti_scraper -t ml_model_versions --schema-only | \
  docker exec -i cti_postgres psql -U cti_user -d cti_scraper_test
```

### Step 3: Copy Data
```bash
docker exec cti_postgres pg_dump -U cti_user -d cti_scraper -t ml_model_versions --data-only | \
  docker exec -i cti_postgres psql -U cti_user -d cti_scraper_test
```

### Step 4: Verify Data Copied
```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper_test -c \
  "SELECT COUNT(*) FROM ml_model_versions;"
```

### Step 5: Create Backup
```bash
mkdir -p /tmp/backup_test
docker exec cti_postgres pg_dump -U cti_user -d cti_scraper_test > \
  /tmp/backup_test/test_backup.sql
```

### Step 6: Verify Backup Contains Data
```bash
grep -c "ml_model_versions" /tmp/backup_test/test_backup.sql
# Should show multiple references (table definition, COPY statement, data)
```

### Step 7: Drop and Restore
```bash
docker exec cti_postgres psql -U cti_user -d postgres -c "DROP DATABASE cti_scraper_test;"
docker exec cti_postgres psql -U cti_user -d postgres -c "CREATE DATABASE cti_scraper_test;"
docker exec -i cti_postgres psql -U cti_user -d cti_scraper_test < /tmp/backup_test/test_backup.sql
```

### Step 8: Verify Restored Count
```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper_test -c \
  "SELECT COUNT(*) FROM ml_model_versions;"
# Should match production count
```

### Step 9: Cleanup
```bash
docker exec cti_postgres psql -U cti_user -d postgres -c "DROP DATABASE cti_scraper_test;"
rm -rf /tmp/backup_test
```

## Verification Checklist

### Basic Verification (each manual run)
- [ ] Test database created successfully
- [ ] Production data copied to test database
- [ ] Backup file created and contains `ml_model_versions`
- [ ] Backup file size is reasonable (not empty)
- [ ] Test database restored from backup
- [ ] Restored count matches production count
- [ ] Sample version records verified (e.g., version 1, latest version)
- [ ] Evaluation metrics present in restored data
- [ ] Test database cleaned up

For the pg_dump/psql commands used in each step, see the Manual Verification steps above.

### Comprehensive Verification (extended criteria for high-stakes checks)
- [ ] Uncompressed backup created and validated
- [ ] Compressed backup created and validated
- [ ] Backup contains COPY statement with data rows
- [ ] Metadata file created with accurate count
- [ ] Restore from uncompressed backup successful
- [ ] Restore from compressed backup successful
- [ ] Evaluation metrics count preserved
- [ ] Confusion matrices count preserved
- [ ] Version range preserved (min/max)
- [ ] Model file paths preserved
- [ ] Version 1 data integrity (exact match)
- [ ] Latest version data integrity (exact match)
- [ ] Confusion matrix JSON preserved
- [ ] Numeric precision preserved (all metrics)
- [ ] Timestamps preserved (trained_at, evaluated_at)
- [ ] Comparison relationships preserved
- [ ] Metadata count accurate
- [ ] NULL values handled correctly
- [ ] Empty JSON objects preserved
- [ ] Average accuracy matches
- [ ] Version number integrity (sum check)
- [ ] Backup format compatible with restore script
- [ ] Backup passes restore script validation

## What to Look For

### ✅ Success Indicators

- Backup file contains `COPY public.ml_model_versions` statement
- Backup file contains data rows for all versions
- Restored database has same count as production
- Sample versions (1, 68, etc.) have all fields populated
- Evaluation metrics (`eval_accuracy`, `eval_f1_score_huntable`, etc.) are present

### ❌ Failure Indicators

- Backup file doesn't mention `ml_model_versions`
- Restored count is 0 or different from production
- Missing evaluation metrics in restored data
- Error messages during restore

## Troubleshooting

### Issue: Test database creation fails
**Solution:** Check if `cti_scraper_test` already exists and drop it first:
```bash
docker exec cti_postgres psql -U cti_user -d postgres -c \
  "DROP DATABASE IF EXISTS cti_scraper_test;"
```

### Issue: Backup file is empty
**Solution:** Check Docker container is running and database is accessible:
```bash
docker ps | grep cti_postgres
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "SELECT 1;"
```

### Issue: Restore fails with constraint errors
**Solution:** This is normal if restoring into existing database. The verification uses a fresh database, so this shouldn't occur. If it does, ensure you're using a clean test database.

## Frequency

**Recommended:** Run verification after:
- Any changes to backup/restore scripts
- Database schema migrations affecting `ml_model_versions`
- Major system updates
- Before critical restore operations

**Optional:** Run monthly as part of backup health checks.

## Related Documentation

- [Backup and Restore Guide](../guides/backup-and-restore.md)
- **ML Model Versioning System**: See `model_versioning.py` in `src/utils/`

_Last updated: 2026-07-05_

