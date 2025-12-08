# Testing Quick Start

Get up and running with CTIScraper testing in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ (for local testing)
- `.env` file configured

## 1. Start the Application

```bash
# Start Docker containers
./start.sh

# Verify containers are running
docker-compose ps
```

## 2. Install Test Dependencies

```bash
# Install test dependencies
python run_tests.py --install
```

## 3. Run Your First Test

```bash
# Quick health check (recommended first step)
python run_tests.py --smoke
```

Expected output:
```
✅ Smoke tests passed
✅ Application is healthy
```

## 4. Run Different Test Types

### Unit Tests (Fastest)
```bash
python run_tests.py --unit
```

### API Tests
```bash
python run_tests.py --api
```

### Integration Tests (Requires Docker)
```bash
python run_tests.py --docker --integration
```

### Full Test Suite
```bash
python run_tests.py --all --coverage
```

## 5. Quick Commands

### Essential Commands
```bash
# Health check
python run_tests.py --smoke

# Full suite with coverage
python run_tests.py --all --coverage

# Docker integration tests
python run_tests.py --docker --integration

# ML feedback tests (critical)
./scripts/run_ml_feedback_tests.sh

# Debug mode
python run_tests.py --debug --verbose
```

## 6. ML Feedback Tests (Critical)

Run these essential regression prevention tests:

```bash
# Run all 3 critical ML feedback tests
./scripts/run_ml_feedback_tests.sh
```

## 7. View Test Results

### Coverage Report
```bash
# Generate HTML coverage report
python run_tests.py --all --coverage
open htmlcov/index.html
```

### Allure Reports (Advanced)
```bash
# Generate visual test reports
python run_tests.py --all
./manage_allure.sh start
# Access at: http://localhost:8080
```

## 8. Common Patterns

### Development Workflow
```bash
# Quick feedback loop
python run_tests.py --smoke

# Component testing
python run_tests.py --unit

# Feature testing
python run_tests.py --api
```

### Pre-commit Testing
```bash
# Complete test suite
python run_tests.py --all --coverage

# Docker validation
python run_tests.py --all --coverage --docker
```

## 9. Troubleshooting

### Tests Won't Start
```bash
# Check application status
docker-compose ps

# Check test environment
source venv-test/bin/activate
python --version
```

### Docker Tests Fail
```bash
# Check Docker containers
docker ps

# Check container logs
docker-compose logs web
```

### Port Conflicts
Check for conflicts on ports 8001, 5432, 6379

## 10. Next Steps

- **Learn more**: See [Testing Guide](TESTING.md) for comprehensive documentation
- **ML Testing**: See [ML Feedback Tests](ML_FEEDBACK_TESTING.md) for regression prevention
- **Advanced**: See [Advanced Testing](docs/development/ADVANCED_TESTING.md) for API, E2E, and performance testing

## Quick Reference

### Test Categories
- **Smoke**: Basic health checks
- **Unit**: Individual components
- **API**: REST endpoints
- **Integration**: System workflows
- **UI**: Web interface
- **E2E**: End-to-end workflows
- **ML Feedback**: Regression prevention

### Execution Contexts
- **Localhost**: Fast development testing
- **Docker**: Production-like environment
- **CI/CD**: Automated quality gates

### Essential Files
- `run_tests.py` - Main test runner
- `pytest.ini` - Configuration
- `tests/` - Test directory

---

**Need help?** Check the [Testing Guide](TESTING.md) or open a GitHub issue.

# Running Tests Guide

## Quick Reference Commands

### Health check
```bash
python3 run_tests.py --smoke          # Quick health check
```

### Full suite
```bash
python3 run_tests.py --all --coverage  # Complete test suite with coverage
```

### Docker integration tests
```bash
python3 run_tests.py --docker --integration
```

### ML feedback tests (critical)
```bash
./scripts/run_ml_feedback_tests.sh
```

### Debug mode
```bash
python3 run_tests.py --debug --verbose
```

## Verbose Output
```bash
python3 run_tests.py all -v
```

## Debug Mode
```bash
python3 run_tests.py all --debug
```

## Coverage Report
```bash
python3 run_tests.py all --coverage
```

## Specific Test Path
```bash
python3 run_tests.py all --paths tests/unit/
```

## Fail Fast (Stop on First Failure)
```bash
python3 run_tests.py all --fail-fast
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

---
