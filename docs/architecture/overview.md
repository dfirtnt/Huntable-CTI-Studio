# Architecture Overview

Huntable CTI Studio is a modern threat intelligence collection and analysis platform that aggregates, processes, and analyzes cybersecurity content from multiple sources.

## Core Mission

- **Collect**: Automatically gather threat intelligence from RSS feeds and web scraping
- **Process**: Clean, normalize, deduplicate, and quality-score content
- **Analyze**: Extract threat techniques using LLM-powered agents
- **Present**: Provide web interface and APIs for threat intelligence consumption

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Huntable CTI Studio Architecture                        │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Sources  │    │  Web Interface  │    │   Background    │    │   Database      │
│                 │    │                 │    │     Tasks       │    │                 │
│ • RSS Feeds     │───▶│ • FastAPI App   │    │ • Celery Worker │    │ • PostgreSQL    │
│ • Web Scraping  │    │ • Dashboard     │    │ • Scheduler     │    │ • Redis Cache   │
│ • 303+ Sources  │    │ • Search/Filter │    │ • Collection    │    │ • pgvector      │
│ • Browser Ext.  │    │ • RAG Chat      │    │ • AI Analysis   │    │ • Async Manager │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │                       │
         ▼                       ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        Docker Container Environment                            │
│                                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │    Web      │  │   Worker    │  │  Scheduler  │  │  LM Studio  │          │
│  │  (FastAPI)  │  │  (Celery)   │  │  (Celery)   │  │    (LLM)    │          │
│  │   Port 8001 │  │             │  │             │  │  Port 1234  │          │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ PostgreSQL  │  │    Redis    │  │     CLI     │  │   Backup    │          │
│  │   Port 5432 │  │  Port 6379  │  │   Service   │  │   System    │          │
│  │  + pgvector │  │             │  │             │  │             │          │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Docker Services

The platform runs as a Docker Compose stack with the following services:

| Service | Image/Build | Purpose | Ports |
|---------|-------------|---------|-------|
| **postgres** | `pgvector/pgvector:pg15` | Primary database with pgvector extension | 5432 |
| **redis** | `redis:7-alpine` | Cache and Celery message broker | 6379 |
| **web** | Dockerfile | FastAPI application (uvicorn) | 8001, 8888 |
| **worker** | Dockerfile | Celery worker for general queues | — |
| **workflow_worker** | Dockerfile | Celery worker for LangGraph workflows | — |
| **scheduler** | Dockerfile | Celery beat for periodic tasks | — |
| **cli** | Dockerfile | CLI interface (profile: `tools`) | — |

## Data Flow

### 1. Article Collection

```
┌─────────────────┐
│   Celery Beat   │
│   Scheduler     │
│   (Every 30min) │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ check_all_sources│
│     Task        │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Source List   │───▶│  RSS Parser     │───▶│ Modern Scraper  │
│   (303+ sources)│    │                 │    │                 │
└─────────────────┘    └─────────┬───────┘    └─────────┬───────┘
                                 │                      │
                                 ▼                      ▼
                        ┌─────────────────┐    ┌─────────────────┐
                        │  Feed Content   │    │  Web Content    │
                        │  Extraction     │    │  Extraction     │
                        └─────────┬───────┘    └─────────┬───────┘
                                  │                      │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ Content Processor│
                                    │                 │
                                    │ • Deduplication │
                                    │ • Quality Filter│
                                    │ • Normalization │
                                    └─────────┬───────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │   Database      │
                                    │   Storage       │
                                    └─────────────────┘
```

### 2. Content Processing Pipeline

1. **Content Extraction**: RSS parser or web scraper fetches articles
2. **Normalization**: Clean HTML, extract metadata (JSON-LD, OpenGraph)
3. **Deduplication**: Compare content hashes and titles
4. **Quality Filtering**: ML-based content classification (if enabled)
5. **Storage**: Save to PostgreSQL with indexed metadata

### 3. LLM-Powered Analysis Workflows

See [Workflow Data Flow](workflow-data-flow.md) for detailed workflow architecture using LangGraph.

## Directory Structure

