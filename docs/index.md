# Huntable CTI Studio

Huntable CTI Studio (CTIScraper) collects threat intelligence, extracts huntable observables, and turns them into Sigma detections. This documentation is the source of truth for running, operating, and extending the system. All pages live in `/docs` and are rendered with MkDocs Material (`mkdocs serve` to preview locally).

## What you can do
- Stand up the full stack with Docker Compose and the `./start.sh` wrapper
- Scrape or upload CTI articles and send them through the agentic workflow
- Review extracted observables ("huntables"), chunk analyses, and generated Sigma rules
- Operate via the web UI at `http://localhost:8001` or the REST API

## Highlights
- **Multi-source aggregation**: RSS feeds, direct scrape endpoints, and browser extension inputs feed the pipeline.
- **Agentic workflow**: OS detection (Windows-only) → junk filter → LLM ranking → Extract Agent (command-line, registry, process tree, event IDs, Sigma query patterns) → Sigma generation → similarity search → queue.
- **Storage & services**: FastAPI web app, PostgreSQL + pgvector, Redis, Celery worker/scheduler.
- **Detection support**: PySigma validation, SigmaHQ similarity matching, and coverage classification with embeddings.
- **Chat & search**: RAG-powered search across collected intelligence, plus observable-aware annotations.

## Running the stack
- Requirements: Docker + Docker Compose plugin, `.env` populated with `POSTGRES_PASSWORD` and optional LLM keys.
- Start: `./start.sh` builds and launches the compose stack (web on `8001`, aux on `8888`).
- Health: `curl http://localhost:8001/health` or open `http://localhost:8001/docs` for the live OpenAPI schema.

## Where to go next
- **Quickstart**: End-to-end ingest → extract huntables → Sigma → pytest (`quickstart.md`).
- **Concepts**: Huntables, agents, pipelines, and observables (`concepts/*`).
- **How-to**: Run locally, add feeds, trigger extraction, generate Sigma, and evaluate models (`howto/*`).
- **Reference**: API endpoints, config, schemas, Sigma prompt, and versioning details (`reference/*`).
- **Internals**: Architecture diagrams, scoring logic, chunking pipeline, and QA loops (`internals/*`).
