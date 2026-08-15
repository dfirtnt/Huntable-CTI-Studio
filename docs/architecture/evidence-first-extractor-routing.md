# Evidence-First Extractor Routing

**Date:** 2026-08-13
**Status:** Proposed
**Audience:** Maintainers, operators, and reviewers

## Summary

Huntable currently identifies platforms for an article and uses that result to decide which extraction agents are eligible to run. The classifier is already multi-label and more capable than a simple dominant-OS selector, but its decision is still made at article scope.

That is the wrong scope for extractor dispatch.

A mostly Linux article can contain one Windows registry persistence paragraph. A Windows intrusion report can contain a macOS command, a platform-neutral query, and network indicators. If article metadata misses the minority evidence, the relevant extractor may never see it.

The proposed architecture routes **evidence**, not articles.

## Before

```text
Article
  -> classify article platform
  -> skip extractors unsupported by the article platform
  -> send broadly shared filtered article content to remaining extractors
  -> normalize observables
  -> generate and validate Sigma rules
```

Consequences:

- A coarse classification influences extractor eligibility.
- Most eligible extractors receive substantially the same article content.
- Small but valuable minority-platform evidence can be suppressed.
- Token use is higher than necessary.
- Extractor output traces point to quoted evidence, but the workflow does not maintain stable source-block IDs and offsets for every route.

## After

```text
Article
  -> divide original content into source-addressable semantic blocks
  -> inspect every block with deterministic evidence detectors
  -> ask a bounded semantic adjudicator about ambiguous candidates only
  -> combine primary evidence with adjacent and entity-definition context
  -> route evidence bundles to applicable specialized extractors
  -> validate extracted observables against dispatched source blocks
  -> normalize observables
  -> use the existing Sigma grouping, generation, validation, and novelty pipeline
```

Article-level platform classification remains available as metadata and weak context. It no longer gets veto authority over evidence-backed routes.

## Core idea

The workflow should answer:

> Which source regions contain evidence useful to which extractor?

It should not first require an answer to:

> What platform best describes this entire article?

Every article block receives a cheap deterministic scan. Strong evidence routes immediately. Only ambiguous candidates go to a constrained LLM adjudicator. The LLM may route, reject, or abstain, and it must identify the supporting source blocks. It cannot invent new lanes or source IDs.

## Evidence bundles

Extractors should not receive isolated fixed-size chunks. Narrow chunks often remove the context needed to interpret a command, process relationship, service, task, or query.

A normal evidence bundle contains:

- the primary matching paragraph or structured block
- one preceding block
- one following block
- a relevant earlier entity-definition block when needed
- article title and source metadata
- stable source block IDs
- original character offsets
- the routing signal and lane

The full filtered article remains an explicit fallback, not normal input. Routing offsets always refer to the original cleaned article content because filtered text can contain duplicated overlap and altered spacing.

## Initial routing lanes

The first implementation maps evidence lanes to the seven existing extractors:

| Evidence lane | Extractor |
|---|---|
| Command lines | `CmdlineExtract` |
| Process lineage | `ProcTreeExtract` |
| Hunt queries and complete Sigma content | `HuntQueriesExtract` |
| Registry persistence and modification | `RegistryExtract` |
| Windows service creation and modification | `ServicesExtract` |
| Scheduled task creation and modification | `ScheduledTasksExtract` |
| Network indicators and behavior | `NetworkIndicatorExtract` |

The lane taxonomy can become richer later without immediately creating more agents. Multiple detailed lanes may map to one existing extractor.

## Examples

### Mixed-platform article

An article is classified primarily as Linux but contains:

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

The registry path is strong local Windows evidence. It routes to `RegistryExtract` regardless of article-level platform metadata.

### Ambiguous service language

A paragraph says the malware "used a service for persistence" but provides no service name, command, registry path, or API behavior.

The deterministic detector marks it ambiguous. The semantic adjudicator receives that paragraph and adjacent context. It may route, reject, or abstain. Abstention widens to routing because a missed route cannot be recovered later.

### Hunt query

A report says analysts should "search for suspicious PowerShell activity" but gives no executable query.

That statement does not route to `HuntQueriesExtract`.

A valid KQL, SPL, EQL, or complete Sigma block containing both `logsource:` and `detection:` does route.

### No evidence routes

