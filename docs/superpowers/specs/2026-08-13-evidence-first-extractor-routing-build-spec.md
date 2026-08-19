# Evidence-First Extractor Routing Build Specification

**Date:** 2026-08-13
**Status:** Proposed
**Primary implementer:** AI coding agent
**Target branch:** `europa-dev`

Human-readable companion: [`Evidence-First Extractor Routing`](../../architecture/evidence-first-extractor-routing.md)

## 1. Objective

Replace article-platform-gated extractor eligibility with evidence-first routing.

The workflow must inspect source-addressable article blocks, identify extractor-relevant evidence, build context-preserving evidence bundles, and dispatch only the applicable extractors. Article-level platform classification remains descriptive metadata and a weak context prior. It must not suppress a route supported by local evidence.

Target flow:

```text
Article content
  -> stable source blocks
  -> deterministic lane detection
  -> bounded semantic adjudication for ambiguous candidates only
  -> validated routing plan
  -> context-preserving evidence bundles
  -> existing specialized extractors
  -> source-validated normalized observables
  -> existing platform/telemetry/logsource grouping
  -> existing Sigma generation, validation, and novelty checks
```

## 2. Success condition

Activate evidence-first dispatch only after evaluation shows:

1. No statistically meaningful reduction in normalized-observable recall.
2. No statistically meaningful reduction in Sigma detection-atom recall.
3. Lane routing recall meets the threshold in Section 16.
4. Average extractor input tokens or extractor invocations decrease.
5. Mixed-platform evidence is not suppressed by article-level platform metadata.

Routing accuracy alone is not a sufficient release criterion.

## 3. Current implementation facts

The implementation agent must verify these facts before editing because line numbers may drift.

- `src/workflows/agentic_workflow.py`
  - Defines `AGENT_PLATFORM_CAPABILITIES`.
  - Performs deterministic multi-label platform classification and bounded platform adjudication.
  - Uses `_agent_supported_for_platforms()` to skip extractors before invocation.
  - Invokes enabled extraction agents with substantially the same `filtered_content`.
  - Aggregates normalized observables and groups Sigma input by platform, telemetry category, and logsource.
- `src/services/llm_service.py`
  - Owns extraction-agent prompt assembly and invocation.
  - Injects required `source_evidence`, justification, and confidence fields.
  - Uses Cmdline and ProcTree attention preprocessors to surface likely snippets while retaining the full article.
- `src/services/cmdline_attention_preprocessor.py` and `src/services/proc_tree_attention_preprocessor.py`
  - Contain proven deterministic signal detection, but return derived snippets without stable source offsets.
- `src/utils/content_filter.py`
  - Uses overlapping approximately 1,000-character chunks for huntability filtering.
  - Reconstructs `filtered_content` with joins, so its offsets do not map reliably to the original article.
  - Strips chunk text while retaining pre-strip offsets and can duplicate overlap when kept chunks are joined.
- `src/core/modern_scraper.py` and `src/utils/content.py`
  - Produce and persist the cleaned article text that is the canonical routing source.
  - Preserve semantic block newlines and inline observable tokens during HTML-to-text conversion.
- `src/services/chunk_analysis_service.py` and `ChunkAnalysisResultTable`
  - Persist huntability-model analysis, not execution-scoped extractor routes.
  - Must not be repurposed as the routing-plan store.
- `src/database/models.py::AgenticWorkflowExecutionTable`
  - Stores execution detail in `error_log` and `extraction_result` JSONB.
- `src/services/workflow_config_snapshot.py`
  - Defines configuration snapshot completeness and immutable execution config capture.
- `src/services/execution_snapshot_store.py` and `AgenticWorkflowExecutionSnapshotTable`
  - Store content-addressed immutable snapshot payloads and leave execution rows with a snapshot reference.
- `src/services/eval_bundle_service.py` and `src/web/routes/workflow_executions.py`
  - Emit `eval_bundle_v1` and `workflow_execution_trace_v1` artifacts that must carry routing provenance.
- `docs/contracts/extractor-standard.md`
  - Requires literal evidence, fail-closed extraction, and source traceability.
- `config/eval_articles.yaml`
  - Contains count-oriented extractor evaluations, which are insufficient by themselves for routing evaluation.

## 4. Scope

### 4.1 In scope

- Stable segmentation of the original cleaned article content.
- Deterministic detection for the seven existing extractor families.
- Optional LLM adjudication of ambiguous route candidates.
- Context-preserving evidence-bundle construction.
- Evidence-first dispatch to the existing extractors.
- Source mapping and validation of extractor outputs.
- Routing persistence, execution trace rendering, metrics, and evaluation.
- Shadow, enforce, and legacy rollout modes.
- Removal of article platform classification from extractor eligibility decisions in enforce mode.
- Backward-compatible execution and preset migration.

### 4.2 Out of scope

- Replacing specialized extractors with one general-purpose agent.
- Replacing the normalized-observable or Sigma pipeline.
- Removing article-level platform metadata in this change.
- Adding new cloud, container, identity, or endpoint extractors.
- Treating arbitrary model confidence values as calibrated probabilities.
- Re-training the huntability content-filter model.
- Reusing fixed-size huntability chunks as evidence bundles.
- Sending all article blocks to an LLM router.
- Changing Sigma novelty or pySigma validation behavior.

