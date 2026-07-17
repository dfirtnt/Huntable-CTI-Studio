# End-to-End Sigma Rule Eval System

Status: **Phases 1-3 landed** (scorer + fixtures + persistence + full-pipeline
workflow wiring + run/results APIs + standalone MLOps UI). The UI has since
been exercised live in production (e.g. commit `1a8e2903`, 2026-06-16, fixed a
perpetual-PENDING-row bug found via `/mlops/sigma-evals`) and gained a
combined-F1 headline metric and a config-version comparison panel not
described below (see `src/web/templates/sigma_evals.html`).

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
- `config/eval_articles_data/sigma/articles.json` -- Sigma eval's own
  self-contained article content snapshot (added 2026-06-18, commit
  `80efcc07`). Content is copied verbatim from the cmdline extractor snapshot
  at authoring time, but the fixture no longer depends on its ground-truth
  URLs incidentally overlapping another subagent's snapshot; `expected_count`
  mirrors `ground_truth.json`'s `expected_rule_count`. Seeded to the DB via
  `seed_eval_articles` (globs `*/articles.json`), same as the extractor
  fixtures.

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

### Phase 3 -- UI (DONE; since exercised live and extended)

- Standalone page `src/web/templates/sigma_evals.html` at route
  `/mlops/sigma-evals` (`src/web/routes/pages.py`). A standalone page was chosen
  over threading into the 3622-line `agent_evals.html` to avoid risking that
  central template -- especially since the environment had no Docker stack at
  authoring time for the contract-required browser verification.
- Built on the documented UI components (`.card` / `.card-elevated`, theme
  tokens, `modal-manager.js`, `window.showNotification`, inline SVG icons, locked
  font scale) rather than copying the bespoke `eval-*` CSS.
- Surfaces: a Run panel (fixture article checkboxes + throttle + Run), a results
  table (count, logsource P/R, atom P/R badges), and a ModalManager detail modal
  (matched / missed / extra atoms and logsources). Calls
  `/sigma-eval-articles`, `/run-sigma-eval`, `/sigma-eval-results`.
- Linked from the MLOps landing page (`src/web/templates/mlops.html`, card M-04).
- New API: `GET /api/evaluations/sigma-eval-articles` (lists fixture articles).
- Static verification: `tests/unit/test_sigma_evals_page.py` (template compiles,
  route registered, DOM hooks + endpoint calls present, ASCII, ModalManager use).

<!-- TODO: verify and document: since this Phase 3 landed, the UI gained a
combined-F1 headline metric (harmonic mean of logsource F1 and atom F1) and
a config-version comparison panel (`configVersionSelect`, `compareVersionA`
/ `compareVersionB`) not described in this section -- see
`src/web/templates/sigma_evals.html` and commits `29dc9a61`, `6fbea9b5`,
`2d3449fe`, `e645b090` (2026-06-17). -->

- A `has_error`-completion reconciliation gap (executions that finished
  `ainvoke()` with an error in state but no raised exception stranded their
  `SigmaEvaluation` row in `pending` forever) was found via live use of
  `/mlops/sigma-evals` and fixed in `1a8e2903` (2026-06-16).

**Operator step (since completed):** live browser verification on the Docker
stack -- the `1a8e2903` bug (found by an operator observing a stuck PENDING
row on the live `/mlops/sigma-evals` page) is direct evidence this happened
after the note above was written.

### Future -- bundle/diagnosis reuse

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
  `_update_single_eval_record` (line ~966) as the wiring template.
- `src/services/sigma_novelty_service.py` -- canonical_class resolution.
- `docs/features/agent-evals.md` -- the existing extractor eval surface to mirror.
