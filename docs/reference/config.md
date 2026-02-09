# Configuration Reference

Configuration is driven by `.env`, `docker-compose.yml`, and YAML files under `config/`.

## Environment variables (.env)
- `POSTGRES_PASSWORD` (required): used by Postgres and `DATABASE_URL` in compose
- `DATABASE_URL`: set in compose to `postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper`
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`: optional LLM providers
- `LMSTUDIO_API_URL` (default `http://host.docker.internal:1234/v1`), `LMSTUDIO_MODEL`, `LMSTUDIO_MODEL_RANK`, `LMSTUDIO_MODEL_EXTRACT`, `LMSTUDIO_MODEL_SIGMA`
- `LMSTUDIO_EMBEDDING_URL`, `LMSTUDIO_EMBEDDING_MODEL`: required for Sigma similarity search
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`: optional tracing (see Settings UI)
- `DISABLE_SOURCE_AUTO_SYNC`: disable initial YAML seeding even when <5 sources exist

## Docker Compose services
- **web**: FastAPI app (`uvicorn src.web.modern_main:app --reload`), ports `8001`, `8888`
- **worker**: Celery worker
- **scheduler**: Celery beat
- **postgres**: `pgvector/pgvector:pg15` on `5432`, volume `postgres_data`
- **redis**: `redis:7-alpine` on `6379`
- **cli** (profile `tools`): runs `python -m src.cli.main` via `./run_cli.sh`

## Source configuration
- File: `config/sources.yaml`
- Runtime source of truth: PostgreSQL `sources` table
- YAML seeding: runs only when the database has fewer than 5 sources; manual sync via `./run_cli.sh sync-sources --config config/sources.yaml --no-remove`

## Port mappings
Default host ports (see `../development/PORT_CONFIGURATION.md`):
- Web/API: `8001`
- Aux/debug: `8888`
- Postgres: `5432`
- Redis: `6379`

## Health and diagnostics
- App health: `GET http://localhost:8001/health`
- API docs: `http://localhost:8001/docs`
- Workflow executions: `GET /api/workflow/executions`
- Ingestion analytics: `GET /api/health/ingestion`

Adjustments should be made in `docker-compose.yml` plus matching environment variables; restart with `docker-compose up -d --build` after changing ports or credentials.

---

## Comprehensive Environment Variable Reference

### Core Infrastructure

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://cti_user:cti_password@postgres:5432/cti_scraper` | Yes |
| `POSTGRES_PASSWORD` | PostgreSQL password | — | Yes |
| `REDIS_URL` | Redis connection for Celery and caching | `redis://redis:6379/0` | Yes |
| `SOURCES_CONFIG` | Path to sources YAML | `config/sources.yaml` | No |
| `ENVIRONMENT` | Environment name | `development` | No |
| `DISABLE_SOURCE_AUTO_SYNC` | Skip YAML→DB sync on startup | `false` | No |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://redis:6379/0` | No |
| `CELERY_MAX_TASKS_PER_CHILD` | Worker task limit before restart | `50` | No |

### LLM Provider Keys

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `OPENAI_API_KEY` | OpenAI API key | — | No |
| `ANTHROPIC_API_KEY` | Anthropic API key | — | No |
| `GEMINI_API_KEY` | Google Gemini API key | — | No |

### Workflow-Specific LLM Configuration

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `WORKFLOW_OPENAI_API_KEY` | OpenAI key for workflows | Falls back to `OPENAI_API_KEY` | No |
| `WORKFLOW_ANTHROPIC_API_KEY` | Anthropic key for workflows | Falls back to `ANTHROPIC_API_KEY` | No |
| `WORKFLOW_GEMINI_API_KEY` | Gemini key for workflows | Falls back to `GEMINI_API_KEY` | No |
| `WORKFLOW_OPENAI_ENABLED` | Enable OpenAI in workflows | DB setting | No |
| `WORKFLOW_ANTHROPIC_ENABLED` | Enable Anthropic in workflows | DB setting | No |
| `WORKFLOW_GEMINI_ENABLED` | Enable Gemini in workflows | DB setting | No |
| `WORKFLOW_LMSTUDIO_ENABLED` | Enable LMStudio in workflows | DB setting | No |
| `WORKFLOW_OPENAI_MODEL` | OpenAI model for workflows | — | No |
| `WORKFLOW_ANTHROPIC_MODEL` | Anthropic model for workflows | — | No |
| `WORKFLOW_GEMINI_MODEL` | Gemini model for workflows | — | No |

### LMStudio Configuration

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `LMSTUDIO_API_URL` | LMStudio API base URL | `http://host.docker.internal:1234/v1` | No |
| `LMSTUDIO_MODEL` | Default LMStudio model | `deepseek-r1-qwen3-8b` | No |
| `LMSTUDIO_MODEL_RANK` | Model for ranking agent | — | No |
| `LMSTUDIO_MODEL_EXTRACT` | Model for extraction agent | — | No |
| `LMSTUDIO_MODEL_SIGMA` | Model for SIGMA generation | — | No |
| `LMSTUDIO_EMBEDDING_URL` | Embedding API URL | `http://localhost:1234/v1/embeddings` | No |
| `LMSTUDIO_EMBEDDING_MODEL` | Embedding model | `text-embedding-e5-base-v2` | No |
| `LMSTUDIO_TEMPERATURE` | LLM temperature | — | No |
| `LMSTUDIO_TOP_P` | Top-p sampling | — | No |
| `LMSTUDIO_SEED` | Random seed for reproducibility | — | No |
| `LMSTUDIO_MAX_CONTEXT` | Max context window size | — | No |

### Content Filtering

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `CONTENT_FILTERING_ENABLED` | Enable ML content filtering | `true` | No |
| `CONTENT_FILTERING_CONFIDENCE` | Minimum confidence threshold | `0.7` | No |
| `CHATGPT_CONTENT_LIMIT` | Max content chars for ChatGPT | `1000000` | No |
| `ANTHROPIC_CONTENT_LIMIT` | Max content chars for Anthropic | `1000000` | No |

### LangFuse Observability

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `LANGFUSE_PUBLIC_KEY` | LangFuse public key | — | No |
| `LANGFUSE_SECRET_KEY` | LangFuse secret key | — | No |
| `LANGFUSE_HOST` | LangFuse server URL | — | No |

### SIGMA / GitHub

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `SIGMA_REPO_PATH` | Path to SIGMA rules repo | `./data/sigma-repo` | No |
| `GITHUB_TOKEN` | GitHub PAT for PR submission | — | No |
| `GITHUB_REPO` | Target repo for SIGMA rule PRs | `dfirtnt/Huntable-SIGMA-Rules` | No |

## Celery Queues

The system uses 8 task queues for workload isolation:

| Queue | Purpose |
|-------|---------|
| `default` | General tasks, embeddings |
| `source_checks` | Periodic source polling |
| `priority_checks` | High-priority source checks |
| `maintenance` | Cleanup, pruning, SIGMA sync |
| `reports` | Daily report generation |
| `connectivity` | Source connectivity testing |
| `collection` | Manual source collection |
| `workflows` | Agentic workflow execution |

## Celery Periodic Tasks

| Task | Schedule | Queue |
|------|----------|-------|
| `check_all_sources` | Every 30 minutes | `source_checks` |
| `cleanup_old_data` | Daily at 2:00 AM | `maintenance` |
| `generate_daily_report` | Daily at 6:00 AM | `reports` |
| `embed_new_articles` | Daily at 3:00 PM | `default` |
| `sync_sigma_rules` | Weekly (Sunday 4:00 AM) | `maintenance` |
