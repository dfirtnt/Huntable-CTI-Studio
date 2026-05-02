# QA Loops

Extraction, Sigma generation, and ranking each include validation retry loops
to catch bad output before it surfaces to users.

## Extraction QA

> **Note:** The regex + encoder + LLM-validator pipeline described here reflects
> an earlier architecture and is archived. Current extraction runs direct LLM
> sub-agents (CmdlineExtract, ProcTreeExtract, etc.) with QA handled per-agent.
> The steps below are retained for historical context.

Historical pipeline steps:

1. **Regex candidate extractor**: High-recall regexes capture command-line
   shapes (executables with arguments, PowerShell invocations, System32 utilities).
2. **Encoder classifier**: Filters candidates using embedding similarity against
   VALID/INVALID exemplars (`ibm-research/CTI-BERT` or `all-MiniLM-L6-v2`).
   Retains only likely Windows commands.
3. **LLM QA validator**: Lightweight model (Qwen2.5-Coder-7B or Llama-3.1-8B)
   re-checks borderline strings and flags invalid items. Output only prunes --
   never expands the candidate list.
4. **Aggregation**: Sub-agent items are merged; `discrete_huntables_count` is
   produced and a newline-joined `content` string is passed to Sigma generation.

## Sigma QA

From [Sigma Detection Rules](../features/sigma-rules.md):

- **pySigma validation**: Every generated rule is validated; syntax and required
  fields are enforced.
- **Iterative retries**: Up to 3 attempts, with validator feedback injected into
  the next prompt when a rule fails.
- **Similarity and coverage checks**: Generated rules are compared to SigmaHQ
  embeddings to prevent duplication and classify coverage.
- **Storage**: Attempt logs, validation errors, and final rules are stored in
  `agentic_workflow_executions.sigma_rules` for post-mortem review.

## Ranking QA

After `LLMService.rank_article()` produces a score, the QA agent validates it
for consistency and compliance. If validation fails, the ranking retries up to
`qa_max_retries` times.

| Setting | Location | Default |
|---|---|---|
| `qa_max_retries` | `agentic_workflow_config` table / Workflow Config UI | 5 |

**QA agent**: `RankAgentQA`
**Failure behavior**: Falls back to the last valid score or terminates with
`rank_below_threshold`.

## Operational Safeguards

- The workflow trigger blocks concurrent executions per article. Stuck pending
  runs older than 5 minutes are marked failed before a retry is allowed.
- Health endpoints (`/health`, `/api/health/*`) surface ingestion and service
  readiness so QA runs against a healthy stack.

_Last updated: 2026-05-01_
