# CTI Scraper Smoke Test Documentation

## Overview

Smoke tests provide rapid health checks of critical system functionality, completing in ~30 seconds for quick verification.

## Current Coverage

### ✅ Existing Smoke Tests (16 tests)
- **API Tests**: Dashboard, articles, sources, RAG chat endpoints
- **Integration Tests**: System startup verification
- **UI Tests**: Basic navigation and functionality (requires Playwright setup)

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
```bash
# Run all smoke tests
python run_tests.py --smoke

# Run new critical smoke tests only
python tests/smoke/run_smoke_tests.py

# Run in Docker
python tests/smoke/run_smoke_tests.py --docker
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
