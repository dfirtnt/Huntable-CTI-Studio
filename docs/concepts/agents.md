# Agents and Responsibilities

The agentic workflow is a multi-step pipeline **orchestrated by LangGraph** and **triggered via Celery tasks** when you call `POST /api/workflow/articles/{id}/trigger` or click **Send to Workflow** on an article. LangGraph manages step sequencing, conditional branching (e.g. early termination on non-Windows OS), and state propagation; Celery is the task queue that schedules and distributes the work. Each agent focuses on a narrow task and writes its results to `agentic_workflow_executions`.

## Core agents (execution order)

0. **OS Detection**: Classifies target OS using CTI-BERT embeddings and keyword matching. Non-Windows articles are terminated early.
1. **Junk filter**: Removes non-huntable content before spending tokens on ranking and extraction.
2. **LLM ranking**: Scores article quality (1–10) and gates the rest of the workflow.
3. **Extract Agent supervisor**: Orchestrates sub-agents and merges their observables into `extraction_result`.
4. **Sigma generator**: Builds Sigma rules from extracted content (prefers aggregated observables) and validates with pySigma.
5. **Similarity matcher**: Compares generated rules against SigmaHQ using behavioral novelty (deterministic or legacy); embeddings used for candidate retrieval.
6. **Promote to Queue**: Queues novel SIGMA rules for human review based on similarity threshold.

## Extract Agent sub-agents

- **CmdlineExtract**: Command-line observables with arguments and QA corrections. Optional **Attention Preprocessor** surfaces LOLBAS-aligned snippets earlier in the LLM prompt; toggle in Workflow Config (Cmdline Extract agent). See [Cmdline Attention Preprocessor](../features/cmdline-preprocessor.md).
- **HuntQueriesExtract**: Detection queries (EDR queries and SIGMA rules) extracted from content.
- **ProcTreeExtract**: Parent/child process lineage.
- **RegistryExtract**: Windows registry artifacts (persistence keys, config changes, defense evasion). Split-hive output (`registry_hive` + `registry_key_path`) for Sigma `registry_event` compatibility.

Each sub-agent returns `items` and `count`; the supervisor aggregates them into `observables`, `discrete_huntables_count`, and a `content` string that Sigma consumes.

## Prompt architecture

### Where prompts live

Prompts have three layers. When they disagree, the higher layer wins.

1. **DB `agent_prompts`** (authoritative at runtime) -- stored in the workflow config in PostgreSQL. This is what the model actually sees.
2. **Seed files in `src/prompts/`** -- loaded into the DB on first bootstrap, empty-fallback, or explicit reset. Not read at runtime once the DB has a value.
3. **Extractor Contract** (human reference) -- canonical design docs that define each agent's extraction rules, boundary agreements, and schema. Not loaded into LLM context. Used for disaster recovery and onboarding.

### Prompt fields

Each agent's prompt config is a JSON object with these fields:

| Field | Purpose | Required? |
|-------|---------|-----------|
| `role` (or `system`) | Persona -- who the agent is. Identity and expertise only, not task instructions. | Yes (runtime raises ValueError if missing for RankAgent; falls back to a generic default for extractors) |
| `task` (or `objective`) | What the agent does this run -- a verb-level statement. | Recommended (falls back to "Extract information.") |
| `instructions` | How to do it -- rules, constraints, negative scope, output format, JSON enforcement. | Recommended (falls back to "Output valid JSON.") |
| `json_example` | A concrete JSON example showing the exact output schema including all fields. | Recommended |
| `output_format` | Prose description of the schema (legacy fallback if `json_example` is absent). | Optional |

**Role is a persona, not instructions.** It should read like a job title and expertise statement ("You extract Windows command-line observables from threat intelligence articles. You are a LITERAL TEXT EXTRACTOR."). Model-specific directives (`/no_think`), task instructions ("Do NOT reason"), and output formatting rules belong in `instructions`, not `role`.

### What the runtime adds (hardcoded, not in the prompt editor)

The code in `llm_service.py` assembles the final prompt from the fields above plus several hardcoded components that the prompt editor UI does not show:

- **User message scaffold**: The `Title:` / `URL:` / `Content:` headers and the article body are assembled in code, not authored in presets. The `instructions` field is injected as a footer.
- **Traceability block** (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, RegistryExtract only): forces every extracted item to include `source_evidence`, `extraction_justification`, and `confidence_score`. Appended after the user message regardless of what the prompt config says.
- **System fallback**: if no `role` or `system` is set, extractors default to "You are a detection engineer." RankAgent raises an error instead.
- **QA feedback prepend**: on retry after QA failure, the QA agent's feedback is prepended to the user message.
- **Content truncation**: article content is truncated to fit the model's context window. A `[Content truncated to fit context window]` marker is injected.
- **System-to-user rewrite**: for Mistral/Mixtral models, the system message is folded into the user message because those models do not support a system role.

The prompt editor UI shows only the `role`, `task`, `instructions`, and schema fields. To see the full prompt that actually hit the model, check the Langfuse trace for that execution.

### Traceability fields

Four fields are required on every extracted item for the extract sub-agents listed above. They serve the QA agent (factuality checks) and the evaluation pipeline:

- **`value`**: the extracted artifact itself (primary content).
- **`source_evidence`**: verbatim excerpt from the article that contains or supports the artifact.
- **`extraction_justification`**: one sentence explaining why this artifact was extracted.
- **`confidence_score`**: float 0.0--1.0 indicating extraction confidence.

These are enforced by a hardcoded append in the runtime. Prompt authors should include them in `json_example` so the model's schema instructions are consistent with the appended block.

## Execution surfaces

- **API**: `POST /api/workflow/articles/{article_id}/trigger` triggers the workflow via Celery.
- **UI**: Article page → **Send to Workflow**. The Workflow page surfaces executions and per-step statuses; article pages render extraction results and Sigma output when present.

## Operational guardrails (from legacy agent SOP)

- Run inside Docker (web/worker/scheduler) and avoid destructive DB actions (`drop`, volume removal) outside managed scripts.
- Keep source-of-truth config in `config/sources.yaml` and PostgreSQL; preserve `.env` secrets and do not bypass authentication.
- Use existing directories for scripts (`scripts/`), temp utilities (`utils/temp/`), and generated outputs (`outputs/`).
- Prefer API/CLI entry points (`./run_cli.sh`, workflow triggers) over ad-hoc code paths to keep telemetry and audits consistent.
