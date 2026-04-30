# Installation

This guide covers installing and running Huntable CTI Studio using Docker Compose, the supported deployment method.

## Prerequisites

- **Docker Desktop** with Compose plugin installed
- **8GB RAM minimum** (16GB recommended for production use)
- **Python 3.11** only if you plan to run tests or tooling locally (otherwise Docker-only)

## Quick Start

```bash
git clone https://github.com/dfirtnt/Huntable-CTI-Studio.git
cd Huntable-CTI-Studio
./setup.sh --no-backups
# or non-interactive:
# ./setup.sh --non-interactive --no-backups
./start.sh
```

`setup.sh` provisions `.env` and first-run security settings.

The `start.sh` script will:
- Reuse the pre-provisioned `.env` from setup (it will fail fast if missing or still templated)
- Create necessary runtime directories (`logs/`, `backups/`, `models/`, `outputs/`, `data/`)
- Run `docker-compose up --build -d`
- Health-check PostgreSQL, Redis, and the web application
- Sync SigmaHQ repo and optionally index rules (when LM Studio / embeddings are available)
- Seed eval articles from config and refresh the **LLM provider model catalog** (OpenAI/Anthropic) so workflow model dropdowns show the current list without waiting for the daily Celery run
- Build the MkDocs docs site and start the MkDocs server in the background (logs in `logs/mkdocs.log`) when `mkdocs.yml` is present

## Access Points

Once running, access the application at:

- **Web UI & API**: http://localhost:8001
- **API Documentation**: http://localhost:8001/docs
- **Health Check**: http://localhost:8001/health

Additional exposed ports:
- PostgreSQL: 5432
- Redis: 6379
- Jupyter (optional): 8888

## Environment Configuration

Before running `./start.sh`, run `./setup.sh` (which creates and configures `.env`). If you edit `.env` manually afterward, keep these variables valid:

### Required
- `POSTGRES_PASSWORD=<strong password>` - Database authentication

### Optional LLM Keys
- `OPENAI_API_KEY` - For OpenAI - ChatGPT models
- `ANTHROPIC_API_KEY` - For Anthropic - Claude models

