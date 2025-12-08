# CTI Scraper Smoke Test Documentation

## Quick Start

**Run smoke tests:**
```bash
python3 run_tests.py smoke
```

**Duration:** ~15 seconds | **Tests:** 15 passed ✅

## Overview

Smoke tests provide rapid health checks of critical system functionality, completing in ~15 seconds for quick verification.

## Current Coverage

### ✅ Smoke Tests (15 tests)

Smoke tests are distributed across multiple test files using the `@pytest.mark.smoke` marker:

**API Endpoints (5 tests)** - `tests/api/test_endpoints.py`
- Dashboard home page
- Articles listing
- Article detail view
- Sources listing
- Rescore all articles action

**System Integration (1 test)** - `tests/integration/test_system_integration.py`
- System startup health check

**UI Flows (4 tests)** - `tests/ui/test_ui_flows.py`
- Dashboard navigation
- Articles listing
- Sources management
- Rescore all articles button

**Article Classification (4 tests)** - `tests/ui/test_article_classification.py`
- Classification buttons visibility
- Classify as chosen
- Classify as rejected
- Classify as unclassified

**RAG Chat (1 test)** - `tests/ui/test_rag_chat_ui.py`
- Chat page loads

### Test File Locations

| File | Tests | Category |
|------|-------|----------|
| `tests/api/test_endpoints.py` | 5 | API endpoints |
| `tests/integration/test_system_integration.py` | 1 | System health |
| `tests/ui/test_ui_flows.py` | 4 | UI navigation |
| `tests/ui/test_article_classification.py` | 4 | Article operations |
| `tests/ui/test_rag_chat_ui.py` | 1 | ML services |

## Running Smoke Tests

### Quick Health Check

**Simplest command:**
```bash
python3 run_tests.py smoke
```

**Alternative methods:**
```bash
# Using venv python directly
.venv/bin/python -m pytest tests/ -m smoke -v

# Activate venv first
source .venv/bin/activate
python -m pytest tests/ -m smoke -v
deactivate

# Run in Docker
docker exec cti_web pytest tests/ -m smoke -v

# Run specific test file
.venv/bin/python -m pytest tests/api/test_endpoints.py -m smoke -v
.venv/bin/python -m pytest tests/ui/test_ui_flows.py -m smoke -v
```

### Test Configuration
- **Timeout**: 30 seconds per test
- **Max Failures**: 5 (fail fast)
- **Environment**: Localhost or Docker
- **Dependencies**: httpx, pytest-asyncio

## Test Categories

| Category | Tests | Duration | Purpose |
|----------|-------|----------|---------|
| **API Endpoints** | 5 | ~5s | Core API functionality |
| **System Health** | 1 | ~2s | System startup verification |
| **UI Navigation** | 4 | ~5s | User interface flows |
| **Article Operations** | 4 | ~3s | Classification functionality |
| **ML Services** | 1 | ~2s | RAG chat availability |

## Integration with CI/CD

### GitHub Actions
```yaml
- name: Run Smoke Tests
  run: python tests/smoke/run_smoke_tests.py --docker
```

### Pre-deployment
```bash
# Quick health check before deployment
python tests/smoke/run_smoke_tests.py --verbose
```

## Monitoring Integration

### Health Check Endpoints
- `/health` - Basic system health
- `/api/health` - API health status
- `/api/health/database` - Database connectivity
- `/api/health/services` - External services status
- `/api/health/celery` - Worker health
- `/api/health/ingestion` - Pipeline health
- `/api/health/deduplication` - Deduplication service

### Alerting Thresholds
- **Response Time**: < 5 seconds per endpoint
- **Success Rate**: > 95% for smoke tests
- **Availability**: 99.9% uptime target

## Troubleshooting

### Common Issues

**Playwright Browser Errors**
```bash
# Install Playwright browsers in Docker
docker exec cti_web playwright install
```

**Test Timeouts**
```bash
# Increase timeout for slow systems
pytest tests/ -m smoke --timeout=60
```

**Missing Dependencies**
```bash
# Install test dependencies
pip install -r requirements-test.txt
```

### Debug Mode
```bash
# Run with verbose output
python tests/smoke/run_smoke_tests.py --verbose

# Run specific test file
pytest tests/api/test_endpoints.py -m smoke -v
pytest tests/ui/test_ui_flows.py -m smoke -v

# Run specific test class
pytest tests/api/test_endpoints.py::TestDashboardEndpoints -m smoke -v
```
