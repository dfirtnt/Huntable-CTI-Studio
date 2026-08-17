---
title: Sigma eval ground truth must be arm-blind, not borrowed from the extractors
date: 2026-08-16
category: docs/solutions/best-practices
module: sigma-eval-system
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - Authoring or expanding Sigma eval ground truth (config/eval_articles_data/sigma/ground_truth.json)
  - Comparing the multi-extractor pipeline against a one-shot baseline
  - Tempted to reuse extractor Eval1/Eval2 fixtures or a generation run to seed Sigma GT
tags: [sigma-eval, ground-truth, evaluation, architecture-ab, one-shot, atom-scoring]
related_components: [sigma_generation_service, agentic_workflow, sigma_eval_scorer]
---

# Sigma eval ground truth must be arm-blind, not borrowed from the extractors

## Context

The Sigma eval currently ships **3 seed ground-truth articles**, all self-flagged
`SEED fixture (Phase 1) ... Requires security-analyst vetting before being treated
as authoritative`. The natural cost-saving instinct is to borrow the ground-truth
work already done for the extractor evals (Eval1 counts + Eval2 `expected_items`),
since all 3 Sigma articles also appear in the `cmdline`/`process_lineage` corpora,
or to bootstrap GT by decomposing a known-good generation run.

The key realization: the Sigma eval is **not just another per-extractor
regression gate**. Its intended purpose is an **architecture A/B** — does the
multi-extractor pipeline (focused subagents feeding observable-driven Sigma
generation) actually beat a **one-shot** baseline (the generator reading the raw
article with no extractor scaffolding)? That purpose changes what "good ground
truth" means, and it makes the borrow actively harmful.

## Guidance

**Do not source Sigma eval ground truth from either pipeline arm.** Specifically:

1. **Arm-blind authoring.** Author each article's `expected_rules` from the
   *article itself*, before looking at any pipeline output. Consult either arm's
   generated rules only afterward as a *miss-check* ("did I overlook an obvious
   behavior?"), never as a source of atoms. Do **not** derive Sigma GT from
   extractor `expected_items`, and do **not** bootstrap it by decomposing a
   generation run (that shortcut is acceptable only for a pure regression gate on
   a single fixed pipeline, never for the A/B).

2. **Keep the existing articles; grow and diversify the corpus.** Don't drop the
   3 articles — they're real, hygiene-fixed CTI, and re-scraping eval articles is
   out of scope (auto memory [claude]: eval articles/fixtures are not re-scraped
   or mutated without approval). But 3 is too few for an architecture conclusion,
   and all 3 resolve to `windows.process_creation` only. Expand to ≥15–20 and
   deliberately span logsource classes (registry, network, file, image_load,
   scheduled_task, script/powershell).

3. **Author atoms as discriminators, not whole command lines.** Model each
   behavior as the process image plus a distinguishing fragment
   (`Image|endswith: \rundll32.exe` **and** `CommandLine|contains: .jpg,init`),
   use `|contains|all` for multi-substring ANDs, keep detection blocks simple so
   they decompose, and let the scorer's normalizer fold case/wildcards/backslash.

4. **Report precision and recall separately, consider fuzzy atom overlap.** The
   arms differ systematically in atom volume (the multi-extractor arm expands →
   more atoms → higher recall / lower precision), so a blended F1 hides *why* one
   wins, and exact-match atom identity rewards whichever arm phrases atoms like
   the GT.

The full repeatable protocol lives in
[`docs/development/sigma-eval-system.md`](../../development/sigma-eval-system.md)
under "Ground-truth authoring protocol".

## Why This Matters

Both arms are scored against the **same** ground truth, so GT provenance is the
whole ballgame. If GT is shaped like one arm's output, the benchmark measures
"which arm resembles the GT," not "which architecture produces better
detections." Two mechanisms make this concrete:

- **Circular contamination on recall.** The extractor observables are exactly
  what drive the multi-extractor arm's Sigma *expansion*. GT built from those
  observables contains precisely the atoms that arm was built to surface, while
  the one-shot arm never sees them. Extractor-derived GT therefore inflates the
  multi-extractor arm's recall by construction.

- **Sparse GT biases the other direction on precision.** A thin GT scores the
  higher-volume arm's real-but-unlisted detections as false positives. So GT
  *completeness* silently picks the winner — sparse punishes the multi-extractor
  arm on precision; extractor-derived inflates it on recall. Neither is neutral;
  a fair A/B needs GT that is complete *and* blind to both arms.

The scorer design already supports a fair comparison and should be preserved: it
ignores rule **count** and compares the set-**union** of detection atoms and
logsource classes across all of an article's rules
(`src/services/sigma_eval_scorer.py`, see
`score_sigma`). That union-based, count-agnostic design is what lets two
architectures that partition detections into different numbers of rules be
compared on one GT — so the eval "just looks at observables (and logsources),"
not how many rules were emitted.

## When to Apply

- Any time you author or expand `config/eval_articles_data/sigma/ground_truth.json`.
- Before running or interpreting a multi-extractor-vs-one-shot comparison.
- When someone proposes reusing extractor fixtures or a generation run to "save
  time" seeding Sigma GT.

## Examples

**One-shot arm is already in the pipeline — no new code needed.** Disable all
extractors and `generate_sigma` hits the full-content fallback: same generator,
same content, zero observables.

```python
# src/workflows/agentic_workflow.py
# When no observable qualifies for Sigma generation (e.g. all extractors off):
if ... and not _has_sigma_generation_eligible_observables(extraction_result):
    fallback_group = _build_sigma_full_content_fallback_group(
        extraction_result, content=content, platforms_detected=...,
    )
    # generation_basis: "full_content_fallback" -> raw article in, no observables
```

**Why the naive borrow fails — measured on the 3 shared articles.** A probe wrapped
each extractor `expected_items` entry into a minimal `process_creation` rule and
ran it through the *same* `extract_atom_fields` the scorer uses:

- **30/30 items decomposed** into ≥1 Sigma atom (feasible mechanically), but
- against the hand-authored GT atoms, only the **image** half was recoverable
  (4/6 `Image|endswith` atoms, from the command-line's first token), and
- **0/11 `CommandLine|contains` discriminator atoms** matched — the GT authors
  picked short discriminators (`.jpg,init`, `--silent`, `|contains|all|antivirusproduct`)
  while the whole-command-line transform produces one brittle literal atom.

So the borrow hands you the corpus + logsource axis + ~image-atom half for free,
but the majority of the scored signal (the discriminator fragments) is analyst
judgment the extractor GT does not encode — and encoding it *from* the extractor
arm is the contamination this doc warns against.

## Related

- [`docs/development/sigma-eval-system.md`](../../development/sigma-eval-system.md) — full authoring protocol + scorer design
- [sigma-group-rule-count-hides-filtered-rules](../logic-errors/sigma-group-rule-count-hides-filtered-rules-2026-08-16.md) — related Sigma-eval rule-count behavior
- [sigma-similarity-case-sensitive-atom-matching](../logic-errors/sigma-similarity-case-sensitive-atom-matching-2026-04-08.md) — the normalizer the scorer relies on
- auto memory [claude]: `reference_sigma_eval_pending_diagnosis` (PENDING rows are pre-fix artifacts; atom_recall=0 with logsource=1.0 is GT divergence, not a scorer bug), `feedback_dont_touch_eval_articles`
