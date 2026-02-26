# Configuration

Huntable CTI Studio configuration is managed through environment variables (`.env`), Docker Compose (`docker-compose.yml`), and YAML files in `config/`.

## Configuration Files

### Environment Variables (.env)
Primary configuration file for sensitive values and service settings. Copy from template:
```bash
cp .env.example .env
```

### Docker Compose (docker-compose.yml)
Defines service configuration, port mappings, and inter-service networking.

### Source Configuration (config/sources.yaml)
Defines CTI feeds and sources. See [Source Configuration Precedence](../guides/source-config.md) for details on YAML vs database sync.

## Port Mappings

### Default Ports

| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| Web/API | 8001 | 8001 | Main FastAPI application |
| Debug/Aux | 8888 | 8888 | Auxiliary services |
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

To resolve conflicts, either:
1. Stop the conflicting service
2. Change the host port in `docker-compose.yml` as shown above

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
| `GEMINI_API_KEY` | Google Gemini API key | No |

### Workflow-Specific LLM Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `WORKFLOW_OPENAI_API_KEY` | OpenAI key for workflows | Falls back to `OPENAI_API_KEY` |
| `WORKFLOW_ANTHROPIC_API_KEY` | Anthropic key for workflows | Falls back to `ANTHROPIC_API_KEY` |
| `WORKFLOW_GEMINI_API_KEY` | Gemini key for workflows | Falls back to `GEMINI_API_KEY` |
| `WORKFLOW_OPENAI_ENABLED` | Enable OpenAI in workflows | DB setting |
| `WORKFLOW_ANTHROPIC_ENABLED` | Enable Anthropic in workflows | DB setting |
| `WORKFLOW_GEMINI_ENABLED` | Enable Gemini in workflows | DB setting |
| `WORKFLOW_LMSTUDIO_ENABLED` | Enable LM Studio in workflows | DB setting |
| `WORKFLOW_OPENAI_MODEL` | OpenAI model for workflows | — |
| `WORKFLOW_ANTHROPIC_MODEL` | Anthropic model for workflows | — |
| `WORKFLOW_GEMINI_MODEL` | Gemini model for workflows | — |

### LM Studio Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `LMSTUDIO_API_URL` | LM Studio API base URL | `http://host.docker.internal:1234/v1` |
| `LMSTUDIO_MODEL` | Default LM Studio model | `deepseek/deepseek-r1-0528-qwen3-8b` |
| `LMSTUDIO_MODEL_RANK` | Model for ranking agent | — |
| `LMSTUDIO_MODEL_EXTRACT` | Model for extraction agent | — |
| `LMSTUDIO_MODEL_SIGMA` | Model for SIGMA generation | — |
| `LMSTUDIO_EMBEDDING_URL` | Embedding API URL | `http://localhost:1234/v1/embeddings` |
| `LMSTUDIO_EMBEDDING_MODEL` | Embedding model | `text-embedding-e5-base-v2` |
| `LMSTUDIO_TEMPERATURE` | LLM temperature | — |
| `LMSTUDIO_TOP_P` | Top-p sampling | — |
| `LMSTUDIO_SEED` | Random seed for reproducibility | — |
| `LMSTUDIO_MAX_CONTEXT` | Max context window size | — |

