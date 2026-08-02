# Workflow Threshold Tuning

The agentic workflow's `Thresholds` config block (`src/config/workflow_config_schema.py`,
`ThresholdConfig`) holds three gating values plus one sibling not covered here
(`JunkFilterThreshold`, see [content filter docs](architecture/scoring.md)):

| Threshold | Default | Range | Gates |
|---|---|---|---|
| `MinHuntScore` | 97.0 | 0-100 | Not currently enforced — see [below](#minhuntscore-970-not-currently-enforced) |
| `RankingThreshold` | 6.0 | 0-10 | Whether the workflow continues past the LLM RankAgent step |
| `SimilarityThreshold` | 0.5 | 0.0-1.0 | Whether a generated SIGMA rule is queued or dropped as a near-duplicate |

All three live in `AgenticWorkflowConfigTable` (`src/database/models.py:555-557`),
are read at runtime from `state["config"]` inside `src/workflows/agentic_workflow.py`,
and can be changed via `PUT /api/workflow/config` (`src/web/routes/workflow_config.py:353`)
or the workflow config UI.

## `RankingThreshold` (6.0)

Gates whether the workflow continues past the ranking step. The LLM RankAgent
scores an article's relevance 0-10; if `ranking_score < RankingThreshold`, the
workflow terminates with `TERMINATION_REASON_RANK_THRESHOLD` and never reaches
extraction or SIGMA generation.

Code: `src/workflows/agentic_workflow.py:1847-1848`
(`should_continue = ranking_score >= ranking_threshold`).

**Raising it** makes the workflow pickier — fewer articles reach extraction,
reducing LLM spend but risking false negatives on borderline-relevant articles.
**Lowering it** lets more articles through extraction at the cost of running
the (expensive) extraction agents on lower-relevance content.

## `SimilarityThreshold` (0.5)

Gates SIGMA rule novelty/deduplication in two places, both in
`src/workflows/agentic_workflow.py`:

1. **Context filtering** (~line 3148): when assessing novelty against existing
   rules, only candidates with `similarity >= SimilarityThreshold` are kept as
   "similar rules" context (top 10).
2. **Queue-promotion gate** (~line 3299-3356): after generation, if a rule's
   `max_similarity >= SimilarityThreshold` against existing rules, it is treated
   as a near-duplicate and **dropped** (not queued for human review). Below the
   threshold — or when the comparator is inconclusive — the rule is queued.

**Raising it** (toward 1.0) requires rules to be nearly identical to existing
ones before they're suppressed, so more near-duplicate rules reach the review
queue (more reviewer noise, fewer missed novel rules). **Lowering it** suppresses
more aggressively, risking silently dropping a genuinely novel rule that happens
to share atoms with an existing one.

## `MinHuntScore` (97.0) — not currently enforced

`MinHuntScore` is stored, exposed via the config API and MCP resources, and
threaded through `AgenticWorkflowConfigTable` and multiple response payloads —
but as of this writing, **no code path in the agentic workflow reads it as a
comparison gate**. Searching for every consumer of `config.min_hunt_score` /
`MinHuntScore` turns up only pass-through reads (API responses, MCP resource
listings, eval-bundle config snapshots) — never an `if hunt_score < config.min_hunt_score`
check that terminates or filters anything.

The value that actually gates whether an ingested article auto-triggers the
agentic workflow is a **different, separate field**:
`AgenticWorkflowConfigTable.auto_trigger_hunt_score_threshold`
(`src/services/workflow_trigger_service.py:89-97`), editable via its own
endpoint (`PATCH /api/workflow/config/auto-trigger-threshold`). An article
auto-triggers only when its keyword hunt score is strictly **above** this
threshold.

Its default is **100.0**, which sits above the 99.9 hunt-score ceiling — so **by
default nothing auto-processes**; auto-triggering is opt-in and only happens once
a user consciously lowers the threshold. This default is set consistently across
the DB model (`src/database/models.py` column default), the two create-default
paths (`workflow_config.py` and `workflow_trigger_service.py:50`), and every
fallback in `workflow_config.py`; the runtime value is read from `AppSettingsTable`
(seeded from the column default on first access). See
[`docs/architecture/scoring.md`](architecture/scoring.md) for the scoring formula
and the 99.9 ceiling.

Independently, several services accept their own `min_hunt_score` filter
parameter with their own local defaults, unrelated to the workflow config value:
`src/services/rag_service.py` (semantic search filter, default `None`),
`src/services/chunk_analysis_backfill.py` (backfill eligibility, default 50.0),
`src/web/routes/ml_hunt_comparison.py` (default 50.0). None of these read
`ThresholdConfig.MinHuntScore`.

**If you're trying to gate workflow triggering by hunt score**, tune
`auto_trigger_hunt_score_threshold`, not `MinHuntScore`. **If you're trying to
gate something else with `MinHuntScore`**, note that changing it today only
changes the number displayed in the UI/API — it has no runtime effect until a
gate is added that reads it.

## How to re-evaluate after a change

Threshold changes to `RankingThreshold` or `SimilarityThreshold` affect how many
articles/rules survive the pipeline, so validate against the eval corpus before
relying on a new value:

1. Change the threshold via `PUT /api/workflow/config` (or the workflow config UI).
2. Run the extraction agents against the canonical eval set from the
   `/mlops/agent-evals` page (or the underlying `EvalBundleService` /
   subagent-eval-aggregate API) — see [Agent Evals](features/agent-evals.md)
   for how to read the results (MAE, badges, node coloring).
3. Compare MAE and per-article deltas against the previous config version;
   the eval UI keeps prior versions for side-by-side comparison.
4. Do not edit the eval fixtures (`config/eval_articles.yaml`,
   `config/eval_articles_data/`) to make a threshold change look better —
   fixtures are ground truth and are changed only through the dedicated
   eval-fixture-audit process, never to chase a threshold-tuning result.

_Last updated: 2026-07-16_
