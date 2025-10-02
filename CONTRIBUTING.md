# Contributing to CTI Scraper

Thank you for your interest in contributing to CTI Scraper! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Feature Requests](#feature-requests)
- [Security Issues](#security-issues)

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code.

## Getting Started

### Prerequisites

- Python 3.9+
- PostgreSQL 15+
- Redis 7+
- Git

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/your-username/CTIScraper.git
   cd CTIScraper
   ```
3. Add the upstream repository:
   ```bash
   git remote add upstream https://github.com/original-owner/CTIScraper.git
   ```

## Development Setup

### 1. Environment Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Copy environment template
cp env.example .env
# Edit .env with your local settings
```

### 2. Database Setup

```bash
# Start PostgreSQL and Redis
brew services start postgresql@15  # macOS
brew services start redis

# Create database
createdb cti_scraper_test
```

### 3. Run Tests

```bash
# Quick health check (recommended first step)
python run_tests.py --smoke
./run_tests.sh smoke

# Run all tests with coverage
python run_tests.py --all --coverage
./run_tests.sh all --coverage

# Run specific test categories
python run_tests.py --unit
python run_tests.py --api
python run_tests.py --integration
./run_tests.sh unit
./run_tests.sh api
./run_tests.sh integration

# Docker-based testing
python run_tests.py --docker --integration
./run_tests.sh integration --docker

# Install test dependencies
python run_tests.py --install
```

## Code Style

We follow PEP 8 with some modifications:

### Python Code Style

- **Line length**: 88 characters (Black default)
- **Import order**: Use `isort` for consistent import ordering
- **Type hints**: Required for all public functions and methods
- **Docstrings**: Use Google-style docstrings

### Code Formatting

We use automated tools for code formatting:

```bash
# Install formatting tools
pip install black isort mypy flake8

# Format code
black src/
isort src/

# Check types
mypy src/

# Lint code
flake8 src/
```

### Pre-commit Hooks

Install pre-commit hooks for automatic formatting:

```bash
pip install pre-commit
pre-commit install
```

## Testing

### Writing Tests

- Write tests for all new functionality
- Use descriptive test names
- Group related tests in classes
- Use fixtures for common setup
- Mock external dependencies

### Test Structure

```python
import pytest
from src.core.models import Article

class TestArticleModel:
    """Test cases for Article model."""
    
    def test_article_creation(self):
        """Test article creation with valid data."""
        article = Article(
            title="Test Article",
            url="https://example.com/test",
            content="Test content"
        )
        assert article.title == "Test Article"
        assert article.url == "https://example.com/test"
    
    def test_article_validation(self):
        """Test article validation with invalid data."""
        with pytest.raises(ValueError):
            Article(title="", url="invalid-url")
```

### Running Tests

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run tests and generate coverage report
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_models.py

# Run tests matching pattern
pytest -k "test_article"
```

## Pull Request Process

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

- Write clear, descriptive commit messages
- Follow the existing code style
- Add tests for new functionality
- Update documentation as needed

### 3. Commit Your Changes

```bash
git add .
git commit -m "feat: add new feature description"
```

### 4. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 5. Create a Pull Request

1. Go to your fork on GitHub
2. Click "New Pull Request"
3. Select your feature branch
4. Fill out the PR template
5. Submit the PR

### Pull Request Guidelines

- **Title**: Clear, descriptive title
- **Description**: Explain what the PR does and why
- **Tests**: Ensure all tests pass
- **Documentation**: Update docs if needed
- **Breaking changes**: Clearly mark breaking changes

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

## Reporting Bugs

### Before Reporting

1. Check existing issues
2. Try the latest version
3. Reproduce the issue

### Bug Report Template

```markdown
**Describe the bug**
Clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
Clear description of what you expected to happen.

**Environment:**
- OS: [e.g. macOS 14.0]
- Python: [e.g. 3.11.0]
- CTI Scraper: [e.g. 2.0.0]

**Additional context**
Add any other context about the problem here.
```

## Feature Requests

### Before Requesting

1. Check if the feature already exists
2. Consider if it fits the project scope
3. Think about implementation details

### Feature Request Template

```markdown
**Is your feature request related to a problem?**
Clear description of the problem.

**Describe the solution you'd like**
Clear description of what you want to happen.

**Describe alternatives you've considered**
Clear description of any alternative solutions.

**Additional context**
Add any other context or screenshots.
```

## Security Issues

**Do not report security issues through public GitHub issues.**

Please report security vulnerabilities via email to `security@ctiscraper.com`. See our [Security Policy](.github/SECURITY.md) for more details.

## Documentation

### Code Documentation

- Use Google-style docstrings
- Include type hints
- Document complex algorithms
- Provide usage examples

### API Documentation

- Document all endpoints
- Include request/response examples
- Document error codes
- Keep docs up to date

## Release Process

### Versioning

We follow [Semantic Versioning](https://semver.org/):

- **Major**: Breaking changes
- **Minor**: New features, backward compatible
- **Patch**: Bug fixes, backward compatible

### Release Checklist

- [ ] All tests pass
- [ ] Documentation updated
- [ ] Changelog updated
- [ ] Version bumped
- [ ] Release notes written

## Getting Help

- **Issues**: GitHub issue tracker
- **Discussions**: GitHub discussions
- **Documentation**: Project README and docs
- **Email**: For security issues only

## Acknowledgments

Thank you to all contributors who have helped make CTI Scraper better! Your contributions are greatly appreciated.

---

**Note**: This contributing guide is a living document. Please suggest improvements through issues or pull requests.
