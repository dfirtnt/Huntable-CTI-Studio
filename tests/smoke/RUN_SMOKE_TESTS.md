# Running Smoke Tests

## Quick Start

Run smoke tests with one command:

```bash
python3 run_tests.py smoke
```

This automatically:
- Uses the correct virtual environment
- Runs all 15 smoke tests
- Completes in ~15 seconds

## What Gets Tested

Smoke tests verify critical system functionality:
- ✓ API endpoints (dashboard, articles, sources, quick actions)
- ✓ System startup and health
- ✓ UI navigation flows
- ✓ Article classification operations
- ✓ RAG chat interface

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
# Run all smoke tests
.venv/bin/python -m pytest tests/ -m smoke -v

# Run specific test file
.venv/bin/python -m pytest tests/api/test_endpoints.py -m smoke -v
.venv/bin/python -m pytest tests/ui/test_ui_flows.py -m smoke -v
```

## Expected Results

- **Duration:** ~15-20 seconds
- **Tests:** 15 passed
- **Coverage:** API endpoints, system health, UI flows, article operations, ML services
