# CTIScraper Application Summary

**CTIScraper v5.0.0 "Callisto"** is an enterprise-grade threat intelligence platform that automates collection, analysis, and detection rule generation from 33+ security sources.

## Core Purpose
Aggregates cybersecurity threat intelligence, uses AI to score relevance, extract IOCs, generate SIGMA detection rules, and prevents duplicates through semantic similarity matching against 3,000+ community rules.

## Technology Stack
- **Backend:** Python 3.11+, FastAPI, Celery with Redis
- **Database:** PostgreSQL 15 + pgvector, SQLAlchemy 2.0 async
- **AI/ML:** OpenAI (GPT-4), Anthropic (Claude), LMStudio (local), sentence-transformers, LangGraph workflows
- **Infrastructure:** 6 Docker containers, pytest + Playwright testing

## Architecture
**6 Services:** postgres, redis, web (FastAPI:8001), worker (Celery), workflow_worker (Celery), scheduler

**19 Database Tables** including: articles with embeddings, sigma_rules with 4-segment embeddings, workflow executions, chat logs, ML model versions

**Key Directories:**
- `src/core/` - Scraping engine with deduplication
- `src/services/` - Business logic (LLM, RAG, SIGMA, embeddings)
- `src/workflows/` - 7-step agentic workflow (OS detect→filter→rank→extract→generate→match→queue)
- `src/web/` - 128 API endpoints, Jinja2 templates
- `src/database/` - SQLAlchemy models, async/sync managers

## Key Features
1. **Content Collection:** RSS parsing, web scraping, SimHash near-duplicate detection, rate limiting
2. **AI Analysis:** LLM threat scoring (0-10), IOC extraction, automated SIGMA rule generation with pySIGMA validation
3. **Advanced Similarity System:** Behavioral novelty assessment combining atom Jaccard (70%) and logic shape similarity (30%)
4. **RAG Chat:** Semantic search with pgvector across article database
5. **Stabilized Workflow Engine:** LangGraph-based 7-step pipeline with checkpointing, retry logic, and comprehensive evaluation datasets
6. **AI-Assisted Rule Editing:** Intelligent SIGMA rule enrichment with context-aware improvements
7. **GitHub Integration:** Automated PR submission for approved SIGMA rules to external repositories

## What's New in Callisto

### Stabilized Agentic Workflow and Evaluation Datasets
- Production-ready agentic workflow system with comprehensive evaluation framework
- Complete evaluation dataset management for testing and validation
- Stable workflow execution with improved error handling and retry logic
- Enhanced evaluation metrics and reporting
- OS Detection step added as Step 0 in workflow pipeline

### Advanced SIGMA Rule Similarity Searching
- **Behavioral Novelty Assessment:** Replaced cosine similarity with sophisticated algorithm combining:
  - Atom Jaccard (70%): Measures overlap of detection predicates (field/operator/value combinations)
  - Logic Shape Similarity (30%): Measures structural similarity of detection logic (AND/OR/NOT patterns)
- Service mismatch and filter difference penalties for accurate matching
- Improved detection predicate overlap analysis
- Structural similarity matching for detection logic patterns

### AI-Assisted SIGMA Rule Editing and Enrichment
- AI-powered rule enrichment with context-aware improvements
- Iterative rule editing with LLM feedback
- Article context integration for better rule quality
- Support for multiple LLM providers (OpenAI, Anthropic, Claude, LMStudio)
- Raw LLM response display for transparency
- Provider indicator badges in enrichment interface
- Rule validation with LLM + pySIGMA integration

### GitHub SIGMA Rule Repository Integration
- **Automated PR Creation:** Submit approved SIGMA rules directly to GitHub repositories
- **SigmaPRService:** Complete repository management service
- **Configurable Integration:** Repository paths, authentication, and Git credentials via UI
- **Branch Management:** Automatic branch creation, commit, and PR automation
- **Settings Integration:** GitHub PR Configuration section in Settings page
- **Queue Integration:** Submit PR functionality directly from SIGMA Queue interface
- **Docker Support:** Repository volume mounting for seamless access

## Notable Implementations
- **Multi-model LLM support:** Deepseek-R1, Mistral, Qwen via configurable service
- **Dual embedding strategy:** all-mpnet-base-v2 (articles), e5-base-v2 (SIGMA rules)
- **SIGMA queue system:** Generated rules await human review before GitHub PR submission
- **Coverage classification:** Determines if threats are covered/uncovered/partial
- **A/B testing interface:** Compare similarity algorithms
- **Langfuse integration:** Full LLM observability and tracing
- **Evaluation framework:** Comprehensive testing datasets for workflow validation

## Current State
Callisto represents a major milestone in SIGMA rule management capabilities. The release stabilizes the agentic workflow system with comprehensive evaluation datasets, introduces advanced similarity searching using behavioral novelty assessment, adds AI-assisted rule editing and enrichment, and completes the workflow with GitHub repository integration for automated PR submission.

## Detailed Architecture

### Service Architecture (6 Docker Containers)

