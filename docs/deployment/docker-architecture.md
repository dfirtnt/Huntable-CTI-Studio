# Docker Architecture Guide

This reflects the current `docker-compose.yml`.

## Services

| Service | Image / Build | Purpose |
|--------|----------------|---------|
| **postgres** | `pgvector/pgvector:pg15` | Primary DB; pgvector extension. Container: `cti_postgres`. |
| **redis** | `redis:7-alpine` | Cache and Celery broker. Appendonly + `maxmemory` / `allkeys-lru`. Container: `cti_redis`. |
| **web** | `Dockerfile` | FastAPI app: `uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001 --workers 2`. Port: 8001 (API/UI). |
| **worker** | `Dockerfile` | Celery worker queues: `collection_immediate` (user Collect Now), `default`, `source_checks`, `maintenance`, `reports`, `connectivity`, `collection`. |
| **workflow_worker** | `Dockerfile` | Celery worker for `workflows` queue (agentic/LangGraph tasks). |
| **codex_auth_init** | `busybox:1.36.1` | One-shot initializer that grants the application user ownership of the shared Codex authentication volume. |
| **scheduler** | `Dockerfile` | Celery beat: `celery -A src.worker.celery_app beat --loglevel=${CELERY_LOG_LEVEL:-info}`. |
| **cli** | `Dockerfile` | Profile `tools`. Command: `python -m src.cli.main`. Same Postgres/Redis as app. |

## Key environment

- **DB:** `POSTGRES_PASSWORD` required. `DATABASE_URL=postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper`.
- **Broker:** `REDIS_URL=redis://redis:6379/0`.
- **AI/LLM:** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `CHATGPT_API_KEY`; optional local-LLM support uses `LMSTUDIO_API_URL` (default `http://host.docker.internal:1234/v1`) and `LMSTUDIO_MODEL*`. The optional Codex workflow provider uses `WORKFLOW_CODEX_ENABLED`, `WORKFLOW_CODEX_MODEL`, and the shared `codex_auth` volume; its ChatGPT login stays inside Codex rather than in an API-key environment variable. LM Studio is not required by the application or by embeddings; embeddings run locally through sentence-transformers. Langfuse (`LANGFUSE_*`) is optional but is **not** declared in `docker-compose.yml`'s `environment:` blocks, so it is not forwarded from a host `.env` file into these containers; configure it via the Settings UI instead (see [Langfuse Setup](../guides/langfuse-setup.md)).
- **Timezone:** `TZ=America/New_York`.

## Volumes and mounts

- **Named volumes:** `postgres_data`, `redis_data`, `langflow_data` (defined; LangFlow service is commented out), `hf_cache` (Hugging Face model cache; mounted on `web` and `cli`), and `codex_auth` (shared Codex-managed ChatGPT authentication for web and workers).
- **Postgres init:** `./init-scripts` is mounted at `/docker-entrypoint-initdb.d` (all scripts there run on first init).
- **App bind mounts (web / workers):** `./src`, `./config`, `./logs`, `./tests`, `./models`, `./outputs`, `./scripts`, `./test-results`, `${HOME}/Huntable-SIGMA-Rules` → `/app/sigma-repo`. Web only: `./docs/contracts`, `./data/diagnoses`, `./backups`, Docker socket `/var/run/docker.sock`, host timezone at `/etc/localtime`, and the `hf_cache` volume. The Sigma repo is set up during `./setup.sh` (clone or create with rules structure); see [Configuration](../getting-started/configuration.md) (SIGMA / GitHub Integration).
- **CLI:** `./src`, `./config`, `./scripts`, `./logs`, `./tests`, `./data`, `${HOME}/Huntable-SIGMA-Rules` → `/app/sigma-repo`, `./backups`, and the `hf_cache` volume.

## Resource limits (env-overridable)

- postgres: `POSTGRES_MEMORY_LIMIT` / `POSTGRES_MEMORY_RESERVATION` (defaults 2G / 512M).
- redis: `REDIS_MEMORY_LIMIT` / `REDIS_MEMORY_RESERVATION` (defaults 512M / 128M); `REDIS_MAXMEMORY` (default 512mb).
- web: `WEB_MEMORY_LIMIT` / `WEB_MEMORY_RESERVATION` (defaults 3G / 512M).
- worker: `WORKER_MEMORY_LIMIT` / `WORKER_MEMORY_RESERVATION` (defaults 2G / 512M), `WORKER_CONCURRENCY` (default 2).
- workflow_worker: `WORKFLOW_WORKER_MEMORY_LIMIT` / `WORKFLOW_WORKER_MEMORY_RESERVATION` (defaults 2G / 512M), `WORKFLOW_WORKER_CONCURRENCY` (default 2).
- scheduler: 512M / 128M (fixed in compose).

## Health checks

- **postgres:** `pg_isready -U cti_user -d cti_scraper`.
- **redis:** `timeout 3 redis-cli ping | grep -q PONG`.
- **web:** Image `HEALTHCHECK`: `curl -f http://localhost:8001/health`.
- **worker / workflow_worker:** `celery -A src.worker.celery_app inspect ping`.
- **scheduler:** `python -c 'import sys; sys.exit(0)'`.

## Networking

- Single bridge network: `cti_network`. Services resolve by name (`postgres`, `redis`, `web`, etc.).
- Exposed ports: 5432 (postgres), 6379 (redis), 8001 (web).

## CLI alignment

`./run_cli.sh` runs `docker compose run --rm cli python -m src.cli.main` with the given args (falling back to the legacy `docker-compose` binary if the `docker compose` plugin is unavailable), so the containerized CLI uses the same Postgres and Redis as the web app. The `cli` service is under profile `tools` (not started by default `docker compose up`).

## Dockerfiles

- **Dockerfile:** Python 3.11-slim; system deps (Postgres client, Playwright/Chromium, Docker CLI); deps installed via `uv sync --frozen --group test` from `pyproject.toml` + `uv.lock`; non-root user; used by compose for web, worker, workflow_worker, scheduler, cli.
- **Dockerfile.prod:** Multi-stage build; slimmer runtime (no Playwright/test deps); for production-style images.

_Last updated: 2026-07-05_
