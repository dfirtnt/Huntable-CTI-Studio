# CTIScraper Application Summary

**CTIScraper v4.0.0 "Kepler"** is an enterprise-grade threat intelligence platform that automates collection, analysis, and detection rule generation from 33+ security sources.

## Core Purpose
Aggregates cybersecurity threat intelligence, uses AI to score relevance, extract IOCs, generate SIGMA detection rules, and prevents duplicates through semantic similarity matching against 3,000+ community rules.

## Technology Stack
- **Backend:** Python 3.11+, FastAPI, Celery with Redis
- **Database:** PostgreSQL 15 + pgvector, SQLAlchemy 2.0 async
- **AI/ML:** OpenAI (GPT-4), Anthropic (Claude), LMStudio (local), sentence-transformers, LangGraph workflows
- **Infrastructure:** 7 Docker containers, pytest + Playwright testing

## Architecture
**7 Microservices:** postgres, redis, web (FastAPI:8001), celery worker, scheduler, langgraph-server, ollama

**19 Database Tables** including: articles with embeddings, sigma_rules with 4-segment embeddings, workflow executions, chat logs, ML model versions

**Key Directories:**
- `src/core/` - Scraping engine with deduplication
- `src/services/` - Business logic (LLM, RAG, SIGMA, embeddings)
- `src/workflows/` - 6-step agentic workflow (filter→rank→extract→generate→match→queue)
- `src/web/` - 128 API endpoints, Jinja2 templates
- `src/database/` - SQLAlchemy models, async/sync managers

## Key Features
1. **Content Collection:** RSS parsing, web scraping, SimHash near-duplicate detection, rate limiting
2. **AI Analysis:** LLM threat scoring (0-10), IOC extraction, automated SIGMA rule generation with pySIGMA validation
3. **Similarity System:** 4-segment weighted matching (title 30%, description 20%, tags 25%, detection 25%)
4. **RAG Chat:** Semantic search with pgvector across article database
5. **Workflow Engine:** LangGraph-based 6-step pipeline with checkpointing and retry logic

## Notable Implementations
- **Multi-model LLM support:** Deepseek-R1, Mistral, Qwen via configurable service
- **Dual embedding strategy:** all-mpnet-base-v2 (articles), e5-base-v2 (SIGMA rules)
- **SIGMA queue system:** Generated rules await human review before SigmaHQ PR submission
- **Coverage classification:** Determines if threats are covered/uncovered/partial
- **A/B testing interface:** Compare similarity algorithms
- **Langfuse integration:** Full LLM observability and tracing

## Current State
Recent commits show active development on SIGMA similarity testing, 4-segment weighted matching implementation, and A/B testing interfaces. Multiple modified files indicate ongoing refinement of the similarity and detection systems.

## Detailed Architecture

### Service Architecture (7 Docker Containers)

1. **postgres** - PostgreSQL with pgvector extension
2. **redis** - Caching and message broker
3. **web** - FastAPI application (port 8001)
4. **worker** - Celery worker for background tasks
5. **scheduler** - Celery Beat for scheduled jobs
6. **langgraph-server** - Agent chat UI debugging (port 2024)
7. **ollama** - Local LLM inference (port 11434)

### Application Structure

```
src/
├── cli/              # Command-line interface
├── core/             # Core scraping & processing logic
│   ├── fetcher.py
│   ├── modern_scraper.py
│   ├── processor.py
│   └── rss_parser.py
├── database/         # Database models & managers
│   ├── models.py     # SQLAlchemy models (19 tables)
│   ├── manager.py    # Sync database operations
│   └── async_manager.py  # Async database operations
├── models/           # Pydantic data models
├── services/         # Business logic layer
│   ├── llm_service.py
│   ├── rag_service.py
│   ├── sigma_*.py    # SIGMA rule services
│   ├── embedding_service.py
│   └── deduplication.py
├── utils/            # Utilities
│   ├── ioc_extractor.py
│   ├── content_filter.py
│   └── langfuse_client.py
├── web/              # Web application
│   ├── modern_main.py
│   ├── routes/       # 33 route files (~11,848 lines)
│   ├── templates/    # Jinja2 templates
│   └── static/       # CSS, JS, images
├── worker/           # Celery tasks
│   ├── celery_app.py
│   └── tasks/
└── workflows/        # LangGraph agentic workflows
    ├── agentic_workflow.py
    └── langgraph_server.py
```

