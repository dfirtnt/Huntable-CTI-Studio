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

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose
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
# Copy environment template
cp env.example .env
# Edit .env with your local settings

# Start Docker services
./start.sh
```

### 2. Database Setup

```bash
# Database is automatically set up with Docker
# No manual setup required - PostgreSQL runs in container
# Access via: docker exec cti_postgres psql -U cti_user -d cti_scraper
```

### 3. Run Tests

```bash
# Quick health check (recommended first step)
python run_tests.py --smoke

# Run all tests with coverage
python run_tests.py --all --coverage

# Run specific test categories
python run_tests.py --unit
python run_tests.py --api
python run_tests.py --integration

# Docker-based testing
python run_tests.py --docker --integration

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

## File Organization

### Directory Structure

Organize files according to their purpose and lifecycle:

```
CTIScraper/
├── utils/temp/              # Temporary scripts (ephemeral, one-off)
│   ├── debug_*.py          # Debug scripts
│   ├── test_*.py           # One-off test scripts
│   ├── analyze_*.py        # Temporary analysis scripts
│   └── score_*.py          # Temporary evaluation scripts
│
├── scripts/                 # Reusable utility scripts (kept in repo)
│   ├── testing/            # Test utilities
│   ├── analysis/           # Analysis tools
│   ├── maintenance/        # Maintenance scripts (fix_*.py)
│   └── shell/              # Shell utilities
│
├── outputs/                 # Generated reports/outputs (.gitignored)
│   ├── reports/           # Analysis reports (.md, .html, .json)
│   ├── exports/           # Data exports (.csv, .json)
│   └── benchmarks/        # Benchmark results
│
├── logs/                   # Log files (.gitignored)
│
└── data/                   # Test/data files (.gitignored)
```

### Classification Rules

| Type | Location | Git Status | Purpose |
|------|----------|------------|---------|
| **Temporary scripts** | `utils/temp/` | Tracked | One-off debug/test/analysis scripts |
| **Reusable scripts** | `scripts/` | Tracked | Production utilities, maintenance tools |
| **Reports** | `outputs/reports/` | Ignored | Generated markdown/HTML/JSON reports |
| **Exports** | `outputs/exports/` | Ignored | CSV/JSON data exports |
| **Benchmarks** | `outputs/benchmarks/` | Ignored | Benchmark results |
| **Logs** | `logs/` | Ignored | Application logs |
| **Test artifacts** | `test-results/`, `allure-results/` | Ignored | Test outputs |

### Guidelines

- **Temporary scripts** (`utils/temp/`): One-off scripts for debugging, testing, or analysis. These are tracked in git but may be cleaned up periodically.
- **Reusable scripts** (`scripts/`): Production utilities, maintenance tools, and scripts used regularly. Organized by purpose in subdirectories.
- **Generated outputs** (`outputs/`): All generated reports, exports, and benchmarks go here. Automatically ignored by git.
- **Root-level files**: Keep only essential project files (README, docker-compose.yml, etc.) at the root. Move temporary or utility scripts to appropriate directories.

## Testing

**For comprehensive testing documentation, see the Testing Guide in the tests directory.**

### Quick Testing Commands

```bash
# Quick health check (recommended first step)
python run_tests.py --smoke

# Run all tests with coverage
python run_tests.py --all --coverage

# Run specific test categories
python run_tests.py --unit
python run_tests.py --api
python run_tests.py --integration
python run_tests.py --ui

# Docker-based testing
python run_tests.py --docker --all
```

### Test Requirements

- **Unit Tests**: Core functionality and business logic
- **Integration Tests**: Database and API interactions
- **UI Tests**: End-to-end user workflows
- **API Tests**: REST endpoint validation
- **Security Tests**: Vulnerability scanning and dependency auditing

### Test Coverage

- Maintain 85%+ overall test coverage
- Write tests for new features
- Update tests when modifying existing functionality
- Use appropriate test markers and categories

### ML Feedback Feature Testing

For ML feedback features, follow the balanced testing approach:
- **Focus on critical paths** that are most likely to break
- **Write integration tests** that catch real-world issues
- **Keep tests simple and maintainable**
- **Test the 3 essential areas**: Huntable probability calculation, API contracts, and retraining workflow

See `tests/ML_FEEDBACK_TESTS_README.md` for detailed guidelines.

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

Please report security vulnerabilities via email to `security@ctiscraper.com`.

For security policy details, see the SECURITY.md file in the .github directory.

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
