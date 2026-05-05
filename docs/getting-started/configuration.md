# Configuration Reference

Huntable CTI Studio configuration uses three files: environment variables (`.env`), Docker Compose (`docker-compose.yml`), and source feeds (`config/sources.yaml`).

## Configuration Files

### Environment Variables (.env)
Primary configuration file for sensitive values and service settings. Provision it with setup:
```bash
./setup.sh --no-backups
```

### Docker Compose (docker-compose.yml)

Defines service topology, port mappings, and volume mounts.

### Source Configuration (config/sources.yaml)
Defines CTI feeds and sources. See [Source Configuration Precedence](../guides/source-config.md) for details on YAML vs database sync.

## Port Mappings

### Default Ports

| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| Web/API | 8001 | 8001 | Main FastAPI application |
| Web (alt) | 8888 | 8888 | Secondary port on the web container |
| PostgreSQL | 5432 | 5432 | Database |
| Redis | 6379 | 6379 | Cache and message broker |
| LM Studio | 1234 | — | External (host machine) |

### Customizing Ports

To change the host port for the web application, edit `docker-compose.yml`:

```yaml
services:
  web:
    ports:
      - "8002:8001"  # Map host port 8002 to container port 8001
      - "8888:8888"
```

After changing ports:
```bash
docker-compose down
docker-compose up -d
```

For tests, set the matching base URL:
```bash
export CTI_SCRAPER_URL=http://localhost:8002
```

### Troubleshooting Port Conflicts

Check if a port is in use:
```bash
lsof -i :8001
```

To resolve conflicts, either stop the conflicting service or change the host port in `docker-compose.yml` as shown above.

## Environment Variables Reference

### Core Infrastructure

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Built by Docker Compose from `POSTGRES_PASSWORD` (see `.env.example`); not a literal default in repo | Yes |
| `POSTGRES_PASSWORD` | PostgreSQL password | — | **Yes** |
| `REDIS_URL` | Redis connection | `redis://redis:6379/0` | Yes |
| `SOURCES_CONFIG` | Path to sources YAML | `config/sources.yaml` | No |
| `ENVIRONMENT` | Environment name | `development` | No |
| `DISABLE_SOURCE_AUTO_SYNC` | Skip YAML→DB sync on startup | `false` | No |

### Celery Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `CELERY_BROKER_URL` | Celery broker URL | `redis://redis:6379/0` |
| `CELERY_MAX_TASKS_PER_CHILD` | Worker task limit before restart | `50` |

### LLM Provider Keys

| Variable | Purpose | Required |
|----------|---------|----------|
| `OPENAI_API_KEY` | OpenAI API key | No |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | No |

**Keys set during `./setup.sh`**: Keys entered when `setup.sh` prompts you are written to `.env` only. The application uses these values at runtime; you do not need to enter them again in the Settings page. The Settings page shows values stored in the database, so the OpenAI/Anthropic fields may appear empty even though the keys are active. To make keys visible and editable in Settings, add them there; values saved in Settings are stored in the database and take precedence over `.env` for the workflow UI.

### Workflow-Specific LLM Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `WORKFLOW_OPENAI_API_KEY` | OpenAI key for workflows | Falls back to `OPENAI_API_KEY` |
| `WORKFLOW_ANTHROPIC_API_KEY` | Anthropic key for workflows | Falls back to `ANTHROPIC_API_KEY` |
| `WORKFLOW_OPENAI_ENABLED` | Enable OpenAI in workflows | DB setting |
| `WORKFLOW_ANTHROPIC_ENABLED` | Enable Anthropic in workflows | DB setting |
| `WORKFLOW_LMSTUDIO_ENABLED` | Enable LM Studio in workflows | DB setting |
| `WORKFLOW_OPENAI_MODEL` | OpenAI model for workflows | — |
| `WORKFLOW_ANTHROPIC_MODEL` | Anthropic model for workflows | — |

### LM Studio Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `LMSTUDIO_API_URL` | LM Studio API base URL | `http://host.docker.internal:1234/v1` |
| `LMSTUDIO_MODEL` | Default LM Studio model | `deepseek/deepseek-r1-0528-qwen3-8b` |
| `LMSTUDIO_MODEL_RANK` | Model for ranking agent | — |
| `LMSTUDIO_MODEL_EXTRACT` | Model for extraction agent | — |
| `LMSTUDIO_MODEL_SIGMA` | Model for Sigma generation | — |
| `LMSTUDIO_EMBEDDING_URL` | Embedding API URL | `http://host.docker.internal:1234/v1/embeddings` |
| `LMSTUDIO_EMBEDDING_MODEL` | Embedding model | `text-embedding-e5-base-v2` |
| `LMSTUDIO_TEMPERATURE` | LLM temperature | — |
| `LMSTUDIO_TOP_P` | Top-p sampling | — |
| `LMSTUDIO_SEED` | Random seed for reproducibility | — |
| `LMSTUDIO_MAX_CONTEXT` | Max context window size | — |

