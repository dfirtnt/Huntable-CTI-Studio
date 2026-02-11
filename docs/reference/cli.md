# CLI Reference

All CLI commands run inside Docker via `./run_cli.sh`. Arguments are passed to `python -m src.cli.main`. See [Config](config.md) for environment and [Docker Architecture](../deployment/DOCKER_ARCHITECTURE.md) for how the CLI container connects to Postgres and Redis.

## Running the CLI

```bash
./run_cli.sh --help
./run_cli.sh <command> [options]
```

**Global options** (before the command):

| Option | Description |
|--------|-------------|
| `--config PATH` | Configuration file or directory (e.g. `config/sources.yaml`) |
| `--database-url URL` | Override database URL |
| `--debug` / `--no-debug` | Enable or disable debug logging (default: off) |

---

## Commands

### init

**When:** First-time setup or after adding/editing sources in YAML. Loads sources from config into the database and optionally validates RSS feeds.

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--config PATH` | (from global or ctx) | Config file or directory |
| `--validate-feeds` / `--no-validate-feeds` | `True` | Validate RSS feeds on load |

**Examples:**

```bash
./run_cli.sh init --config config/sources.yaml
./run_cli.sh init --config config/sources.yaml --no-validate-feeds
```

**See also:** [Add feed](../howto/add_feed.md), [Source config precedence](../operations/SOURCE_CONFIG_PRECEDENCE.md).

---

### collect

**When:** Manual fetch from configured sources. Normally the scheduler runs collection; use this for one-off runs or testing. Use `--dry-run` to see what would be collected without saving.

**Options:**

| Option | Description |
|--------|-------------|
| `--source ID` | Collect only from this source identifier |
| `--force` | Collect even if source is not due per schedule |
| `--dry-run` | Do not save articles; show what would be collected |

**Examples:**

```bash
./run_cli.sh collect --dry-run
./run_cli.sh collect --source threatpost --dry-run
./run_cli.sh collect --source threatpost --force
```

---

### search

**When:** Query articles in the database by text, source, and time window. Use for ad-hoc lookup or piping to other tools (e.g. `--format json`).

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--query TEXT` | — | Search query (title/content) |
| `--source ID` | — | Filter by source identifier |
| `--days N` | `30` | Only articles from last N days |
| `--limit N` | `50` | Max results |
| `--format table|json` | `table` | Output format |

**Examples:**

```bash
./run_cli.sh search --query ransomware --limit 25 --format json
./run_cli.sh search --source threatpost --days 7
./run_cli.sh search --query CVE --limit 10 --format table
```

---

### sync-sources

**When:** After editing `config/sources.yaml` (add/remove/change sources). Pushes YAML state into the database. Use `--no-remove` to add/update without deleting DB sources that are missing from YAML.

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--config PATH` | `config/sources.yaml` | Path to sources YAML |
| `--no-remove` | `False` | Do not remove DB sources that are not in YAML |

**Examples:**

```bash
./run_cli.sh sync-sources --config config/sources.yaml --no-remove
./run_cli.sh sync-sources --config config/sources.yaml
```

**See also:** [Add feed](../howto/add_feed.md), [Source config precedence](../operations/SOURCE_CONFIG_PRECEDENCE.md).

---

### compare-sources

**When:** Compare database source settings with `sources.yaml` to see drift (only in YAML, only in DB, or field differences). Use before or after `sync-sources` to verify consistency.

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--config-path PATH` | `SOURCES_CONFIG` or `config/sources.yaml` | Path to sources YAML |

**Examples:**

```bash
./run_cli.sh compare-sources
./run_cli.sh compare-sources --config-path config/sources.yaml
```

