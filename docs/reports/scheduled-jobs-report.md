# Scheduled Jobs Report

All scheduled/periodic jobs (Celery Beat + host crontab).

---

## 1. Celery Beat (periodic tasks)

**Runtime:** `celery -A src.worker.celery_app beat` (Docker service: `scheduler`).  
**Timezone:** UTC (`celeryconfig.timezone = "UTC"`).

| # | Registered name | Task | Schedule (crontab) | Human schedule | Queue |
|---|-----------------|------|--------------------|----------------|-------|
| 1 | `check-all-sources-every-30min` | `check_all_sources` | `*/30 * * * *` | Every 30 minutes | `source_checks` |
| 2 | `cleanup-old-data-daily` | `cleanup_old_data` | `0 2 * * *` | Daily 02:00 UTC | `maintenance` |
| 3 | `embed-new-articles-daily` | `embed_new_articles` | `0 15 * * *` | Daily 15:00 UTC | `default` |
| 4 | `sync-sigma-rules-weekly` | `sync_sigma_rules` | `0 4 * * 0` | Sunday 04:00 UTC | `maintenance` |
| 5 | `update-provider-model-catalogs-daily` | `update_provider_model_catalogs` | `0 4 * * *` | Daily 04:00 UTC | `maintenance` — refreshes **OpenAI** (project allowlist only), **Anthropic** model lists → `config/provider_model_catalog.json` |
| 6 | `index-customer-repo-daily` | `index_customer_repo` | `30 4 * * *` | Daily 04:30 UTC | `default` — indexes the local customer Sigma repo (`SIGMA_REPO_PATH`) into the dedup corpus; Redis-locked, skips already-indexed rules |

**Disabled (commented in code):**

| Registered name | Task | Intended schedule | Queue |
|-----------------|------|-------------------|-------|
| `embed-annotations-weekly` | `generate_annotation_embeddings` | Sunday 04:00 UTC | (default) |

**Source:** `src/worker/celery_app.py` (`setup_periodic_tasks`) for jobs 1 and 6; `src/services/scheduled_jobs_service.py` and `src/worker/scheduled_jobs_scheduler.py` for configurable jobs 2–5; `src/worker/celeryconfig.py` for routes and queues.

---

## 2. Host crontab (CTI-managed backup)

**Applicable when:** User enables backup automation via UI, API, or CLI (`backup cron apply`).  
**Config:** `config/backup.yaml` (defaults) and runtime `BackupConfig` (e.g. `backup_time`, `cleanup_time`, `cleanup_day`).

| # | Purpose | Default schedule (config) | Cron expression (when installed) | Command |
|---|---------|---------------------------|-----------------------------------|---------|
| 1 | Daily backup | `backup_time: "02:00"` | `0 2 * * *` | `./scripts/backup_restore.sh create ...` |
| 2 | Weekly cleanup/prune | `cleanup_time: "03:00"`, `cleanup_day: 0` (Sunday) | `0 3 * * 0` | `./scripts/backup_restore.sh prune ...` |

- **Managed marker:** Lines are prefixed with comment `# CTI Scraper backup`; only these are replaced/removed by `install_backup_schedule` / `remove_backup_schedule`.
- **Inspect:** `GET /api/cron`, `GET /api/backup/cron`, or CLI `backup cron show` / `cron show`.

**Source:** `src/services/backup_cron_service.py`, `config/backup.yaml`.

---

## 2a. Managing Celery Beat jobs via API

The four configurable Celery Beat jobs from Section 1 (`cleanup_old_data`, `embed_new_articles`,
`sync_sigma_rules`, `update_provider_model_catalogs`) can be enabled/disabled and rescheduled
without a restart:

- `GET /api/scheduled-jobs` — returns the persisted state (enabled flag + cron expression) for
  each configurable job.
- `PUT /api/scheduled-jobs` — body `{"jobs": {"<job_id>": {"enabled": bool, "cron": "<crontab expr>"}}}`.
  Persists the config and an audit event (`scheduled_jobs.updated`) in one transaction. The
  database-backed scheduler polls for changes (every 30 seconds by default), so no process
  restart or Celery Beat reload is required. `check_all_sources` and `index_customer_repo` are
  registered directly in code (Section 1) and are not editable through this endpoint.

**Source:** `src/web/routes/scheduled_jobs.py`, `src/services/scheduled_jobs_service.py`, `src/worker/scheduled_jobs_scheduler.py`.

---

## 3. Queue summary

| Queue | Scheduled tasks (Celery) |
|-------|---------------------------|
| `source_checks` | check_all_sources (every 30 min) |
| `maintenance` | cleanup_old_data, sync_sigma_rules, update_provider_model_catalogs |
| `default` | embed_new_articles, index_customer_repo |

---

## 4. Quick reference

- **Celery scheduler:** `src/worker/celery_app.py` (static periodic registration), `src/worker/scheduled_jobs_scheduler.py` (database-backed schedules), `src/worker/celeryconfig.py` (queues/routes).
- **Backup cron:** `src/services/backup_cron_service.py`, `config/backup.yaml`, `src/cli/commands/backup.py` (`backup cron`), `src/web/routes/backup.py` (`/api/backup/cron`).
- **Generic crontab:** `src/cli/commands/cron.py` (`cron show` / `cron set`), `src/web/routes/cron.py` (`/api/cron`).

_Last updated: 2026-08-13_