1. **postgres** - PostgreSQL with pgvector extension
2. **redis** - Caching and message broker
3. **web** - FastAPI application (port 8001)
4. **worker** - Celery worker (default, source_checks, maintenance, etc.)
5. **workflow_worker** - Celery worker for agentic workflow tasks (queue: workflows)
6. **scheduler** - Celery Beat for scheduled jobs

*Note: LangGraph server and Ollama have been removed. The agentic workflow runs inside Celery workers via LangGraph; local LLMs use LMStudio.*

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
│   ├── sigma_pr_service.py  # GitHub PR integration
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
└── workflows/        # LangGraph agentic workflows (runs in Celery)
    └── agentic_workflow.py
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
- `sigma_rule_queue` - Generated rules pending review with PR tracking
- `agentic_workflow_executions` - Workflow execution tracking
- `agentic_workflow_config` - Workflow configuration with versioning
- `chat_logs` - RAG chat history and evaluation
- `ml_model_versions` - ML model performance tracking

## Agentic Workflow (7 Steps)

The workflow runs inside Celery workers (LangGraph state machine). No separate LangGraph server.

1. **OS Detection** - Windows-only routing (non-Windows articles terminate)
2. **Junk Filter** - Conservative filtering (configurable threshold)
3. **LLM Rank** - Score article relevance (0-10)
4. **Extract Agent** - Extract techniques and behaviors
5. **Generate SIGMA** - Create detection rules with iterative validation
6. **Similarity Search** - Advanced behavioral novelty assessment against 3,000+ community rules
7. **Promote to Queue** - Queue for human review and GitHub PR submission

## Notable Services & Modules

### LLM Service
- Multi-model support (Deepseek-R1, Mistral, Qwen via LMStudio)
- Per-operation model configuration (RankAgent, ExtractAgent, SigmaAgent)
- Context window management (32K tokens for reasoning models)
- System message conversion for Mistral models
- Langfuse integration for tracing

### SIGMA Services
- **sigma_generation_service.py** - Rule generation with iterative fixing
- **sigma_matching_service.py** - Behavioral novelty assessment similarity matching
- **sigma_sync_service.py** - SigmaHQ repository synchronization
- **sigma_validator.py** - pySIGMA validation and cleaning
- **sigma_coverage_service.py** - Coverage classification
- **sigma_pr_service.py** - GitHub PR submission and repository management

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

### Behavioral Novelty Assessment for SIGMA Similarity
- Replaced cosine similarity with sophisticated algorithm
- Atom Jaccard (70%): Overlap of detection predicates (field/operator/value combinations)
- Logic Shape Similarity (30%): Structural similarity of detection logic (AND/OR/NOT patterns)
- Service mismatch and filter difference penalties
- More accurate duplicate detection and rule matching

### AI-Assisted Rule Enrichment
- Context-aware rule improvement using article metadata
- Iterative editing with LLM feedback loops
- Support for custom user instructions
- Multi-provider LLM support (OpenAI, Anthropic, Claude, LMStudio)
- Raw response transparency for debugging

### GitHub Integration
- Automated branch creation and management
- Git credential handling via environment variables or UI
- PR creation via GitHub API
- Repository path configuration (Docker volume or local)
- Error handling with fallback to manual PR creation

### Agentic Workflow with LangGraph
- State-based workflow with checkpointing
- Error handling with retry logic
- Termination reasons tracked (rank threshold, no rules generated, etc.)
- Config snapshots for auditability
- Step-by-step execution tracking
- Comprehensive evaluation dataset support

### Embedding Strategy
- Articles: all-mpnet-base-v2 (768 dimensions)
- SIGMA rules: intfloat/e5-base-v2 (768 dimensions)
- LMStudio for embedding generation (local, no API costs)
- Separate embedding services for different content types

### Testing Infrastructure
- 111+ Python test files
- Comprehensive test suites: unit, integration, E2E, API, Playwright
- Allure reporting with visual test results
- Docker-based test environments
- ML model feedback tests for regression prevention
- Evaluation dataset validation

### SIGMA Rule Queue System
- Generated rules stored in queue for human review
- Advanced similarity scores with behavioral novelty assessment
- AI-assisted enrichment and editing capabilities
- GitHub PR submission tracking for repository contributions
- Review workflow with approval/rejection states
- PR URL and repository tracking

### Configuration Management
- Database-backed settings (overrides environment variables)
- Workflow config versioning with audit trail
- Agent prompt versioning system
- Per-source configuration in YAML
- GitHub repository configuration via UI

### Performance Optimizations
- Connection pooling (10 pool size, 20 max overflow)
- Vector index optimization with pgvector
- Content caching with Redis
- Async/await throughout web layer
- Background task processing with Celery

## Value Proposition

Callisto represents a significant advancement in SIGMA rule management capabilities. The release stabilizes the agentic workflow system, introduces sophisticated similarity searching using behavioral novelty assessment, adds AI-assisted rule editing and enrichment, and completes the workflow with GitHub repository integration. This creates a complete end-to-end pipeline from threat intelligence collection to SIGMA rule generation, validation, enrichment, and automated PR submission to external repositories.