## 5. Architectural invariants

1. **Local evidence wins.** A supported source span creates a route even when article-level platform metadata disagrees.
2. **Article platform is not a hard gate.** `_agent_supported_for_platforms()` cannot suppress an evidence-backed route in enforce mode.
3. **Strong deterministic routes bypass the LLM.** The semantic adjudicator only receives ambiguous candidates.
4. **Uncertainty widens fan-out.** Adjudicator failure, malformed output, or abstention routes all affected ambiguous candidates rather than dropping them.
5. **No candidate means no normal route.** High-value zero-route cases use the explicit fallback policy in Section 11.
6. **Extractors remain fail closed.** Routing is recall-biased; extraction and source validation are precision-biased.
7. **Offsets refer to original cleaned article content.** Never calculate source offsets against reconstructed `filtered_content`.
8. **Verbatim source survives.** Bundle source blocks are exact substrings of the original content.
9. **One article may route to multiple lanes and platforms.** No dominant-platform selection is permitted.
10. **Cloud-only deployments work.** Deterministic routing requires no model. Semantic adjudication supports configured cloud providers and is optional.
11. **No silent fallback.** Every fallback is recorded with a reason code.
12. **Legacy behavior remains available during rollout.** Rollback is a config change, not a database rollback.

## 6. Initial lane registry

Create `src/services/evidence_routing/lane_registry.py` as the only source of truth for lane-to-extractor mapping.

| Lane ID | Extractor | Initial platform scope | Strong examples |
|---|---|---|---|
| `process.command_line` | `CmdlineExtract` | any | literal executable command, shell command, script invocation with arguments |
| `process.lineage` | `ProcTreeExtract` | any | explicit parent-child or process-chain relationship |
| `query.hunt` | `HuntQueriesExtract` | any | executable SIEM/EDR query, or complete Sigma block containing `logsource:` and `detection:` |
| `persistence.registry` | `RegistryExtract` | windows | registry hive/path plus modification, query, or persistence semantics |
| `persistence.service` | `ServicesExtract` | windows | service creation/configuration command, API, registry service path, or explicit service persistence action |
| `persistence.scheduled_task` | `ScheduledTasksExtract` | windows initially | `schtasks`, Task Scheduler XML, task cmdlets, or explicit task creation/modification details |
| `network.indicator` | `NetworkIndicatorExtract` | any | literal URL, domain, IP, endpoint, protocol indicator, or network behavior used by the extractor contract |

Rules:

- Do not add platform names to lane IDs. Platform is route evidence metadata, not the route identity.
- The registry must expose lane ID, extractor name, detector, supported platforms, display name, and schema version.
- Unknown lanes fail validation.
- Disabled extractors remain disabled. Routing cannot re-enable them.
- The registry must support future many-lanes-to-one-extractor mappings without changing dispatcher interfaces.

## 7. Data contracts

Implement these contracts with frozen dataclasses or Pydantic models under `src/services/evidence_routing/contracts.py`. JSON serialization must use the exact field names below.

### 7.1 `SourceBlock`

```json
{
  "schema_version": "1.0",
  "block_id": "blk-<article-hash-prefix>-<source-field>-<start>-<end>",
  "article_id": 1427,
  "ordinal": 17,
  "source_field": "content",
  "kind": "paragraph",
  "start_offset": 5201,
  "end_offset": 5488,
  "text": "exact article substring",
  "section_path": ["Persistence"],
  "content_sha256": "sha256 of exact text"
}
```

Contract:

- `start_offset` is inclusive and `end_offset` is exclusive.
- `source_field` is `content` or `title`; offsets are relative to that source field.
- `source_fields[source_field][start_offset:end_offset] == text` must always hold.
- `block_id` must be deterministic for the same article content and offsets.
- `block_id` must include `source_field`; title and content offsets occupy separate coordinate spaces.
- IDs must not depend on database insertion order or workflow execution ID.
- `kind` values for version 1: `title`, `heading`, `paragraph`, `list_item`, `code_block`, `table_block`, `ocr_block`, `other`.
- Heading context may populate `section_path`, but heading text remains an independent source block.

### 7.2 `SignalMatch`

```json
{
  "signal_id": "registry.hive_path",
  "lane_id": "persistence.registry",
  "strength": "strong",
  "block_ids": ["blk-..."],
  "ranges": [{"block_id": "blk-...", "start_offset": 5260, "end_offset": 5314}],
  "literal": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
  "platforms": ["windows"],
  "detector_version": "1.0"
}
```

Contract:

- `strength` is `strong` or `ambiguous`.
- Every range must identify and be inside one referenced source block.
- `literal` must equal the corresponding original article substring.
- A signal may nominate more than one lane only by emitting separate `SignalMatch` records.
- Detectors do not emit probability scores.

### 7.3 `RouteCandidate`

```json
{
  "candidate_id": "cand-...",
  "lane_id": "persistence.service",
  "basis": "deterministic_ambiguous",
  "primary_block_ids": ["blk-..."],
  "signal_ids": ["service.generic_reference"],
  "platforms": ["windows"],
  "requires_adjudication": true
}
```

