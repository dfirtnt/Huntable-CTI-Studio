# Virtual Environments Guide

## Overview

CTI Scraper uses multiple virtual environments for different development workflows. This document explains the purpose and usage of each environment.

## Virtual Environments

### 1. `venv-test` (Python 3.13.7)
**Purpose**: Testing and development
- **Primary use**: Running tests locally against Dockerized application
- **Dependencies**: All testing frameworks and tools
- **Activation**: `source venv-test/bin/activate`
- **Usage**: `python run_tests.py --smoke`

### 2. `venv-lg` (Python 3.13.7)
**Purpose**: LG workflow (commit + push + GitHub hygiene)
- **Primary use**: Code quality, security auditing, documentation generation
- **Dependencies**: Development tools, security scanners, documentation generators
- **Activation**: `source venv-lg/bin/activate`
- **Usage**: Triggered by `lg` command for GitHub hygiene

### 3. `venv-ml` (Python 3.9.6)
**Purpose**: ML/AI tasks and fine-tuning
- **Primary use**: Machine learning experiments, model training, AI analysis
- **Dependencies**: ML libraries, data science tools, specific Python 3.9 compatibility
- **Activation**: `source venv-ml/bin/activate`
- **Usage**: ML experiments and model development

## Environment Setup

### Creating Virtual Environments

```bash
# Testing environment
python3 -m venv venv-test
source venv-test/bin/activate
pip install -r requirements.txt
pip install -r requirements-test.txt

# LG workflow environment
python3 -m venv venv-lg
source venv-lg/bin/activate
pip install -r requirements.txt
pip install -r requirements-test.txt

# ML environment (Python 3.9)
python3.9 -m venv venv-ml
source venv-ml/bin/activate
pip install -r requirements.txt
# Install ML-specific dependencies as needed
```

### Environment Activation

```bash
# For testing
source venv-test/bin/activate

# For LG workflow
source venv-lg/bin/activate

# For ML tasks
source venv-ml/bin/activate
```

## Usage Patterns

### Testing Workflow
```bash
# Activate test environment
source venv-test/bin/activate

# Run tests
python run_tests.py --smoke
python run_tests.py --all --coverage

# Or use the unified script
./run_tests.sh smoke
./run_tests.sh all --coverage
```

### LG Workflow
```bash
# Activate LG environment
source venv-lg/bin/activate

# Run LG workflow (commit + push + GitHub hygiene)
# This is typically triggered by the 'lg' command
```

### ML Workflow
```bash
# Activate ML environment
source venv-ml/bin/activate

# Run ML experiments
python scripts/ml_experiment.py
```

## Best Practices

### 1. Environment Isolation
- Each virtual environment serves a specific purpose
- Don't mix dependencies across environments
- Use the appropriate environment for each task

### 2. Dependency Management
- Keep `requirements.txt` updated for core dependencies
- Use `requirements-test.txt` for testing-specific dependencies
- Document ML-specific dependencies separately

### 3. Environment Switching
- Always deactivate current environment before switching
- Use `which python` to verify active environment
- Check `pip list` to verify installed packages

### 4. Docker Integration
- Application runs in Docker containers
- Virtual environments are for local development tasks
- Tests can run locally or in Docker containers

## Troubleshooting

### Common Issues

**Environment not found:**
```bash
# Check if environment exists
ls -la venv-*/

# Recreate if missing
python3 -m venv venv-test
```

**Wrong Python version:**
```bash
# Check Python version
python --version

# Use specific version for ML environment
python3.9 -m venv venv-ml
```

**Dependencies not installed:**
```bash
# Install requirements
pip install -r requirements.txt
pip install -r requirements-test.txt
```

**Environment conflicts:**
```bash
# Deactivate current environment
deactivate

# Activate correct environment
source venv-test/bin/activate
```

## Integration with Docker

### Application Architecture
- **Application**: Runs in Docker containers
- **Development**: Uses virtual environments for local tasks
- **Testing**: Can run locally or in Docker containers

### Test Execution
```bash
# Local testing (using venv-test)
source venv-test/bin/activate
python run_tests.py --smoke

# Docker testing
python run_tests.py --docker --smoke

# Unified script
./run_tests.sh smoke --docker
```

## Environment Variables

### Test Environment
```bash
# Set in .env or environment
TESTING=true
DATABASE_URL=postgresql://user:pass@postgres/test_db
REDIS_URL=redis://localhost:6379
```

### Development Environment
```bash
# Set in .env
ENVIRONMENT=development
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql://user:pass@postgres/cti_scraper
```

## Maintenance

### Regular Updates
- Update dependencies monthly
- Check for security vulnerabilities
- Keep Python versions current

### Environment Cleanup
- Remove unused environments
- Clean up old dependencies
- Archive experimental environments

### Documentation
- Keep this guide updated
- Document new environments
- Update usage patterns