**Note**: LM Studio runs on your host machine. The `host.docker.internal` hostname allows Docker containers to access services on the host. Context length can differ by service: `docker-compose.yml` may set `LMSTUDIO_CONTEXT_LENGTH_<model_slug>` to 16384 for web and 4096 for workers; see [LM Studio Integration](../llm/lmstudio.md#context-length) for details.

### Workflow baseline presets (getting started)

Pre-built workflow config presets with **all agent prompts included** are in the repo so you can run the pipeline without configuring prompts by hand. Each preset sets one LLM provider and model for every workflow agent.

| Preset file | Provider | Model | Use when |
|-------------|----------|--------|----------|
| `config/presets/AgentConfigs/anthropic-sonnet-4.5.json` | Anthropic | Claude Sonnet 4.5 | You have `ANTHROPIC_API_KEY` and want to use Claude for all agents. |
| `config/presets/AgentConfigs/chatgpt-4o-mini.json` | OpenAI | gpt-4o-mini | You have `OPENAI_API_KEY` or `CHATGPT_API_KEY` and want 4o-mini for all agents. |
| `config/presets/AgentConfigs/lmstudio-qwen2.5-8b.json` | LM Studio | Qwen 2.5 8B (local) | You run LM Studio with a model such as Qwen2.5-8B-Instruct and want to use it for all agents. |

Tracked quickstart presets (v2 format) live in `config/presets/AgentConfigs/quickstart/` (e.g. `Quickstart-anthropic-sonnet-4-6.json`, `Quickstart-openai-gpt-4.1-mini.json`, `Quickstart-LMStudio-Qwen3.json`). Load them the same way via **Import from file**.

**How to load a preset**

1. Open the **Workflow** page in the web UI.
2. In the workflow config panel, use **Import from file** and choose one of the JSON files above (e.g. `config/presets/AgentConfigs/chatgpt-4o-mini.json`).
3. Confirm the import; the active workflow config (thresholds, agent models, and **agent prompts**) will be replaced by the preset. You can then run the workflow or tweak settings.

**Private presets**: To keep presets out of version control, put JSON files in `config/presets/private/`. That directory is gitignored (only `*.json` there); use **Import from file** to load from it.

To regenerate the preset files (e.g. after changing prompts in `src/prompts`), run from the repo root:

```bash
python3 scripts/build_baseline_presets.py
```

### Content Filtering

| Variable | Purpose | Default |
|----------|---------|---------|
| `CONTENT_FILTERING_ENABLED` | Enable ML content filtering | `true` |
| `CONTENT_FILTERING_CONFIDENCE` | Minimum confidence threshold | `0.7` |
| `CHATGPT_CONTENT_LIMIT` | Max content chars for ChatGPT | `1000000` |
| `ANTHROPIC_CONTENT_LIMIT` | Max content chars for Anthropic | `1000000` |

### LangFuse Observability

| Variable | Purpose |
|----------|---------|
| `LANGFUSE_PUBLIC_KEY` | LangFuse public key |
| `LANGFUSE_SECRET_KEY` | LangFuse secret key |
| `LANGFUSE_HOST` | LangFuse server URL |

Configure LangFuse either through environment variables or via the Settings UI.

### SIGMA / GitHub Integration

| Variable | Purpose | Default |
|----------|---------|---------|
| `SIGMA_REPO_PATH` | Path to SIGMA rules repo | `./data/sigma-repo` |
| `GITHUB_TOKEN` | GitHub PAT for PR submission | — |
| `GITHUB_REPO` | Target repo for SIGMA rule PRs | `dfirtnt/Huntable-SIGMA-Rules` |

## Source Configuration

- **YAML File**: `config/sources.yaml` (version-controlled template)
- **Runtime Source of Truth**: PostgreSQL `sources` table
- **Auto-sync behavior**: YAML → DB sync runs automatically on startup if fewer than 5 sources exist in the database
- **Manual sync**: Use `./run_cli.sh sync-sources --config config/sources.yaml --no-remove`
- **Disable auto-sync**: Set `DISABLE_SOURCE_AUTO_SYNC=true`

See [Source Configuration Precedence](../guides/source-config.md) for details.

## Celery Task Queues

The system uses specialized queues for workload isolation:

| Queue | Purpose |
|-------|---------|
| `default` | General tasks, embeddings |
| `source_checks` | Periodic source polling |
| `maintenance` | Cleanup, pruning, SIGMA sync |
| `reports` | Daily report generation |
| `connectivity` | Source connectivity testing |
| `collection` | Manual source collection |
| `workflows` | Agentic workflow execution |

## Periodic Tasks

| Task | Schedule | Queue |
|------|----------|-------|
| `check_all_sources` | Every 30 minutes | `source_checks` |
| `cleanup_old_data` | Daily at 2:00 AM | `maintenance` |
| `generate_daily_report` | Daily at 6:00 AM | `reports` |
| `embed_new_articles` | Daily at 3:00 PM | `default` |
| `sync_sigma_rules` | Weekly (Sunday 4:00 AM) | `maintenance` |
| `update_provider_model_catalogs` | Daily at 4:00 AM | `maintenance` |

The provider model catalog is also refreshed **at setup** (`./setup.sh`) and **at start** (`./start.sh`) so users see the current OpenAI/Anthropic/Gemini model list immediately; the daily run keeps it updated for long-running instances.

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

_Last verified: February 2025_