### Database Schema (19 Tables)

Key tables:
- `sources` - RSS feeds and scraping sources
- `articles` - Collected threat intelligence articles with embeddings
- `source_checks` - Source health tracking
- `article_annotations` - Huntability annotations with embeddings
- `chunk_analysis_results` - ML vs hunt scoring comparison
- `sigma_rules` - SigmaHQ repository (3,000+ rules) with multi-segment embeddings
- `article_sigma_matches` - Article-to-rule matches with coverage analysis
- `sigma_rule_queue` - Generated rules pending review
- `agentic_workflow_executions` - Workflow execution tracking
- `agentic_workflow_config` - Workflow configuration with versioning
- `chat_logs` - RAG chat history and evaluation
- `ml_model_versions` - ML model performance tracking

## Agentic Workflow (6 Steps)

1. **Junk Filter** - Conservative filtering (configurable threshold)
2. **LLM Rank** - Score article relevance (0-10)
3. **Extract Agent** - Extract techniques and behaviors
4. **Generate SIGMA** - Create detection rules with iterative validation
5. **Similarity Search** - Compare against 3,000+ community rules
6. **Promote to Queue** - Queue for human review and PR submission

## Notable Services & Modules

### LLM Service
- Multi-model support (Deepseek-R1, Mistral, Qwen via LMStudio)
- Per-operation model configuration (RankAgent, ExtractAgent, SigmaAgent)
- Context window management (32K tokens for reasoning models)
- System message conversion for Mistral models
- Langfuse integration for tracing

### SIGMA Services
- **sigma_generation_service.py** - Rule generation with iterative fixing
- **sigma_matching_service.py** - 4-segment weighted similarity matching
- **sigma_sync_service.py** - SigmaHQ repository synchronization
- **sigma_validator.py** - pySIGMA validation and cleaning
- **sigma_coverage_service.py** - Coverage classification

### Deduplication Service
- Content hash-based exact duplicate detection
- SimHash for near-duplicate detection (64-bit hashes)
- Bucket-based SimHash lookup for efficiency
- URL normalization and tracking

### Content Filter
- ML-based chunk classification
- Conservative filtering mode for workflows
- Token optimization for GPT-4 (saves ~50% tokens)
- Confidence-based thresholding

## Interesting Implementation Details

### Multi-Segment SIGMA Similarity
- Weighted similarity across 4 segments: title (30%), description (20%), tags (25%), detection structure (25%)
- Separate embeddings for each segment stored in database
- Configurable similarity thresholds per segment

### Agentic Workflow with LangGraph
- State-based workflow with checkpointing
- Error handling with retry logic
- Termination reasons tracked (rank threshold, no rules generated, etc.)
- Config snapshots for auditability
- Step-by-step execution tracking

### Embedding Strategy
- Articles: all-mpnet-base-v2 (768 dimensions)
- SIGMA rules: intfloat/e5-base-v2 (768 dimensions)
- LMStudio for embedding generation (local, no API costs)
- Separate embedding services for different content types

### Testing Infrastructure
- 111 Python test files
- Comprehensive test suites: unit, integration, E2E, API, Playwright
- Allure reporting with visual test results
- Docker-based test environments
- ML model feedback tests for regression prevention

### SIGMA Rule Queue System
- Generated rules stored in queue for human review
- Similarity scores with top matches displayed
- PR submission tracking for SigmaHQ contributions
- Review workflow with approval/rejection states

### Configuration Management
- Database-backed settings (overrides environment variables)
- Workflow config versioning with audit trail
- Agent prompt versioning system
- Per-source configuration in YAML

### Performance Optimizations
- Connection pooling (10 pool size, 20 max overflow)
- Vector index optimization with pgvector
- Content caching with Redis
- Async/await throughout web layer
- Background task processing with Celery

## Value Proposition

This is a sophisticated, production-grade threat intelligence platform with impressive AI integration, comprehensive testing, and well-structured architecture. The codebase shows mature software engineering practices with clear separation of concerns, extensive documentation, and robust error handling.
