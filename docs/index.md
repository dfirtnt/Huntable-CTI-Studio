# Huntable CTI Studio

**Turn threat intelligence into Sigma detections—faster.**

CTI reports bury actionable signals in prose; manual extraction is slow and error-prone. Huntable CTI Studio automates observable extraction and Sigma rule generation with transparent, tunable AI—so detection engineers can focus on hunting, not parsing.

## Who is this for?

| Role | What you get |
|------|--------------|
| **Detection Engineers** | Auto-generated Sigma rules from CTI articles, validated with pySigma and de-duplicated against SigmaHQ |
| **Threat Hunters** | Extracted command-lines, process trees, and hunt queries ready for triage |
| **SOC Analysts** | Curated, scored intelligence feed with RAG-powered search |

## Highlights

- **Multi-source aggregation** — RSS feeds, direct scrape endpoints, and browser extension. Multiple threat intelligence inputs feed the pipeline
- **Agentic workflows** — OS detection → junk filter → LLM ranking → Extract Agent (command-lines, process trees, hunt queries) → Sigma generation → similarity search → Promote to Queue
- **Detection support** — PySigma validation, SigmaHQ similarity matching, coverage classification with embeddings
- **Storage & services** — FastAPI web app, PostgreSQL + pgvector, Redis, Celery worker/scheduler
- **Chat & search** — RAG-powered search across collected intelligence, observable-aware annotations

## Quick Start

```bash
git clone https://github.com/dfirtnt/Huntable-CTI-Studio.git
cd Huntable-CTI-Studio
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD
./start.sh
```

**Health check**: `curl http://localhost:8001/health`
**Web UI**: http://localhost:8001

## Where to Go Next

**I want to…**

- **Run it now** → [Quickstart](quickstart.md) — ingest an article, run the workflow, see Sigma rules in 5 minutes
- **Understand the concepts** → [Huntables](concepts/huntables.md) | [Agents](concepts/agents.md) | [Pipelines](concepts/pipelines.md) | [Observables](concepts/observables.md)
- **Configure and operate** → [Installation](getting-started/installation.md) | [Configuration](getting-started/configuration.md) | [First Workflow](getting-started/first-workflow.md)
- **Add feeds and extract data** → [Add a Feed](guides/add-feed.md) | [Extract Observables](guides/extract-observables.md) | [Generate Sigma Rules](guides/generate-sigma.md)
- **Understand the architecture** → [Architecture Overview](architecture/overview.md) | [Workflow Data Flow](architecture/workflow-data-flow.md) | [Scoring](architecture/scoring.md)
- **Extend or integrate** → [API Reference](reference/api.md) | [CLI Reference](reference/cli.md) | [Schemas](reference/schemas.md)
- **Develop and contribute** → [Development Setup](development/setup.md) | [Testing](development/testing.md) | [Contributing](CONTRIBUTING.md)

## Features

### Sigma Detection Rules
Automatically generate Sigma detection rules from CTI content. See [Sigma Detection Rules](features/sigma-rules.md) for details.

### Content Filtering
ML-based classification to filter low-quality content. See [Content Filtering](features/content-filtering.md).

### OS Detection
Multi-tier detection to identify Windows/Linux/macOS content. See [OS Detection](features/os-detection.md).

### RAG Search
Semantic search across your CTI corpus using embeddings. See [RAG Search](features/rag-search.md).

## LLM Support

Huntable CTI Studio works with multiple LLM providers:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude 3)
- Google (Gemini)
- LM Studio (local models)

See [Model Selection Guide](llm/model-selection.md) for recommendations.

## Getting Help

- **Documentation**: You're reading it! Navigate using the sidebar
- **Issues**: [GitHub Issues](https://github.com/dfirtnt/Huntable-CTI-Studio/issues)
- **Contributing**: See [Contributing Guide](CONTRIBUTING.md)

---

_Automate observables extraction and Sigma rule generation with transparent, tunable AI._
