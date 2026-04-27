# Run Locally (Docker)

Use Docker Compose as the supported way to run Huntable CTI Studio. These steps mirror `../deployment/GETTING_STARTED.md` and the `./start.sh` wrapper.

## Prerequisites
- Docker Desktop with Compose plugin
- `python3` available if you plan to run tests
- Run `./setup.sh` first to provision `.env` and secure local credentials
- If editing `.env` manually after setup, set:
  - `POSTGRES_PASSWORD=<strong password>`
  - Optional LLM keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHATGPT_API_KEY`
  - LM Studio defaults: `LMSTUDIO_API_URL=http://host.docker.internal:1234/v1` plus model names already set in compose

## Start the stack
```bash
./setup.sh --no-backups
./start.sh
```
What happens:
- Reuses the existing `.env` from setup (fails fast if missing or templated)
- Creates runtime directories (`logs/`, `backups/`, `models/`, `outputs/`, `data/`)
- Runs `docker-compose up --build -d`
- Health-checks Postgres, Redis, and the web app
- Automatically builds docs and starts the MkDocs server in the background when `mkdocs.yml` is present (logs: `logs/mkdocs.log`)

## Service endpoints
- Web UI + API: http://localhost:8001
- OpenAPI docs: http://localhost:8001/docs
- Ports exposed by default: `8001`, `8888`, `5432` (Postgres), `6379` (Redis)

## Verify health
```bash
docker-compose ps
curl http://localhost:8001/health
```

## Common commands
```bash
# run CLI commands in the tools container
./run_cli.sh --help
./run_cli.sh init --config config/sources.yaml
./run_cli.sh collect --dry-run

# view logs
docker-compose logs -f web

# restart or stop
docker-compose restart web
docker-compose down
```

If you change host ports, edit the `web` service mappings in `docker-compose.yml` and update any scripts or environment variables that reference `localhost:8001`.
