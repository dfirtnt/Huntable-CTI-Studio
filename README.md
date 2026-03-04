# Huntable CTI Studio
<img width="952" height="64" alt="image" src="https://github.com/user-attachments/assets/4b29bc70-b518-4559-af0c-caf23b86000d" />


## ** SECURITY WARNING **
!! DO NOT DEPLOY IN HOSTILE NETWORK!!
This app is a suite of utilities for processing open source intel. It is for research, learning, and automation purposes. Code is NOT SECURE, and is not intended to be used in production!!
##

**Huntable CTI Studio v5.0.0 "Callisto"** -  A Cyber Threat Intelligence ML/AI workbench that automates collection, extraction, and detection rule generation from 33+ OSINT sources.

## Purpose

Aggregates cybersecurity threat intelligence from RSS feeds and web scraping; uses regex and AI to score relevance and extract observables; generates SIGMA detection rules, and prevents duplicates through jaccard similarity matching against 3,000+ community rules. More details here: https://dfirtnt.wordpress.com/2026/02/04/introducing-huntable-cti-studio/ 

## Approach

### Architecture
- **6 services**: PostgreSQL (pgvector), Redis, FastAPI web app, Celery workers (default + workflow), scheduler
- **LangGraph**: Orchestrates the 7-step agentic workflow (state machine, conditional branching, checkpointing)
- **28 database tables**: Articles with embeddings, Sigma rules, workflow executions, chat logs, eval presets, model versions, and more
- **Multi-model AI**: OpenAI GPT-4, Anthropic Claude, LMStudio (local models)

### Agentic Workflow (7 Steps)

<img width="1021" height="455" alt="image" src="https://github.com/user-attachments/assets/f00d6796-026d-4540-b6c5-ad25d73779cd" />


The main engine is a LangGraph-based agentic workflow (#4-6 in diagram above) executed by Celery workers:
1. **OS Detection** — Windows-only routing (non-Windows articles terminate)
2. **Junk Filter** — Conservative content filtering
3. **LLM Rank** — Relevance scoring (0-10)
4. **Extract Agent** — Extract observables (command-line, registry, process trees, event IDs)
5. **Generate SIGMA** — Create detection rules with iterative validation
6. **Similarity Search** — Compare against 3,000+ SigmaHQ rules using behavioral novelty assessment
7. **Promote to Queue** — Queue for human review and PR submission

### Key Features
- **Content Collection**: RSS parsing, web scraping, SimHash near-duplicate detection
- **AI Analysis**: LLM threat scoring, obserbavles extraction (with confidence score), automated Sigma generation, interactive Sigma rule enrichment.
- **RAG Chat**: Chat with your CTI articles - semantic search with pgvector across article database
- **Agentic Workflow Engine**: LangGraph-based pipeline with checkpointing and retry logic. Native and LangFuse trace support.

## Quick Start

**Requirements:** Docker + Docker Compose

```bash
git clone https://github.com/dfirtnt/Huntable-CTI-Studio.git
cd Huntable-CTI-Studio
cp .env.example .env   # start.sh creates .env from .env.example if missing
# Edit .env and set POSTGRES_PASSWORD=your_secure_password
./start.sh
```

**Access:**
- Web UI: http://localhost:8001
- API Docs: http://localhost:8001/docs
- Docs site: http://localhost:8000 (MkDocs; started by start.sh)
- Health: `curl http://localhost:8001/health`
- CLI: `./run_cli.sh <command>` (e.g. `./run_cli.sh init`, `./run_cli.sh sigma sync`)


The documentation is organized under `/docs` and is published with MkDocs Material.

- **Quickstart**: `docs/quickstart.md` (Docker-first run, ingest → workflow → Sigma → pytest)
- **Docs site**: http://localhost:8000 (`mkdocs serve`; started by start.sh); navigation mirrors `/docs` (concepts, how-tos, reference, internals).
- **UI**: http://localhost:8001 (OpenAPI at `/docs`; LangFuse traces for workflow debugging when configured)
- **Stack**: FastAPI + PostgreSQL/pgvector + Redis + Celery + LangGraph; start with `./start.sh` (it also builds docs and starts the MkDocs server in the background when `mkdocs.yml` is present).

For full details, begin at `docs/index.md`.

## License

MIT License — see [LICENSE](LICENSE) for details.
