# Testing Workflow Guide

## Overview

This guide explains the comprehensive testing workflow for CTI Scraper, including different execution contexts, test categories, and best practices.

## Testing Architecture

### Execution Contexts

| Context | Purpose | Environment | Use Case |
|---------|---------|-------------|----------|
| **Localhost** | Development testing | Virtual environment | Fast iteration, debugging |
| **Docker** | Integration testing | Containerized | Production-like environment |
| **CI/CD** | Automated testing | GitHub Actions | Quality gates, regression testing |

### Test Categories

| Category | Duration | Purpose | Dependencies |
|----------|----------|---------|--------------|
| **Smoke** | ~30s | Quick health check | Minimal |
| **Unit** | ~1m | Component testing | None |
| **API** | ~2m | Endpoint testing | Application running |
| **Integration** | ~3m | System testing | Full Docker stack |
| **UI** | ~5m | Web interface testing | Playwright, browser |
| **All** | ~8m | Complete test suite | Full environment |

## Quick Start

### 1. Install Test Dependencies
```bash
# Install test dependencies
python run_tests.py --install

# Or use the unified script
./run_tests.sh --install
```

### 2. Run Quick Health Check
```bash
# Smoke tests (recommended first step)
python run_tests.py --smoke

# Or use the unified script
./run_tests.sh smoke
```

### 3. Run Full Test Suite
```bash
# Complete test suite with coverage
python run_tests.py --all --coverage

# Or use the unified script
./run_tests.sh all --coverage
```

## Execution Contexts

### Localhost Testing (Default)
**Best for**: Development, debugging, rapid iteration

```bash
# Activate test environment
source venv-test/bin/activate

# Run tests locally
python run_tests.py --smoke
python run_tests.py --unit
python run_tests.py --api
python run_tests.py --integration
python run_tests.py --ui
python run_tests.py --all --coverage

# Using unified script
./run_tests.sh smoke
./run_tests.sh unit
./run_tests.sh api
./run_tests.sh integration
./run_tests.sh ui
./run_tests.sh all --coverage
```

### Docker Testing
**Best for**: Integration testing, production-like environment

```bash
# Ensure Docker containers are running
docker-compose up -d

# Run tests in Docker containers
python run_tests.py --docker --smoke
python run_tests.py --docker --integration
python run_tests.py --docker --all --coverage

# Using unified script
./run_tests.sh smoke --docker
./run_tests.sh integration --docker
./run_tests.sh all --coverage --docker
```

### CI/CD Testing
**Best for**: Automated quality gates, regression testing

```bash
# CI/CD mode (automatically detected in GitHub Actions)
python run_tests.py --ci --all --coverage
```

## Test Categories

### Smoke Tests
**Purpose**: Quick health check, basic functionality
**Duration**: ~30 seconds
**Dependencies**: Minimal

```bash
# Run smoke tests
python run_tests.py --smoke
./run_tests.sh smoke

# Docker mode
python run_tests.py --docker --smoke
./run_tests.sh smoke --docker
```

### Unit Tests
**Purpose**: Test individual components in isolation
**Duration**: ~1 minute
**Dependencies**: None

```bash
# Run unit tests
python run_tests.py --unit
./run_tests.sh unit

# Docker mode
python run_tests.py --docker --unit
./run_tests.sh unit --docker
```

### API Tests
**Purpose**: Test API endpoints and responses
**Duration**: ~2 minutes
**Dependencies**: Application running

```bash
# Run API tests
python run_tests.py --api
./run_tests.sh api

# Docker mode
python run_tests.py --docker --api
./run_tests.sh api --docker
```

### Integration Tests
**Purpose**: Test system integration and workflows
**Duration**: ~3 minutes
**Dependencies**: Full Docker stack

```bash
# Run integration tests
python run_tests.py --integration
./run_tests.sh integration

# Docker mode (recommended)
python run_tests.py --docker --integration
./run_tests.sh integration --docker
```

### UI Tests
**Purpose**: Test web interface and user interactions
**Duration**: ~5 minutes
**Dependencies**: Playwright, browser

```bash
# Run UI tests
python run_tests.py --ui
./run_tests.sh ui

# Docker mode
python run_tests.py --docker --ui
./run_tests.sh ui --docker
```

### Performance Tests
**Purpose**: Test system performance and load
**Duration**: Variable
**Dependencies**: Full environment

```bash
# Run performance tests
python run_tests.py --performance
./run_tests.sh performance

# Docker mode
python run_tests.py --docker --performance
./run_tests.sh performance --docker
```

