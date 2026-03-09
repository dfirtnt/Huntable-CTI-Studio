# Getting Started with Huntable CTI Studio Deployment

Concise setup that matches the current Docker and CLI.

## Prerequisites
- Docker + Docker Compose plugin
- 8GB RAM recommended
- Python 3.11 only if you plan to run tooling locally (otherwise Docker only)

## Quick Start
```bash
git clone https://github.com/dfirtnt/Huntable-CTI-Studio.git
cd Huntable-CTI-Studio
./setup.sh --no-backups           # provisions .env and secure defaults
./start.sh                        # daily startup (builds + starts compose stack)
```
`start.sh` now requires an existing `.env` from setup and fails fast if `.env` is missing or still uses template placeholders.

Access:
- Web UI/API: http://localhost:8001
- API docs: http://localhost:8001/docs

## Services (from `docker-compose.yml`)
- postgres: `pgvector/pgvector:pg15`, persistent volume `postgres_data`, port 5432
- redis: `redis:7-alpine`, volume `redis_data`, port 6379
- web: FastAPI app (`uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001 --reload`), ports 8001/8888
- worker: Celery worker (queues: default, source_checks, maintenance, reports, connectivity, collection)
- workflow_worker: Celery worker (queue: workflows)
- scheduler: Celery beat
- cli (profile `tools`): `python -m src.cli.main`

## Required environment
Run `./setup.sh` before `./start.sh` so `.env` is created and initialized. If you edit `.env` manually after setup, keep these values valid:
- `POSTGRES_PASSWORD=<strong password>`
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `CHATGPT_API_KEY` (optional AI features)
- `LMSTUDIO_API_URL` (default: `http://host.docker.internal:1234/v1`)
- `LMSTUDIO_MODEL`, `LMSTUDIO_MODEL_RANK`, `LMSTUDIO_MODEL_EXTRACT`, `LMSTUDIO_MODEL_SIGMA` (defaults set in compose)
- Langfuse tracing: configure via Settings UI or env vars. This project supports Langfuse Cloud only, and tracing can export sensitive prompts, outputs, and workflow metadata off-box. See [Langfuse Setup](../guides/langfuse-setup.md).

Notes:
- `.env.example` template includes required PostgreSQL configuration; Docker uses PostgreSQL via `DATABASE_URL=postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@postgres:5432/cti_scraper` defined in compose.
- Test template: `env.test.template` for pytest/Playwright values.

## CLI usage
Run inside Docker:
```bash
./run_cli.sh --help
./run_cli.sh init --config config/sources.yaml
./run_cli.sh collect --dry-run
./run_cli.sh search --query ransomware --limit 25 --format json
./run_cli.sh sync-sources --config config/sources.yaml --no-remove
./run_cli.sh rescore --article-id 123 --dry-run
```

## Verification
```bash
docker-compose ps
curl http://localhost:8001/health
docker-compose logs -f web
```

## Troubleshooting
- Port conflicts: adjust host ports in `docker-compose.yml` (`8001`, `8888`)
- Database auth errors: ensure `POSTGRES_PASSWORD` is set and matches `.env` and compose
- AI errors: confirm API keys or LM Studio endpoint reachable
- CLI errors: use `./run_cli.sh --help` to see current commands; arguments are passed directly to `python -m src.cli.main`

_Last verified: Feb 2025_
<!--stackedit_data:
eyJoaXN0b3J5IjpbLTk0NTYwODIyNywxMDMzODc4Mjg0XX0=
-->
