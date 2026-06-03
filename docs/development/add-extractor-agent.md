# Adding an Extraction Sub-Agent

This page is a companion reference for the **`Create-Huntable-Agent` skill** — the Claude Code skill that guides you through wiring a new extractor into the LangGraph pipeline.

The interactive wiring map below visualises every integration point across all 7 layers, all 17 known pitfalls, and the 4 behaviours that are auto-wired for free once Layers 1–3 are complete.

[Open Wiring Map :material-arrow-top-right:](./create-agent-wiring-map.html){ .md-button .md-button--primary target="_blank" }

---

## What the wiring map covers

| Layer | Files | Key concern |
|-------|-------|-------------|
| 1 — Schema & Config | `workflow_config_schema.py`, `workflow_config_loader.py`, `workflow_config_migrate.py`, `subagent_utils.py`, `default_agent_prompts.py` | If these are wrong, nothing downstream works |
| 2 — Prompt Files | `src/prompts/{Agent}` (new), `src/prompts/{QA}` (new), all existing extractor prompts | Sibling Architecture Context maintenance is mandatory |
| 3 — Services & Workflow Engine | `llm_service.py`, `lmstudio_model_loader.py`, `eval_bundle_service.py`, `agentic_workflow.py` | LangGraph graph wiring, traceability validation, Langfuse keys |
| 4 — Web Routes | `workflow_executions.py`, `evaluation_api.py` | 5 locations in evaluation_api.py alone |
| 5 — UI Templates | `workflow.html` (~40 pts), `workflow-config-display.js`, `agent_evals.html`, `workflow_executions.html`, `base.html`, and more | Most complex layer — cache-busting and dual-template drift are common failure modes |
| 6 — Config & Data | All 8 quickstart presets (full prompt embedding), eval articles directory | Preset `Prompt.prompt = ""` silently breaks every user who imports the preset |
| 7 — Tests | 1 new wiring test + 8 existing files to update | `TestSubAgentsRenderingArray` and `TestPresetFiles` are the key regression guards |
| 8 — Sigma `canonical_class` *(conditional)* | `canonical_logsource.py`, both `FIELD_ALIAS_MAP`s, `test_canonical_class.py` | Only if the extractor's telemetry generates Sigma rules — see below |

## Naming identifiers

Decide all six before writing any code — they must be consistent everywhere:

| Identifier | Pattern | Example |
|------------|---------|---------|
| `AgentName` | `{Name}Extract` | `RegistryExtract` |
| `QAName` | `{Name}QA` | `RegistryQA` |
| `canonical_alias` | `{descriptive_snake}` | `registry_artifacts` |
| UI display name | Human label | `"Registry Artifacts"` |
| UI scope key | lowercase | `registry` |
| Icon emoji | — | 🗝️ |

!!! warning "canonical_alias is not derived from AgentName"
    The alias should describe what the agent *extracts*, not mirror the PascalCase name.
    `HuntQueriesExtract` uses `hunt_queries`, not `hunt_queries_extract`.

## Highest-severity pitfalls

These five pitfalls are flagged **High** because they produce silent failures — the agent appears to work but outputs nothing meaningful, or old presets break on import with no clear error:

1. **Old Presets Reject New Agent on Import** — add agent to `_OPTIONAL_SUB_AGENT_SECTIONS` in `workflow_config_loader.py` so pre-existing presets get a disabled default injected before strict validation.
2. **Prompt File Seeds DB Once Only** — `src/prompts/{Agent}` is read only on first DB seed. After that the DB is authoritative. Refresh via preset re-import (only if embedded prompt was regenerated) or manual paste.
3. **Preset `Prompt.prompt` Left Empty** — use the checklist script to embed prompts; do not hand-write. `TestPresetFiles` must assert the value is truthy.
4. **Sibling Preset Embedded Prompts Go Stale** — editing disk prompts does not update the JSON-encoded strings in all 8 preset files. Run the regeneration script after any disk prompt change.
5. **Dual-Template Execution Card Drift** — `workflow.html` (Category 11) and `workflow_executions.html` both maintain a `subAgents` rendering array. Missing from `workflow.html` silently drops the execution detail card. `TestSubAgentsRenderingArray` locks both.

## Sigma `canonical_class` (conditional Layer 8)

If the new extractor's telemetry produces Sigma rules — most do; exceptions like
`HuntQueriesExtract` emit hunt queries, not detections — wire the family into the novelty/dedup
engine's `CANONICAL_CLASS_REGISTRY` so generated rules are compared **within their telemetry
class** instead of the weak `logsource_key` fallback. The link is not 1:1: `CmdlineExtract` and
`ProcTreeExtract` both map to `process_creation`.

This is **Layer 8** in the skill's integration checklist — *conditional*, not part of the
mandatory 7-layer wiring. It touches:

- `sigma_semantic_similarity/sigma_similarity/canonical_logsource.py` — a
  `(product, category, service, event_id)` registry tuple, grouped by **field schema** (sources
  logging the same observable under different field names need separate classes).
- The two `FIELD_ALIAS_MAP`s — `atom_extractor.py` (precomputed) and `sigma_novelty_service.py`
  (on-the-fly) — kept in sync so the two extractors agree.
- `tests/sigma_semantic_similarity/test_canonical_class.py` — resolution + comparability + mismatch.

Because `sigma_semantic_similarity` is **COPY'd into the image, not bind-mounted**, a change is
live only after an image rebuild + `./run_cli.sh sigma recompute-semantics` — not a plain
restart. See [Sigma rules](../features/sigma-rules.md) for the live modeled-class list.

## See also

- [`references/integration-checklist.md`](../contracts/extractor-standard.md) — file-by-file insertion guide with code patterns
- [`references/workflow-html-checklist.md`](../contracts/extractor-standard.md) — the ~40-point `workflow.html` checklist
- [Extractor Standard Contract](../contracts/extractor-standard.md) — Architecture Context block format, traceability field requirements
- [Agent Evals](../features/agent-evals.md) — how eval data directories and ground truth files are consumed
