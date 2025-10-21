# CTI Scraper Test Runner Documentation

This document provides comprehensive guidance for using the CTI Scraper unified test runner.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Command Line Interface](#command-line-interface)
4. [Test Types](#test-types)
5. [Execution Contexts](#execution-contexts)
6. [Advanced Features](#advanced-features)
7. [Error Handling and Debugging](#error-handling-and-debugging)
8. [Migration Guide](#migration-guide)
9. [Best Practices](#best-practices)

## Overview

The CTI Scraper test runner (`run_tests.py`) is the single entry point for all test execution needs. It consolidates functionality from multiple previous interfaces and provides:

- **Unified Interface**: Single command for all test execution
- **Context Awareness**: Automatic detection and configuration for different environments
- **Enhanced Reporting**: Rich output formatting and comprehensive reports
- **Advanced Debugging**: Detailed error reporting and debugging options
- **Backward Compatibility**: Support for existing workflows

### Key Features

- **Environment Management**: Automatic setup and teardown of test environments
- **Parallel Execution**: Run tests in parallel for faster execution
- **Coverage Reporting**: Generate comprehensive coverage reports
- **Test Discovery**: Intelligent test discovery and filtering
- **Error Recovery**: Retry failed tests and fail-fast options
- **Rich Output**: Progress indicators, colored output, and detailed reports

## Quick Start

### Basic Usage

```bash
# Quick health check
python run_tests.py smoke

# Full test suite with coverage
python run_tests.py all --coverage

# Docker-based integration tests
python run_tests.py --docker integration

# Debug mode with verbose output
python run_tests.py --debug --verbose
```

### Installation

```bash
# Install test dependencies
python run_tests.py --install

# Or install manually
pip install -r requirements-test.txt
playwright install chromium
```

## Command Line Interface

### Basic Syntax

```bash
python run_tests.py [OPTIONS] [TEST_TYPE]
```

### Positional Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `test_type` | Type of tests to run | `smoke` |

### Options

#### Execution Context

| Option | Description | Default |
|--------|-------------|---------|
| `--context {localhost,docker,ci}` | Execution context | `localhost` |
| `--docker` | Run tests in Docker containers | `False` |
| `--ci` | Run tests in CI/CD mode | `False` |

#### Test Execution

| Option | Description | Default |
|--------|-------------|---------|
| `--verbose`, `-v` | Verbose output | `False` |
| `--debug` | Debug mode with detailed output | `False` |
| `--parallel` | Run tests in parallel | `False` |
| `--coverage` | Generate coverage report | `False` |
| `--install` | Install test dependencies | `False` |
| `--no-validate` | Skip environment validation | `False` |

#### Test Filtering

| Option | Description | Default |
|--------|-------------|---------|
| `--paths PATH [PATH ...]` | Specific test paths to run | `None` |
| `--markers MARKER [MARKER ...]` | Test markers to include | `None` |
| `--exclude-markers MARKER [MARKER ...]` | Test markers to exclude | `None` |
| `--skip-real-api` | Skip real API tests | `False` |

#### Output and Reporting

| Option | Description | Default |
|--------|-------------|---------|
| `--output-format {progress,verbose,quiet}` | Output format | `progress` |
| `--fail-fast`, `-x` | Stop on first failure | `False` |
| `--retry COUNT` | Number of retries for failed tests | `0` |
| `--timeout SECONDS` | Timeout for test execution | `None` |

#### Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--config FILE` | Path to test configuration file | `None` |

## Test Types

### Available Test Types

| Test Type | Description | Duration | Command |
|-----------|-------------|----------|---------|
| `smoke` | Quick health check | ~30s | `python run_tests.py smoke` |
| `unit` | Unit tests only | ~1m | `python run_tests.py unit` |
| `api` | API endpoint tests | ~2m | `python run_tests.py api` |
| `integration` | System integration tests | ~3m | `python run_tests.py integration` |
| `ui` | Web interface tests | ~5m | `python run_tests.py ui` |
| `e2e` | End-to-end tests | ~3m | `python run_tests.py e2e` |
| `performance` | Performance tests | ~2m | `python run_tests.py performance` |
| `ai` | AI Assistant tests | ~3m | `python run_tests.py ai` |
| `ai-ui` | AI UI tests only | ~1m | `python run_tests.py ai-ui` |
| `ai-integration` | AI integration tests | ~2m | `python run_tests.py ai-integration` |
| `all` | Complete test suite | ~8m | `python run_tests.py all` |
| `coverage` | Tests with coverage report | ~8m | `python run_tests.py coverage` |

### Test Type Examples

```bash
# Quick health check
python run_tests.py smoke

# Unit tests with coverage
python run_tests.py unit --coverage

# Integration tests in Docker
python run_tests.py --docker integration

# AI tests without real API calls
python run_tests.py ai --skip-real-api

# Performance tests with parallel execution
python run_tests.py performance --parallel
```

## Execution Contexts

### Localhost Context (Default)

**Use case**: Local development and testing
**Services**: Local PostgreSQL, Redis, and application
**Configuration**: Uses local environment variables

```bash
# Default localhost execution
python run_tests.py smoke

# Explicit localhost context
python run_tests.py --context localhost integration
```

### Docker Context

**Use case**: Containerized testing with isolated services
**Services**: Docker containers for PostgreSQL, Redis, and application
**Configuration**: Uses Docker-specific environment variables

```bash
# Docker execution
python run_tests.py --docker smoke

# Explicit Docker context
python run_tests.py --context docker integration
```

### CI Context

**Use case**: Automated testing in CI/CD pipelines
**Services**: CI-provided services (PostgreSQL, Redis)
**Configuration**: Uses CI-specific environment variables

```bash
# CI execution
python run_tests.py --ci smoke

# Explicit CI context
python run_tests.py --context ci integration
```

## Advanced Features

### Parallel Execution

Run tests in parallel for faster execution:

```bash
# Parallel execution
python run_tests.py all --parallel

# Parallel with specific worker count
python run_tests.py all --parallel -n 4
```

### Test Filtering

Filter tests using markers and paths:

```bash
# Include specific markers
python run_tests.py --markers smoke integration

# Exclude specific markers
python run_tests.py --exclude-markers slow performance

# Run specific test paths
python run_tests.py --paths tests/api/ tests/integration/
```

### Coverage Reporting

Generate comprehensive coverage reports:

```bash
# Basic coverage
python run_tests.py all --coverage

# Coverage with specific format
python run_tests.py unit --coverage --cov-report=html --cov-report=xml
```

### Error Handling

Configure error handling behavior:

```bash
# Fail fast on first error
python run_tests.py all --fail-fast

# Retry failed tests
python run_tests.py all --retry 3

# Set timeout
python run_tests.py all --timeout 300
```

### Debugging

Enable debugging features:

```bash
# Debug mode with detailed output
python run_tests.py --debug --verbose

# Debug specific test type
python run_tests.py --debug integration

# Debug with no capture (see print statements)
python run_tests.py --debug --capture=no
```

## Error Handling and Debugging

### Common Issues

#### 1. Environment Setup Failures

**Problem**: Tests fail with environment setup errors

**Solutions**:
```bash
# Validate environment
python run_tests.py --debug --no-validate smoke

# Check environment manually
python tests/utils/test_environment.py --verbose

# Install dependencies
python run_tests.py --install
```

#### 2. Test Execution Failures

**Problem**: Tests fail during execution

**Solutions**:
```bash
# Debug mode for detailed output
python run_tests.py --debug --verbose [test_type]

# Retry failed tests
python run_tests.py [test_type] --retry 3

# Run specific failing test
python run_tests.py --paths tests/specific/test_file.py
```

#### 3. Docker Issues

**Problem**: Docker-based tests fail

**Solutions**:
```bash
# Check Docker services
docker-compose ps

# Start services
docker-compose up -d

# Debug Docker execution
python run_tests.py --docker --debug smoke
```

### Debugging Options

#### Verbose Output

```bash
# Verbose output
python run_tests.py --verbose smoke

# Debug mode
python run_tests.py --debug smoke

# Both verbose and debug
python run_tests.py --verbose --debug smoke
```

#### Error Reporting

```bash
# Long traceback
python run_tests.py --debug smoke

# No capture (see print statements)
python run_tests.py --debug --capture=no smoke

# Fail fast for quick debugging
python run_tests.py --fail-fast smoke
```

#### Test Isolation

```bash
# Run single test
python run_tests.py --paths tests/specific/test_file.py::test_function

# Run specific test class
python run_tests.py --paths tests/specific/test_file.py::TestClass

# Run tests with specific marker
python run_tests.py --markers smoke
```

## Migration Guide

### From Shell Script (`run_tests.sh`)

The shell script is deprecated but maintained for backward compatibility.

#### Old Interface
```bash
./run_tests.sh smoke
./run_tests.sh all --coverage
./run_tests.sh integration --docker
```

#### New Interface
```bash
python run_tests.py smoke
python run_tests.py all --coverage
python run_tests.py --docker integration
```

### From Old Python Runner

The old Python runner has been enhanced with new features.

#### Old Interface
```bash
python run_tests.py --smoke
python run_tests.py --all --coverage
python run_tests.py --docker --integration
```

#### New Interface
```bash
python run_tests.py smoke
python run_tests.py all --coverage
python run_tests.py --docker integration
```

### Migration Checklist

- [ ] Update scripts to use new positional argument syntax
- [ ] Replace `--smoke` with `smoke`
- [ ] Replace `--all` with `all`
- [ ] Update Docker flags to use `--docker` instead of `--docker` + test type
- [ ] Test new interface with existing workflows
- [ ] Update CI/CD pipelines to use new syntax

## Best Practices

### Test Execution

#### 1. Use Appropriate Test Types

```bash
# Development: Quick smoke tests
python run_tests.py smoke

# Pre-commit: Unit tests with coverage
python run_tests.py unit --coverage

# Pre-deploy: Full integration tests
python run_tests.py integration --docker

# Release: Complete test suite
python run_tests.py all --coverage --parallel
```

#### 2. Optimize for Context

```bash
# Local development
python run_tests.py smoke --no-validate

# CI/CD pipeline
python run_tests.py --ci all --parallel

# Docker testing
python run_tests.py --docker integration
```

#### 3. Use Parallel Execution

```bash
# For large test suites
python run_tests.py all --parallel

# With specific worker count
python run_tests.py all --parallel -n 4
```

### Error Handling

#### 1. Use Fail-Fast for Development

```bash
# Stop on first failure during development
python run_tests.py unit --fail-fast
```

#### 2. Use Retry for Flaky Tests

```bash
# Retry failed tests
python run_tests.py integration --retry 2
```

#### 3. Use Timeouts for Long-Running Tests

```bash
# Set timeout for performance tests
python run_tests.py performance --timeout 600
```

### Debugging

#### 1. Use Debug Mode for Troubleshooting

```bash
# Debug failing tests
python run_tests.py --debug --verbose [test_type]
```

#### 2. Use Specific Test Paths

```bash
# Debug specific test
python run_tests.py --paths tests/specific/test_file.py::test_function
```

#### 3. Use Marker Filtering

```bash
# Debug specific test category
python run_tests.py --markers smoke --debug
```

### Reporting

#### 1. Generate Coverage Reports

```bash
# Regular coverage
python run_tests.py all --coverage

# Coverage with multiple formats
python run_tests.py unit --coverage --cov-report=html --cov-report=xml
```

#### 2. Use Rich Output Formats

```bash
# Progress output (default)
python run_tests.py all

# Verbose output
python run_tests.py all --verbose

# Quiet output
python run_tests.py all --output-format quiet
```

### CI/CD Integration

#### 1. Use CI Context

```bash
# In CI/CD pipelines
python run_tests.py --ci all --parallel
```

#### 2. Use Appropriate Test Types

```bash
# Quick CI checks
python run_tests.py --ci smoke

# Full CI validation
python run_tests.py --ci all --coverage
```

#### 3. Use Parallel Execution

```bash
# Speed up CI execution
python run_tests.py --ci all --parallel
```

## Examples

### Development Workflow

```bash
# Quick health check during development
python run_tests.py smoke

# Unit tests before commit
python run_tests.py unit --coverage

# Integration tests before push
python run_tests.py integration --docker
```

### CI/CD Pipeline

```bash
# Smoke tests
python run_tests.py --ci smoke

# Full test suite
python run_tests.py --ci all --coverage --parallel

# Performance tests
python run_tests.py --ci performance --timeout 600
```

### Debugging Workflow

```bash
# Debug failing test
python run_tests.py --debug --verbose [test_type]

# Debug specific test
python run_tests.py --debug --paths tests/specific/test_file.py

# Debug with retry
python run_tests.py --debug --retry 2 [test_type]
```

### Production Testing

```bash
# Full validation
python run_tests.py all --coverage --parallel

# Docker-based testing
python run_tests.py --docker all --coverage

# Performance validation
python run_tests.py performance --timeout 1200
```

---

## Support

For issues and questions:

1. **Check the troubleshooting section** above
2. **Use debug mode** for detailed error information
3. **Validate your environment** using the provided utilities
4. **Check the CI/CD pipeline** for automated validation results
5. **Review the migration guide** for interface changes

## Contributing

When contributing to the test runner:

1. **Follow the established patterns** for command-line interfaces
2. **Add appropriate test markers** for new test types
3. **Update documentation** for new features or changes
4. **Test across all contexts** (localhost, Docker, CI/CD)
5. **Maintain backward compatibility** when possible
