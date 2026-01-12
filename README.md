# Huntable CTI Studio

## ** SECURITY WARNING **
!! DO NOT DEPLOY IN HOSTILE NETWORK!!
This app is a suite of utilities for processing open source intel. It is for reasearch learning and automation purposes. Code is NOT SECURE, and is not intended to be used in production!!
##

**CTIScraper v5.0.0 "Ganymede"** -  A Cyber Threat Intelligence ML/AI workbench that automates collection, extraction, and detection rule generation from 33+ OSINT sources.

## Purpose

Aggregates cybersecurity threat intelligence from RSS feeds and web scraping; uses regex and AI to score relevance and extract observables; generates SIGMA detection rules, and prevents duplicates through semantic cosign similarity matching against 3,000+ community rules.

## Approach

### Architecture
- **7 microservices**: PostgreSQL (pgvector), Redis, FastAPI web app, Celery workers, scheduler
- **19 database tables**: Articles with embeddings, Sigma rules, workflow executions, chat logs
- **Multi-model AI**: OpenAI GPT-4, Anthropic Claude, LMStudio (local models)

### Agentic Workflow (6 Steps)
1. **Junk Filter** — Conservative content filtering
2. **LLM Rank** — Relevance scoring (0-10)
3. **Extract Agent** — Extract observables (command-line, registry, process trees, event IDs)
4. **Generate SIGMA** — Create detection rules with iterative validation
5. **Similarity Search** — Compare against 3,000+ SigmaHQ rules using 4-segment weighted embeddings
6. **Promote to Queue** — Queue for human review and PR submission

### Key Features
- **Content Collection**: RSS parsing, web scraping, SimHash near-duplicate detection
- **AI Analysis**: LLM threat scoring, IOC extraction, automated SIGMA generation
- **RAG Chat**: Semantic search with pgvector across article database
- **Agentic Workflow Engine**: LangGraph-based pipeline with checkpointing and retry logic. Native and LangFuse trace support.

## Quick Start

# Requirements: Docker + Docker Compose, .env with POSTGRES_PASSWORD
./start.sh

# Access
# Web UI: http://localhost:8001
# API Docs: http://localhost:8001/docs
# Health: curl http://localhost:8001/health


The documentation has been reorganized under `/docs` and is published with MkDocs Material.

- **Quickstart**: `docs/quickstart.md` (Docker-first run, ingest → workflow → Sigma → pytest)
- **Docs site**: `mkdocs serve` to preview locally; navigation mirrors `/docs` (concepts, how-tos, reference, internals).
- **UI**: http://localhost:8001 (OpenAPI at `/docs`; LangGraph debug port on `:2024` when that service is enabled)
- **Stack**: FastAPI + PostgreSQL/pgvector + Redis + Celery + optional LangGraph server; start with `./start.sh`.

For full details, begin at `docs/index.md`.