### 7.4 `AdjudicationDecision`

```json
{
  "candidate_id": "cand-...",
  "lane_id": "persistence.service",
  "decision": "route",
  "support_block_ids": ["blk-..."],
  "reason_code": "explicit_service_configuration",
  "rationale": "Short explanation tied only to supplied source blocks"
}
```

Contract:

- `decision` is `route`, `reject`, or `abstain`.
- No numeric confidence field is accepted.
- Candidate ID and lane ID must match the submitted candidate.
- `support_block_ids` must be a subset of blocks supplied for that candidate.
- Unknown IDs, unsupported lanes, prose outside the schema, and missing required fields invalidate that decision.
- Invalid, timed-out, unavailable, or `abstain` decisions resolve to `route` for recall.
- A valid `reject` may suppress only an ambiguous candidate. It can never suppress a strong deterministic route.

### 7.5 `EvidenceBundle`

```json
{
  "schema_version": "1.0",
  "bundle_id": "bundle-...",
  "lane_id": "persistence.registry",
  "extractor": "RegistryExtract",
  "route_basis": "deterministic_strong",
  "primary_block_ids": ["blk-17"],
  "context_block_ids": ["blk-16", "blk-18", "blk-4"],
  "signal_ids": ["registry.hive_path"],
  "platforms": ["windows"],
  "source": {
    "article_id": 1427,
    "title": "Article title",
    "canonical_url": "https://example.test/article"
  },
  "blocks": [
    {
      "block_id": "blk-16",
      "role": "preceding_context",
      "source_field": "content",
      "start_offset": 4900,
      "end_offset": 5200,
      "text": "exact article substring"
    }
  ],
  "full_article_reference_available": true
}
```

Contract:

- Include each block once. Render title metadata first, then body blocks ordered by original content offset.
- Normal context is the primary block plus one preceding and one following semantic block.
- Include the nearest relevant earlier entity-definition block only when a deterministic entity reference or adjudication decision requires it.
- Do not include unrelated blocks merely to reach a token minimum.
- Overlapping candidates for the same lane merge when their context windows intersect.
- Bundle text rendering must label metadata and block IDs without altering block text.
- The original full article remains available to fallback logic but is not included in normal extractor input.

### 7.6 `RoutingPlan`

```json
{
  "schema_version": "1.0",
  "mode": "enforce",
  "article_id": 1427,
  "source_content_sha256": "...",
  "blocks_scanned": 42,
  "block_index": [],
  "signals": [],
  "candidates": [],
  "adjudications": [],
  "routes": [],
  "bundles": [],
  "extractor_dispatch": {
    "RegistryExtract": ["bundle-1"],
    "NetworkIndicatorExtract": ["bundle-2"]
  },
  "fallback": null,
  "metrics": {}
}
```

`block_index` stores block ID, source field, kind, offsets, and content hash. It does not duplicate full block text.

The plan must be deterministic when semantic adjudication is disabled.

## 8. Source segmentation

Create `src/services/evidence_routing/source_segmenter.py`.

### 8.1 Input

- `article.id`
- `article.title`
- Original cleaned `article.content` loaded by the workflow

Do not segment `filtered_content`.

### 8.2 Required behavior

1. Emit a title block with `source_field=title` and offsets relative to the title. Do not pretend the title occurs in article content.
2. Parse article content into paragraph and structured blocks while preserving exact source slices.
3. Treat fenced code, indented command listings, tables, OCR blocks, headings, and list sequences as bounded structured units where possible.
4. Preserve empty-line boundaries for context selection without emitting empty blocks.
5. Never normalize whitespace in `SourceBlock.text`.
6. Verify all offsets before returning.
7. On parser uncertainty, emit a larger `other` block rather than altering text or dropping content.
8. Scan every emitted body block with deterministic detectors.

### 8.3 Relationship to existing chunking

- Do not change `ContentFilter.chunk_content()` as part of the first routing implementation.
- Do not use its overlapping fixed-size chunks as route source blocks.
- Add regression tests proving that source-block offsets still refer to original article content after junk filtering reconstructs `filtered_content`.

## 9. Deterministic detection

Create one detector module per lane under `src/services/evidence_routing/detectors/` plus shared utilities.

### 9.1 Detector interface

```python
class LaneDetector(Protocol):
    lane_id: str
    detector_version: str

    def detect(self, blocks: Sequence[SourceBlock]) -> list[SignalMatch]: ...
```

Detectors must be pure, deterministic, provider-independent, and free of database access.

### 9.2 Reuse requirements

- Extract reusable matching primitives from the Cmdline and ProcTree attention preprocessors rather than maintaining duplicate rule sets.
- Preserve legacy preprocessor output and tests while `mode=legacy` or `mode=shadow`.
- Add offset-aware match APIs. Do not infer offsets by searching normalized snippets after the fact.
- Existing preprocessors may become wrappers around the shared detectors after parity tests pass.

### 9.3 Strong and ambiguous policy

Strong signals require literal evidence sufficient to justify extractor invocation. Examples:

