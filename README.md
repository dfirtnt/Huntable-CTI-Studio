# Huntable CTI Studio
<img width="952" height="64" alt="image" src="https://github.com/user-attachments/assets/4b29bc70-b518-4559-af0c-caf23b86000d" />


## ** SECURITY WARNING **
!! DO NOT DEPLOY IN HOSTILE NETWORK!!
This app is a suite of utilities for processing open source intel. It is for research, learning, and automation purposes. Code is NOT SECURE, and is not intended to be used in production!! The app is also not intended to support classified or proprietary threat intelligence at this time.
##

**Huntable CTI Studio v6.1.0 "Io"** - A Cyber Threat Intelligence ML/AI workbench that automates collection, extraction, and detection rule generation from 38 seeded OSINT sources (see `config/sources.yaml`; runtime may add or replace rows after DB sync).

## Purpose

Aggregates cybersecurity threat intelligence from RSS feeds and web scraping; uses regex and AI to score relevance and extract observables; generates SIGMA detection rules, and prevents duplicates through jaccard similarity matching against 3,000+ community rules. More details here: https://dfirtnt.wordpress.com/2026/02/04/introducing-huntable-cti-studio/

## Architecture

- **6 services**: PostgreSQL (pgvector), Redis, FastAPI web app, Celery workers (default + workflow), scheduler
- **LangGraph**: Orchestrates the 7-step agentic workflow as a linear pipeline with conditional early-exit gates (state machine, checkpointing)
- **Database-backed workflows**: Articles, workflow executions, Sigma rules, presets, settings, evals, and supporting metadata
- **Source auto-healing**: LLM-powered diagnostics (RSS inspection, sitemap discovery, JS-rendering detection, WP JSON API probing) automatically repair failing sources
- **Multi-model AI**: OpenAI, Anthropic, LM Studio

## Agentic Workflow

The main engine is a LangGraph-based workflow executed by Celery workers:

1. **OS Detection** — Windows-only routing (non-Windows articles terminate)
2. **Junk Filter** — Conservative content filtering
3. **LLM Rank** — Relevance scoring
4. **Extract Agent** — Extract observables (command-line, process trees, event IDs, hunt queries)
5. **Generate SIGMA** — Create detection rules with iterative validation
6. **Similarity Search** — Compare against indexed Sigma rules using behavioral similarity
7. **Promote to Queue** — Queue novel rules for human review and PR submission

## Quick Start

**Requirements:** Docker + Docker Compose

```bash
git clone https://github.com/dfirtnt/Huntable-CTI-Studio.git
cd Huntable-CTI-Studio
./setup.sh --no-backups
./start.sh
```

**Access:**

- Web UI: http://localhost:8001
- API Docs: http://localhost:8001/docs
- Docs site: http://localhost:8000
- Health: `curl http://localhost:8001/health`
- CLI: `./run_cli.sh <command>`

### MCP (optional)

Read-only MCP server for agents (articles, sources, SIGMA, workflow tools). Requires app env/DB as for the web app.

**Tool reference:** [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md) (nine tools; `get_article` uses **Article ID** from search output, not list position).

```bash
python3 run_mcp.py
# or: python3 -m src.huntable_mcp
```

## For Coding Agents And Contributors

If you need to get oriented quickly, read these first:

1. [`AGENTS.md`](AGENTS.md)
2. [`docs/development/agent-orientation.md`](docs/development/agent-orientation.md)
3. [`docs/architecture/workflow-data-flow.md`](docs/architecture/workflow-data-flow.md)
4. [`docs/development/testing.md`](docs/development/testing.md)
5. [`config/presets/AgentConfigs/README.md`](config/presets/AgentConfigs/README.md)

Runtime entry points worth opening early:

- [`src/web/modern_main.py`](src/web/modern_main.py)
- [`src/web/routes/__init__.py`](src/web/routes/__init__.py)
- [`src/workflows/agentic_workflow.py`](src/workflows/agentic_workflow.py)
- [`src/worker/celery_app.py`](src/worker/celery_app.py)
- [`src/config/workflow_config_schema.py`](src/config/workflow_config_schema.py)
- [`run_tests.py`](run_tests.py)

## Documentation

The documentation is organized under `/docs` and is published with MkDocs Material.

- **Start here**: `docs/index.md`
- **Quickstart**: `docs/quickstart.md`
- **Architecture**: `docs/architecture/overview.md`, `docs/architecture/workflow-data-flow.md`
- **Development**: `docs/development/setup.md`, `docs/development/testing.md`
- **Reference**: `docs/reference/api.md`, `docs/reference/schemas.md`, `docs/reference/mcp-tools.md`

## License

MIT License — see [LICENSE](LICENSE) for details.