If you enter these during `./setup.sh`, they are written to `.env` and used at runtime; you do not need to re-enter them in the web Settings page. They will not appear in the Settings UI (those fields show database-stored values), but workflows will still use the keys from `.env`. See [Configuration](configuration.md#llm-provider-keys) for details.

### LM Studio Configuration
- `LMSTUDIO_API_URL` - Default: `http://host.docker.internal:1234/v1`
- `LMSTUDIO_MODEL` - Main completion model
- `LMSTUDIO_MODEL_RANK` - Ranking model
- `LMSTUDIO_MODEL_EXTRACT` - Observable extraction model
- `LMSTUDIO_MODEL_SIGMA` - SIGMA rule generation model

### Langfuse Tracing (Optional)
Langfuse is an optional tracing integration for workflow and LLM observability.

!!! warning "Cloud-only support and security boundary"
    Huntable CTI Studio supports **Langfuse Cloud only**. Local or self-hosted Langfuse deployments are not supported by this project.

    Enabling Langfuse sends operational telemetry to a third-party cloud service. Depending on the workflow, traces may contain prompts, article excerpts, extracted observables, model outputs, workflow metadata, and debug context. Enable it only if your organization permits sending that data to Langfuse Cloud.

Configure Langfuse through the Settings UI or environment variables:
- `LANGFUSE_PUBLIC_KEY` required
- `LANGFUSE_SECRET_KEY` required
- `LANGFUSE_HOST` optional, defaults to `https://cloud.langfuse.com`
- `LANGFUSE_PROJECT_ID` optional, but recommended for stronger workflow debug links

For the full setup flow, region host selection, verification steps, and troubleshooting, see [Langfuse Setup](../guides/langfuse-setup.md).

**Notes**:
- `.env.example` template includes required PostgreSQL configuration
- Docker uses `DATABASE_URL=postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper`
- Test template available at `env.test.template` for pytest/Playwright values

## Docker Services

The `docker-compose.yml` stack includes:

- **postgres**: `pgvector/pgvector:pg15` with persistent `postgres_data` volume
- **redis**: `redis:7-alpine` with `redis_data` volume
- **web**: FastAPI application (uvicorn on port 8001/8888)
- **worker**: Celery worker handling queues: collection_immediate (user "Collect Now"), default, source_checks, maintenance, reports, connectivity, collection (does not process `workflows` queue)
- **workflow_worker**: Dedicated Celery worker that consumes only the `workflows` queue (agentic workflow execution); separate from the main worker
- **scheduler**: Celery beat for scheduled tasks
- **cli** (profile `tools`): CLI interface for management commands

## CLI Usage

Run CLI commands using the wrapper script:

```bash
./run_cli.sh --help
./run_cli.sh init --config config/sources.yaml
./run_cli.sh collect --dry-run
./run_cli.sh search --query ransomware --limit 25 --format json
./run_cli.sh stats
./run_cli.sh sync-sources --config config/sources.yaml --no-remove
./run_cli.sh compare-sources --config-path config/sources.yaml
./run_cli.sh rescore --article-id 123 --dry-run
./run_cli.sh rescore-ml --article-id 123 --dry-run
./run_cli.sh capabilities check
./run_cli.sh embed stats
./run_cli.sh sigma stats
```

The `run_cli.sh` script executes commands inside the Docker `cli` container.
For the full command reference, see [CLI Reference](../reference/cli.md).

## Verification

Check that all services are running:

```bash
# View container status
docker-compose ps

# Check application health
curl http://localhost:8001/health

# View web application logs
docker-compose logs -f web

# View all service logs
docker-compose logs -f
```

## Common Operations

```bash
# Restart a specific service
docker-compose restart web

# Restart all services
docker-compose restart

# Stop the stack
docker-compose down

# Stop and remove volumes (deletes data)
docker-compose down -v

# View resource usage
docker stats
```

## Troubleshooting

### Port Conflicts
If default ports are in use, modify `docker-compose.yml`:
```yaml
services:
  web:
    ports:
      - "9001:8001"  # Change host port from 8001 to 9001
```
See `configuration.md` for detailed port configuration.

### Database Authentication Errors
- Ensure `POSTGRES_PASSWORD` is set in `.env`
- Verify the password matches between `.env` and `docker-compose.yml`
- Check PostgreSQL logs: `docker-compose logs postgres`

### AI/LLM Errors
- Confirm API keys are set in `.env`
- For LM Studio, verify the endpoint is reachable from Docker containers
- Test connection: `curl http://host.docker.internal:1234/v1/models`

### CLI Command Errors
- Use `./run_cli.sh --help` to see current commands
- Arguments are passed directly to `python3 -m src.cli.main`
- Check CLI logs: `docker-compose logs cli`

### Container Won't Start
- Review logs: `docker-compose logs [service_name]`
- Check disk space: `df -h`
- Verify Docker daemon is running
- Try rebuilding: `docker-compose up --build -d`

## Agent evals

**MLOps → Agent evals** (Load Eval Articles, run subagent evals) use article snapshots committed in the repo under `config/eval_articles_data/{subagent}/articles.json`. No network fetch is required: the web app seeds these files into the DB at startup, and `start.sh` also runs the seed. If "Load Eval Articles" shows no articles, ensure you have the latest repo so the committed JSON files are present.

The committed eval article directories cover all six extraction sub-agents:

| Directory | Sub-agent |
|-----------|-----------|
| `config/eval_articles_data/cmdline/` | CmdlineExtract |
| `config/eval_articles_data/process_lineage/` | ProcTreeExtract |
| `config/eval_articles_data/hunt_queries/` | HuntQueriesExtract |
| `config/eval_articles_data/registry_artifacts/` | RegistryExtract |
| `config/eval_articles_data/windows_services/` | ServicesExtract |
| `config/eval_articles_data/scheduled_tasks/` | ScheduledTasksExtract |

## Next Steps

- Configure your sources in [`configuration.md`](configuration.md)
- Walk through your first workflow in [`first-workflow.md`](first-workflow.md)
- Review the [quickstart guide](../quickstart.md) for common tasks

---

_Last verified: April 2026_