A highly ranked article produces no routes. The workflow records `high_value_zero_routes` and runs the legacy full-content path as a safety net. A low-ranked zero-route article ends extraction normally.

## Why deterministic first

Strong literal signals are cheap, explainable, testable, and resistant to routing hallucination. Examples include registry hives, `schtasks`, service-control commands, explicit parent-child process statements, executable query syntax, and literal network observables.

The semantic component is useful for language that requires context, but it is not an oracle. It receives only bounded candidates and allowed lane definitions. Numeric model confidence is not treated as calibrated probability.

## Recall and precision policy

The two stages have different risk profiles:

- **Routing favors recall.** Missing a route means the relevant extractor never sees the evidence.
- **Extraction favors precision.** Inferred or fabricated observables contaminate Sigma generation.

Therefore:

- Strong deterministic routes cannot be rejected by the model.
- Invalid model output, timeout, provider failure, or abstention widens ambiguous routes.
- Extracted items must map back to source blocks actually sent to that extractor.
- Items without valid source evidence remain in diagnostics but do not enter normalized observables or Sigma generation.

## What remains unchanged

This is not a replacement of Huntable's core analytical pipeline.

The following remain:

- existing specialized extraction agents
- literal-evidence extractor contracts
- normalized-observable aggregation
- platform, telemetry, and logsource grouping
- Sigma generation
- pySigma validation
- intra-batch deduplication
- novelty comparison and queue promotion

The change is inserted before extractor invocation and strengthens traceability after extraction.

## Operational modes

The rollout uses three modes:

| Mode | Behavior |
|---|---|
| `legacy` | Current platform-gated routing and full filtered-content input |
| `shadow` | Build and persist an evidence routing plan, but execute the unchanged legacy path |
| `enforce` | Use evidence routes and bundles for extractor eligibility and input |

New installations and migrated configurations start in `legacy`. Rollback from enforce mode is a configuration change.

## Visibility

The execution trace should show:

- routing mode
- detected lanes
- supporting block IDs and excerpts
- deterministic or semantic basis
- extractors invoked
- disabled extractors that had routes
- fallback reason
- article-platform disagreements
- source-validation rejections
- shadow comparison against legacy

Full and slim evaluation bundles retain routing IDs, source offsets, hashes, selected evidence, and metrics. Old executions without routing data remain readable as legacy executions.

Platform Detection remains visible as article metadata during migration.

## Benefits

- Better recall for minority-platform and mixed-platform evidence.
- Lower extractor input volume and potentially fewer invocations.
- Clear evidence-to-extractor provenance.
- Reduced dependence on a coarse article decision.
- Better protection against model-generated unsupported observables.
- A route taxonomy that can expand without immediately multiplying agents.
- Safe rollout and rollback through shadow and legacy modes.

## Trade-offs

- More routing and source-mapping code.
- A new evaluation corpus is required because current count-only extractor evaluations do not measure route or span recall.
- Deterministic detectors require ongoing maintenance as telemetry forms evolve.
- Ambiguous-case fan-out can temporarily increase invocations.
- Strict source validation may initially reject outputs that were previously accepted, exposing extractor prompt or formatting weaknesses.
- Execution traces will contain more routing metadata and require payload-size controls.

## How success is measured

The architecture should not ship based only on router precision.

The release decision compares legacy and evidence-first execution on the same articles using:

- lane and supporting-span recall
- extractor fan-out
- extractor input tokens
- normalized-observable recall and precision
- Sigma logsource recall
- Sigma detection-atom recall and precision
- fallback rate
- cost and latency

The principal requirement is lower cost or fan-out without meaningful loss in downstream observable or Sigma detection-atom recall. Mixed-platform and minority-evidence cases must retain every expected route in the checked-in evaluation corpus.

## Delivery sequence

1. Add stable source blocks and routing contracts.
2. Add deterministic lane detectors.
3. Add route policy and context-preserving bundle construction.
4. Add optional bounded semantic adjudication.
5. Run the router in shadow mode while preserving current execution.
6. Add evidence-bundle extractor dispatch and source validation.
7. Enable enforce mode only after paired evaluation gates pass.
8. Keep Platform Detection as metadata until production data supports a separate removal decision.

## Detailed specification

The implementation contract, schemas, migration steps, tests, and acceptance criteria are in the repository at `docs/superpowers/specs/2026-08-13-evidence-first-extractor-routing-build-spec.md`.