**Note**: LM Studio runs on your host machine. The `host.docker.internal` hostname allows Docker containers to reach services on the host. You can also set `LMSTUDIO_API_URL` and `LMSTUDIO_EMBEDDING_URL` in **Settings -> Agentic Workflow Configuration** (LM Studio section); those values override `.env`. Context length is configured per-model via `LMSTUDIO_CONTEXT_LENGTH_<model_slug>` in `docker-compose.yml` and can differ between web and worker services. See [LM Studio Integration](../llm/lmstudio.md#context-length) for details.

## Workflow Presets

Pre-built workflow config presets let you run the pipeline without configuring prompts by hand. Each preset sets one LLM provider and model for every workflow agent, plus default prompt configs (role, task, instructions, schema) for each agent. Seed prompt files live in `src/prompts/` but are only read on first bootstrap or explicit reset; the authoritative prompts at runtime live in the database. See [Prompt Architecture](../concepts/agents.md#prompt-architecture) for details.

Quickstart presets (v2 format, always committed to the repo) are in `config/presets/AgentConfigs/quickstart/`:

| Preset file | Provider | Model | Use when |
|-------------|----------|--------|----------|
| `Quickstart-anthropic-sonnet-4-6.json` | Anthropic | Claude Sonnet 4.6 | You have `ANTHROPIC_API_KEY` and want Claude for all agents. |
| `Quickstart-anthropic-haiku-4-5.json` | Anthropic | Claude Haiku 4.5 | You have `ANTHROPIC_API_KEY` and want a faster, lower-cost Claude model. |
| `Quickstart-openai-gpt-4.1-mini.json` | OpenAI | gpt-4.1-mini | You have `OPENAI_API_KEY` and want a fast, low-cost OpenAI model. |
| `Quickstart-openai-gpt-4.1.json` | OpenAI | gpt-4.1 | You have `OPENAI_API_KEY` and want the full gpt-4.1 model. |
| `Quickstart-openai-gpt-4o.json` | OpenAI | gpt-4o | You have `OPENAI_API_KEY` and want gpt-4o. |
| `Quickstart-openai-gpt-4o-mini.json` | OpenAI | gpt-4o-mini | You have `OPENAI_API_KEY` and want the gpt-4o-mini variant. |
| `Quickstart-openai-gpt-5.json` | OpenAI | gpt-5 | You have `OPENAI_API_KEY` and want gpt-5. |
| `Quickstart-LMStudio-Qwen3.json` | LM Studio | Qwen 3 (local) | You run LM Studio with a Qwen3-compatible model. |
| `Quickstart-LMStudio-Gemma4B.json` | LM Studio | Gemma 4B (local) | You run LM Studio with a Gemma 4B-compatible model. |

All paths are relative to `config/presets/AgentConfigs/quickstart/`.

**How to load a preset**

1. Open the **Workflow** page in the web UI.
2. In the workflow config panel, use **Import from file** and choose a JSON file from `config/presets/AgentConfigs/quickstart/`.
3. Confirm the import; the active workflow config (thresholds, agent models, and agent prompts) is replaced by the preset. Tweak individual prompt fields (role, task, instructions, schema) in the workflow config editor as needed.

**Private presets**: To keep presets out of version control, put JSON files in `config/presets/private/`. That directory is gitignored (only `*.json` there); use **Import from file** to load from it.

To normalize key order in quickstart presets after a schema update, run from the repo root:

```bash
python3 scripts/build_baseline_presets.py
```

`src/prompts/` files are seed defaults, not live prompts. Editing them only affects new installs or explicit bootstrap resets; it does not change prompts for a running instance. To change prompts on a running instance, use the workflow config editor or the prompt API endpoints.

## Content Filtering

| Variable | Purpose | Default |
|----------|---------|---------|
| `CONTENT_FILTERING_ENABLED` | Enable ML content filtering | `true` |
| `CONTENT_FILTERING_CONFIDENCE` | Minimum confidence threshold | `0.7` |
| `CHATGPT_CONTENT_LIMIT` | Max content chars for ChatGPT | `1000000` |
| `ANTHROPIC_CONTENT_LIMIT` | Max content chars for Anthropic | `1000000` |

## Langfuse Observability

| Variable | Purpose | Notes |
|----------|---------|-------|
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | Required to enable tracing |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | Required to enable tracing |
| `LANGFUSE_HOST` | Langfuse Cloud host URL | Optional; runtime default is `https://cloud.langfuse.com` |
| `LANGFUSE_PROJECT_ID` | Langfuse project ID | Optional; improves workflow trace deep links in the UI |

Configure Langfuse through environment variables or the Settings UI. Settings stored in the web UI take precedence over the same values in the environment.

Huntable CTI Studio supports **Langfuse Cloud only**. Local or self-hosted Langfuse deployments are outside this project's supported and tested configurations.

Set `LANGFUSE_HOST` to the correct Langfuse Cloud region for your account. If unset, the runtime defaults to `https://cloud.langfuse.com`. Common cloud hosts: `https://cloud.langfuse.com`, `https://us.cloud.langfuse.com`, `https://hipaa.cloud.langfuse.com`.

Security note: Langfuse receives workflow and LLM telemetry. Depending on the workflow path, traces may contain prompts, article content, extracted observables, outputs, and metadata. Enable Langfuse only where external cloud tracing is acceptable for your data.

See [Langfuse Setup](../guides/langfuse-setup.md) for the full setup and verification workflow.

## SIGMA / GitHub Integration

The app submits approved SIGMA rules via GitHub PRs. **Setup is automated during `./setup.sh`.**

**During setup.sh (interactive):**

1. Create a repo at [github.com/new](https://github.com/new) (e.g. `Huntable-SIGMA-Rules`)
2. When prompted, enter `owner/repo` (e.g. `myuser/Huntable-SIGMA-Rules`)
3. The script clones to `../Huntable-SIGMA-Rules` and creates the `rules/` structure

**After setup (required):**

- Add your **GitHub Personal Access Token** in **Settings -> GitHub** (repo scope)
- Create token at [github.com/settings/tokens](https://github.com/settings/tokens)

**Non-interactive:** Set `SIGMA_GITHUB_REPO=owner/repo` before running `./setup.sh --non-interactive` to clone automatically.

| Variable | Purpose | Default |
|----------|---------|---------|
| `SIGMA_REPO_PATH` | Path to SIGMA rules repo (PR submission); also used by `sigma index-customer-repo` so similarity search includes approved rules from this repo | `sigma-repo` |
| `GITHUB_TOKEN` | GitHub PAT for PR submission | — |
| `GITHUB_REPO` | Target repo for SIGMA rule PRs | `owner/repo` (from setup) |

## Source Configuration

- **YAML file**: `config/sources.yaml` (version-controlled template)
- **Runtime source of truth**: PostgreSQL `sources` table
- **Auto-sync**: YAML -> DB sync runs on startup when fewer than 5 sources exist in the database
- **Manual sync**: `./run_cli.sh sync-sources --config config/sources.yaml --no-remove`
- **Disable auto-sync**: Set `DISABLE_SOURCE_AUTO_SYNC=true`

See [Source Configuration Precedence](../guides/source-config.md) for details.

## Celery and Scheduled Jobs

Task queues, Celery Beat periodic tasks (source checks, cleanup, reports, embeddings, Sigma sync, provider model catalog refresh), and host backup cron are documented in [Scheduled Jobs](../reports/scheduled-jobs-report.md). The provider model catalog is also refreshed at **setup** (`./setup.sh`) and **start** (`./start.sh`) so workflow model dropdowns show the current list immediately.

## Source Auto-Healing

Sources that accumulate consecutive failures are automatically diagnosed and repaired. The healing pipeline runs deep probes (RSS content, sitemaps, WP JSON API, JS-rendering detection) and uses an LLM to propose config fixes. Configure via the Settings page:

- **Enable/disable**: Toggle auto-healing on or off
- **Provider/model**: Which LLM to use for diagnosis
- **Max attempts**: Rounds per healing session (default: 5)
- **Failure threshold**: Consecutive failures before healing triggers (default: 100)
- **Check interval**: Hours between scheduled scans (default: 1)

Eligibility: the coordinator skips sources with a recent success (`last_success` within 24 hours) to avoid rewriting config for transient failures.

For architecture details, see `src/services/source_healing_service.py`.

## Health Checks and Diagnostics

### Application Health
```bash
curl http://localhost:8001/health
```

### API Documentation
http://localhost:8001/docs

### Database Connection
```bash
PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U cti_user -d cti_scraper -c "SELECT 1"
```

### Redis Connection
```bash
redis-cli -h localhost -p 6379 ping
```

### Workflow Status
```bash
curl http://localhost:8001/api/workflow/executions
```

### Ingestion Analytics
```bash
curl http://localhost:8001/api/health/ingestion
```

## Applying Configuration Changes

After modifying configuration:

1. **Environment variables only**: Restart affected services
   ```bash
   docker-compose restart web worker
   ```

2. **Port changes or docker-compose.yml**: Rebuild and restart
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

3. **Source configuration**: Sync sources
   ```bash
   ./run_cli.sh sync-sources --config config/sources.yaml
   ```

---

_Last updated: 2026-05-01_
_Last reviewed: 2026-05-04_
