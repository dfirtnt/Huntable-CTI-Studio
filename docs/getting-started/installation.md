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
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD and optional API keys
./start.sh
```

The `start.sh` script will:
- Create necessary `logs/` and `data/` directories
- Run `docker-compose up --build -d`
- Health-check PostgreSQL, Redis, and the web application
- Sync SigmaHQ repo and optionally index rules (when LM Studio / embeddings are available)
- Optionally prompt: **Run MkDocs docs build/server?** If you answer **y**, it runs `./run_mkdocs.sh` in the background (logs in `logs/mkdocs.log`); the terminal stays free

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

Before running `./start.sh`, configure these variables in `.env`:

### Required
- `POSTGRES_PASSWORD=<strong password>` - Database authentication

### Optional LLM Keys
- `OPENAI_API_KEY` - For OpenAI models
- `ANTHROPIC_API_KEY` - For Claude models
- `CHATGPT_API_KEY` - For ChatGPT API

### LM Studio Configuration
- `LMSTUDIO_API_URL` - Default: `http://host.docker.internal:1234/v1`
- `LMSTUDIO_MODEL` - Main completion model
- `LMSTUDIO_MODEL_RANK` - Ranking model
- `LMSTUDIO_MODEL_EXTRACT` - Observable extraction model
- `LMSTUDIO_MODEL_SIGMA` - SIGMA rule generation model

### Langfuse Tracing (Optional)
Configure via the Settings UI or environment variables:
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- Additional Langfuse settings in `.env.example`

**Notes**:
- `.env.example` template includes required PostgreSQL configuration
- Docker uses `DATABASE_URL=postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper`
- Test template available at `env.test.template` for pytest/Playwright values

## Docker Services

The `docker-compose.yml` stack includes:

- **postgres**: `pgvector/pgvector:pg15` with persistent `postgres_data` volume
- **redis**: `redis:7-alpine` with `redis_data` volume
- **web**: FastAPI application (uvicorn on port 8001/8888)
- **worker**: Celery worker handling queues: default, source_checks, maintenance, reports, connectivity, collection (does not process `workflows` queue)
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
./run_cli.sh sync-sources --config config/sources.yaml --no-remove
./run_cli.sh rescore --article-id 123 --dry-run
```

The `run_cli.sh` script executes commands inside the Docker `cli` container.

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
- Arguments are passed directly to `python -m src.cli.main`
- Check CLI logs: `docker-compose logs cli`

### Container Won't Start
- Review logs: `docker-compose logs [service_name]`
- Check disk space: `df -h`
- Verify Docker daemon is running
- Try rebuilding: `docker-compose up --build -d`

## Next Steps

- Configure your sources in [`configuration.md`](configuration.md)
- Walk through your first workflow in [`first-workflow.md`](first-workflow.md)
- Review the [quickstart guide](../quickstart.md) for common tasks

---

_Last verified: February 2025_
