# Docker Architecture Guide

This reflects the current `docker-compose.yml`.

## Services

| Service | Image / Build | Purpose |
|--------|----------------|---------|
| **postgres** | `pgvector/pgvector:pg15` | Primary DB; pgvector extension. Container: `cti_postgres`. |
| **redis** | `redis:7-alpine` | Cache and Celery broker. Appendonly + `maxmemory` / `allkeys-lru`. Container: `cti_redis`. |
| **web** | `Dockerfile:web-runtime` | FastAPI app: `uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001 --workers 2`. Port: 8001 (API/UI). No Docker socket or Docker CLI. |
| **maintenance** | `Dockerfile:maintenance-runtime` | Internal-only allowlisted backup/restore executor. It is the sole runtime with the Docker socket and CLI. Listens on 8002 (not published to the host; reached by `web` at `MAINTENANCE_API_URL=http://maintenance:8002`). |
| **worker** | `Dockerfile:ingest-worker-runtime` | Celery worker queues: `collection_immediate` (user Collect Now), `default`, `source_checks`, `maintenance`, `reports`, `connectivity`, `collection`. Source collection, OCR, Playwright/Chromium. |
| **workflow_worker** | `Dockerfile:workflow-worker-runtime` | Celery worker for `workflows` queue (agentic/LangGraph tasks). LangGraph + pinned Codex app-server support; no browser/OCR/Docker CLI. |
| **codex_auth_init** | `busybox:1.36.1` | One-shot initializer that grants the application user ownership of the shared Codex authentication volume. |
| **scheduler** | `Dockerfile:scheduler-runtime` | Celery beat: `celery -A src.worker.celery_app beat --loglevel=${CELERY_LOG_LEVEL:-info}`. |
| **cli** | `Dockerfile:semantic-tools-runtime` | Profile `tools`. Command: `python -m src.cli.main`. Same Postgres/Redis as app. Local embeddings (Torch + sentence-transformers). |
| **mcp_http** | `Dockerfile:semantic-tools-runtime` | Profile `mcp`. FastMCP over streamable-HTTP for the Docker MCP Gateway (bearer-protected via `HUNTABLE_MCP_TOKEN`; fails closed without it). Published on `127.0.0.1:${HUNTABLE_MCP_PORT:-8009}` only. Same tools/write-risk tiers as the stdio MCP server. See [MCP Gateway](../guides/mcp-gateway.md) and [MCP Tools Reference](../reference/mcp-tools.md). |

## Key environment

- **DB:** `POSTGRES_PASSWORD` required. `DATABASE_URL=postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper`.
- **Broker:** `REDIS_URL=redis://redis:6379/0`.
- **AI/LLM:** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `CHATGPT_API_KEY`; optional local-LLM support uses `LMSTUDIO_API_URL` (default `http://host.docker.internal:1234/v1`) and `LMSTUDIO_MODEL*`. The optional Codex workflow provider uses `WORKFLOW_CODEX_ENABLED`, `WORKFLOW_CODEX_MODEL`, and the shared `codex_auth` volume; its ChatGPT login stays inside Codex rather than in an API-key environment variable. LM Studio is not required by the application or by embeddings; embeddings run locally through sentence-transformers. Langfuse (`LANGFUSE_*`) is optional but is **not** declared in `docker-compose.yml`'s `environment:` blocks, so it is not forwarded from a host `.env` file into these containers; configure it via the Settings UI instead (see [Langfuse Setup](../guides/langfuse-setup.md)).
- **Timezone:** `TZ=America/New_York`.

## Volumes and mounts

- **Named volumes:** `postgres_data`, `redis_data`, `langflow_data` (defined; LangFlow service is commented out), `hf_cache` (Hugging Face model cache; mounted on `web` and `cli`), and `codex_auth` (shared Codex-managed ChatGPT authentication for web and workers).
- **Postgres init:** `./init-scripts` is mounted at `/docker-entrypoint-initdb.d` (all scripts there run on first init).
- **App bind mounts (web / workers):** `./src`, `./config`, `./logs`, `./tests`, `./models`, `./outputs`, `./scripts`, `./test-results`, `${HOME}/Huntable-SIGMA-Rules` → `/app/sigma-repo`. Web only: `./docs/contracts`, `./data/diagnoses`, `./backups`, host timezone at `/etc/localtime`, and the `hf_cache` volume. The maintenance service alone mounts `/var/run/docker.sock`. The Sigma repo is set up during `./setup.sh` (clone or create with rules structure); see [Configuration](../getting-started/configuration.md) (SIGMA / GitHub Integration).
- **CLI:** `./src`, `./config`, `./scripts`, `./logs`, `./tests`, `./data`, `${HOME}/Huntable-SIGMA-Rules` → `/app/sigma-repo`, `./backups`, and the `hf_cache` volume.
- **mcp_http:** `./src`, `./config`, `./scripts`, `./logs`, `./data`, and the `hf_cache` volume. No Sigma-repo or backups mount.