- Registry hive/path with an operation or persistence relation.
- `schtasks` creation/modification syntax or Task Scheduler XML.
- `sc.exe create/config`, service API calls, or explicit malicious service installation.
- Explicit parent-child/process-chain statement.
- Literal command with executable/interpreter and arguments.
- Executable query syntax for a named EDR/SIEM language.
- Complete Sigma content containing both `logsource:` and `detection:`.
- Literal network observable accepted by the NetworkIndicator extractor.

Ambiguous signals include generic prose such as "service", "task", "query", shell names without commands, unlabeled tables, or platform-neutral utility mentions.

Negative constraints:

- Generic use of "service" must not be strong.
- A product description containing "scheduled task" without an observable action must not be strong.
- MITRE technique names alone must not create routes.
- A prose recommendation to hunt without an executable query must not create `query.hunt`.
- `HuntQueriesExtract` routing must retain the existing true-query and complete-Sigma requirements.

## 10. Semantic adjudication

Create `src/services/evidence_routing/adjudicator.py`.

### 10.1 Invocation limits

- Only ambiguous `RouteCandidate` records are submitted.
- Strong candidates are excluded.
- Batch candidates by article, with a configurable hard cap.
- Each candidate includes its nominated lanes, primary blocks, adjacent context, allowed lane definitions, and explicit abstention rules.
- Do not send the unrestricted full article.
- If candidates exceed `MaxAmbiguousCandidates`, route the overflow candidates without adjudication and record `semantic_budget_widened`; never discard overflow.

### 10.2 Model contract

Add a canonical optional model configuration named `EvidenceRouteAdjudicator`.

Required settings:

- `Enabled`
- `Provider`
- `Model`
- `Temperature`, default `0.0`
- `TopP`, default `1.0`
- Prompt block in the v2 workflow config

The feature must work with OpenAI, Anthropic, or supported local providers through existing provider abstraction. If no adjudicator model is configured, all ambiguous candidates route.

### 10.3 Validation and fallback

Validate model output before applying it. Record one of:

- `semantic_route`
- `semantic_reject`
- `semantic_abstain_widened`
- `semantic_invalid_widened`
- `semantic_unavailable_widened`
- `semantic_timeout_widened`

Do not retry with a more permissive free-form prompt. Existing provider retry policy may retry transport failures only.

## 11. Route policy and fallback behavior

Create `src/services/evidence_routing/policy.py`.

### 11.1 Modes

- `legacy`: Current platform-capability routing and full `filtered_content` extractor input. No behavior change.
- `shadow`: Build and persist a routing plan, but execute the legacy path. Never change extractor eligibility or inputs.
- `enforce`: Dispatch from the validated routing plan and evidence bundles.

Default on migration: `legacy`.

### 11.2 Enforce policy

1. Route every strong deterministic candidate.
2. Apply valid semantic decisions to ambiguous candidates.
3. Widen abstained, invalid, timed-out, or unavailable ambiguous candidates to routes.
4. Remove exact duplicate routes.
5. Merge overlapping same-lane route context into bundles.
6. Drop routes only when their extractor is explicitly disabled. Record `extractor_disabled`.
7. Do not call `_agent_supported_for_platforms()` as an eligibility gate.
8. Use lane registry platform scope to validate impossible configurations, not article metadata to suppress evidence.

### 11.3 Full-article fallback

Fallback reasons:

- `router_internal_error`
- `segment_validation_failed`
- `high_value_zero_routes`
- `bundle_render_failed`

Behavior:

- Internal routing or segmentation failure: execute the legacy extractor path and record the error.
- Zero routes after a sufficiently high RankAgent score: execute enabled extractors using current legacy eligibility and `filtered_content`.
- Zero routes below the configured high-value threshold: terminate extraction normally with zero routes.
- A single extractor bundle-render failure: run that extractor with legacy input; do not widen every extractor.

The initial `high_value_zero_routes` threshold must reuse or derive from an existing evaluated workflow score. Do not add an arbitrary hidden constant. Expose it in config and evaluate it.

## 12. Evidence-bundle dispatch

Create `src/services/evidence_routing/bundle_builder.py` and `dispatcher.py`.

### 12.1 Dispatch unit

- Group bundles by extractor.
- Normally invoke each enabled extractor once with all of its ordered bundles.
- If an extractor input exceeds its provider/model context budget, split only at bundle boundaries, invoke multiple batches, and merge results using existing subresult normalization.
- Record batch count and input character/token counts.

### 12.2 `LLMService` change

Extend `LLMService.run_extraction_agent()` with an optional structured evidence input. Preserve legacy callers.

Required behavior:

- Legacy `article_content` behavior remains unchanged when no evidence input is supplied.
- Evidence mode renders metadata, lane definitions, bundle IDs, source block IDs, and exact block text.
- Evidence mode tells the extractor that source evidence must be copied verbatim from supplied source blocks.
- Do not append the full article during normal evidence mode.
- Bypass legacy Cmdline/ProcTree attention preprocessors in evidence mode because routing already selected their evidence. Keep them active in legacy mode.

## 13. Source validation and normalized observables

Add `src/services/evidence_routing/source_validator.py`.

For every extracted item:

