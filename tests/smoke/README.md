# Huntable CTI Studio Smoke Test Documentation

## Quick Start

**Run smoke tests:**
```bash
python3 run_tests.py smoke
```

**Duration:** ~35 seconds | **Tests:** 31 passed ✅

## Overview

Smoke tests provide rapid health checks of critical system functionality, completing in ~30 seconds for quick verification.

## Current Coverage

### ✅ Smoke Tests (31 tests)

Smoke tests are distributed across multiple test files using the `@pytest.mark.smoke` and `@pytest.mark.ui_smoke` markers. **Run only via `run_tests.py smoke`** so `APP_ENV=test` and `TEST_DATABASE_URL` are set; three smoke tests (rescore-all, annotation creation, workflow trigger with real article) mutate DB/queue and are safe only in test env.

**API Endpoints (24 tests)** - `tests/api/test_endpoints.py`
- Dashboard home page
- Articles listing
- Article detail view
- Sources listing
- Provider model catalog
- Workflow config defaults
- Rescore all articles action (mutates: rescores articles)
- Health endpoints (/health, /api/health, /api/health/database, /api/health/deduplication, /api/health/services, /api/health/celery, /api/health/ingestion)
- Annotations export CSV (/api/export/annotations)
- Database connectivity detailed check
- Workflow trigger endpoint accessibility (read-only: uses non-existent ID)
- Annotation endpoint accessibility (read-only: invalid payload)
- Redis connectivity check
- Celery worker health check
- Annotation creation smoke (mutates: creates then deletes annotation when articles exist)
- Workflow trigger smoke (mutates: enqueues workflow when articles exist)
- SIGMA generation endpoint accessibility (read-only: empty payload)
- **Backup** status and list (read-only)
- **Search** module (/api/search/help)
- **Workflow executions** list
- **Evaluations** config-versions-models
- **Dashboard data** API
- **Metrics** health and **metrics volume** (read-only)
- **Annotations** stats and types (read-only)
- **Jobs** status (read-only)
- **Workflow config** versions (read-only)

**System Integration (1 test)** - `tests/integration/test_system_integration.py`
- System startup health check

**UI Flows (4 tests)** - `tests/ui/test_ui_flows.py` (using `@pytest.mark.ui_smoke`)
- Dashboard navigation
- Articles listing
- Sources management
- Rescore all articles button

**RAG Chat (2 tests)** - `tests/ui/test_rag_chat_ui.py` (using `@pytest.mark.ui_smoke`)
- Chat page loads
- Chat send path renders without errors

### Test File Locations

| File | Tests | Category |
|------|-------|----------|
| `tests/api/test_endpoints.py` | 24 | API endpoints |
| `tests/integration/test_system_integration.py` | 1 | System health |
| `tests/ui/test_ui_flows.py` | 4 | UI navigation |
| `tests/ui/test_rag_chat_ui.py` | 2 | ML services |

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
| **API Endpoints** | 24 | ~20s | Core API/export/health/backup/search/workflow/evaluations/metrics/annotations/jobs |
| **System Health** | 1 | ~2s | System startup verification |
| **UI Navigation** | 4 | ~5s | User interface flows |
| **ML Services** | 2 | ~3s | RAG chat availability and send path |
| **Database & Services** | 3 | ~5s | Database connectivity, Redis, Celery health |
| **Workflow & Annotations** | 2 | ~5s | Workflow trigger and annotation endpoints |

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
