# End-to-End Sigma Rule Eval System

Status: **Phases 1-2 landed** (scorer + fixtures + persistence + full-pipeline
workflow wiring + run/results APIs). Phase 3 (UI) planned.

## Why

The extraction subagents are evaluated end-to-end (`SubagentEvaluationTable`,
Eval1 count + Eval2 item-level precision/recall). The Sigma generation step that
sits downstream -- `generate_sigma` in `src/workflows/agentic_workflow.py`,
backed by `SigmaGenerationService` -- is linted and novelty-scored, but nothing
checks the generated rules against an *expected* set of rules. This system fills
that gap: given a fixture article, does the pipeline produce the Sigma rules we
expect?

## Design decisions (confirmed)

- **Ground truth = detection atoms + logsource**, scored as precision/recall
  (not full golden YAML, not count-only, not LLM-judge). Robust to YAML
  cosmetics and prompt drift; reuses existing deterministic decomposition.
- **Scope = full pipeline from article** (extract -> generate_sigma), evaluating
  the final rules. True end-to-end signal.
- **Integration = extend the existing eval framework** (new eval target
  alongside the six subagents; reuse the `/mlops/agent-evals` surface).

## How scoring works

Both expected and actual rules are decomposed through the **same** extractor,
`src/services/sigma_atom_precompute.py::extract_atom_fields` (wrapping the
`sigma_similarity` workspace package). For any rule dict with `logsource` +
`detection` it returns:

- `canonical_class` -- e.g. `windows.process_creation`
- `positive_atoms` -- normalized `field|modifier|value` identities, e.g.
  `process.image|endswith|/rundll32.exe`, with case/wildcard/backslash folding
  and taxonomy field aliasing already applied
- `negative_atoms`, `surface_score`

Because both sides run through identical normalization, only a genuine
difference in detection logic moves the score. Aggregation is set-based across
all of an article's rules (union of canonical classes, union of atoms), which
sidesteps the rule-to-rule alignment problem. Two precision/recall headlines
result:

- **logsource**: did we produce rules about the right telemetry classes?
- **atoms**: did the detections contain the right fields and values?

Plus a count layer (expected vs actual rule count) and decomposition-health
counters (undecomposable rules, unresolved logsources).

Scorer: `src/services/sigma_eval_scorer.py` -> `score_sigma(expected_rules,
actual_rules, expected_rule_count=None) -> SigmaEvalResult`.

## Fixtures

- `config/eval_articles_data/sigma/ground_truth.json` -- per-article expected
  rules (`logsource` + `detection` fragments). See that directory's `README.md`
  for the schema.
- Article content is reused from the extractor `articles.json` snapshots (URLs
  must overlap), so no new article fetching is needed.

### Authoring strategy

1. Hand-author a small high-quality set to prove the scorer and anchor expected
   detections (current seeds).
2. Bootstrap the rest from a *vetted* generation run (decompose known-good
   output, then hand-correct) rather than writing every detection from scratch.

The current seed entries are flagged (`_note`) as Phase 1 seeds pending
security-analyst vetting.

## Phased rollout

### Phase 1 -- scorer + fixtures + tests (DONE)

- `src/services/sigma_eval_scorer.py`
- `config/eval_articles_data/sigma/{ground_truth.json,README.md}`
- `tests/services/test_sigma_eval_scorer.py`,
  `tests/unit/test_sigma_ground_truth_files.py`

Runnable standalone against any list of generated rules; no schema/UI/workflow
changes, so zero risk to the running pipeline.

### Phase 2 -- persistence + workflow wiring (DONE)

- `SigmaEvaluationTable` in `src/database/models.py` (mirrors
  `SubagentEvaluationTable`): article_url/id, workflow_execution_id,
  workflow_config_id+version, status; count fields; `logsource_precision/recall`,
  `atom_precision/recall`; JSONB `expected_rules`, `actual_rules`,
  `matched/missed/extra_atoms`, `matched/missed/extra_logsources`, decomposition
  health counters. A separate table (rather than overloading
  `SubagentEvaluationTable`, whose columns are count/item-centric) keeps each
  contract clean. Auto-created by `Base.metadata.create_all`; standalone migration
  `scripts/migrate_sigma_evaluation_table.py` for existing DBs.
- `src/services/sigma_eval_service.py`: `load_sigma_ground_truth()`,
  `build_eval_values()` (pure scorer-to-columns mapping),
  `score_and_persist_execution()`, `mark_pending_sigma_evals_as_failed()`.
- Workflow wiring in `src/workflows/agentic_workflow.py`:
  - A dedicated `sigma_eval` config flag overrides the blanket
    `eval_run -> skip-sigma` router so the full pipeline reaches `generate_sigma`.
  - `promote_to_queue_node` skips queue promotion for sigma eval runs (rules are
    scored, never pushed to the production review queue).
  - `score_and_persist_execution()` is called at execution completion (next to
    `_update_subagent_eval_on_completion`); `mark_pending_sigma_evals_as_failed()`
    runs on terminal failure.
- APIs in `src/web/routes/evaluation_api.py`: `POST /api/evaluations/run-sigma-eval`
  (creates executions with the sigma-eval snapshot + pending rows, triggers
  workflows) and `GET /api/evaluations/sigma-eval-results`.
- Tests: `tests/services/test_sigma_eval_service.py` (loader + build_eval_values
  + column contract).

### Phase 3 -- UI + bundle/diagnosis reuse

- Add a Sigma section/column to `/mlops/agent-evals` with count + P/R badges and
  a cell-click modal showing matched/missed/extra atoms, lint failures, and the
  generated YAML.
- Extend eval-bundle export and AI diagnosis to cover Sigma evals.

## Possible future refinements

- Rule-aligned scoring (match generated rules to expected rules first, then
  score atoms per pair) if the flat-set signal proves too coarse.
- Promote negative (filter) atoms into the headline metrics.
- Score validity/lint pass-rate as a first-class metric using
  `SigmaGenerationService` metadata.

## Key references

- `src/services/sigma_generation_service.py` -- rule output contract
  (`rules`: list of `{title, logsource, detection, ...}`).
- `src/workflows/agentic_workflow.py` -- `generate_sigma` node; eval routing and
  `_update_single_eval_record` (line ~428) as the wiring template.
- `src/services/sigma_novelty_service.py` -- canonical_class resolution.
- `docs/features/agent-evals.md` -- the existing extractor eval surface to mirror.
