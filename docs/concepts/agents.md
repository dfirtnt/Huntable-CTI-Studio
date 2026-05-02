# Agents and Responsibilities

The agentic workflow is a multi-step pipeline orchestrated by LangGraph and
triggered via Celery when you call `POST /api/workflow/articles/{id}/trigger`
or click **Reprocess** on an article. LangGraph manages step sequencing,
conditional early-exit gates, and state propagation. Celery is the task queue
that schedules and distributes the work. Each agent writes results to
`agentic_workflow_executions`.

## Core Agents (Execution Order)

0. **OS Detection**: Classifies target OS using `ibm-research/CTI-BERT`
   embeddings and keyword matching. Non-Windows articles exit early.
1. **Junk filter**: Removes non-huntable content before spending tokens on
   ranking and extraction.
2. **LLM ranking**: Scores article quality (1-10) and gates the rest of the
   workflow.
3. **Extract Agent**: Runs sub-agents in parallel and merges their observables
   into `extraction_result`.
4. **Sigma generator**: Builds Sigma rules from extracted observables and
   validates with pySigma.
5. **Similarity matcher**: Compares generated rules against SigmaHQ using
   behavioral novelty scoring; embeddings used for candidate retrieval.
6. **Promote to queue**: Queues Sigma rules with low similarity scores for
   human review.

## Extract Agent Sub-Agents

- **CmdlineExtract**: Command-line observables with arguments and QA
  corrections. The optional **Attention Preprocessor** surfaces LOLBAS-aligned
  snippets earlier in the LLM prompt; toggle in Workflow Config under
  Cmdline Extract. See [Cmdline Attention Preprocessor](../features/cmdline-preprocessor.md).
- **HuntQueriesExtract**: Detection queries (EDR queries and Sigma rules)
  extracted from content.
- **ProcTreeExtract**: Parent/child process lineage.
- **RegistryExtract**: Windows registry artifacts (persistence keys, config
  changes, defense evasion). Split-hive output (`registry_hive` +
  `registry_key_path`) for Sigma `registry_event` compatibility.
- **ScheduledTasksExtract**: Windows scheduled task artifacts (task name,
  action, trigger, run-as user).
- **ServicesExtract**: Windows service artifacts (service name, binary path,
  command line, start type).

Each sub-agent returns `items` and `count`. The Extract Agent merges results
into `observables`, `discrete_huntables_count`, and a `content` string that
Sigma generation consumes.

Disable individual sub-agents under **Workflow Config > Extract Agent Settings
> Disabled Agents**.

## Prompt Architecture

### Where Prompts Live

Prompts have three layers. When they disagree, the higher layer wins.

1. **DB `agent_prompts`** (authoritative at runtime): stored in the workflow
   config in PostgreSQL. This is what the model actually sees.
2. **Seed files in `src/prompts/`**: loaded into the DB on first bootstrap,
   empty-fallback, or explicit reset. Not read at runtime once the DB has a
   value.
3. **Extractor Contract** (human reference): canonical design docs defining
   each agent's extraction rules, boundary agreements, and schema. Not loaded
   into LLM context. Used for disaster recovery and onboarding.

### Prompt Fields

Each agent's prompt config is a JSON object with these fields:

| Field | Purpose | Required? |
|---|---|---|
| `role` (or `system`) | Persona -- who the agent is. Identity and expertise only, not task instructions. | Yes (RankAgent raises `ValueError` if missing; extractors fall back to a generic default) |
| `task` (or `objective`) | What the agent does this run -- a verb-level statement. | Recommended (falls back to "Extract information.") |
| `instructions` | Rules, constraints, negative scope, output format, JSON enforcement. | Recommended (falls back to "Output valid JSON.") |
| `json_example` | Concrete JSON showing the exact output schema including all fields. | Recommended |
| `output_format` | Prose schema description (legacy fallback if `json_example` is absent). | Optional |

**Role is a persona, not instructions.** It should read like a job title and
expertise statement. Model-specific directives (`/no_think`), task instructions,
and output formatting rules belong in `instructions`.

### What the Runtime Adds

[`src/services/llm_service.py`](../../src/services/llm_service.py) assembles
the final prompt from the fields above plus several hardcoded components the
prompt editor UI does not expose:

- **User message scaffold**: `Title:` / `URL:` / `Content:` headers and the
  article body are assembled in code. The `instructions` field is injected as
  a footer.
- **Traceability block** (all six extract sub-agents): forces every extracted
  item to carry `value`, `source_evidence`, `extraction_justification`, and
  `confidence_score`. Appended after the user message regardless of the prompt
  config.
- **System fallback**: if no `role` or `system` is set, extractors default to
  "You are a detection engineer." RankAgent raises an error instead.
- **QA feedback prepend**: on retry after QA failure, the QA agent's feedback
  is prepended to the user message.
- **Content truncation**: article content is truncated to fit the model's
  context window. A `[Content truncated to fit context window]` marker is
  injected.
- **System-to-user rewrite**: for Mistral/Mixtral models, the system message
  is folded into the user message (those models do not support a system role).

To see the full assembled prompt for any execution, check its Langfuse trace.

### Traceability Fields

All six extract sub-agents require these fields on every extracted item. They
feed the QA agent and the evaluation pipeline:

- **`value`**: the extracted artifact itself.
- **`source_evidence`**: verbatim excerpt from the article supporting the artifact.
- **`extraction_justification`**: one sentence explaining why this artifact was extracted.
- **`confidence_score`**: float 0.0-1.0 indicating extraction confidence.

Include these fields in `json_example` so the model's schema instructions stay
consistent with the appended traceability block.

## Execution Surfaces

- **API**: `POST /api/workflow/articles/{article_id}/trigger` triggers the
  workflow via Celery.
- **UI**: Article page > **Reprocess**. The Workflow page surfaces executions
  and per-step statuses; article pages render extraction results and Sigma
  output when present.

## Status Vocabulary

Two "status" fields appear in the UI and API -- they are not the same thing.

### Workflow Execution Status (`agentic_workflow_executions.status`)

Per-article workflow run state, surfaced on the Workflow page and article pages:

| Value | Meaning |
|---|---|
| `pending` | Queued, not yet picked up by a worker |
| `running` | A worker has started executing the LangGraph pipeline |
| `completed` | All steps finished (including early termination for non-Windows OS) |
| `failed` | An unrecoverable error occurred in one of the agents |

A `pending` execution older than the stale cutoff is re-triggerable. See
[`src/services/workflow_trigger_service.py`](../../src/services/workflow_trigger_service.py).

### Agent Evaluation Badges (Agent Evals Page)

On `/agent-evals`, the comparison table shows per-row badges:

| Badge | Meaning |
|---|---|
| `exact` | Prediction matches ground truth exactly |
| `mismatch` | Prediction differs from ground truth |
| `pending` | Evaluation has not yet produced a verdict |
| `warning` | Prediction is close but outside the strict-match threshold |

The live dot (`eval-status-dot--live`) on the header indicates an evaluation
run is currently streaming results.

## Operational Guardrails

- Run inside Docker (web/worker/scheduler). Avoid destructive DB actions
  (`drop`, volume removal) outside managed scripts.
- Keep source-of-truth config in `config/sources.yaml` and PostgreSQL.
  Preserve `.env` secrets and do not bypass authentication.
- Use `scripts/` for scripts, `utils/temp/` for temp utilities, and `outputs/`
  for generated outputs.
- Prefer API/CLI entry points (`./run_cli.sh`, workflow triggers) over ad-hoc
  code paths to keep telemetry consistent.

_Last updated: 2026-05-01_