1. Require `source_evidence` under the existing extractor contract.
2. Match `source_evidence` exactly against one or more blocks dispatched to that extractor.
3. Confirm the extracted literal or domain identity fields occur in the source evidence when the extractor contract requires literal presence.
4. Attach:
   - `source_block_ids`
   - `source_field`
   - `source_start_offset`
   - `source_end_offset`
   - `route_ids`
   - `bundle_ids`
   - `routing_lane`
5. Reject the item from normalized observables when source evidence cannot be mapped or literal-presence validation fails.
6. Preserve rejected items in trace diagnostics with a reason code. Do not silently discard them.
7. If the same evidence occurs more than once, restrict mapping to blocks actually dispatched to that extractor; if still ambiguous, store all matching block IDs and the first ordered range.

Platform and telemetry enrichment order:

1. Explicit literal evidence and extractor-specific inference.
2. Route signal platform metadata.
3. Evidence-bundle context.
4. Article-level platform metadata as a weak fallback only.

Keep `_build_sigma_generation_groups()` and downstream Sigma behavior intact.

## 14. Workflow integration

### 14.1 Graph shape

Do not add or remove a top-level LangGraph step in the first implementation. Keep the seven-step workflow and contract-grade UI step IDs.

Evidence routing is a subphase of `extract_agent_node()`:

```text
extract_agent_node
  -> segment original article content
  -> detect signals
  -> adjudicate ambiguous candidates
  -> apply policy
  -> build bundles
  -> dispatch extractors
  -> validate and aggregate results
```

Platform Detection remains its current top-level step for metadata and migration comparison.

### 14.2 Workflow state additions

Add typed state fields:

- `source_blocks`
- `evidence_routing_plan`
- `evidence_routing_summary`

Do not place full article text in multiple state fields.

### 14.3 Platform classifier change

- `legacy`: retain current `_agent_supported_for_platforms()` behavior.
- `shadow`: execute legacy behavior and calculate counterfactual evidence routes.
- `enforce`: article platform results cannot skip an evidence-backed extractor.
- Keep `platforms_detected` in execution summary and UI.
- Add comparison telemetry when route platforms contradict article metadata.

## 15. Configuration and persistence

### 15.1 V2 config

Add strict top-level `EvidenceRouting` configuration:

```json
{
  "Mode": "legacy",
  "SemanticAdjudicationEnabled": false,
  "ContextBlocksBefore": 1,
  "ContextBlocksAfter": 1,
  "EntityLookbackBlocks": 12,
  "MaxAmbiguousCandidates": 24,
  "HighValueZeroRouteThreshold": 8.0
}
```

Validation:

- `Mode`: `legacy`, `shadow`, or `enforce`.
- Context counts: integers from 0 through 3.
- Entity lookback: integer from 0 through 50.
- Max ambiguous candidates: integer from 1 through 100.
- High-value threshold: bounded by the existing RankAgent score scale.

Add `EvidenceRouteAdjudicator` to canonical model/prompt mappings. It may be disabled and unconfigured when semantic adjudication is false.

### 15.2 Active database config

Persist routing settings on `AgenticWorkflowConfigTable`. Use explicit columns for mode, semantic enablement, context sizes, candidate cap, and high-value threshold. Add an idempotent migration script following existing `scripts/migrate_add_*` conventions.

Update:

- `src/config/workflow_config_schema.py`
- `src/config/workflow_config_loader.py`
- `src/config/workflow_config_migrate.py`
- `src/database/manager.py` and `src/database/async_manager.py` startup schema reconciliation
- workflow config API request/response mappings
- workflow config save/load paths
- `src/services/workflow_config_snapshot.py`
- `src/services/execution_snapshot_store.py` snapshot attachment and hydration compatibility
- preset export/import and all full-snapshot presets
- baseline preset generation scripts and tests

Migration defaults must reproduce current behavior: `Mode=legacy`, semantic adjudication disabled.

### 15.3 Execution persistence

Do not add a new routing execution table in version 1.

Persist:

- A versioned routing manifest at `execution.extraction_result.routing` immediately after plan validation and before extractor calls. Commit or flush it with the same incremental durability used for extractor conversation records.
- The manifest's block index, signal/candidate/decision records, bundle references, fallback status, and source-validation counts in that one canonical location.
- Every behavior-affecting setting in the existing content-addressed immutable execution snapshot, not only in mutable active config columns.
- A routing summary in existing execution detail responses without requiring clients to parse the full manifest.

Do not use `error_log` as a second routing-plan store. Preserve errors there as errors only, with references to routing IDs when useful. Keep full block text out of the manifest by default; offsets and hashes recover it from the execution article input. Cap any diagnostic excerpts using existing execution-log size safeguards.

Legacy executions without `extraction_result.routing` remain valid and render as `router_not_recorded`.

### 15.4 Evaluation and trace artifacts

Update `src/services/eval_bundle_service.py` so full `eval_bundle_v1` bundles include the routing manifest, source-content hash, and selected evidence. Slim bundles retain IDs, source fields, offsets, hashes, selections, and metrics while deduplicating block text.

Update `_extract_config_snapshot()` to include all evidence-routing settings alongside the current attention-preprocessor settings. Hydrate immutable snapshot references before filtering the snapshot.

