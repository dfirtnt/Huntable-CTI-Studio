# Docker Architecture Guide

This reflects the current `docker-compose.yml`.

## Services
- **postgres** (`pgvector/pgvector:pg15`): primary DB, volume `postgres_data`, healthcheck `pg_isready`.
- **redis** (`redis:7-alpine`): cache/broker, appendonly enabled, volume `redis_data`.
- **web**: FastAPI app, command `uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001 --reload`; mounts source/config/logs/tests/models/outputs; ports `8001:8001`, `8888:8888`; depends on postgres/redis.
- **worker**: Celery worker for default, source_checks, maintenance, reports, connectivity, collection queues.
- **workflow_worker**: Celery worker for `workflows` queue (agentic workflow tasks); runs LangGraph state machine.
- **scheduler**: Celery beat `celery -A src.worker.celery_app beat --loglevel=debug`; shares code/config volumes.
- **cli** (profile `tools`): runs `python -m src.cli.main` with the same env/volumes for DB parity.

## Key environment
- `POSTGRES_PASSWORD` required; `DATABASE_URL` injected by compose: `postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper`.
- `REDIS_URL=redis://redis:6379/0`.
- AI: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHATGPT_API_KEY`, `LMSTUDIO_API_URL` (default `http://host.docker.internal:1234/v1`), `LMSTUDIO_MODEL` and model-specific overrides, `LANGSMITH_API_KEY` (optional).
- Timezone: `TZ=America/New_York`.

## Volumes & mounts
- Named volumes: `postgres_data`, `redis_data`.
- Bind mounts: `./src`, `./config`, `./logs`, `./tests`, `./outputs`, `./models`, `./scripts`, `./allure-results`, `./test-results`, `./backups` (web only), Docker socket for web/worker.

## Health checks
- postgres: `pg_isready`
- redis: `redis-cli ping`
- web: `curl http://localhost:8001/health`
- worker, workflow_worker: `celery ... inspect ping`
- scheduler: trivial python exit 0

## Networking
- Single bridge network `cti_network`; services address each other by name (`postgres`, `redis`, `web`).
- External access via mapped ports 8001 (API/UI) and 8888 (debug/aux port if needed).

## CLI alignment
`./run_cli.sh` passes args directly to `python -m src.cli.main`, ensuring the containerized CLI uses the same Postgres and Redis as the web app.

_Last verified: Dec 2025_
