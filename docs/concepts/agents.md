# Agents and Responsibilities

The agentic workflow is a 7-step pipeline **orchestrated by LangGraph** and **triggered via Celery tasks**chain of specialized workers executed by Celery when you hittrigger `/api/workflow/articles/{id}/trigger` or click **Send to Workflow** on an article. LangGraph manages step sequencing, conditional branching (e.g. early termination on non-Windows OS), and state propagation; Celery is the task queue that schedules and distributes the work. Each agent focuses on a narrow task and writes its results to `agentic_workflow_executions`.

## Core agents
- **OS Detection**: Classifies target OS using CTI-BERT embeddings and keyword matching. Non-Windows articles are terminated early.Each agent focuses on a narrow task and writes its results to `agentic_workflow_executions`.

## Core agents
- **Junk filter**: Removes non-huntable content before spending tokens on ranking and extraction.
- **LLM ranking**: Scores article quality (0–10) and gates the rest of the workflow.
- **Extract Agent supervisor**: Orchestrates sub-agents and merges their observables into `extraction_result`.
- **Sigma generator**: Builds Sigma rules from extracted content (prefers aggregated observables) and validates with pySigma.
- **Similarity matcher**: Compares generated rules against SigmaHQ embeddings to avoid duplicates and classify coverage.
- **Promote to Queue**: Queues novel SIGMA rules for human review based on similarity threshold.

## Extract Agent sub-agents
- **CmdlineExtract**: Command-line observables with arguments and QA corrections. Optional **Attention Preprocessor** surfaces LOLBAS-aligned snippets earlier in the LLM prompt; toggle in Workflow Config (Cmdline Extract agent). See [Cmdline Attention Preprocessor](../features/CMDLINE_ATTENTION_PREPROCESSOR.md).
- **HuntQueriesExtract**: Detection queries (EDR queries and SIGMA rules) extracted from content.
- **ProcTreeExtract**: Parent/child process lineage.

Each sub-agent returns `items` and `count`; the supervisor aggregates them into `observables`, `discrete_huntables_count`, and a `content` string that Sigma consumes.

## Execution surfaces
- **API**: `POST /api/workflow/articles/{article_id}/trigger` triggers the workflow via Celery.
- **UI**: Article page → **Send to Workflow**. The Workflow page surfaces executions and per-step statuses; article pages render extraction results and Sigma output when present.

## Operational guardrails (from legacy agent SOP)
- Run inside Docker (web/worker/scheduler) and avoid destructive DB actions (`drop`, volume removal) outside managed scripts.
- Keep source-of-truth config in `config/sources.yaml` and PostgreSQL; preserve `.env` secrets and do not bypass authentication.
- Use existing directories for scripts (`scripts/`), temp utilities (`utils/temp/`), and generated outputs (`outputs/`).
- Prefer API/CLI entry points (`./run_cli.sh`, workflow triggers) over ad-hoc code paths to keep telemetry and audits consistent.
<!--stackedit_data:
eyJoaXN0b3J5IjpbMTY2MDQ0NDI0N119
-->