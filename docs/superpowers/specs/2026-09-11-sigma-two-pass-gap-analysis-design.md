# Sigma Two-Pass Gap-Analysis Design

**Date:** 2026-09-11
**Status:** Proposed
**Scope:** Replace the behavior of `sigma_fallback_enabled` with an explicitly two-pass Sigma-generation mode.

## Objective

When enabled, the Sigma toggle must produce rules in two distinct passes:

```text
Pass 1: eligible extracted observables -> grouped, extraction-grounded Sigma rules
Pass 2: junk-filtered article + accepted pass-one rule manifest -> cited rules for additional behavior
Final: validate, deduplicate, preserve provenance, then run existing novelty handling
```

The second pass is not bound to one platform or logsource group. It may emit rules for any supported platform, including macOS, only when it identifies behavior that is materially distinct from accepted pass-one rules.

## Confirmed decisions

1. The existing **Use Full Article Content (Minus Junk)** toggle is repurposed; no second user-facing toggle is introduced.
2. Pass one remains extraction-grounded and uses the existing per-platform, telemetry-category, and logsource grouping.
3. Pass two receives the junk-filtered article and a compact manifest of accepted pass-one rules. It is free to select its own platform and logsource.
4. Pass-two rules require a specific, verbatim supporting excerpt from the article.
5. Citations are retained as reviewer-visible metadata, not embedded in the Sigma YAML.
6. Pass two suppresses detections that overlap with accepted pass-one rules, but may retain materially distinct rules for the same broad TTP.
7. macOS is in scope for pass two.

## Current implementation boundary

The workflow currently groups eligible observables by this key:

```text
(platform, telemetry_category, logsource_hint)
```

It calls Sigma once per group and discards a generated rule that does not match the group's logsource hint. A full-content fallback exists only when no eligible groups are available. The current service can also run an internal artifact-driven expansion phase per group.

Relevant code:

- `src/workflows/agentic_workflow.py::_build_sigma_generation_groups`
- `src/workflows/agentic_workflow.py::_rule_logsource_matches_group`
- `src/workflows/agentic_workflow.py::_deduplicate_batch_rules`
- `src/services/sigma_generation_service.py::SigmaGenerationService.generate_sigma_rules`
- `src/services/sigma_generation_service.py::_build_expansion_prompt`
- `src/services/workflow_config_snapshot.py`

## Target behavior

### Toggle disabled

Preserve the current extraction-only behavior. Sigma receives eligible extracted-observable groups. No full-article gap-analysis call occurs.

### Toggle enabled: pass one

Generate rules from each eligible observable group. A pass-one rule must retain its existing observable attribution and remain subject to its group's logsource enforcement.

The pass-one input must be extraction-grounded rather than use the full article as its main content block.

### Toggle enabled: pass two

Run once after pass-one candidates have been validated, repaired where applicable, and deduplicated. The input includes:

- the exact junk-filtered article representation selected for this execution;
- a compact manifest of accepted pass-one rules, including normalized logsource and detection information needed for overlap avoidance; and
- instructions to create only distinct, evidence-supported rules.

Pass two does not use `_rule_logsource_matches_group`. It must still pass normal Sigma validation and existing corpus-novelty handling.

## Citation and provenance contract

Each pass-two candidate must carry non-Sigma metadata equivalent to:

```text
generation_phase: full_article_gap_analysis
article_citation: <verbatim excerpt>
article_citation_start: <zero-based character offset>
article_citation_end: <zero-based exclusive character offset>
article_content_sha256: <hash of the exact article representation>
```

The service must reject a candidate when its excerpt is absent, empty, or cannot be matched exactly against the article representation supplied to the model. Citation metadata must survive parsing, validation repair, rule aggregation, queue serialization, and reviewer display.

Verified citation text demonstrates traceability, not semantic proof that every detection predicate follows from that text. Reviewer UI must preserve that distinction.

## Deduplication contract

Pass two compares candidates against final accepted pass-one rules and previously accepted pass-two rules. The initial deterministic policy should reuse the existing intra-batch predicate unless a stronger canonical atom comparison is available:

```text
same logsource (category + product)
AND detection leaf-value Jaccard overlap >= 0.80
```

When rules overlap, retain the more specific detection. Record the suppression reason and compared rule identifier in execution metadata.

## Adversarial-review gates

Implementation must resolve these before enabling the mode:

1. **Whole-article coverage:** current provider prompt limits truncate long prompts. The design must either chunk and cover the full filtered article, or explicitly define the mode as bounded coverage. It must not claim whole-article review while silently truncating.
2. **Snapshot compatibility:** changing the meaning of `sigma_fallback_enabled` requires a versioned execution-snapshot semantic, so old/replayed executions retain their historical behavior.
3. **Legacy expansion:** disable or replace the current per-group Phase 4 expansion in two-pass mode. Otherwise the proposed two-pass model silently becomes many additional calls.
4. **Failure policy:** pass two must run if extraction produces no eligible group or pass one yields no accepted rule, provided a usable filtered article exists. A pass-one failure must be recorded rather than hidden.
5. **Bounded operation:** define provider-call, prompt-size, output-rule, and timeout limits independently for pass two.
6. **macOS validation:** prove the validator, rule queue, novelty pipeline, and UI accept and render supported macOS rules.

## Required acceptance tests

- Toggle-off behavior remains extraction-only.
- Toggle-on executes pass one before one pass-two gap-analysis call.
- Pass-two output can include a valid platform/logsource absent from pass-one groups, including macOS.
- Pass-two candidates without a citation, with an empty citation, or with an unmatched citation are rejected.
- Citation text, offsets, content hash, and generation phase persist to reviewer-visible metadata and survive repair.
- Pass-two duplicates are suppressed against accepted pass-one rules and within pass two; materially distinct rules remain.
- Pass two still runs when extraction returns no eligible observables but filtered article content is available.
- Long-article behavior proves the declared coverage contract.
- Legacy snapshots preserve historical toggle behavior; new snapshots record the new semantic version.
- Phase-four expansion cannot create undeclared additional passes in two-pass mode.

## Documentation follow-up after implementation

- Update `docs/architecture/workflow-data-flow.md` with the implemented flow and provenance contract.
- Update `docs/guides/generate-sigma.md` with the operator-facing toggle behavior.
- Consider an ADR if the snapshot-versioning and citation-evidence policy becomes a permanent architecture boundary.