## Resource limits (env-overridable)

- postgres: `POSTGRES_MEMORY_LIMIT` / `POSTGRES_MEMORY_RESERVATION` (defaults 2G / 512M).
- redis: `REDIS_MEMORY_LIMIT` / `REDIS_MEMORY_RESERVATION` (defaults 512M / 128M); `REDIS_MAXMEMORY` (default 512mb).
- web: `WEB_MEMORY_LIMIT` / `WEB_MEMORY_RESERVATION` (defaults 3G / 512M).
- worker: `WORKER_MEMORY_LIMIT` / `WORKER_MEMORY_RESERVATION` (defaults 2G / 512M), `WORKER_CONCURRENCY` (default 2).
- workflow_worker: `WORKFLOW_WORKER_MEMORY_LIMIT` / `WORKFLOW_WORKER_MEMORY_RESERVATION` (defaults 2G / 512M), `WORKFLOW_WORKER_CONCURRENCY` (default 2).
- scheduler: 512M / 128M (fixed in compose).
- maintenance, cli, mcp_http: no `deploy.resources` block in compose; unbounded by default.

## Health checks

- **postgres:** `pg_isready -U cti_user -d cti_scraper`.
- **redis:** `timeout 3 redis-cli ping | grep -q PONG`.
- **web:** Image `HEALTHCHECK`: `curl -f http://localhost:8001/health`.
- **worker / workflow_worker:** `celery -A src.worker.celery_app inspect ping`.
- **scheduler:** `python -c 'import sys; sys.exit(0)'`.
- **mcp_http:** `curl -fsS http://localhost:8009/healthz`.

## Networking

- Single bridge network: `cti_network`. Services resolve by name (`postgres`, `redis`, `web`, etc.).
- Exposed ports: 5432 (postgres), 6379 (redis), 8001 (web), 8009 (mcp_http, bound to `127.0.0.1` only).

## CLI alignment

`./run_cli.sh` runs `docker compose run --rm cli python -m src.cli.main` with the given args (falling back to the legacy `docker-compose` binary if the `docker compose` plugin is unavailable), so the containerized CLI uses the same Postgres and Redis as the web app. The `cli` service is under profile `tools` (not started by default `docker compose up`).

## Dockerfiles

- **Dockerfile:** Python 3.11-slim multi-stage build. The builder creates locked role-specific virtual environments from `pyproject.toml` dependency groups; each runtime target copies only its role environment. Compose targets and their intentional capabilities:
  - `web-runtime`: FastAPI app. Excludes Docker CLI/socket and OCR; it retains Codex because web routes probe its subscription/provider capability.
  - `maintenance-runtime`: authenticated, internal-only allowlisted backup/restore operations; this is the privileged Docker-socket boundary.
  - `scheduler-runtime`: Celery beat only; inherits the lean web/base Python environment.
  - `ingest-worker-runtime`: source-collection worker. Playwright/Chromium + Tesseract for scraping/OCR; local Torch + sentence-transformers for extraction. No Codex, no Docker CLI/socket.
  - `workflow-worker-runtime`: workflow worker. LangGraph + pinned Codex app-server binary (optional provider, shares the `codex_auth` volume). No Playwright/Chromium, no Tesseract/OCR, no Docker CLI/socket.
  - `semantic-tools-runtime`: CLI + MCP. Torch + sentence-transformers for local embeddings with LM Studio unavailable. No browser, no OCR, no Codex, no Docker CLI (the optional `cli backup` system-backup subcommand needs `docker exec`, which is unavailable here and in the `cli` service's mounts; backups run via the web service or host scripts). Backs both the `cli` and `mcp_http` services.
  - `development-runtime`: compatibility target; no active Compose service uses it yet, but it remains the default for unconverted services.
- **Dockerfile.prod:** Multi-stage build; slimmer runtime (no Playwright/test deps); for production-style images. Not part of the active Compose/runtime contract here.

_Last updated: 2026-08-11_
_Last reviewed: 2026-09-01_
