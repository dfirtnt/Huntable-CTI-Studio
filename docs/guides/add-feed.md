# Add a Feed or Source

Sources are defined in `config/sources.yaml`, seeded into PostgreSQL, and used by the scheduler and collectors. Runtime always reads from the database; YAML is only used for seeding and manual syncs.

## Precedence rules
- Database values win at runtime.
- On startup, YAML seeding only runs if fewer than 5 sources exist (see `../guides/source-config.md`).
- Manual sync: `./run_cli.sh sync-sources` overwrites database entries with YAML values unless `--no-remove` is set.

## Steps to add a source
1. Edit `config/sources.yaml` and add an entry with a unique `id`.
   ```yaml
   - id: "vmray_blog"
     name: "VMRay Blog"
     url: "https://www.vmray.com/blog/"
     rss_url: "https://www.vmray.com/blog/feed/"
     check_frequency: 1800
     active: true
     config:
       allow: ["vmray.com"]
       title_filter_keywords: ["webinar", "training", "careers"]
       rss_only: false
   ```
   Keep `allow`, `post_url_regex`, and `title_filter_keywords` consistent with existing entries to avoid scraping noise.

2. Sync YAML to the database without deleting existing rows:
   ```bash
   ./run_cli.sh sync-sources --config config/sources.yaml --no-remove
   ```

3. Verify the source is active:
   ```bash
   # quick breakdown via health endpoint
   curl -s http://localhost:8001/api/health/ingestion | jq '.ingestion.source_breakdown[] | {name, total: .total_articles, active: .active}'
   ```
   The Sources page in the UI also reflects the new entry and its enablement state.

## Notes
- To reset the database to YAML defaults, rerun sync **without** `--no-remove` (overwrites DB rows not present in YAML).
- Set `active: false` to keep a source defined but disabled; collectors skip inactive sources at runtime.
- Scheduler cadence is controlled by `check_frequency` (seconds) and the Celery Beat schedule defined in `docker-compose.yml`.
