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
2. [Backup & Restore](docs/operations/BACKUP_AND_RESTORE.md) - Comprehensive backup system
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
- **[SIGMA Detection Rules](docs/features/SIGMA_DETECTION_RULES.md)** - AI-powered rule generation, matching & similarity
- **[Content Filtering](docs/features/CONTENT_FILTERING.md)** - ML-based content optimization for GPT-4o
- **[OS Detection](docs/features/OS_DETECTION.md)** - Automated operating system detection for threat intelligence articles
- **[Workflow Data Flow](docs/WORKFLOW_DATA_FLOW.md)** - Data storage, supervisor aggregation, and execution methods (Celery vs LangGraph Server)
- **[AGENTS.md](AGENTS.md)** - AI assistant guidelines and instructions

### Development Documentation
- **[Development Setup](docs/development/DEVELOPMENT_SETUP.md)** - Environment, pytest, virtual environments
- **[Database Queries](docs/development/DATABASE_QUERY_GUIDE.md)** - Database operations
- **[Threat Hunting Scoring](docs/development/THREAT_HUNTING_SCORING.md)** - Scoring algorithms
- **[Hybrid IOC Extraction](docs/development/HYBRID_IOC_EXTRACTION.md)** - IOC extraction system
- **[Web App Testing](docs/development/WEB_APP_TESTING.md)** - Playwright-based UI testing
- **[Allure Reports](docs/development/ALLURE_REPORTS.md)** - Test visualization and reporting
- **[Lightweight Integration](docs/development/LIGHTWEIGHT_INTEGRATION_TESTING.md)** - Fast integration testing
- **[RAG System](docs/RAG_SYSTEM.md)** - Retrieval-Augmented Generation
- **[LangGraph Integration](docs/LANGGRAPH_INTEGRATION.md)** - Agentic workflow orchestration and debugging

### Testing Documentation
- **[Testing Guide](tests/TESTING.md)** - Comprehensive testing documentation
- **[Testing Quick Start](tests/QUICK_START.md)** - 5-minute testing setup
- **[Advanced Testing](tests/ADVANCED_TESTING.md)** - API, E2E, and performance testing
- **[CI/CD Testing](tests/CICD_TESTING.md)** - GitHub Actions and pipeline integration
- **[ML Feedback Tests](tests/ML_FEEDBACK_TESTS_README.md)** - Essential regression prevention
- **[Skipped Tests](tests/SKIPPED_TESTS.md)** - Test status reference
- **[AI Tests](tests/AI_TESTS_README.md)** - AI-specific testing

### Deployment Documentation
- **[Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md)** - Container setup and architecture
- **[Getting Started](docs/deployment/GETTING_STARTED.md)** - Quick deployment guide
- **[Technical Readout](docs/deployment/TECHNICAL_READOUT.md)** - Technical overview

### Operations Documentation
- **[Backup & Restore](docs/operations/BACKUP_AND_RESTORE.md)** - Database and full system backups
- **[Automated Backups](docs/operations/BACKUP_AND_RESTORE.md#automated-backups)** - Scheduled backup configuration

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
- **Backing Up Data** → [Backup & Restore](docs/operations/BACKUP_AND_RESTORE.md)
- **Generating SIGMA Rules** → [SIGMA Detection Rules](docs/features/SIGMA_DETECTION_RULES.md)
- **Understanding Architecture** → [Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md)

### By Component
- **Web Interface** → [README.md](README.md#web-interface) + [API Endpoints](docs/API_ENDPOINTS.md)
- **AI Features** → [RAG System](docs/RAG_SYSTEM.md) + [SIGMA Detection Rules](docs/features/SIGMA_DETECTION_RULES.md) + [Content Filtering](docs/features/CONTENT_FILTERING.md) + [OS Detection](docs/features/OS_DETECTION.md)
- **Workflow System** → [LangGraph Integration](docs/LANGGRAPH_INTEGRATION.md) + [Agentic Workflow](src/workflows/agentic_workflow.py)
- **Testing** → [Testing Guide](tests/TESTING.md) + [Advanced Testing](tests/ADVANCED_TESTING.md) + [ML Tests](tests/ML_FEEDBACK_TESTS_README.md)
- **Database** → [Database Queries](docs/development/DATABASE_QUERY_GUIDE.md) + [Backup & Restore](docs/operations/BACKUP_AND_RESTORE.md)
- **Docker** → [Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md) + [Getting Started](docs/deployment/GETTING_STARTED.md)

### By Audience
- **End Users** → [README.md](README.md) + [Getting Started](docs/deployment/GETTING_STARTED.md)
- **Developers** → [Development Setup](docs/development/DEVELOPMENT_SETUP.md) + [Testing](tests/TESTING.md) + [Advanced Testing](tests/ADVANCED_TESTING.md)
- **DevOps** → [Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md) + [Backup & Restore](docs/operations/BACKUP_AND_RESTORE.md)
- **API Integrators** → [API Endpoints](docs/API_ENDPOINTS.md)

## 📖 Documentation Standards

- **Accuracy**: All documentation is kept current with the codebase
- **Completeness**: Every feature has corresponding documentation
- **Clarity**: Documentation uses clear, concise language
- **Examples**: Code examples and usage patterns provided
- **Cross-references**: Related documentation is linked appropriately

## 🔄 Recent Changes (January 2025)

Major documentation consolidation completed:
- **Eliminated 57 redundant files** (116 → 59 files, 49% reduction)
- **Consolidated SIGMA docs** (4 → 1): New comprehensive guide at `docs/features/SIGMA_DETECTION_RULES.md`
- **Consolidated backup docs** (3 → 1): Unified guide at `docs/operations/BACKUP_AND_RESTORE.md`
- **Consolidated testing docs** (15 redundant → streamlined): Moved advanced guides to `tests/`
- **Consolidated content filtering** (2 → 1): Single guide at `docs/features/CONTENT_FILTERING.md`
- **Archived historical docs**: Moved implementation notes to `docs/archive/`
- **Deleted 30 sample articles**: Removed test data from version control
- **Created new structure**: Added `docs/features/` and `docs/operations/` directories

Benefits:
- Clearer navigation paths for all user types
- Eliminated duplicate and outdated information
- Improved maintainability and discoverability
- Reduced cognitive load with focused, comprehensive guides

## 💡 Need Help?

- **Can't find what you're looking for?** Check the [README.md](README.md) for quick links
- **Found outdated information?** Please open an issue or submit a PR
- **Want to improve documentation?** See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines

---

*Last updated: January 2025*

## Recent Documentation Updates

### January 2025 - MDU Update
- **OS Detection**: Added comprehensive documentation for OS detection system
- **Workflow Steps**: Updated to reflect correct 7-step agentic workflow (including OS Detection as Step 1.5)
- **Docker Services**: Added LangGraph Server and LangFlow to architecture documentation
- **API Endpoints**: Updated count to 133+ endpoints
- **Feature Index**: Added OS Detection and Workflow System to component navigation
