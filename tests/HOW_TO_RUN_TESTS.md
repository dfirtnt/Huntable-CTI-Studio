# How to Run Tests - Quick Reference

## Quick Start

### Always Use Virtual Environment

**CRITICAL:** Always use `.venv` for running tests. The test runner automatically manages this:

```bash
python3 run_tests.py all
```

The runner will:
- Create `.venv` if it doesn't exist
- Install dependencies if missing
- Run tests using the correct Python environment from `.venv/bin/python`

**Manual venv usage:**
```bash
.venv/bin/pytest tests/smoke/ -m smoke -v
```

**NEVER use system python directly:**
```bash
# WRONG - Don't do this
python3 -m pytest tests/

# CORRECT - Use venv python
.venv/bin/python -m pytest tests/
```

### Run Specific Test Types
```bash
python3 run_tests.py smoke          # Quick health check (~15s)
python3 run_tests.py unit           # Unit tests only (~1m)
python3 run_tests.py api            # API endpoint tests (~2m)
python3 run_tests.py integration    # Integration tests (~3m)
python3 run_tests.py ui             # Web interface tests (~5m)
python3 run_tests.py e2e            # End-to-end tests (~3m)
```

### Manual Venv (Alternative)

If you prefer manual control:

```bash
# Activate existing venv
source .venv/bin/activate

# Run tests
python -m pytest tests/

# Or use the test runner
python run_tests.py all

# Deactivate when done
deactivate
```

## Command Options

### Verbose Output
```bash
python3 run_tests.py all -v
```

### Debug Mode
```bash
python3 run_tests.py all --debug
```

### Coverage Report
```bash
python3 run_tests.py all --coverage
```

### Specific Test Path
```bash
python3 run_tests.py all --paths tests/unit/
```

### Fail Fast (Stop on First Failure)
```bash
python3 run_tests.py all --fail-fast
```

## Test Types Explained

| Type | Duration | What It Tests |
|------|----------|---------------|
| **smoke** | ~15s | Critical system health (26 tests) |
| **unit** | ~1m | Individual component functionality |
| **api** | ~2m | HTTP endpoints and responses |
| **integration** | ~3m | Full system integration |
| **ui** | ~5m | Web interface with Playwright |
| **e2e** | ~3m | End-to-end user workflows |

## Examples

### Quick Health Check
```bash
python3 run_tests.py smoke
```

### Full Test Suite with Coverage
```bash
python3 run_tests.py all --coverage
```

### Debug Failing Integration Tests
```bash
python3 run_tests.py integration --debug -v
```

### Run Specific Test File
```bash
python3 -m pytest tests/api/test_endpoints.py -v
```

## Docker Environment

### Run Tests Inside Docker
```bash
docker exec cti_web pytest tests/smoke/ -m smoke -v
```

### Run with Docker Compose
```bash
docker-compose -f docker-compose.test.yml up --abort-on-container-exit
```

## Common Issues

### Missing Dependencies

The test runner will automatically install them, but if you need to manually:

```bash
# Using the runner
python3 run_tests.py all --install

# Manual install
pip install -r requirements-test.txt
pip install -r requirements.txt
python -m playwright install chromium
```

### Database Connection Issues
```bash
# Ensure services are running
docker-compose ps

# Check database is accessible
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "SELECT 1"
```

### Playwright Browser Issues
```bash
# Install Playwright browsers
python -m playwright install chromium
```

## Output Locations

- **Test Results**: `allure-results/`
- **Coverage Reports**: `htmlcov/`
- **Test Logs**: `test-results/`
- **Videos**: `test-results/videos/` (on failure)

## View Reports

### Allure Report
```bash
allure serve allure-results
```

### Coverage Report
```bash
open htmlcov/index.html
```

## Summary

**Simplest command for all tests:**
```bash
python3 run_tests.py all
```

**For quick health check:**
```bash
python3 run_tests.py smoke
```
