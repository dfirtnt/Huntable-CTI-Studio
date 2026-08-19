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

### Purpose beyond gap-filling: the architecture A/B

Scoring generated rules against expected rules is not only a regression gate. The
primary intended use is an **architecture comparison**: does the multi-extractor
pipeline (focused subagents feeding observable-driven Sigma generation) actually
produce better detections than a **one-shot** baseline (the generator reading the
raw article with no extractor scaffolding)?

- The **one-shot arm** already exists in the pipeline: disable all extractors, and
  `generate_sigma` hits the `full_content_fallback` group
  (`_build_sigma_full_content_fallback_group`, `agentic_workflow.py`) — full
  article content in, zero observables. Same generator, same content; the only
  toggled variable is observable augmentation.
- Both arms are scored against the **same** ground truth. That makes ground-truth
  provenance the whole ballgame: if the GT is shaped like one arm's output, the
  benchmark is rigged toward that arm.

This reframing changes the authoring rules below. In particular it **supersedes**
the old "bootstrap from a vetted generation run" shortcut: bootstrapping GT from
the multi-extractor arm's output biases the comparison toward that arm (its
observables are exactly what drive its Sigma expansion — circular). Bootstrapping
from generation output is acceptable *only* for a pure regression gate on a single
fixed pipeline, never for the A/B.

### Ground-truth authoring protocol

Ground truth must be **arm-blind** (sourced from neither pipeline) and
**complete** (dense enough that a valid detection isn't scored as a false
positive). The current 3 seed entries are flagged (`_note`) as Phase 1 seeds
pending this protocol; treat them as a *draft to check against*, not authority.

**1. Arm-blindness.** Author each article's expected rules from the *article
itself*, before looking at any pipeline output. You may consult either arm's
generated rules afterward **only** as a miss-check ("did I overlook an obvious
behavior?"), never as a source of atoms. Do not derive Sigma GT from extractor
`expected_items` or from a generation run.

**2. Completeness standard.** For each article, enumerate every behavior a
competent detection engineer would turn into a rule — the bar is a behavior that
is (a) attacker-controlled, (b) observable in a named telemetry class, and
(c) reasonably low false-positive as a detection. Represent each such behavior
exactly once in the atom union. Not "every observable in the article"
(over-broad, punishes precision on both arms); not "only the headline IOCs"
(sparse GT punishes the higher-recall arm on precision — the documented
`sparse GT masks precision` failure).

GT spans **all telemetry classes the article supports**, including classes no
extractor covers. Verified wiring: grouped generation passes the *full* article
content to every group (`article_content=content_to_use`) and the prompt permits
rules with `observables_used: []` — the arms differ in observable augmentation
and in *output filtering*, not input. The multi-extractor arm's
logsource-containment filter (`_rule_logsource_matches_group`) drops rules
outside its groups' classes, so uncovered-class GT entries measure that
suppression cost honestly. Report metrics **per canonical class** so
covered-turf gains and suppression losses stay attributable: if one-shot wins
only via uncovered classes, the remedy is a supplementary full-content group,
not removing extractors.

**2b. Respect shared generation doctrine.** The prompts both arms share define
what a correct rule may contain — e.g. the "Network Observable Abstraction"
doctrine (`src/prompts/sigma_generation.txt`) forbids atomic IOCs (bare
domains, IPs, full User-Agent strings) in selections. GT must not expect atoms
that doctrine forbids: they are unattainable for both arms by design, and every
such atom is a guaranteed recall miss that drowns real signal.

**3. Atom format — write Sigma YAML the normalizer can decompose.** Author
`logsource` + `detection` fragments in normal Sigma style; the scorer folds
case, wildcards, backslash direction, and taxonomy aliases on both sides, so do
**not** pre-normalize. Constraints for clean decomposition:

- **Logsource must resolve to a canonical class.** Use resolvable pairs like
  `{category: process_creation, product: windows}`. An unresolved logsource
  still contributes atoms but is counted as `logsource_unresolved` and produces
  no class-level signal.
- **Pick discriminators, not whole command lines.** Model each behavior as the
  process image plus a distinguishing fragment: `Image|endswith: \rundll32.exe`
  **and** `CommandLine|contains: .jpg,init` — not the full literal command line
  as one `CommandLine|contains`. Whole-string atoms are brittle and match
  nothing the other arm produces.
- **Use `|contains|all` for multi-substring AND** when a single fragment is too
  weak: `CommandLine|contains|all: [SecurityCenter2, AntiVirusProduct]`.
- **Keep detection blocks simple** — `selection` maps + a `condition`. Avoid
  Sigma features the extractor rejects (aggregations, temporal/near, or wildcard
  expansions large enough to trip the deterministic expansion limit); such rules
  decompose to `None` and count as `expected_undecomposable` (a GT authoring
  bug).
- **Use taxonomy field names** that alias cleanly: `Image`, `ParentImage`,
  `CommandLine`, `TargetFilename`, `Image`/`OriginalFileName`, registry
  `TargetObject`, network `DestinationHostname`, etc.

**4. Validate every entry decomposes.** After authoring, confirm each expected
rule yields ≥1 positive atom and a resolved canonical class, and that the file
still parses. The pinned test is
`tests/unit/test_sigma_ground_truth_files.py`; run it, plus a quick self-score
(decompose `expected_rules` and assert `expected_undecomposable == 0`).

### Corpus selection (as you scale past the seed set)

The seed corpus is **3 articles, all `windows.process_creation`** — too small and
too mono-logsource to support an architecture conclusion. When expanding:

- **Size:** grow well past 3 (target ≥15–20 detection-rich articles) so the A/B
  delta survives article-to-article and run-to-run variance.
- **Logsource diversity, covered-class-dominant:** pick articles whose detection
  surface is dominated by the five extractor-covered classes (process_creation,
  registry, service_creation, scheduled_task, network_connection) — that is
  where extraction can show *gains*. GT authored on those articles still spans
  every class the article supports (see the completeness standard above);
  uncovered-class behaviors that appear are priced as suppression cost, not
  excluded.
- **Keep, don't replace, the existing articles.** They are real, hygiene-fixed
  CTI; re-scraping eval articles is out of scope. Add to them.

### Reporting for the A/B

- Report **precision and recall separately** per arm, not just combined F1 — the
  arms differ systematically in atom volume (the multi-extractor arm expands →
  more atoms → higher recall / lower precision), and a blended score hides *why*
  one wins.
- Consider **fuzzy atom overlap** (via `sigma_similarity`) rather than exact-set
  intersection if the exact-match strictness penalizes an arm for expressing the
  same detection with a differently-normalized atom.

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
  table (count, logsource P/R, atom P/R, and combined-F1 badges), a config-version
  filter and baseline/candidate comparison panel, and a ModalManager detail modal
  (matched / missed / extra atoms and logsources). Calls
  `/sigma-eval-articles`, `/run-sigma-eval`, `/sigma-eval-results`.
- Linked from the MLOps landing page (`src/web/templates/mlops.html`, card M-04).
- New API: `GET /api/evaluations/sigma-eval-articles` (lists fixture articles).
- Static verification: `tests/unit/test_sigma_evals_page.py` (template compiles,
  route registered, DOM hooks + endpoint calls present, ASCII, ModalManager use).

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
