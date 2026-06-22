# QA Loops

Extraction, Sigma generation, and ranking each include validation retry loops
to catch bad output before it surfaces to users.

## Extraction QA

> **Note:** The regex + encoder + LLM-validator pipeline described here reflects
> an earlier architecture and is archived. Current extraction runs direct LLM
> sub-agents (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract,
> RegistryExtract, ServicesExtract, ScheduledTasksExtract). The per-extractor QA
> agent layer was removed in v7.0.0 (2026-05-12) and the remaining shared QA
> subsystem (`RankAgentQA`, `qa_max_retries`) was removed in v7.1.0
> (2026-05-22); extractor output now reaches aggregation directly. The steps
> below are retained for historical context only.

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

- **pySigma validation (deterministic -- no LLM)**: Every generated rule is
  validated by `validate_sigma_rule` (`src/services/sigma_validator.py`): a
  pySigma library parse plus structural/metadata checks.
  `sigma_extended_validator.py` adds a pySigma hard-fail gate and extended
  checks. No model is called here -- this is a pure-Python gate, so its verdict
  is reproducible.
- **Iterative repair (LLM)**: Up to 3 attempts per rule
  (`max_repair_attempts_per_rule`, default 3). On failure, `_repair_rules`
  (`src/services/sigma_generation_service.py`) injects the deterministic
  validation errors into the `sigma_repair_single` / `SigmaRepair` prompt
  (`{validation_errors}`, `{original_rule}`) and asks the model to fix the rule.
  Repair reuses the **SigmaAgent** model, provider, temperature, `top_p`, and
  seed, and the **same system prompt** as generation -- only the user prompt
  differs (`sigma_repair_single` instead of
  `sigma_generate_multi`/`sigma_generation`). There is no separate repair-model
  config; both phases funnel through `_call_provider_for_sigma`.
- **Similarity and coverage checks**: Generated rules are compared to SigmaHQ
  embeddings to prevent duplication and classify coverage.
- **Storage**: Attempt logs, validation errors, and final rules are stored in
  `agentic_workflow_executions.sigma_rules` for post-mortem review.

## Ranking QA

> **Deprecated (v7.1.0, 2026-05-22):** The `RankAgentQA` agent and the `qa_max_retries` config field were removed as part of the full QA agent subsystem removal. Ranking now proceeds directly to the threshold check without a QA validation step. The content below is retained for historical context only.

## Operational Safeguards

- The workflow trigger blocks concurrent executions per article. Stuck pending
  runs older than 5 minutes are marked failed before a retry is allowed.
- Health endpoints (`/health`, `/api/health/*`) surface ingestion and service
  readiness so QA runs against a healthy stack.

_Last updated: 2026-06-22_
