# Huntable CTI Studio

**Turn threat intelligence into Sigma detections—faster.**

CTI reports bury actionable signals in prose; manual extraction is slow and error-prone. Huntable CTI Studio automates observable aton igma rule generation with transparent, tunable AI—so detection engineers can focus on hunting, not parsing.

## Who is this for?

| Role | What you get |
|------|--------------|
| **Detection Engineers** | Auto-gerte Sm CTI articles, validated with pySigma and de-duplicated against SigmaHQ |
| **Threat Hunters** | Extracted command-lines, process trees, and hunt queries ready for triage |
| **SOC Analysts** | Curated, scored intelligence feed with RAG-powered search |

## Highlights

- **Multi-source aggregation** RSS feeds, direct scrape endpoints, and browser extensionTur threat intelligence inputs feed the pipeline
- **Agentic workflow** OS detection → junk filter → LLM ranking → Extract Agent (command-line, process tree, hunt queries) → Sigma generation → similarity search → Promote to Queue
- **Detection support** PySigma validation, SigmaHQ similarity matching, coverage classification with embeddings
- **Storage & services** — FastAPI web app, PostgreSQL + pgvector, Redis, Celery worker/scheduler
- **Chat & search** RAG-powered search across collected intelligence, observable-aware annotations

## Quick start

```bash
git clone https://github.com/starlord/CTIScraper.git && cd CTIScraper
cp .env.example .env && echo "POSTGRES_PASSWORD=change_me" >> .env
./start.sh
```

Health ceck: `curl http://localhost:8001/health` · Web UI: e th

## Where to go next

**I want to…**

- **Run it now** → [Quickstart](quickstart.md) — ingest an article, run the workflow, see Sigma rules in 5 minutes
- **Understand the concepts** → [Huntables](concepts/huntables.md) | [Agents](concepts/agents.md) | [Pipelines](concepts/pipelines.md)
- **Operate it** → [Add feeds](howto/add_feed.md) | [Extract oeres]bles.md) | [Generate Sigma](howto/generate_sigma.md)
- **Extend or integrate** → [API Reference](reference/api.md) | [CLI Reference](reference/cli.md) | [Architecture](icfceaim   erne(reference/. nternals/arcture.md)
- **Deploy to production** → [Getting Started](deployment/GETTING_STARTED.md) | [Docker Architecture](deployment/DOCKER_ARCHITECTURE.md)

---

*s malives o and enerwith s tal o eeto eie oca.*
<!--stackedit_data:
eyJoaXN0b3J5IjpbMTQzNzM4MjA3MF19
-->