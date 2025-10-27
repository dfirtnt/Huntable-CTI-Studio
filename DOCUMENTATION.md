# CTIScraper Documentation

Welcome to the CTIScraper documentation. This is your single entry point for all project documentation.

## 🚀 Quick Start Paths

Choose your path based on your role:

### New Users
**Getting Started with CTIScraper**
1. [Installation Guide](README.md#quick-start) - One-command setup
2. [First Steps](docs/deployment/GETTING_STARTED.md) - Basic usage
3. [Web Interface](README.md#access-the-application) - Dashboard and features

### Developers
**Contributing to CTIScraper**
1. [Development Setup](docs/development/DEVELOPMENT_SETUP.md) - Environment configuration
2. [Architecture Overview](docs/deployment/DOCKER_ARCHITECTURE.md) - System design
3. [Contributing Guidelines](CONTRIBUTING.md) - Code style and PR process
4. [Testing Guide](tests/TESTING.md) - Comprehensive testing documentation

### DevOps & Operations
**Deploying and Managing CTIScraper**
1. [Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md) - Container setup
2. [Backup System](docs/DATABASE_BACKUP_RESTORE.md) - Data protection
3. [Monitoring](README.md#monitoring) - Health checks and metrics
4. [Production Deployment](README.md#production-deployment) - Production setup

### API Users
**Integrating with CTIScraper**
1. [API Reference](docs/API_ENDPOINTS.md) - Complete API documentation
2. [API Examples](docs/API_ENDPOINTS.md#usage-examples) - Code samples
3. [Authentication](docs/API_ENDPOINTS.md#authentication) - Security setup

## 📚 Documentation Map

### Core Documentation
- **[README.md](README.md)** - Project overview, features, and quick start
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - How to contribute to the project
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and changes
- **[VERSIONING.md](VERSIONING.md)** - Version numbering system

### Feature Documentation
- **[SIGMA_RULE_GENERATION.md](SIGMA_RULE_GENERATION.md)** - AI-powered detection rule generation
- **[AGENTS.md](AGENTS.md)** - AI assistant guidelines and instructions

### Development Documentation
- **[Development Setup](docs/development/DEVELOPMENT_SETUP.md)** - Environment, pytest, virtual environments
- **[Advanced Testing](docs/development/ADVANCED_TESTING.md)** - API, E2E, performance testing
- **[Database Queries](docs/development/DATABASE_QUERY_GUIDE.md)** - Database operations
- **[Threat Hunting Scoring](docs/development/THREAT_HUNTING_SCORING.md)** - Scoring algorithms
- **[Hybrid IOC Extraction](docs/development/HYBRID_IOC_EXTRACTION.md)** - IOC extraction system
- **[Content Filtering](docs/CONTENT_FILTERING_SYSTEM.md)** - ML-based content filtering
- **[RAG System](docs/RAG_SYSTEM.md)** - Retrieval-Augmented Generation

### Testing Documentation
- **[Testing Guide](tests/TESTING.md)** - Comprehensive testing documentation
- **[Testing Quick Start](tests/QUICK_START.md)** - 5-minute testing setup
- **[ML Feedback Tests](tests/ML_FEEDBACK_TESTS_README.md)** - Essential regression prevention
- **[Skipped Tests](tests/SKIPPED_TESTS.md)** - Test status reference
- **[AI Tests](tests/AI_TESTS_README.md)** - AI-specific testing

### Deployment Documentation
- **[Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md)** - Container setup and architecture
- **[Getting Started](docs/deployment/GETTING_STARTED.md)** - Quick deployment guide
- **[Database Backup](docs/DATABASE_BACKUP_RESTORE.md)** - Backup and restore procedures
- **[Technical Readout](docs/deployment/TECHNICAL_READOUT.md)** - Technical overview

### API Documentation
- **[API Endpoints](docs/API_ENDPOINTS.md)** - Complete API reference (128 endpoints)
- **[API Examples](docs/API_ENDPOINTS.md#usage-examples) - Usage examples and code samples**

### Process and System Documentation
- **[Process Diagrams](process_diagrams.md)** - ASCII diagrams for presentations
- **[SYSTEM OVERVIEW](docs/SYSTEM_OVERVIEW.md)** - Detailed system workflow
- **[Technical Readout](docs/deployment/TECHNICAL_READOUT.md)** - Technical overview**

## 🔍 Finding What You Need

### By Task
- **Installing CTIScraper** → [README.md](README.md#quick-start)
- **Running Tests** → [Testing Quick Start](tests/QUICK_START.md)
- **Contributing Code** → [CONTRIBUTING.md](CONTRIBUTING.md)
- **Using the API** → [API Endpoints](docs/API_ENDPOINTS.md)
- **Backing Up Data** → [Database Backup](docs/DATABASE_BACKUP_RESTORE.md)
- **Understanding Architecture** → [Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md)

### By Component
- **Web Interface** → [README.md](README.md#web-interface) + [API Endpoints](docs/API_ENDPOINTS.md)
- **AI Features** → [RAG System](docs/RAG_SYSTEM.md) + [SIGMA Rules](SIGMA_RULE_GENERATION.md)
- **Testing** → [Testing Guide](tests/TESTING.md) + [ML Tests](tests/ML_FEEDBACK_TESTS_README.md)
- **Database** → [Database Queries](docs/development/DATABASE_QUERY_GUIDE.md) + [Backup](docs/DATABASE_BACKUP_RESTORE.md)
- **Docker** → [Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md) + [Getting Started](docs/deployment/GETTING_STARTED.md)

### By Audience
- **End Users** → [README.md](README.md) + [Getting Started](docs/deployment/GETTING_STARTED.md)
- **Developers** → [Development Setup](docs/development/DEVELOPMENT_SETUP.md) + [Testing](tests/TESTING.md)
- **DevOps** → [Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md) + [Backup](docs/DATABASE_BACKUP_RESTORE.md)
- **API Integrators** → [API Endpoints](docs/API_ENDPOINTS.md)

## 📖 Documentation Standards

- **Accuracy**: All documentation is kept current with the codebase
- **Completeness**: Every feature has corresponding documentation
- **Clarity**: Documentation uses clear, concise language
- **Examples**: Code examples and usage patterns provided
- **Cross-references**: Related documentation is linked appropriately

## 🔄 Recent Changes

This documentation structure was restructured to:
- Eliminate duplication across testing and setup docs
- Provide clear navigation paths for different user types
- Consolidate scattered information into focused guides
- Improve maintainability and discoverability

## 💡 Need Help?

- **Can't find what you're looking for?** Check the [README.md](README.md) for quick links
- **Found outdated information?** Please open an issue or submit a PR
- **Want to improve documentation?** See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines

---

*Last updated: January 2025*