Update `workflow_execution_trace_v1` exports in `src/web/routes/workflow_executions.py`. If routing fields become a consumer contract, version the trace schema rather than silently changing `v1`. Legacy trace exports must remain readable.

### 15.5 Observable identity compatibility

Assign each normalized observable a stable `observable_id` derived from execution, extractor, bundle lineage, canonical type/value, and occurrence ordinal. Dual-write it while preserving:

- flat `extraction_result.observables` order
- legacy zero-based observable indices
- `original_observable_index` and `group_observable_index`
- `observables_used` rebasing semantics
- canonical extractor/subresult insertion order

Do not reorder or deduplicate existing observables in version 1. Sigma queue grounding remains in `rule_metadata`, never in emitted Sigma YAML.

### 15.6 Metrics

Persist or emit:

- blocks scanned
- strong and ambiguous signal counts
- adjudication candidate/route/reject/abstain counts
- routes and bundles by lane
- enabled extractors invoked
- legacy counterfactual extractors
- fallback reason
- platform disagreement count
- extractor input characters
- provider-reported input tokens when available
- approximate input tokens only when provider usage is unavailable, marked `estimated=true`
- routing, adjudication, extraction, and end-to-end latency
- source-validation accepted/rejected item counts
- selected source characters and selected/source character ratio by extractor

Langfuse remains the detailed per-call telemetry source. Database metrics must be sufficient for rollout comparisons without Langfuse.

## 16. Evaluation design and release gates

### 16.1 Gold routing corpus

Add checked-in fixtures under:

- `tests/fixtures/evidence_routing/articles/`
- `tests/fixtures/evidence_routing/gold.yaml`

Each case must contain:

- stable article text fixture
- expected lanes
- required supporting literal substrings
- forbidden lanes
- expected mixed-platform facts when applicable
- expected fallback behavior
- optional expected normalized observables and Sigma detection atoms

Minimum corpus coverage:

- 10 positive and 5 hard-negative cases per initial lane.
- At least 10 mixed-platform articles.
- At least 10 minority-evidence cases where relevant evidence occupies less than 10 percent of article text.
- At least 10 no-route articles.
- At least 5 semantic-abstention cases.
- Structured code, tables, OCR blocks, repeated evidence, and duplicate paragraphs.

External URLs in `config/eval_articles.yaml` may supplement but cannot replace checked-in source fixtures.

### 16.2 Metrics

Calculate:

- lane routing recall and precision
- evidence-span recall
- average routes per article
- average extractor fan-out
- extractor input characters and tokens
- selected/source character ratio
- normalized-observable recall and precision
- Sigma logsource recall
- Sigma detection-atom recall and precision
- end-to-end cost and latency
- fallback rate
- source-validation rejection rate

### 16.3 Release gates

Before `shadow -> enforce`:

- Overall lane recall >= 0.98.
- Per-lane recall >= 0.95.
- Mixed-platform and minority-evidence route recall = 1.00 on the checked-in corpus.
- Strong deterministic signal recall = 1.00 on positive strong-signal fixtures.
- No article-platform contradiction suppresses a gold route.
- Normalized-observable recall loss is <= 1 percentage point versus legacy on paired cases.
- Sigma detection-atom recall loss is <= 1 percentage point versus legacy on paired cases.
- Source-invalid observables do not enter Sigma generation.
- Median extractor input characters decrease by at least 30 percent, or median extractor invocations decrease by at least 20 percent, without violating recall gates.
- Router internal fallback rate < 1 percent on the evaluation corpus.

Use paired article-level comparisons and report the sample size. Do not claim statistical significance for a corpus too small to support it.

## 17. UI and API behavior

Read `docs/contracts/ui-designer.md` before editing UI.

### 17.1 Workflow config UI

Add an Evidence Routing subsection inside the existing Extract Agent step. Do not rename/remove contract-grade IDs or functions.

Controls:

- mode
- semantic adjudication enabled
- adjudicator provider/model/temperature/top-p
- context before/after
- entity lookback
- ambiguous-candidate cap
- high-value zero-route threshold

Requirements:

- Semantic model controls disable when semantic adjudication is off.
- Enforce mode displays a concise warning that extractor eligibility is evidence-driven.
- Autosave, preset import/export, version history, and reset flows include all fields.

### 17.2 Execution trace UI

Inside Extract Agent trace, render:

- routing mode and fallback status
- lanes detected
- extractor dispatch list
- supporting block IDs and short source excerpts
- deterministic versus semantic basis
- skipped disabled extractors
- source-validation rejections
- article-platform disagreements
- shadow comparison summary

Use exact offsets for evidence navigation when routing metadata exists. Retain the current substring-based behavior for legacy executions.

Do not expose raw prompt text by default. Keep long source text collapsed.

### 17.3 API

Existing execution detail APIs must include the persisted routing summary without requiring a separate endpoint. If payload size becomes material, add an execution-scoped routing-detail endpoint and keep the default summary bounded.

## 18. Security and safety requirements