**See also:** [Sync sources](#sync-sources), [Source config precedence](../operations/SOURCE_CONFIG_PRECEDENCE.md).

---

### backup

**When:** Create, list, restore, or verify system backups; prune old backups. For full procedures see [Backup & Restore](../operations/BACKUP_AND_RESTORE.md).

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `create` | Create backup (full, database, or files) |
| `list` | List available backups |
| `restore BACKUP_NAME` | Restore from backup |
| `verify BACKUP_NAME` | Verify backup integrity |
| `prune` | Remove old backups by retention policy |
| `stats` | Show backup statistics |

**Options (create):**

| Option | Default | Description |
|--------|---------|-------------|
| `--backup-dir PATH` | `backups` | Backup directory |
| `--type full|database|files` | `full` | Backup type |
| `--no-compress` | — | Skip compression |
| `--no-verify` | — | Skip file validation |

**Options (restore):** `--backup-dir`, `--components` (comma-separated), `--no-snapshot`, `--force`, `--dry-run`.

**Options (verify):** `--backup-dir`, `--test-restore`.

**Options (prune):** `--backup-dir`, `--daily` (default 7), `--weekly` (4), `--monthly` (3), `--max-size-gb` (50), `--dry-run`, `--force`.

**Examples:**

```bash
./run_cli.sh backup create --backup-dir backups/
./run_cli.sh backup create --type database
./run_cli.sh backup list
./run_cli.sh backup list --show-details
./run_cli.sh backup restore system_backup_20251010_103000 --dry-run
./run_cli.sh backup verify system_backup_20251010_103000
./run_cli.sh backup prune --dry-run
./run_cli.sh backup stats
```

**See also:** [Backup & Restore](../operations/BACKUP_AND_RESTORE.md).

---

### rescore

**When:** Regenerate **keyword-based** threat hunting scores (`threat_hunting_score` in article metadata). Use after changing scoring rules or to backfill missing scores. Does not change ML-based scores (use `rescore-ml` for that).

**Options:**

| Option | Description |
|--------|-------------|
| `--article-id ID` | Rescore only this article (including archived) |
| `--force` | Rescore even if score already exists |
| `--dry-run` | Compute scores but do not save |

**Examples:**

```bash
./run_cli.sh rescore --article-id 123 --dry-run
./run_cli.sh rescore --force
./run_cli.sh rescore
```

**See also:** [Scoring](../internals/scoring.md). After scoring-rule changes, run `./run_cli.sh rescore --force` (per AGENTS.md).

---

### rescore-ml

**When:** Regenerate **ML-based** hunt scores (chunk-level RandomForest predictions aggregated to article score). Use after retraining the ML model or to backfill/change metric. Distinct from `rescore` (keyword-based).

**Options:**

| Option | Description |
|--------|-------------|
| `--article-id ID` | Rescore only this article |
| `--force` | Recalculate even if score exists |
| `--dry-run` | Compute but do not save |
| `--metric NAME` | `weighted_average`, `proportion_weighted`, `confidence_sum_normalized`, `top_percentile`, `user_proposed` |
| `--model-version VERSION` | Use specific model version (default: latest) |

**Examples:**

```bash
./run_cli.sh rescore-ml --article-id 1234 --dry-run
./run_cli.sh rescore-ml --metric proportion_weighted
./run_cli.sh rescore-ml --force
```

**See also:** [ML Hunt Scoring](../ML_HUNT_SCORING.md), [Chunking](../internals/chunking.md).

---

### embed

**When:** Manage article embeddings for RAG and Sigma similarity search. Use `embed stats` to see coverage; use `embed embed` (i.e., the `embed` group has an `embed`` (no subcommand) to generate embeddings for articles that don’t have them (queues a Celery task). Use `embed search` for semantic search from the CLI.

> **Note:** The embedding generation subcommand is `embed embed` (not just `embed` by itself). Example: `./run_cli.sh embed embed --batch-size 1000`

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `embed`*(none)* | Generate embeddings for articles missing them (interactive confirm; use `--dry-run` to preview) |
| `stats` | Show embedding coverage (total, embedded, pending, per-source) |
| `search` | Semantic search: prompt for query, return similar articles |

**Options (embed embe, no subcommand):**

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size N` | `1000` | Batch size for processing |
| `--source-id ID` | — | Only embed articles from this source |
| `--dry-run` | — | Show what would be processed, do not run task |

**Options (embed search):**

| Option | Default | Description |
|--------|---------|-------------|
| `--limit N` | `10` | Number of results |
| `--threshold T` | `0.7` | Similarity threshold (0–1) |
| `--source-id ID` | — | Filter by source ID |

**Examples:**

```bash
./run_cli.sh embed stats
./run_cli.sh embed embed --dry-run
./run_cli.sh embed embed --source-id 1
./run_cli.sh embed search --limit 5 --threshold 0.75
```

**See also:** [RAG System](../RAG_SYSTEM.md), [Sigma Detection Rules](../features/SIGMA_DETECTION_RULES.md).

---

### sigma

**When:** Sync SigmaHQ rules, index them (with embeddings), and match articles to rules. Required for Sigma similarity search and workflow Sigma generation.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `sync` | Clone or pull SigmaHQ rules repository |
| `index` | Index rules into DB (generates embeddings); use `--force` to re-index |
| `match ARTICLE_ID` | Match one article to Sigma rules; `--save` to persist |
| `match-all` | Match all articles (optional filters) |
| `stats` | Show Sigma rule and match statistics |

**Options (sync):** `--force` — force re-clone.

**Options (index):** `--force` — re-index all rules.

**Options (match):** `--threshold T` (default `0.7`), `--save`.

**Options (match-all):** `--threshold T`, `--limit N`, `--min-hunt-score N` (default `50`).

**Examples:**

```bash
./run_cli.sh sigma sync
./run_cli.sh sigma index
./run_cli.sh sigma index --force
./run_cli.sh sigma match 123 --threshold 0.7 --save
./run_cli.sh sigma match-all --min-hunt-score 50 --limit 100
./run_cli.sh sigma stats
```

**See also:** [Generate Sigma](../howto/generate_sigma.md), [Sigma Detection Rules](../features/SIGMA_DETECTION_RULES.md), [Sigma reference](sigma.md).

---

### export

**When:** Dump articles to JSON or CSV for analysis, reporting, or migration. Uses last N days and optional source filter.

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--format json|csv` | `json` | Output format |
| `--days N` | `7` | Articles from last N days |
| `--output PATH` | — | Write to file (default: stdout) |
| `--source ID` | — | Export only from this source |

**Examples:**

```bash
./run_cli.sh export --format json --days 14 --output articles.json
./run_cli.sh export --format csv --source threatpost
./run_cli.sh export --days 30
```

---

### stats

**When:** Quick overview of database state (sources, article counts, recent activity).

**Options:** None.

**Example:**

```bash
./run_cli.sh stats
```

---

### archive

**When:** Soft-delete articles (archive) or restore them (unarchive). Useful for cleaning up or hiding a source’s articles without losing data.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `add` | Archive articles (`--article-id` or `--source-id`) |
| `remove` | Unarchive articles |
| `list` | List archived articles |
| `cleanup` | Show archive statisticsrestore` | Restore from a backup of archived articles (advanced) |

**Options (add / remove):**

| Option | Description |
|--------|-------------|
| `--article-id ID` | Single article |
| `--source-id ID` | All articles from this source |
| `--dry-run` | Show what would be archived/unarchived |
| `--force` | Skip confirmation |

**Examples:**

```bash
./run_cli.sh archive add --article-id 456 --dry-run
./run_cli.sh archive add --source-id 2 --force
./run_cli.sh archive remove --article-id 456
./run_cli.sh archive list --limit 50
```

---

## Quick reference table

| Command | When to use |
|---------|-------------|
| `init` | First setup; load sources from YAML into DB |
| `collect` | Manual fetch from sources (scheduler does this automatically) |
| `search` | Query articles (text, source, time window) |
| `sync-sources` | Apply YAML source changes to DB (add/update; use `--no-remove` to avoid deleting) |
| `compare-sources` | Compare DB source settings vs sources.yaml (drift check) |
| `backup create/list/restore/verify/prune/stats` | Full backup workflow |
| `rescore` | Recompute keyword-based threat hunting scores |
| `rescore-ml` | Recompute ML-based hunt scores |
| `embed embed` / `embed stats` / `embed search` | Embedding coverage, generation, coverage stats, semantic search |
| `sigma sync/index/match/match-all/stats` | Sigma rules sync, index, matching |
| `export` | Dump articles to JSON/CSV |
| `stats` | DB summary (sources, articles, activity) |
| `archive add/remove/list/cleanup` | Soft-delete, or restore, or clean up articles |
<!--stackedit_data:
eyJoaXN0b3J5IjpbODI4NTQ5MTgyXX0=
-->