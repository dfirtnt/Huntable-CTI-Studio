# Docker Architecture Guide

This reflects the current `docker-compose.yml` and `docker-compose.override.yml`.

## Services

| Service | Image / Build | Purpose |
|--------|----------------|---------|
| **postgres** | `pgvector/pgvector:pg15` | Primary DB; pgvector extension. Container: `cti_postgres`. |
| **redis** | `redis:7-alpine` | Cache and Celery broker. Appendonly + `maxmemory` / `allkeys-lru`. Container: `cti_redis`. |
| **web** | `Dockerfile` | FastAPI app: `uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001 --reload`. Ports: 8001 (API/UI), 8888. |
| **worker** | `Dockerfile` | Celery worker queues: `default`, `source_checks`, `maintenance`, `reports`, `connectivity`, `collection`. |
| **workflow_worker** | `Dockerfile` | Celery worker for `workflows` queue (agentic/LangGraph tasks). |
| **scheduler** | `Dockerfile` | Celery beat: `celery -A src.worker.celery_app beat --loglevel=debug`. |
| **cli** | `Dockerfile` | Profile `tools`. Command: `python -m src.cli.main`. Same Postgres/Redis as app. |

## Key environment

- **DB:** `POSTGRES_PASSWORD` required. `DATABASE_URL=postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper`.
- **Broker:** `REDIS_URL=redis://redis:6379/0`.
- **AI/LLM:** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHATGPT_API_KEY`; `LMSTUDIO_API_URL` (default `http://host.docker.internal:1234/v1`), `LMSTUDIO_MODEL*`, `LMSTUDIO_EMBEDDING_*`; optional Langfuse via `LANGFUSE_*`.
- **Timezone:** `TZ=America/New_York`.

## Volumes and mounts

- **Named volumes:** `postgres_data`, `redis_data`, `langflow_data` (defined; LangFlow service is commented out).
- **Postgres init:** With override, `./init-scripts` is mounted at `/docker-entrypoint-initdb.d` (all scripts there run on first init).
- **App bind mounts (web / workers):** `./src`, `./config`, `./logs`, `./tests`, `./models`, `./outputs`, `./scripts`, `./allure-results`, `./test-results`, `../Huntable-SIGMA-Rules` → `/app/sigma-repo`. Web only: `./backups`, Docker socket `/var/run/docker.sock`, and host timezone at `/etc/localtime`.
- **CLI:** `./src`, `./config`, `./logs`, `./tests`, `./data`, `./backups`.

## Resource limits (env-overridable)

- postgres: `POSTGRES_MEMORY_LIMIT` / `POSTGRES_MEMORY_RESERVATION` (defaults 2G / 512M).
- redis: `REDIS_MEMORY_LIMIT` / `REDIS_MEMORY_RESERVATION` (defaults 512M / 128M); `REDIS_MAXMEMORY` (default 512mb).
- web: `WEB_MEMORY_LIMIT` / `WEB_MEMORY_RESERVATION` (defaults 1G / 256M).
- worker: `WORKER_MEMORY_LIMIT` / `WORKER_MEMORY_RESERVATION` (defaults 2G / 512M), `WORKER_CONCURRENCY` (default 2).
- workflow_worker: `WORKFLOW_WORKER_MEMORY_LIMIT` / `WORKFLOW_WORKER_MEMORY_RESERVATION` (defaults 2G / 512M), `WORKFLOW_WORKER_CONCURRENCY` (default 2).
- scheduler: 256M / 64M (fixed in compose).

## Health checks

- **postgres:** `pg_isready -U cti_user -d cti_scraper`.
- **redis:** `timeout 3 redis-cli ping | grep -q PONG`.
- **web:** Image `HEALTHCHECK`: `curl -f http://localhost:8001/health`.
- **worker / workflow_worker:** `celery -A src.worker.celery_app inspect ping`.
- **scheduler:** `python -c 'import sys; sys.exit(0)'`.

## Networking

- Single bridge network: `cti_network`. Services resolve by name (`postgres`, `redis`, `web`, etc.).
- Exposed ports: 5432 (postgres), 6379 (redis), 8001 and 8888 (web). Use 8001 for API/UI from the host.

## CLI alignment

`./run_cli.sh` runs `docker-compose run --rm cli python -m src.cli.main` with the given args, so the containerized CLI uses the same Postgres and Redis as the web app. The `cli` service is under profile `tools` (not started by default `docker-compose up`).

## Dockerfiles

- **Dockerfile:** Python 3.11-slim; system deps (Postgres client, Playwright/Chromium, Docker CLI); `requirements.txt` + `requirements-test.txt`; non-root user; used by compose for web, worker, workflow_worker, scheduler, cli.
- **Dockerfile.prod:** Multi-stage build; slimmer runtime (no Playwright/test deps); for production-style images.

_Last verified: Feb 2025_