- Treat article blocks as untrusted content, including OCR and code blocks.
- Semantic router prompts must delimit source data and state that source instructions are data, not commands.
- The adjudicator has no tools and no network access.
- Validate all model-returned IDs against submitted candidates.
- Never interpolate model-returned lane or extractor names into dynamic imports or shell commands.
- Cap candidate count, source text size, model output size, and persisted trace size.
- Escape source excerpts in HTML templates.
- Do not log API keys, authorization headers, or provider secrets.
- Preserve current provider capability checks and cloud-only support.

## 19. Implementation sequence

Each task must leave the repository testable. Do not combine all phases into one unreviewable change.

### Task 0: Baseline and coordination

1. Run `git status --short --branch` and inspect existing changes.
2. Read current coordination/WIP notes if present.
3. Run targeted current tests for platform routing, workflow steps, attention preprocessors, config schema, snapshot completeness, preset lifecycle, and execution rendering.
4. Capture paired baseline outputs for the selected evaluation articles.
5. Do not modify unrelated working-tree files.

### Task 1: Contracts and source segmentation

Create:

- `src/services/evidence_routing/__init__.py`
- `contracts.py`
- `source_segmenter.py`
- tests for IDs, offsets, structured blocks, duplicate text, OCR, Unicode content, and malformed structure

Exit gate: every emitted body block satisfies exact substring and offset invariants.

### Task 2: Lane registry and deterministic detectors

Create registry and seven detector modules. Refactor Cmdline/ProcTree matching behind offset-aware APIs while retaining legacy wrappers.

Exit gate: detector unit tests and existing attention-preprocessor tests pass.

### Task 3: Route policy and bundle construction

Implement strong/ambiguous candidates, route merging, context selection, entity lookback, bundle rendering, and fallback reason codes.

Exit gate: deterministic plan snapshots are stable and no full article is present in normal bundles.

### Task 4: Semantic adjudicator

Add strict schema, provider call, output validation, timeout/error handling, and recall-widening fallback. Add canonical config and prompt support but keep disabled by default.

Exit gate: malformed, invented-ID, timeout, and abstention tests all widen routes.

### Task 5: Shadow workflow integration

Integrate routing inside `extract_agent_node()` with `Mode=shadow`. Persist the canonical routing manifest before legacy extraction. Do not alter current extractor calls.

Exit gate: paired shadow executions produce byte-equivalent legacy extractor inputs and equivalent outputs, apart from added trace fields.

### Task 6: Evidence dispatch and source validation

Extend `LLMService`, implement grouped bundle dispatch, source mapping, validation, result enrichment, and per-extractor fallback.

Exit gate: mocked extraction tests prove only routed evidence is sent and invalid source evidence is excluded from normalized observables.

### Task 7: Enforce mode

Switch eligibility and input selection only when `Mode=enforce`. Remove article-platform gating from that branch. Preserve legacy and shadow branches.

Exit gate: mixed-platform and minority-evidence integration tests pass, and mode rollback requires no restart beyond normal config loading behavior.

### Task 8: Config, presets, API, and UI

Add database migration, sync/async startup schema reconciliation, config/schema/load/save/snapshot wiring, immutable snapshot hydration, UI controls, execution trace details, eval-bundle projection, preset updates, and API tests.

Exit gate: no config field is UI-only or backend-only; full-snapshot presets validate.

### Task 9: Evaluation harness

Create the checked-in gold corpus and an evaluation command that compares legacy, shadow counterfactual, and enforce outputs. Produce machine-readable JSON and a concise Markdown report.

Suggested command:

```bash
uv run python scripts/evaluate_evidence_routing.py --modes legacy,shadow,enforce --output artifacts/evidence-routing-eval
```

The script must not mutate the active workflow config permanently. Restore state in `finally` and test restoration.

### Task 10: Documentation and rollout

Update:

- `docs/architecture/workflow-data-flow.md`
- `docs/features/os-detection.md`
- `docs/features/content-filtering.md`
- `docs/concepts/agents.md`
- `docs/reference/schemas.md`
- `docs/quickstart.md`
- relevant diagrams and changelog at release time

Document that Platform Detection is metadata/weak context in enforce mode.

## 20. Required tests

### 20.1 Unit

- Source segmentation and offset invariants.
- Stable block IDs.
- Every detector positive, negative, and ambiguous behavior.
- Lane registry uniqueness and extractor mapping.
- Semantic response validation and widening fallbacks.
- Route deduplication and bundle merging.
- Context adjacency and entity lookback.
- Source-evidence exact mapping and rejection.
- Config validation, migration defaults, and snapshot completeness.

### 20.2 Workflow/integration

- `legacy` reproduces current routing.
- `shadow` cannot change extractor inputs or outputs.
- `enforce` invokes only routed enabled extractors.
- Evidence-backed Windows route survives a Linux-heavy article classification.
- Platform-neutral network/query routes survive unknown platform classification.
- One article fans out to multiple platform evidence groups.
- Router failure falls back to legacy.
- High-value zero-route fallback is recorded.
- Disabled extractor remains disabled despite a route.
- Bundle-render failure falls back only for the affected extractor.
- Invalid source evidence never reaches Sigma grouping.
- Existing Sigma grouping, deduplication, pySigma validation, and novelty tests remain green.

### 20.3 API/UI

