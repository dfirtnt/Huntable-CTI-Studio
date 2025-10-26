# Running Smoke Tests

## Quick Start

Run smoke tests with one command:

```bash
python3 run_tests.py smoke
```

This automatically:
- Uses the correct virtual environment
- Runs all 26 smoke tests
- Completes in ~15 seconds

## What Gets Tested

Smoke tests verify critical system functionality:
- ✓ Health endpoints and database connectivity
- ✓ Core services (Redis, Celery, Ollama)
- ✓ Data pipeline and source management
- ✓ ML services (RAG, embeddings)
- ✓ Search, analytics, and export features
- ✓ Background jobs and task queues
- ✓ Performance and concurrency

## Detailed Output

For verbose output:

```bash
python3 run_tests.py smoke -v
```

For debug mode:

```bash
python3 run_tests.py smoke --debug
```

## Manual Run (Advanced)

If you prefer to use pytest directly:

```bash
.venv/bin/python -m pytest tests/smoke/test_critical_smoke_tests.py -m smoke -v
```

## Expected Results

- **Duration:** ~15-20 seconds
- **Tests:** 26 passed
- **Coverage:** System health, services, data pipeline, ML, security, jobs, search, analytics
