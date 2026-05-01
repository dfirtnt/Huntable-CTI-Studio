# Huntable CTI Studio

**Reports to Rules… in record time.**

Huntable CTI Studio is an AI-assisted workbench for detection engineers and threat hunters. It ingests open-source threat intelligence from RSS feeds and web scraping, extracts Windows observables — command lines, process trees, event IDs, registry keys, services, scheduled tasks, and hunt queries — and turns them into Sigma rules you can validate, review, and ship.

No black box required: every article moves through an explicit LangGraph pipeline, execution state is checkpointed in PostgreSQL, configuration is versioned through presets, and novelty is enforced by similarity search against 3,000+ community Sigma rules. Bring your own model — OpenAI, Anthropic, or local LM Studio.

## Who Is This For?

| Role | What you get |
|------|--------------|
| **Detection Engineers** | Auto-generated Sigma rules from CTI articles, validated and de-duplicated against SigmaHQ |
| **Threat Hunters** | Extracted command-lines, process trees, and hunt queries ready for triage |
| **SOC Analysts** | Curated, scored intelligence feed with RAG-powered search |
| **Contributors and agents** | A Docker-first stack with explicit workflow, config, and persistence contracts |

## Highlights

- **Multi-source aggregation** — 38 seeded OSINT sources via RSS, direct scraping, and a browser extension; LLM-powered source auto-healing repairs broken feeds.
- **Agentic workflow** — LangGraph pipeline: OS detection → junk filter → relevance ranking → observable extraction → Sigma generation → similarity check → queue promotion, with conditional early-exit gates and Postgres checkpointing.
- **Detection engineering tools** — Iterative Sigma validation, behavioral similarity against 3,000+ community rules, and coverage classification.
- **Multi-model AI** — Mix and match OpenAI, Anthropic, and local LM Studio per workflow step; configuration is versioned through presets.
- **Semantic search & MCP** — pgvector-backed search across collected intelligence; a read-only Model Context Protocol server (`python3 run_mcp.py`) exposes nine tools for conversational retrieval ([tool reference](reference/mcp-tools.md)).
- **Storage & services** — FastAPI web app, PostgreSQL + pgvector, Redis, and Celery workers/scheduler.

## Quick Start

```bash
git clone https://github.com/dfirtnt/Huntable-CTI-Studio.git
cd Huntable-CTI-Studio
./setup.sh --no-backups
./start.sh
```

If prompted, you can run the MkDocs docs server in the background; logs go to `logs/mkdocs.log`.

**Health check**: `curl http://localhost:8001/health`  
**Web UI**: http://localhost:8001

## Where To Go Next

**I want to…**

- **Run it now** → [Quickstart](quickstart.md)
- **Understand the workflow** → [Agents](concepts/agents.md) | [Workflow Data Flow](architecture/workflow-data-flow.md)
- **Understand the architecture** → [Architecture Overview](architecture/overview.md) | [Scoring](architecture/scoring.md)
- **Configure workflow models and prompts** → [Configuration](getting-started/configuration.md) | [Schemas](reference/schemas.md)
- **Develop or debug the app** → [Agent Orientation](development/agent-orientation.md) | [Development Setup](development/setup.md) | [Testing](development/testing.md) | [UI Test Tiers](development/ui-test-tiers.md)
- **Integrate with the API** → [API Reference](reference/api.md) | [CLI Reference](reference/cli.md) | [MCP tools](reference/mcp-tools.md)

## Features

### Sigma Detection Rules

Automatically generate Sigma detection rules from CTI content. See [Sigma Detection Rules](features/sigma-rules.md).

### Content Filtering

ML-based classification to filter low-quality content. See [Content Filtering](features/content-filtering.md).

### OS Detection

Multi-tier detection to identify Windows/Linux/macOS content. See [OS Detection](features/os-detection.md).

### RAG Search

Semantic search across your CTI corpus using embeddings. See [RAG Search](features/rag-search.md).

### Source Auto-Healing

LLM-powered diagnostics automatically repair failing sources. Deep probes inspect RSS content, sitemaps, WP JSON APIs, and JS-rendering behavior before proposing config fixes. See [Source Healing Architecture](internals/source-healing.md).

### Model Versioning And Rollback

Train, evaluate, and roll back the content-filtering model through the MLOps control center. Every training run is versioned with metrics (accuracy, precision, recall, F1); rollback restores a prior artifact and re-scores all chunks in the background. See [Content Filtering](features/content-filtering.md).

## LLM Support

Huntable CTI Studio works with multiple LLM providers:

- OpenAI
- Anthropic
- LM Studio

See [Local Model Selection Guide](llm/model-selection.md) for recommendations.

## Getting Help

- **Documentation**: Navigate using the docs sidebar
- **Contributing**: See [Contributing Guide](CONTRIBUTING.md)
- **Issues**: [GitHub Issues](https://github.com/dfirtnt/Huntable-CTI-Studio/issues)