```
Huntable-CTI-Studio/
├── src/                          # Main application code
│   ├── web/                      # FastAPI web application
│   │   ├── modern_main.py        # Main FastAPI app entry point
│   │   ├── templates/            # Jinja2 HTML templates
│   │   └── static/               # CSS, JS, images
│   │
│   ├── core/                     # Core processing engine
│   │   ├── rss_parser.py         # RSS feed parsing
│   │   ├── modern_scraper.py     # Modern web scraping (JSON-LD, OpenGraph)
│   │   ├── fetcher.py            # Content fetching orchestration
│   │   ├── processor.py          # Content processing pipeline
│   │   └── source_manager.py     # Source configuration management
│   │
│   ├── database/                 # Database layer
│   │   ├── async_manager.py      # Async database operations
│   │   ├── sync_manager.py       # Sync database operations
│   │   └── models.py             # SQLAlchemy ORM models
│   │
│   ├── models/                   # Pydantic data models
│   ├── worker/                   # Background task processing (Celery)
│   ├── utils/                    # Utility functions
│   ├── cli/                      # Command-line interface
│   └── workflows/                # LangGraph agentic workflows
│
├── config/                       # Configuration files
│   ├── sources.yaml              # Source definitions
│   ├── models.yaml               # LLM model configurations
│   └── recommended_models.yaml   # Recommended model settings
│
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── api/                      # API tests
│
├── docker-compose.yml            # Full stack orchestration
├── Dockerfile                    # Application container
└── requirements.txt              # Python dependencies
```

## Networking

- **Single bridge network**: `cti_network`
- Services resolve by name: `postgres`, `redis`, `web`, etc.
- **Exposed ports**: 5432 (PostgreSQL), 6379 (Redis), 8001/8888 (web)
- **LM Studio** (optional): Runs on host at `http://host.docker.internal:1234/v1`

## Data Storage

### Named Volumes
- `postgres_data`: PostgreSQL database persistence
- `redis_data`: Redis persistence (appendonly + LRU eviction)
- `langflow_data`: LangFlow integration (service commented out)

### Bind Mounts
- **Web/Workers**: `./src`, `./config`, `./logs`, `./tests`, `./models`, `./outputs`, `./scripts`, `./allure-results`, `./test-results`
- **SIGMA rules**: `../Huntable-SIGMA-Rules` → `/app/sigma-repo`
- **Postgres init**: `./init-scripts` → `/docker-entrypoint-initdb.d` (with override)
- **CLI**: `./src`, `./config`, `./logs`, `./tests`, `./data`, `./backups`

## Resource Management

Environment variables control resource limits (with defaults):

| Service | Memory Limit | Memory Reservation | Additional |
|---------|--------------|-------------------|------------|
| postgres | 2G (configurable) | 512M | — |
| redis | 512M (configurable) | 128M | maxmemory: 512mb |
| web | 1G (configurable) | 256M | — |
| worker | 2G (configurable) | 512M | concurrency: 2 |
| workflow_worker | 2G (configurable) | 512M | concurrency: 2 |
| scheduler | 256M (fixed) | 64M | — |

## Health Checks

| Service | Health Check |
|---------|-------------|
| postgres | `pg_isready -U cti_user -d cti_scraper` |
| redis | `timeout 3 redis-cli ping \| grep -q PONG` |
| web | `curl -f http://localhost:8001/health` |
| worker | `celery -A src.worker.celery_app inspect ping` |
| workflow_worker | `celery -A src.worker.celery_app inspect ping` |
| scheduler | `python -c 'import sys; sys.exit(0)'` |

## Deployment Topology

### Development (Default)
- All services in docker-compose
- Volume mounts for hot-reload
- Debug logging enabled
- Test dependencies included

### Production (Dockerfile.prod)
- Multi-stage build
- Slimmer runtime (no Playwright/test deps)
- Production-optimized uvicorn settings
- Separate secrets management

## CLI Integration

The `./run_cli.sh` wrapper executes commands in the `cli` Docker service:

```bash
./run_cli.sh --help
./run_cli.sh init --config config/sources.yaml
./run_cli.sh collect --dry-run
```

The CLI shares the same PostgreSQL and Redis as the web application, ensuring consistency.

## Related Documentation

- [Workflow Data Flow](workflow-data-flow.md) - Detailed LangGraph workflow architecture
- [Scoring](scoring.md) - Quality scoring and ranking algorithms
- [Chunking](chunking.md) - Content chunking strategy for LLM context
- [QA Loops](qa-loops.md) - Quality assurance feedback loops

---

_Last verified: February 2025_
