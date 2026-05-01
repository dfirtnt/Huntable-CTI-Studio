# Source Configuration Precedence

## Overview

Source configurations can be stored in two places:
1. **Database** (`sources` table) - **Primary source of truth for runtime** (user's active settings)
2. **YAML file** (`config/sources.yaml`) - **Only for brand new builds** (initial seed)

## Precedence Rules

### Runtime Behavior
**Database values are ALWAYS used at runtime** for all source operations:
- Source fetching (`check_all_sources` task)
- Article collection
- Source health checks
- UI display

### Startup Behavior
**YAML is ONLY used for brand new builds:**
- **New build**: If < 5 sources exist, automatically seeds from `sources.yaml`
- **Existing installation**: If ≥ 5 sources exist, **skips YAML sync** and uses database values
- **Auto-sync can be disabled**: Set `DISABLE_SOURCE_AUTO_SYNC=true` to always use database

### Manual Sync
**YAML overwrites database** when sync runs manually:
- `./run_cli.sh sync-sources` command overwrites database with YAML values
- Use only when you want to reset to YAML defaults
- Use `--new-only` to insert new sources without touching existing DB configs (preserves lookback_days, check_frequency, etc.):
  ```bash
  ./run_cli.sh sync-sources --no-remove --new-only
  ```

### RSS-first sources (`rss_only: true`)
Some sites are best ingested from their feed content without HTML scraping. In `config/sources.yaml`, set `rss_url` on the source and set `config.rss_only: true` to prefer feed extraction.

Example pattern:
```yaml
url: "https://example.com/"
rss_url: "https://example.com/feed.xml"
config:
  rss_only: true
```

## Implications for Backup/Restore

### ✅ Default Behavior (Database-First)

**By default, restored database settings are preserved:**
- Startup checks: If ≥ 5 sources exist, YAML sync is **automatically skipped**
- Database values are used at runtime
- User's active source settings (enabled/disabled, lookback_days, etc.) are preserved

### Recommended Backup Strategy

**Database backup is sufficient for preserving user settings:**
```bash
# Database backup includes all source configurations
./scripts/backup_database.py

# Full system backup (includes database + config files)
./scripts/backup_restore.sh create
```

**Note:** `config/sources.yaml` is included in full system backups but is only used for new builds.

## Restore Procedure

### Standard Restore (Preserves Database Settings)

```bash
# Restore database (includes all source configs)
./scripts/backup_restore.sh db-restore backup.sql.gz

# Startup will automatically:
# - Detect ≥ 5 sources exist
# - Skip YAML sync
# - Use database values (your restored settings)
```

**No additional steps needed.** Your restored database settings will be used.

### Disable Auto-Sync (Optional)

To ensure YAML sync never runs, even on new builds:

```bash
# Set environment variable in docker-compose.yml or .env
DISABLE_SOURCE_AUTO_SYNC=true
```

### Reset to YAML (Only if Needed)

If you want to reset to YAML defaults (overwrites database):

```bash
# Restore database first
./scripts/backup_restore.sh db-restore backup.sql.gz

# Then manually sync from YAML (overwrites database)
./run_cli.sh sync-sources
```

## Verification

After restore, verify source configurations:

```bash
# Check database values
docker exec cti_postgres psql -U cti_user -d cti_scraper -c \
  "SELECT identifier, active, lookback_days, check_frequency FROM sources LIMIT 5;"

# Compare with YAML file
cat config/sources.yaml | grep -A 5 "active:"
```

## Source health status (dashboard badges)

The `/analytics/scraper-metrics` "Source Performance Details" table shows a status badge per source. The badge reflects **scraper reachability**, not publisher cadence.

| Badge | Meaning | Threshold |
|-------|---------|-----------|
| `healthy` | Scraper reached and parsed the feed today | `last_success` is today |
| `warning` | 1-2 days since the scraper successfully reached the feed | 1 <= days since `last_success` <= 2 |
| `error`   | More than 2 days since a successful reach, or timestamp is missing/unparseable | days since `last_success` > 2 |

Thresholds live in `src/web/routes/analytics.py` (see the `days_since_success` branches).

### What counts as success

A collection run sets `last_success = now()` when **any** of these is true (see `src/worker/celery_app.py`):

- Fetch succeeded and new articles were saved.
- Fetch succeeded and zero new articles were found (explicitly treated as success: "No articles is still a successful check").
- Fetch succeeded and all returned articles were duplicates.

A run is recorded as a failure only when:

- `fetch_result.success` is false (HTTP/RSS/connection error).
- An exception was raised during collection.

This means a weekly-cadence blog polled hourly will keep flipping to `healthy` every poll, regardless of whether new articles were published.

### Status vs. error rate

The `status` column (freshness) and the `error_rate` column (reliability over the last 7 days) are independent signals:

- A source can be `healthy` with a high error rate (succeeded today, but failed often recently).
- A source can be `warning` with 0% error rate (no failures, but no successful poll today).

Use `status` to detect "is this source reachable right now?" and `error_rate` to detect "is this source flaky?" `consecutive_failures` (persisted across restarts, reset on any success) is the complementary alerting signal.

## Best Practices

1. **Always backup both** database and `config/sources.yaml`
2. **Document your preference**: Do you want database or YAML to be source of truth?
3. **After restore**: Decide whether to sync from YAML or use database values
4. **Version control**: Keep `config/sources.yaml` in git for tracking changes
