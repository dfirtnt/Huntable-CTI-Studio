# Agents and Responsibilities

The agentic workflow is a chain of specialized workers executed by Celery when you trigger `/api/workflow/articles/{id}/trigger` or click **Send to Workflow** on an article. Each agent focuses on a narrow task and writes its results to `agentic_workflow_executions`.

## Core agents
- **Junk filter**: Removes non-huntable content before spending tokens on ranking and extraction.
- **LLM ranking**: Scores article quality (0–10) and gates the rest of the workflow.
- **Extract Agent supervisor**: Orchestrates sub-agents and merges their observables into `extraction_result`.
- **Sigma generator**: Builds Sigma rules from extracted content (prefers aggregated observables) and validates with pySigma.
- **Similarity matcher**: Compares generated rules against SigmaHQ embeddings to avoid duplicates and classify coverage.

## Extract Agent sub-agents
- **CmdlineExtract**: Command-line observables with arguments and QA corrections.
- **SigExtract**: Sigma-like query fragments extracted directly from content.
- **EventCodeExtract**: Windows Event IDs and log channel hints.
- **ProcTreeExtract**: Parent/child process lineage.
- **RegExtract**: Registry keys and persistence artifacts.

Each sub-agent returns `items` and `count`; the supervisor aggregates them into `observables`, `discrete_huntables_count`, and a `content` string that Sigma consumes.

## Execution surfaces
- **API**: `POST /api/workflow/articles/{article_id}/trigger?use_langgraph_server=false` (fast path). Set `use_langgraph_server=true` to route through the LangGraph server on `:2024` for traceable debugging.
- **UI**: Article page → **Send to Workflow**. The Workflow page surfaces executions and per-step statuses; article pages render extraction results and Sigma output when present.

## Operational guardrails (from legacy agent SOP)
- Run inside Docker (web/worker/scheduler) and avoid destructive DB actions (`drop`, volume removal) outside managed scripts.
- Keep source-of-truth config in `config/sources.yaml` and PostgreSQL; preserve `.env` secrets and do not bypass authentication.
- Use existing directories for scripts (`scripts/`), temp utilities (`utils/temp/`), and generated outputs (`outputs/`).
- Prefer API/CLI entry points (`./run_cli.sh`, workflow triggers) over ad-hoc code paths to keep telemetry and audits consistent.