## Coverage Analysis

### Generate Coverage Report
```bash
# With coverage report
python run_tests.py --coverage
./run_tests.sh all --coverage

# Docker mode
python run_tests.py --docker --coverage
./run_tests.sh all --coverage --docker
```

### Coverage Reports
- **HTML Report**: `htmlcov/index.html`
- **Terminal Report**: Displayed in console
- **XML Report**: `coverage.xml` (for CI/CD)

## Development Workflow

### 1. Development Phase
```bash
# Quick feedback loop
./run_tests.sh smoke

# Component testing
./run_tests.sh unit

# Feature testing
./run_tests.sh api
```

### 2. Integration Phase
```bash
# System integration
./run_tests.sh integration --docker

# UI testing
./run_tests.sh ui --docker
```

### 3. Pre-commit Phase
```bash
# Complete test suite
./run_tests.sh all --coverage

# Docker validation
./run_tests.sh all --coverage --docker
```

### 4. CI/CD Phase
```bash
# Automated testing (GitHub Actions)
python run_tests.py --ci --all --coverage
```

## Best Practices

### 1. Test Execution Order
1. **Smoke tests** - Quick health check
2. **Unit tests** - Component validation
3. **API tests** - Endpoint validation
4. **Integration tests** - System validation
5. **UI tests** - User interface validation
6. **Performance tests** - Load validation

### 2. Environment Management
- Use **localhost** for development speed
- Use **Docker** for integration validation
- Use **CI/CD** for automated quality gates

### 3. Test Data Management
- Use **mocked data** for unit tests
- Use **test databases** for integration tests
- Use **isolated environments** for UI tests

### 4. Error Handling
- **Fail fast** on critical errors
- **Continue testing** on non-critical errors
- **Generate reports** for all test runs

## Troubleshooting

### Common Issues

**Tests fail to start:**
```bash
# Check application status
docker-compose ps

# Check test environment
source venv-test/bin/activate
python --version
pip list
```

**Docker tests fail:**
```bash
# Check Docker containers
docker ps

# Check container logs
docker-compose logs web
docker-compose logs worker
```

**Coverage reports missing:**
```bash
# Check coverage installation
pip install pytest-cov

# Check coverage configuration
cat pytest.ini | grep cov
```

**UI tests fail:**
```bash
# Check Playwright installation
playwright install

# Check browser availability
playwright --version
```

### Environment Issues

**Virtual environment problems:**
```bash
# Recreate test environment
rm -rf venv-test
python3 -m venv venv-test
source venv-test/bin/activate
pip install -r requirements.txt
pip install -r requirements-test.txt
```

**Docker environment problems:**
```bash
# Clean restart
docker-compose down
docker-compose up -d

# Check container health
docker-compose ps
```

## Advanced Usage

### Custom Test Configuration
```bash
# Custom pytest configuration
pytest tests/ -v --tb=short --cov=src --cov-report=html

# Custom test markers
pytest tests/ -m "not slow" -v

# Custom test paths
pytest tests/unit/ tests/api/ -v
```

### Parallel Test Execution
```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel
pytest tests/ -n 4 -v
```

### Test Debugging
```bash
# Verbose output
pytest tests/ -v -s

# Debug specific test
pytest tests/test_specific.py::test_function -v -s

# Break on failure
pytest tests/ --pdb
```

## Integration with CI/CD

### GitHub Actions
```yaml
# .github/workflows/test.yml
- name: Run tests
  run: |
    python run_tests.py --ci --all --coverage
```

### Local CI Simulation
```bash
# Simulate CI environment
export CI=true
python run_tests.py --ci --all --coverage
```

## Performance Optimization

### Test Speed
- Use **smoke tests** for quick feedback
- Use **parallel execution** for large test suites
- Use **mocked dependencies** where possible

### Resource Usage
- Use **Docker** for resource isolation
- Use **test databases** for data isolation
- Use **cleanup procedures** for resource management

## Monitoring and Reporting

### Test Results
- **HTML Reports**: `test-results/report.html`
- **Coverage Reports**: `htmlcov/index.html`
- **CI/CD Reports**: GitHub Actions artifacts

### Metrics
- **Test Duration**: Track execution time
- **Coverage Percentage**: Monitor code coverage
- **Failure Rate**: Track test reliability

## Conclusion

This testing workflow provides comprehensive coverage for CTI Scraper across different execution contexts and test categories. Use the appropriate context and category for your specific needs, and follow the best practices for optimal results.
