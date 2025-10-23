# CTI Scraper Documentation

This directory contains comprehensive documentation for the CTI Scraper project.

## Directory Structure

```
docs/
├── development/           # Development guides and technical documentation
│   ├── ADVANCED_TESTING.md      # API, E2E, and performance testing
│   ├── DEVELOPMENT_SETUP.md     # Environment setup, pytest, virtual environments
│   ├── DATABASE_QUERY_GUIDE.md  # Database operations
│   ├── HYBRID_IOC_EXTRACTION.md # IOC extraction system
│   ├── THREAT_HUNTING_SCORING.md # Scoring algorithms
│   └── ... (other development docs)
├── deployment/           # Deployment and infrastructure documentation
│   ├── DOCKER_ARCHITECTURE.md   # Container setup and architecture
│   ├── GETTING_STARTED.md       # Quick deployment guide
│   ├── DATABASE_BACKUP_RESTORE.md # Backup and restore procedures
│   └── ... (other deployment docs)
├── API_ENDPOINTS.md      # Complete API reference
├── RAG_SYSTEM.md         # Retrieval-Augmented Generation
├── CONTENT_FILTERING_SYSTEM.md # ML-based content filtering
└── README.md             # This file
```

## Quick Navigation

### 🚀 Getting Started
- **Main README**: `../README.md` - Quick start and overview
- **Master Documentation**: `../DOCUMENTATION.md` - Complete documentation index
- **Getting Started**: `deployment/GETTING_STARTED.md` - Quick deployment guide
- **Docker Architecture**: `deployment/DOCKER_ARCHITECTURE.md` - Complete Docker setup guide

### 🔧 Development
- **Testing Guide**: `../tests/TESTING.md` - Comprehensive testing documentation
- **Development Setup**: `development/DEVELOPMENT_SETUP.md` - Environment setup and pytest
- **Advanced Testing**: `development/ADVANCED_TESTING.md` - API, E2E, and performance testing
- **Database Queries**: `development/DATABASE_QUERY_GUIDE.md` - Database operations
- **ML Feedback Tests**: `../tests/ML_FEEDBACK_TESTS_README.md` - Essential regression prevention tests

### 🤖 AI Features
- **RAG System**: `RAG_SYSTEM.md` - Retrieval-Augmented Generation with conversational AI
- **Content Filtering**: `CONTENT_FILTERING_SYSTEM.md` - ML-based content filtering
- **Hybrid IOC Extraction**: `development/HYBRID_IOC_EXTRACTION.md` - Advanced IOC extraction system
- **Threat Hunting Scoring**: `development/THREAT_HUNTING_SCORING.md` - Scoring algorithms with ML integration

### 📦 Deployment
- **Getting Started**: `deployment/GETTING_STARTED.md` - Quick deployment guide
- **Docker Architecture**: `deployment/DOCKER_ARCHITECTURE.md` - Container setup and architecture
- **Backup System**: `deployment/DATABASE_BACKUP_RESTORE.md` - Backup and restore procedures

### 🔌 API Reference
- **API Endpoints**: `API_ENDPOINTS.md` - Complete API documentation (128 endpoints)

## Contributing

When adding new documentation:
1. Place it in the appropriate subdirectory
2. Update this README with a brief description
3. Follow the existing naming conventions
4. Link to it from relevant existing documentation
5. Update the master documentation index at `../DOCUMENTATION.md`

## Notes

- All documentation is written in Markdown format
- Keep documentation up to date with code changes
- Use relative links when referencing other documentation files
- Include code examples where appropriate
- See `../DOCUMENTATION.md` for the complete documentation structure
