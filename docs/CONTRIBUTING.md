# Contributing to Huntable CTI Studio

Thank you for your interest in contributing to Huntable CTI Studio! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [File Organization](#file-organization)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Feature Requests](#feature-requests)
- [Security Issues](#security-issues)
- [Documentation](#documentation)
- [Release Process](#release-process)
- [Getting Help](#getting-help)
<!-- AUDIT: Clarity -- Table of contents was missing 5 of the document's 14 top-level sections (File Organization, Documentation, Release Process, Getting Help, and Acknowledgments); added the first four, Acknowledgments omitted intentionally as a closing note rather than a navigable section. -->

## Code of Conduct

<!-- AUDIT: Accuracy (Med) -- This references "our Code of Conduct" but no CODE_OF_CONDUCT.md (or equivalent) exists anywhere in the repository. Either add one and link it here, or replace this paragraph with the actual expectation for this project. -->
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
   git clone https://github.com/your-username/Huntable-CTI-Studio.git
   cd Huntable-CTI-Studio
   ```
3. Add the upstream repository:
   ```bash
   git remote add upstream https://github.com/dfirtnt/Huntable-CTI-Studio.git
   ```

## Development Setup

For the full local setup walkthrough, see [Development Setup](development/setup.md) <!-- AUDIT: Hyperlinks -- [VERIFY LINK] -->.

> **Package manager:** This project uses [`uv`](https://github.com/astral-sh/uv) (not pip). CI runs `uv sync --frozen` and `uv run` for all Python commands. Install uv before the steps below.

### 1. Environment Setup

```bash
# Provision environment and secure local secrets
./setup.sh --no-backups

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
python3 run_tests.py smoke

# Run specific test categories
python3 run_tests.py unit
python3 run_tests.py api
python3 run_tests.py integration
```

## Code Style

We follow PEP 8 with some modifications:

### Python Code Style

- **Line length**: 120 characters (configured in `pyproject.toml`, `[tool.ruff]`)
- **Import order**: Managed by `ruff` (replaces isort)
- **Type hints**: Required for all public functions and methods
- **Docstrings**: Use Google-style docstrings

### Code Formatting

The project uses `ruff` for linting and formatting (configured in `pyproject.toml`). Pre-commit hooks run automatically on `git commit`:

```bash
uv run pre-commit install
```

To run manually:

```bash
uv run ruff check src/
uv run ruff format src/
```

## File Organization

### Directory Structure

Organize files according to their purpose and lifecycle:

```text
Huntable-CTI-Studio/
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

**For comprehensive testing documentation, see `tests/TESTING.md` <!-- AUDIT: Hyperlinks -- Was a dead-end "see the Testing Guide in the tests directory" reference with no path; referenced as a code span rather than a relative link since mkdocs build --strict rejects links that resolve outside docs/. --> in the repo root.**

### Quick Testing Commands

```bash
python3 run_tests.py smoke
python3 run_tests.py unit
python3 run_tests.py api
python3 run_tests.py integration
python3 run_tests.py ui
```

### Test Requirements

- **Unit Tests**: Core functionality and business logic
- **Integration Tests**: Database and API interactions
- **UI Tests**: End-to-end user workflows
- **API Tests**: REST endpoint validation
- **Security Tests**: Vulnerability scanning and dependency auditing

### Test Coverage

- CI enforces coverage gates on `src.services`/`src.utils` in `.github/workflows/tests.yml`
  (currently 60% combined baseline, 68% for `src.services`, 20% for `src.utils`; not a repo-wide 85% target)
- Write tests for new features
- Update tests when modifying existing functionality
- Use appropriate test markers and categories

### ML Feedback Feature Testing

For ML feedback features, follow the balanced testing approach:
- **Focus on critical paths** that are most likely to break
- **Write integration tests** that catch real-world issues
- **Keep tests simple and maintainable**
- **Test the 3 essential areas**: Huntable probability calculation, API contracts, and retraining workflow

See `tests/TESTING.md` <!-- AUDIT: Hyperlinks -- Same dead-end reference resolved as above. --> in the repo root for detailed guidelines.

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

Please report security vulnerabilities using GitHub's private vulnerability reporting: go to the repository's **Security** tab and select **Report a vulnerability**.

See the [Security Policy](https://github.com/dfirtnt/Huntable-CTI-Studio/security/policy) (`.github/SECURITY.md`) for the project's security posture.

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
- **Security**: See [Security Issues](#security-issues) above <!-- AUDIT: Accuracy (Med) -- Original bullet said "Email: For security issues only" with no address given, contradicting the Security Issues section above, which directs reporters to GitHub's private vulnerability reporting instead of email. Replaced with a link to the section that has the actual process. -->

## Acknowledgments

Thank you to all contributors who have helped make Huntable CTI Studio better! Your contributions are greatly appreciated.

---

_Last updated: 2026-07-05_
_Last reviewed: 2026-09-01_