- Config round trip for every new field.
- Preset export/import and version restore.
- Execution routing summary serialization.
- UI controls bind to labels and autosave.
- Execution trace renders routes, excerpts, fallbacks, and disagreements.
- Contract-grade IDs/functions remain present.

### 20.4 Regression commands

Run the smallest targeted tests while implementing, then:

```bash
python3 run_tests.py smoke
python3 run_tests.py unit
python3 run_tests.py api
python3 run_tests.py integration
python3 run_tests.py ui
uv run ruff check
uv run ruff format --check
uv run mypy src --config-file pyproject.toml
mkdocs build
```

Browser-verify the config and execution trace against `http://localhost:8001`. Python changes require the documented container restarts.

### 20.5 Exact test touchpoints

Add new focused suites under `tests/services/evidence_routing/` for contracts, source segmentation, detectors, policy, adjudication, bundle construction, and source validation.

Extend these existing files rather than creating overlapping compatibility suites:

- `tests/unit/test_content_filter_chunking.py`
- `tests/services/test_cmdline_attention_preprocessor.py`
- `tests/services/test_proc_tree_attention_preprocessor.py`
- `tests/workflows/test_agentic_workflow_helpers.py`
- `tests/workflows/test_agentic_workflow_steps.py`
- `tests/workflows/test_platform_telemetry_phase_one.py`
- `tests/services/test_workflow_config_snapshot.py`
- `tests/unit/test_execution_snapshot_store.py`
- `tests/services/test_eval_bundle_service.py`
- `tests/unit/test_observable_traceability_regressions.py`
- `tests/api/test_workflow_config_api.py`
- `tests/playwright/workflow_config_persistence.spec.ts`
- `tests/playwright/execution_detail_tabs.spec.ts`

For manual verification in Hermes, prefix repository test commands with `PYTHONPATH=.` so the agent environment cannot shadow project dependencies.

## 21. Acceptance criteria

Implementation is complete only when all statements are true.

- [ ] Original article content is segmented into validated, source-addressable blocks.
- [ ] All body blocks receive deterministic routing inspection.
- [ ] Seven initial lanes map to existing specialized extractors through one registry.
- [ ] Strong evidence routes without LLM participation.
- [ ] Semantic adjudication is bounded, schema-validated, optional, and abstention-capable.
- [ ] Invalid or unavailable adjudication widens rather than drops ambiguous routes.
- [ ] Evidence bundles preserve primary, adjacent, and needed entity-definition context.
- [ ] Normal evidence dispatch excludes unrelated full-article text.
- [ ] Article-level platform classification cannot suppress evidence-backed routes in enforce mode.
- [ ] Extractor outputs are mapped to source block IDs and offsets.
- [ ] Source-invalid outputs do not enter normalized observables or Sigma generation.
- [ ] Existing Sigma generation, validation, grouping, and novelty behavior remains intact.
- [ ] Legacy and shadow modes remain available.
- [ ] Config snapshots and presets fully capture routing behavior.
- [ ] Routing behavior is read from the immutable execution snapshot, not mutable active configuration.
- [ ] Full/slim eval bundles and execution trace exports retain reproducible routing provenance.
- [ ] Stable observable IDs are dual-written without changing legacy list/index ordering.
- [ ] Execution traces show routing basis, evidence, fallback, and source-validation outcomes.
- [ ] Gold-corpus and paired end-to-end release gates pass.
- [ ] Cloud-only deployments require no LMStudio component.
- [ ] Relevant automated suites, lint, typecheck, docs build, and browser verification pass.

## 22. Explicit non-acceptance conditions

Reject the implementation if any is true:

- It chooses one dominant article platform before routing.
- It routes only fixed-size `ContentFilter` chunks without source-preserving context.
- It sends every article block to the semantic adjudicator.
- It trusts model-returned confidence numbers as probabilities.
- It allows the semantic model to invent lanes, extractors, or source IDs.
- It suppresses strong deterministic evidence based on article metadata.
- It silently falls back to full-article extraction.
- It stores offsets relative to reconstructed `filtered_content`.
- It replaces the seven specialized extractors or the Sigma validation pipeline.
- It requires LMStudio or another local provider.
- It activates enforce mode by default before evaluation gates pass.

## 23. Rollout and rollback

1. Ship code with `Mode=legacy`.
2. Enable `shadow` for evaluation executions.
3. Compare plans and downstream outputs against paired legacy baselines.
4. Fix detector and bundle errors until Section 16 gates pass.
5. Enable `enforce` for an explicit pilot preset or controlled environment.
6. Monitor fallback, source rejection, route recall proxies, cost, and latency.
7. Expand enforce rollout only after pilot review.
8. Roll back immediately by setting `Mode=legacy`; persisted execution records remain readable.
9. Consider removing Platform Detection from the critical workflow only in a separate specification after evidence-first production data proves it has no required operational role.

## 24. Deliverables

- Evidence routing package and tests.
- Config/database migration and updated full-snapshot presets.
- Workflow, LLM service, API, and UI integration.
- Checked-in gold routing corpus.
- Reproducible evaluation script and report format.
- Updated architecture, feature, schema, quickstart, and execution-trace documentation.
- Release-gate report showing legacy versus enforce metrics and sample size.
