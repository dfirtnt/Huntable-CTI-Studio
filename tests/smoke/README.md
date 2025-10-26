# CTI Scraper Smoke Test Documentation

## Quick Start

**Run smoke tests:**
```bash
python3 run_tests.py smoke
```

**Duration:** ~15 seconds | **Tests:** 26 passed ✅

## Overview

Smoke tests provide rapid health checks of critical system functionality, completing in ~15 seconds for quick verification.

## Current Coverage

### ✅ Smoke Tests (26 tests)
- **System Health** (3): Health endpoints, core endpoints, database connectivity
- **Service Health** (3): External services, ingestion pipeline, deduplication
- **Data Pipeline** (2): Article processing, source management
- **ML Services** (2): RAG, embeddings
- **Security** (2): Security headers, API error handling
- **Backup System** (1): Backup endpoints
- **Performance** (2): Response times, concurrency
- **Background Jobs** (3): Celery workers, job queues, task status
- **Search** (2): Search functionality, help
- **Analytics** (3): Dashboard, scraper overview, hunt metrics
- **Article Operations** (2): Next unclassified, annotations stats
- **Export** (1): CSV export

### 🚧 Coverage Gaps Identified

| Category | Missing Tests | Priority |
|----------|---------------|----------|
| **Health Endpoints** | `/health`, `/api/health/*` | High |
| **Service Health** | Database, Redis, Celery workers | High |
| **Data Pipeline** | Article processing, ingestion | High |
| **ML Services** | RAG, embeddings, model health | Medium |
| **Security** | Headers, error handling | Medium |
| **Backup System** | Backup/restore functionality | Medium |
| **Performance** | Response times, concurrency | Low |

## New Smoke Test Suite

### Critical Smoke Tests (`tests/smoke/test_critical_smoke_tests.py`)

**System Health (3 tests)**
- Health endpoints verification
- Core endpoints availability  
- Database connectivity

**Service Health (3 tests)**
- External services health
- Ingestion pipeline health
- Deduplication service health

**Data Pipeline (2 tests)**
- Article processing pipeline
- Source management functionality

**ML Services (2 tests)**
- RAG service availability
- Embedding service health

**Security (2 tests)**
- Security headers verification
- API error handling

**Backup System (1 test)**
- Backup endpoints availability

**Performance (2 tests)**
- Response time verification
- Concurrent request handling

**Total: 15 new critical smoke tests**

## Running Smoke Tests

### Quick Health Check

**Simplest command:**
```bash
python3 run_tests.py smoke
```

**Alternative methods:**
```bash
# Using venv python directly
.venv/bin/python -m pytest tests/smoke/test_critical_smoke_tests.py -m smoke -v

# Activate venv first
source .venv/bin/activate
python -m pytest tests/smoke/test_critical_smoke_tests.py -m smoke -v
deactivate

# Run in Docker
docker exec cti_web pytest tests/smoke/test_critical_smoke_tests.py -m smoke -v
```

### Test Configuration
- **Timeout**: 30 seconds per test
- **Max Failures**: 5 (fail fast)
- **Environment**: Localhost or Docker
- **Dependencies**: httpx, pytest-asyncio

## Test Categories

| Category | Tests | Duration | Purpose |
|----------|-------|----------|---------|
| **System Health** | 3 | ~5s | Core system verification |
| **Service Health** | 3 | ~5s | Infrastructure health |
| **Data Pipeline** | 2 | ~5s | Data processing verification |
| **ML Services** | 2 | ~5s | AI service availability |
| **Security** | 2 | ~3s | Basic security checks |
| **Backup** | 1 | ~2s | Backup system health |
| **Performance** | 2 | ~5s | Response time verification |

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
pytest tests/smoke/ --timeout=60
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

# Run specific test category
pytest tests/smoke/test_critical_smoke_tests.py::TestSystemHealthSmoke -v
```

## Future Enhancements

### Planned Additions
- **Load Testing**: Concurrent user simulation
- **End-to-End**: Complete workflow verification
- **Security Scanning**: Vulnerability detection
- **Performance Benchmarking**: Response time tracking

### Integration Points
- **Monitoring**: Prometheus metrics integration
- **Alerting**: Slack/email notifications
- **Dashboard**: Real-time health visualization
- **Logging**: Centralized test result logging
