# Configuration Reference

Configuration is driven by `.env`, `docker-compose.yml`, and YAML files under `config/`.

## Environment variables (.env)
- `POSTGRES_PASSWORD` (required): used by Postgres and `DATABASE_URL` in compose
- `DATABASE_URL`: set in compose to `postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper`
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHATGPT_API_KEY`: optional LLM providers
- `LMSTUDIO_API_URL` (default `http://host.docker.internal:1234/v1`), `LMSTUDIO_MODEL`, `LMSTUDIO_MODEL_RANK`, `LMSTUDIO_MODEL_EXTRACT`, `LMSTUDIO_MODEL_SIGMA`
- `LMSTUDIO_EMBEDDING_URL`, `LMSTUDIO_EMBEDDING_MODEL`: required for Sigma similarity search
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `LANGFUSE_PROJECT_ID`: optional tracing (see Settings UI)
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
