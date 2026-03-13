# Development Setup

This project is Docker-first. The application stack runs in containers; local Python is mainly for tests, docs tooling, and targeted scripts.

## Prerequisites

- Docker
- Docker Compose plugin
- `python3` for local tooling
- Git

## Standard Local Workflow

### 1. Provision local secrets and config

```bash
./setup.sh --no-backups
```

### 2. Start the stack

```bash
./start.sh
```

### 3. Verify the app is healthy

```bash
curl http://localhost:8001/health
```

Primary access points:

- Web UI: `http://localhost:8001`
- OpenAPI docs: `http://localhost:8001/docs`
- MkDocs site: `http://localhost:8000`

## Important Runtime Files

Open these files first when debugging setup or boot behavior:

- `src/web/modern_main.py`
- `src/worker/celery_app.py`
- `docker-compose.yml`
- `docker-compose.test.yml`
- `run_tests.py`

## Environment Model

### Application runtime

- The main app runs in Docker.
- Database and Redis are provided by Docker Compose.
- Settings may come from `.env`, the database, or both depending on subsystem.

### Local Python tooling

- `run_tests.py` is the canonical test entrypoint.
- `run_tests.py` ensures a local `.venv` exists before running tests.
- Stateful suites use isolated test containers rather than the primary dev stack.

You do not need to maintain separate named virtual environments for normal repo work.

## Canonical Commands

```bash
./setup.sh --no-backups
./start.sh
curl http://localhost:8001/health
python3 run_tests.py smoke
python3 run_tests.py unit
python3 run_tests.py api
python3 run_tests.py integration
python3 run_tests.py ui
python3 run_tests.py e2e
python3 run_tests.py all
```

## Test Infrastructure

### Stateless suites

These typically run locally without containers:

- `python3 run_tests.py smoke`
- `python3 run_tests.py unit`

### Stateful suites

These use the isolated test stack:

- `python3 run_tests.py api`
- `python3 run_tests.py integration`
- `python3 run_tests.py ui`
- `python3 run_tests.py e2e`
- `python3 run_tests.py all`

The test runner auto-manages the isolated test environment when needed. See [Testing](testing.md) for details.

## Common Setup Traps

- The application expects `.env` to exist; use `./setup.sh` to create it.
- Source configuration is seeded from YAML only on near-empty installs; after that the database is authoritative unless synced manually.
- Startup performs side effects such as table verification and eval-article seeding.
- Browser-visible changes still require UI or E2E verification even if API tests pass.

## Where To Go Next

- [Agent Orientation](agent-orientation.md)
- [Testing](testing.md)
- [Workflow Queue](workflow-queue.md)
- [Architecture Overview](../architecture/overview.md)
