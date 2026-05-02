# Technical Readout

High-level overview for engineers joining the project. For detailed setup
see [Installation](../getting-started/installation.md); for architecture
see [Overview](../architecture/overview.md); for Docker specifics see
[Docker Architecture](docker-architecture.md).

## Core Mission

- **Collect**: Gather threat intelligence articles from RSS feeds and web scraping
- **Process**: Clean, normalize, deduplicate, and quality-score content
- **Analyze**: Extract observables and generate Sigma detection rules via an agentic workflow
- **Present**: Web interface and REST API for threat intelligence consumption

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy (async + sync), Celery + Redis |
| Frontend | Jinja2, Tailwind CSS, vanilla JS, HTMX |
| Database | PostgreSQL 15 with pgvector extension |
| Orchestration | LangGraph (agentic workflow), Celery Beat (scheduling) |
| Infrastructure | Docker Compose, non-root containers |
| Embeddings | sentence-transformers (`all-mpnet-base-v2` for articles, `intfloat/e5-base-v2` for Sigma) |

## Data Flows

### Collection

```
Scheduler triggers source check
  -> RSS parser extracts article metadata
  -> Modern scraper (JSON-LD, OpenGraph) or CSS selector fallback
  -> Content processor: clean, normalize, deduplicate
  -> Quality scoring and metadata enrichment
  -> Store in PostgreSQL
```

### Agentic Workflow

```
Article trigger (API or UI)
  -> OS Detection (Windows gate)
  -> Junk Filter
  -> LLM Ranking (score threshold)
  -> Extract Agent (6 sequential sub-agents + aggregation)
  -> Sigma Generation (pySigma validation + retry)
  -> Similarity Search (pgvector)
  -> Promote to review queue
```

See [Pipelines](../concepts/pipelines.md) for the full execution order.

### Web Interface

```
User request -> FastAPI route -> async DB query -> Jinja2 template -> HTML
```

Boolean search, pagination, source filtering, and article detail views.

## Source Management

- **Primary**: Browser-based Source Config editor (scheduling, crawling
  policy, keyword filters, extraction selectors)
- **Bootstrap**: `config/sources.yaml` seeds the database on first run
- **Reconcile**: `./run_cli.sh sync-sources --config config/sources.yaml`
  overwrites DB sources with YAML (destructive to local edits; use
  `--no-remove` to preserve DB-only sources)

## Key References

| Topic | Document |
|-------|----------|
| Architecture and directory structure | [Overview](../architecture/overview.md) |
| Docker services, volumes, health checks | [Docker Architecture](docker-architecture.md) |
| CLI commands | [CLI Reference](../reference/cli.md) |
| Database schema | [Schemas](../reference/schemas.md) |
| Testing | [Testing](../development/testing.md) |
| Workflow execution | [Pipelines](../concepts/pipelines.md) |
| Agent responsibilities | [Agents](../concepts/agents.md) |

_Last updated: 2026-05-01_
