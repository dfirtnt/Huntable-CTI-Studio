# QA Loops

Quality controls are built into both extraction and Sigma generation to keep outputs actionable.

## Extraction QA (Hybrid Cmdline pipeline)
Based on the extraction pipeline spec (archived):
1. **Regex candidate extractor**: High-recall regexes capture command-line shapes (executables with args, powershell, System32 utilities).
2. **Encoder classifier**: Filters candidates using embedding similarity against VALID/INVALID exemplars (e.g., Microsoft/CTI-BERT or `all-mpnet-baseMiniLM-L6-v2`). Keeps only likely Windows commands.
3. **Optional LLM QA validator**: Lightweight model (Qwen2.5-Coder-7B or Llama-3.1-8B) re-checks borderline strings and flags invalid items. Output never expands the list—only prunes.
4. **Supervisor merge**: Aggregates sub-agent items, produces `discrete_huntables_count`, and emits a newline-joined `content` string used by Sigma.

## Sigma QA
From [Sigma Detection Rules](../features/sigma-rules.md):
- **pySigma validation**: Every generated rule is validated; syntax and required fields are enforced.
- **Iterative retries**: Up to 3 attempts with validator feedback injected into the next prompt when a rule fails validation.
- **Similarity/coverage checks**: Generated rules are compared to SigmaHQ embeddings to prevent duplication and classify coverage.
- **Storage**: Attempt logs, validation errors, and final rules are stored in `agentic_workflow_executions.sigma_rules` for post-mortem review.

## Ranking QA

The ranking step includes a QA retry loop. After `LLMService.rank_article()` produces a score, the QA agent validates the ranking for consistency and compliance. If the QA check fails, the ranking is retried up to `qa_max_retries` times (configurable in `agentic_workflow_configs`).

**QA Prompt**: `QAAgentBase` (with ranking-specific context)
**Max Retries**: Configurable via workflow config (`qa_max_retries`)
**Failure Behavior**: Falls back to the last valid score or terminates with `rank_below_threshold`

## Operational safeguards
- Workflow trigger blocks concurrent executions per article; stuck pending runs older than 5 minutes are marked failed before allowing a retry.
- Health endpoints (`/health`, `/api/health/*`) surface ingestion and service readiness so QA runs against a healthy stack.
<!--stackedit_data:
eyJoaXN0b3J5IjpbLTkwNjQwNTA0Nl19
-->