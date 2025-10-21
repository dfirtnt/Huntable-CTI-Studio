# Test Environment Setup Guide

This guide provides comprehensive instructions for setting up and managing the CTI Scraper test environment across different execution contexts (localhost, Docker, and CI/CD).

## Table of Contents

1. [Overview](#overview)
2. [Environment Contexts](#environment-contexts)
3. [Quick Start](#quick-start)
4. [Detailed Setup](#detailed-setup)
5. [Environment Configuration](#environment-configuration)
6. [Testing Procedures](#testing-procedures)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

## Overview

The CTI Scraper test environment is designed to provide consistent testing across multiple execution contexts:

- **Localhost**: Development and local testing
- **Docker**: Containerized testing with isolated services
- **CI/CD**: Automated testing in GitHub Actions

### Key Features

- **Context-aware configuration**: Automatically detects and configures for the current environment
- **Test isolation**: Separate databases and Redis instances for each test run
- **Standardized fixtures**: Consistent test fixtures across all environments
- **Environment validation**: Automatic validation of required services
- **Mock services**: Configurable mocking of external services

## Environment Contexts

### Localhost Context

**Use case**: Local development and testing
**Services**: Local PostgreSQL, Redis, and application
**Configuration**: `env.test.template` with localhost settings

```bash
# Default localhost configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=test_user
POSTGRES_PASSWORD=test_password
REDIS_HOST=localhost
REDIS_PORT=6379
TEST_PORT=8002
```

### Docker Context

**Use case**: Containerized testing with isolated services
**Services**: Docker containers for PostgreSQL, Redis, and application
**Configuration**: `docker-compose.test.yml` with container settings

```bash
# Docker configuration
POSTGRES_HOST=test_postgres
POSTGRES_PORT=5432
POSTGRES_USER=test_user
POSTGRES_PASSWORD=test_password
REDIS_HOST=test_redis
REDIS_PORT=6379
TEST_PORT=8002
```

### CI Context

**Use case**: Automated testing in GitHub Actions
**Services**: GitHub Actions services (PostgreSQL, Redis)
**Configuration**: CI-specific environment variables

```bash
# CI configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
REDIS_HOST=localhost
REDIS_PORT=6379
TEST_PORT=8002
```

## Quick Start

### 1. Localhost Testing

```bash
# Clone and setup
git clone <repository>
cd CTIScraper

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Setup test environment
cp env.test.template .env.test

# Start local services (PostgreSQL and Redis)
# Ensure PostgreSQL is running on localhost:5432
# Ensure Redis is running on localhost:6379

# Validate environment
python tests/utils/test_environment.py --config .env.test --verbose

# Run tests
pytest tests/ -v
```

### 2. Docker Testing

```bash
# Start test services
docker-compose -f docker-compose.test.yml up -d test_postgres test_redis

# Wait for services to be ready
docker-compose -f docker-compose.test.yml logs -f test_postgres test_redis

# Run tests in Docker
docker-compose -f docker-compose.test.yml run --rm test_web pytest tests/ -v

# Cleanup
docker-compose -f docker-compose.test.yml down
```

### 3. CI/CD Testing

The CI/CD pipeline automatically:
- Sets up PostgreSQL and Redis services
- Configures environment variables
- Validates the test environment
- Runs tests with appropriate markers

## Detailed Setup

### Prerequisites

#### System Requirements

- **Python 3.11+**
- **PostgreSQL 15+** (with pgvector extension)
- **Redis 7+**
- **Docker** (for Docker testing)
- **Git**

#### Python Dependencies

```bash
# Core dependencies
pip install -r requirements.txt

# Test dependencies
pip install -r requirements-test.txt

# Additional test utilities
pip install pytest-asyncio pytest-cov pytest-xdist
pip install playwright
playwright install chromium
```

### Localhost Setup

#### 1. Database Setup

```bash
# Install PostgreSQL with pgvector
# Ubuntu/Debian:
sudo apt-get install postgresql-15 postgresql-15-pgvector

# macOS:
brew install postgresql@15
brew install pgvector

# Create test database
sudo -u postgres psql
CREATE DATABASE test_cti_scraper;
CREATE USER test_user WITH PASSWORD 'test_password';
GRANT ALL PRIVILEGES ON DATABASE test_cti_scraper TO test_user;
\q
```

#### 2. Redis Setup

```bash
# Install Redis
# Ubuntu/Debian:
sudo apt-get install redis-server

# macOS:
brew install redis

# Start Redis
redis-server

# Test connection
redis-cli ping
```

#### 3. Environment Configuration

```bash
# Copy test environment template
cp env.test.template .env.test

# Edit configuration if needed
nano .env.test

# Validate configuration
python tests/utils/test_environment.py --config .env.test --verbose
```

### Docker Setup

#### 1. Docker Compose Configuration

```bash
# Use test-specific compose file
docker-compose -f docker-compose.test.yml up -d

# Check service status
docker-compose -f docker-compose.test.yml ps

# View logs
docker-compose -f docker-compose.test.yml logs -f
```

#### 2. Test Database Setup

```bash
# Run database migrations
docker-compose -f docker-compose.test.yml exec test_web python -m alembic upgrade head

# Verify database connection
docker-compose -f docker-compose.test.yml exec test_web python tests/utils/database_connections.py --validate
```

### CI/CD Setup

#### 1. GitHub Actions Configuration

The CI/CD pipeline uses the `.github/workflows/standardized-tests.yml` workflow:

```yaml
# Key features:
- Automatic environment detection
- Service health checks
- Environment validation
- Test isolation
- Artifact collection
```

#### 2. Environment Variables

Set the following secrets in GitHub repository settings:

```bash
# Optional API keys for integration tests
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
CHATGPT_API_KEY=your_chatgpt_key
```

## Environment Configuration

### Configuration Files

#### `env.test.template`

Base template for test environment configuration:

```bash
# Test environment identification
ENVIRONMENT=test
TESTING=true
TEST_DB_PREFIX=test_

# Database configuration
POSTGRES_DB=test_cti_scraper
POSTGRES_USER=test_user
POSTGRES_PASSWORD=test_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=1

# Test-specific settings
TEST_PORT=8002
MOCK_EXTERNAL_SERVICES=true
MOCK_LLM_RESPONSES=true
TEST_ISOLATION=true
```

#### `docker-compose.test.yml`

Docker Compose configuration for test services:

```yaml
services:
  test_postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: test_cti_scraper
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_password
    ports:
      - "5433:5432"
  
  test_redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
```

### Environment Variables

#### Core Variables

| Variable | Description | Default | Contexts |
|----------|-------------|---------|----------|
| `ENVIRONMENT` | Environment type | `test` | All |
| `TESTING` | Test mode flag | `true` | All |
| `TEST_DB_PREFIX` | Database prefix | `test_` | All |
| `TEST_ISOLATION_LEVEL` | Isolation level | `function` | All |

#### Database Variables

| Variable | Description | Default | Contexts |
|----------|-------------|---------|----------|
| `POSTGRES_HOST` | Database host | `localhost` | All |
| `POSTGRES_PORT` | Database port | `5432` | All |
| `POSTGRES_USER` | Database user | `test_user` | Localhost/Docker |
| `POSTGRES_PASSWORD` | Database password | `test_password` | Localhost/Docker |
| `POSTGRES_DB` | Database name | `test_cti_scraper` | All |

#### Redis Variables

| Variable | Description | Default | Contexts |
|----------|-------------|---------|----------|
| `REDIS_HOST` | Redis host | `localhost` | All |
| `REDIS_PORT` | Redis port | `6379` | All |
| `REDIS_DB` | Redis database | `1` | All |
| `REDIS_PASSWORD` | Redis password | (empty) | All |

#### Test Execution Variables

| Variable | Description | Default | Contexts |
|----------|-------------|---------|----------|
| `TEST_PORT` | Test server port | `8002` | All |
| `MOCK_EXTERNAL_SERVICES` | Mock external services | `true` | All |
| `MOCK_LLM_RESPONSES` | Mock LLM responses | `true` | All |
| `TEST_ISOLATION` | Enable test isolation | `true` | All |
| `PERFORMANCE_TEST_ENABLED` | Enable performance tests | `false` | All |
| `INTEGRATION_TEST_ENABLED` | Enable integration tests | `true` | All |

## Testing Procedures

### Test Types

#### 1. Smoke Tests

Quick validation tests to ensure basic functionality:

```bash
pytest tests/smoke/ -v
```

#### 2. Unit Tests

Individual component tests with mocked dependencies:

```bash
pytest tests/ -k "not (smoke or integration or api or performance)" -v
```

#### 3. Integration Tests

Tests that verify component interactions:

```bash
pytest tests/integration/ -v
```

#### 4. API Tests

Tests for API endpoints:

```bash
pytest tests/api/ -v
```

#### 5. Performance Tests

Load and performance testing:

```bash
pytest tests/ -m performance -v
```

### Test Execution

#### Localhost Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test types
pytest tests/smoke/ -v
pytest tests/integration/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run in parallel
pytest tests/ -n auto
```

#### Docker Testing

```bash
# Run tests in Docker
docker-compose -f docker-compose.test.yml run --rm test_web pytest tests/ -v

# Run specific test types
docker-compose -f docker-compose.test.yml run --rm test_web pytest tests/smoke/ -v

# Run with environment validation
docker-compose -f docker-compose.test.yml run --rm test_web python tests/utils/test_environment.py --verbose
```

#### CI/CD Testing

The CI/CD pipeline automatically runs tests based on the workflow configuration:

```yaml
# Test execution order:
1. Environment validation
2. Security audit
3. Code quality checks
4. Unit tests
5. Integration tests
6. Performance tests (if enabled)
7. Docker tests
```

### Test Isolation

#### Database Isolation

Each test run uses a separate database to prevent interference:

```python
# Automatic database cleanup
@pytest.fixture(autouse=True)
async def test_isolation(test_environment_config, test_environment_manager):
    if not test_environment_config.test_isolation:
        return
    
    # Set up isolation before test
    await test_environment_manager._setup_test_isolation()
    
    yield
    
    # Clean up after test
    await test_environment_manager._cleanup_test_data()
```

#### Redis Isolation

Each test run uses a separate Redis database:

```python
# Redis database isolation
REDIS_DB=1  # Test-specific database
```

#### File System Isolation

Test files are created in isolated directories:

```python
# Test data directories
TEST_DATA_DIR=test-data
TEST_TEMP_DIR=test-results/temp
TEST_FIXTURES_DIR=tests/fixtures
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Issues

**Problem**: Tests fail with database connection errors

**Solutions**:
```bash
# Check PostgreSQL status
pg_isready -h localhost -p 5432

# Check database exists
psql -h localhost -p 5432 -U test_user -d test_cti_scraper -c "SELECT 1"

# Verify environment variables
python tests/utils/test_environment.py --config .env.test --verbose
```

#### 2. Redis Connection Issues

**Problem**: Tests fail with Redis connection errors

**Solutions**:
```bash
# Check Redis status
redis-cli ping

# Check Redis database
redis-cli -n 1 ping

# Verify Redis configuration
python tests/utils/database_connections.py --validate
```

#### 3. Port Conflicts

**Problem**: Port already in use errors

**Solutions**:
```bash
# Check port usage
lsof -i :5432
lsof -i :6379
lsof -i :8002

# Kill conflicting processes
kill -9 <PID>

# Use different ports in configuration
TEST_PORT=8003
```

#### 4. Docker Issues

**Problem**: Docker containers fail to start

**Solutions**:
```bash
# Check Docker status
docker-compose -f docker-compose.test.yml ps

# View container logs
docker-compose -f docker-compose.test.yml logs test_postgres

# Rebuild containers
docker-compose -f docker-compose.test.yml build --no-cache

# Clean up volumes
docker-compose -f docker-compose.test.yml down -v
```

#### 5. Environment Validation Failures

**Problem**: Environment validation fails

**Solutions**:
```bash
# Run detailed validation
python tests/utils/test_environment.py --config .env.test --verbose

# Check service health
docker-compose -f docker-compose.test.yml ps

# Verify configuration
cat .env.test
```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Set debug environment variables
export TEST_LOG_LEVEL=DEBUG
export SQL_ECHO=true
export SQL_ECHO_POOL=true

# Run tests with debug output
pytest tests/ -v -s --tb=long
```

### Performance Issues

#### Slow Test Execution

**Solutions**:
```bash
# Use parallel execution
pytest tests/ -n auto

# Skip slow tests
pytest tests/ -m "not slow"

# Use in-memory database for unit tests
pytest tests/unit/ --db-url=sqlite:///:memory:
```

#### Memory Issues

**Solutions**:
```bash
# Reduce database pool size
DB_POOL_SIZE=1
DB_MAX_OVERFLOW=0

# Use NullPool for CI
# Automatically configured in CI context
```

## Best Practices

### Test Development

#### 1. Use Appropriate Fixtures

```python
# Use environment-aware fixtures
@pytest_asyncio.fixture
async def test_session(test_database_session):
    return test_database_session

@pytest.fixture
def test_redis(test_redis_client):
    return test_redis_client
```

#### 2. Implement Proper Cleanup

```python
# Clean up resources
@pytest.fixture
def test_data_dir():
    test_data_path = Path("test-data")
    test_data_path.mkdir(exist_ok=True)
    yield test_data_path
    shutil.rmtree(test_data_path, ignore_errors=True)
```

#### 3. Use Test Markers

```python
# Mark tests appropriately
@pytest.mark.smoke
def test_basic_functionality():
    pass

@pytest.mark.integration
def test_component_integration():
    pass

@pytest.mark.performance
def test_performance():
    pass
```

### Environment Management

#### 1. Context-Aware Configuration

```python
# Use context-specific settings
if config.context == TestContext.CI:
    # CI-specific configuration
    pool_size = 1
elif config.context == TestContext.DOCKER:
    # Docker-specific configuration
    pool_size = 5
else:
    # Localhost-specific configuration
    pool_size = 5
```

#### 2. Service Health Checks

```python
# Implement health checks
async def wait_for_services():
    await wait_for_postgres()
    await wait_for_redis()
    await wait_for_web_server()
```

#### 3. Environment Validation

```python
# Validate environment before tests
@pytest.fixture(scope="session")
async def test_environment_validation():
    is_valid = await validate_test_environment()
    if not is_valid:
        pytest.exit("Test environment validation failed")
    return is_valid
```

### CI/CD Best Practices

#### 1. Parallel Job Execution

```yaml
# Run independent jobs in parallel
jobs:
  security-audit:
    runs-on: ubuntu-latest
  code-quality:
    runs-on: ubuntu-latest
  tests:
    runs-on: ubuntu-latest
```

#### 2. Conditional Test Execution

```yaml
# Run tests conditionally
- name: Run performance tests
  if: github.event.inputs.test_type == 'performance'
  run: pytest tests/ -m performance
```

#### 3. Artifact Collection

```yaml
# Collect test artifacts
- name: Upload test results
  uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: |
      test-results/
      htmlcov/
      allure-results/
```

### Monitoring and Maintenance

#### 1. Regular Environment Updates

```bash
# Update dependencies regularly
pip install -r requirements.txt --upgrade
pip install -r requirements-test.txt --upgrade

# Update Docker images
docker-compose -f docker-compose.test.yml pull
```

#### 2. Environment Health Monitoring

```bash
# Regular health checks
python tests/utils/test_environment.py --config .env.test --verbose
python tests/utils/database_connections.py --validate --verbose
```

#### 3. Test Performance Monitoring

```bash
# Monitor test execution time
pytest tests/ --durations=10

# Generate performance reports
pytest tests/ -m performance --benchmark-only
```

---

## Support

For issues and questions:

1. **Check the troubleshooting section** above
2. **Review the logs** for detailed error information
3. **Validate your environment** using the provided utilities
4. **Check the CI/CD pipeline** for automated validation results

## Contributing

When contributing to the test environment:

1. **Follow the established patterns** for fixtures and configuration
2. **Add appropriate test markers** for new test types
3. **Update documentation** for new features or changes
4. **Test across all contexts** (localhost, Docker, CI/CD)
5. **Maintain backward compatibility** when possible
