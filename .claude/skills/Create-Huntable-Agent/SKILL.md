---
name: Create-Huntable-Agent
description: >
  Add a new extraction sub-agent to Huntable CTI Studio as a first-class peer of CmdlineExtract,
  ProcTreeExtract, HuntQueriesExtract, RegistryExtract, ServicesExtract, and ScheduledTasksExtract.
  Use this skill whenever the user asks
  to "add a new agent", "create a sub-agent", "wire up a new extractor", "add a new extraction
  type", or anything related to adding a new LangGraph extraction sub-agent to the agentic workflow
  pipeline. This covers the full stack: schema, config pipeline, migration, services, routes,
  UI templates, config display JS, presets, and tests.
---

# Create Huntable Agent

This skill guides you through adding a **new extraction sub-agent** to Huntable CTI Studio's
agentic workflow. The system uses a LangGraph-based pipeline with 7 steps, where Step 3
(ExtractAgent) is a supervisor that delegates to sub-agents. Each sub-agent has an optional
QA agent for validation.

## Before You Start

Read these files in order to understand the current codebase contract:

1. `AGENTS.md` — authoritative repo contract
2. `src/config/workflow_config_schema.py` — Pydantic v2 schema (source of truth)
3. `src/config/workflow_config_loader.py` — config load/export/import
4. `src/config/workflow_config_migrate.py` — v1→v2 migration

## Naming Convention

Every new agent needs **three identifiers** that must be consistent everywhere:

| Identifier | Example (Registry) | Pattern |
|-----------|-------------------|---------|
| **AgentName** (PascalCase) | `RegistryExtract` | `{Name}Extract` |
| **QAName** (PascalCase) | `RegistryQA` | `{Name}QA` |
| **canonical_alias** (snake_case) | `registry_artifacts` | `{descriptive_snake}` |

The canonical alias is used in workflow execution results, eval data directories, and
subagent normalization. It does NOT need to match the PascalCase name — it should be
descriptive of what the agent extracts (e.g., `hunt_queries`, `process_lineage`, `registry_artifacts`).

Also decide:
- **UI display name** — short human label (e.g., "Registry Artifacts", "Hunt Queries")
- **UI scope key** — lowercase key for SUBAGENT_SCOPE_MAP (e.g., `registry`, `huntqueries`)
- **Icon emoji** — for execution modals and eval cards (e.g., `🗝️`)

## Integration Checklist

There are **30+ integration points** across ~15 files. Read `references/integration-checklist.md`
for the complete file-by-file guide with code patterns to follow.

The checklist is organized into these layers:

### Layer 1: Schema & Config (5 files) — Do These First

These establish the agent's existence in the system. If these are wrong, nothing else works.

1. **`src/config/workflow_config_schema.py`** — Constants, validation, flatten
2. **`src/config/workflow_config_loader.py`** — Group lists, UI order, export/import
3. **`src/config/workflow_config_migrate.py`** — v1→v2 migration prefixes
4. **`src/utils/subagent_utils.py`** — Canonical alias normalization
5. **`src/utils/default_agent_prompts.py`** — Prompt file mapping

### Layer 2: Prompt Files (2 files) — Create These

6. **`src/prompts/{AgentName}`** — Extract prompt (JSON format)
7. **`src/prompts/{QAName}`** — QA prompt (JSON format)

> **Sibling prompt maintenance (mandatory):** When you add a new extractor, you must update
> ALL existing extractor prompts to acknowledge the new sibling in their Architecture Context
> block and define boundary rules in both directions — what the new agent owns, and what
> existing agents must not cross into. This applies to every current extractor:
> CmdlineExtract, ProcTreeExtract, RegistryExtract, ServicesExtract, ScheduledTasksExtract,
> HuntQueriesExtract, and any others present at the time. Verify the current list against
> `AGENT_NAMES_SUB` in `src/config/workflow_config_schema.py` before updating prompts.
> See `docs/contracts/extractor-standard.md` section 3 (ARCHITECTURE CONTEXT) for the
> required format.

> **QA prompt traceability (mandatory):** The new QA prompt (`src/prompts/{QAName}`) MUST
> include all three traceability checks in its `evaluation_criteria` array:
> - `source_evidence contains the verbatim source text supporting the extraction.`
> - `extraction_justification explains which rule triggered the extraction.`
> - `confidence_score is a numeric value in [0.0, 1.0].`
> Without these, the QA agent cannot verify factuality and will silently pass extractions
> it should flag. Use `[PASS]` prefix notation (ASCII) consistent with other QA prompts.

### Layer 3: Services & Workflow Engine (5 files)

8. **`src/services/llm_service.py`** — traceability block, JSON normalization, Langfuse output keys
9. **`src/services/lmstudio_model_loader.py`** — Sub-agent preload list
10. **`src/services/eval_bundle_service.py`** — Eval bundle export maps (3 locations)
10b. **`src/workflows/agentic_workflow.py`** — LangGraph execution: subagent maps, default results, QA name mapping (~5 spots)

### Layer 4: Web Routes (2 files)

11. **`src/web/routes/workflow_executions.py`** — Agent mapping + primary_agents set
12. **`src/web/routes/evaluation_api.py`** — Subagent maps, result extraction, model display (5 locations)

### Layer 5: UI Templates (7 files) — Most Complex

13. **`src/web/static/js/components/workflow-config-display.js`** — Selected Models panel
14. **`src/web/templates/workflow.html`** — ~40 insertion points (see `references/workflow-html-checklist.md`)
15. **`src/web/templates/agent_evaluation.html`** — Eval card (1 insertion)
16. **`src/web/templates/agent_evals.html`** — Dropdown, SUBAGENT_MAP, QA ternary, modal rendering (~7 insertions)
17. **`src/web/templates/subagent_evaluation.html`** — Purpose description block
18. **`src/web/templates/workflow_executions.html`** — Execution results entry
19. **`src/web/templates/base.html`** — Cache-busting version bump on JS

### Layer 6: Config & Data (2 areas)

20. **`config/presets/AgentConfigs/quickstart/*.json`** — All quickstart presets
    > **Critical**: `Prompt.prompt` and `QAPrompt.prompt` must be populated with the full
    > content of `src/prompts/{Agent}` and `src/prompts/{QA}`. Use the script in the
    > checklist — do NOT leave these as empty strings. An empty preset prompt silently
    > leaves users with a broken agent after import. See Pitfall #10.
    >
    > **QA temperature**: Set `Temperature` to `0.1` for all QA agents across all 8 presets.
    > Older presets may have 0.3 for some QA entries — match the newer uniform standard.
    >
    > **Preset description**: If you copy an existing preset as a template, update the
    > `Description` field. Stale values like `"Exported preset"` are flagged by the quality test.
21. **`config/eval_articles_data/{canonical_alias}/`** — Eval data directory

### Layer 7: Tests (5+ files)

22. **`tests/config/test_{agent}_wiring.py`** — New: full-stack wiring tests (schema, config, migration, subagent utils, prompts, presets, eval data, Langfuse keys). The `TestPresetFiles` class **must** assert that `Prompt.prompt` and `QAPrompt.prompt` are non-empty strings — not just that the section key exists. See the ScheduledTasksExtract wiring test for the pattern.
23. **`tests/config/test_workflow_config_migrate.py`** — Update agent count assertion AND extend `_MINIMAL_AGENT_MODELS` with `{Agent}_model` and `{Agent}QA` entries (otherwise prompt-symmetry validation fails on minimal-config tests)
24. **`tests/config/test_workflow_config_export.py`** — Add section to UI-ordered fixture
25. **`tests/config/test_workflow_config_import_export_fidelity.py`** — Add the new agent block to `_full_ui_ordered_preset` plus `FIDELITY_<AGENT>_ENABLED` / `FIDELITY_<AGENT>_QA_ENABLED` constants. Skipping this triggers the phantom-DisabledAgents bug (see Pitfall #13).
26. **`tests/config/test_backfill_sub_agents.py`** — Add new agent name to the `BACKFILL_AGENTS` list at top of file. Tests are parametrized across that list; one entry adds 11 new test cases automatically.
27. **`tests/config/test_subagent_traceability_contract.py`** — Three coupled additions: `MIGRATED_QA_AGENTS`, `base_for_qa` map, and `MIGRATED_EXTRACT_AGENTS` (only if envelope uses `count`, not a variant). See Pitfall #16.
28. **`tests/worker/test_test_agents_provider_resolution.py`** — Already exists; verify the parametrized cross-agent test includes the new agent name
29. **`tests/integration/test_lmstudio_minimal_e2e.py`** — Append new agent to the `disabled_agents` list (around line 189) so the minimal e2e stays minimal (see Pitfall #14)
30. **`tests/workflows/test_conversation_log_truncation.py`** — Already exists; no per-agent changes needed (truncation is agent-agnostic)

### Layer 8 (Conditional): Sigma `canonical_class` — only if the extractor's telemetry generates Sigma rules

**Skip this layer if your extractor does not produce artifacts that SigmaAgent turns into
Sigma rules.** The extractor → canonical_class link is **not 1:1**: `CmdlineExtract` and
`ProcTreeExtract` both map to `process_creation` (many-to-one), and `HuntQueriesExtract`
maps to **nothing** (it emits hunt queries, not detections). Gate this layer on the
question *"does this telemetry generate Sigma rules?"* — it is conditional, not mandatory.

The Sigma novelty/dedup engine groups rules into **canonical telemetry classes**
(`CANONICAL_CLASS_REGISTRY` in `sigma_semantic_similarity/sigma_similarity/canonical_logsource.py`)
so a proposed rule is only compared against rules in the same class. A rule whose `logsource`
matches no registered class falls to the weaker `logsource_key` fallback and dedups poorly.
Current mappings:

| Extractor | Sigma telemetry / canonical_class |
|-----------|-----------------------------------|
| CmdlineExtract, ProcTreeExtract | `windows`/`linux`/`macos.process_creation` |
| RegistryExtract | `windows.registry_event` |
| ServicesExtract | `windows.service` |
| ScheduledTasksExtract | `windows.scheduled_task` |
| HuntQueriesExtract | none (produces hunt queries, not Sigma rules) |

If your extractor introduces a NEW telemetry family (e.g. a hypothetical `DnsExtract`
→ `*.dns_query`), wire it:

1. **Registry tuple** — add a `(product, category, service, event_id)` entry to
   `CANONICAL_CLASS_REGISTRY` (`None` = "any" for a slot). **Group by field *schema*, not
   by logsource label**: two sources that log the same observable under *different* field
   names (e.g. DNS `query` vs `QueryName`) are not comparable and belong in separate classes
   until a field alias bridges them.
2. **Field aliases** — add the family's field names to `FIELD_ALIAS_MAP` in
   `sigma_semantic_similarity/sigma_similarity/atom_extractor.py` so equivalent fields
   normalize to one atom identity. **Keep it in sync with the on-the-fly map** in
   `src/services/sigma_novelty_service.py` (`FIELD_ALIAS_MAP`) — there are currently two
   extractors that must agree, and a silent divergence between them is a recurring bug class
   (the "collapse the two extractors" work will eventually unify them; until then, edit both).
3. **Keyword selections already work on both paths** — if the family's rules use keyword-list
   selections (`keywords: [...]`, webserver/XSS/Log4j-style), both extractors model them as
   field-less `contains` atoms (Conditional B, commit `5514381b`), so there is no empty-atom
   trap. `EventCode` is treated as `EventID` during resolution (the Splunk/EventLog field name).
4. **Test** — add resolution + comparability + mismatch tests to
   `tests/sigma_semantic_similarity/test_canonical_class.py` (the new logsource resolves to the
   class; two same-class rules score comparable; a different-class rule scores `0` with
   `canonical_class_mismatch`).
5. **Operational — NOT just a restart** — `sigma_semantic_similarity` is **COPY'd into the
   Docker image at build time, not bind-mounted**. A registry/alias change is live only after
   `docker compose build && docker compose --profile tools build cli && docker compose up -d`,
   then `./run_cli.sh sigma recompute-atoms` to repopulate `canonical_class`/`positive_atoms`.
   Verify the per-class count rises post-recompute. (Contrast: `src/` IS bind-mounted, so the
   on-the-fly `FIELD_ALIAS_MAP` edit there takes effect on a plain restart — land both map edits
   together and rebuild so the two paths never drift in production.)

See `docs/features/sigma-rules.md` (modeled-class list) and the Coverage-Chain addenda in
`docs/development/sigma-novelty-audit-followup-2026-06-01.md` for the live registry and the
field-schema-grouping rationale.

## Common Pitfalls

These are real bugs encountered during the RegistryExtract and ScheduledTasksExtract implementations:

### 1. QA_AGENT_TO_BASE Orphan Detection
If you add a QA agent but forget to add the base→QA mapping in `BASE_AGENT_TO_QA`,
the schema validator derives the base name by stripping "QA" suffix — e.g., `RegistryQA`
becomes `Registry` not `RegistryExtract`. This causes: `"Orphan QA agent RegistryQA:
base agent Registry must exist"`. Fix: always add to `BASE_AGENT_TO_QA`.

### 2. Empty String vs Undefined in JS Backfill
Config values for new agents come back as `""` (empty string) from the API, not `undefined`.
JavaScript's `!am[key]` is falsy for `""` but the backfill condition needs explicit
`|| am[key] === ''` to catch it.

### 3. Browser Static File Caching
After editing `workflow-config-display.js`, the browser serves the cached version.
Always bump the cache-busting `?v=` parameter in `base.html`.

### 4. Sub-Agent Model Fallback Tiers
Extract sub-agents and QA agents use **different model tiers**:
- Extract sub-agents → fall back to `ExtractAgent`'s model (e.g., qwen3-8b)
- QA agents → fall back to a **peer QA agent**'s model (e.g., qwen3-14b)

Never use ExtractAgent as the fallback for QA agents.

### 5. Migration Agent Count
`test_workflow_config_migrate.py` has a hardcoded agent count assertion.
Adding 2 agents (extract + QA) means incrementing by 2.

### 6. UI-Ordered Export Fixtures
`test_workflow_config_export.py` has fixtures that must include the new agent's
section with all required keys, or import validation fails.

### 7. Sub-Agent Model Dropdown Stays Empty (LMStudio)
`loadAgentModels()` in `workflow.html` calls `getAgentConfigs()` to check whether any
agent uses LMStudio before hitting the `/api/lmstudio-models` endpoint. If the new agent
is **not registered in `AGENT_CONFIG`** (workflow.html Category 2.1), the API call may
be skipped and the model dropdown will show only "Use Extract Agents Fallback Model"
with no selectable models — even when LMStudio is running and the provider is set to
LMStudio. Fix: ensure AGENT_CONFIG contains the new agent's entry with the correct
`providerKey` before testing.

### 8. Old Presets Reject New Agent on Import
`validate_ui_ordered_preset_strict` runs **before** `ui_ordered_to_v2`, so a preset
saved before this agent existed will fail with `"missing or null: {Agent}"` even though
`ui_ordered_to_v2` would have defaulted it gracefully. Fix: add a default block for the
new agent to `_OPTIONAL_SUB_AGENT_SECTIONS` in `workflow_config_loader.py` (checklist
insertion H). This runs before strict validation and injects a disabled default so the
preset imports cleanly.

### 9. Prompt File Only Seeds the DB Once
`src/prompts/{Agent}` is read **only on first DB seed** — when no workflow config exists
in the database. After that, the active prompt lives in the DB. There is **no per-agent
"Reset to default" button** in the UI prompt editor. Three real options to refresh disk
edits into a live DB:

1. **Re-import a quickstart preset** (recommended, non-destructive) — but this only
   propagates the new content if you also regenerated the preset's embedded prompt
   string after editing the disk file. See Pitfall #12.
2. **Manual paste** — open each affected agent's prompt editor in the UI, paste the
   disk content, save. Tedious but surgical.
3. **Delete the workflow config DB row** to trigger re-seed (destructive — wipes any
   custom edits in the DB).

Also: include `/no_think` in the `role` field for Qwen3 models — without it, Qwen3 emits
`<think>...</think>` reasoning blocks before JSON, breaking `json.loads()`.

### 10. Preset Prompt.prompt Left Empty — All Evals Silently Broken
When adding a new agent section to all 8 quickstart presets, it is easy to populate the
structural keys (`Provider`, `Model`, `Temperature`) but leave `Prompt.prompt` and
`QAPrompt.prompt` as `""`. This passes import validation — the schema doesn't require
non-empty prompts — but every user who imports a quickstart preset gets an agent with no
instructions and no error message. The agent runs, produces empty or nonsensical output,
and there is no log entry pointing to the root cause.

The integration checklist script populates the fields from the prompt files on disk. Use it.
Do not hand-write or copy-paste the JSON. After running the script, verify with:
`json.loads(data["{Agent}"]["Prompt"]["prompt"])` must succeed and return a non-empty dict.
The `TestPresetFiles` class in the wiring test must assert `prompt_val` is truthy.

### 11. Structured Extractor — `value` Field Not Required if Domain Identity Fields Present
`_validate_extraction_prompt_config` in `llm_service.py` checks every item in `json_example`
for the four traceability fields. For simple extractors, `value` is required (the extracted
artifact). For **structured extractors** whose items have domain-specific identity fields
(e.g., `task_name`, `task_path`, `trigger` for ScheduledTasksExtract, or `indicator_type`,
`indicator_value` for network extractors), `value` is **not** required — those domain fields
satisfy the identity contract.

If you use structured fields but also include a `value` key, that is fine and also passes.
If you use structured fields but omit `value`, the validator checks `has_domain_fields` and
skips the `value` requirement automatically.

What causes a hard failure: including a generic `value` field in the schema while the
`json_example` items do NOT have it, or omitting `source_evidence` / `extraction_justification`
/ `confidence_score` (these three are always required). When the validator rejects the config,
every eval result for that agent will be `MESSAGES_MISSING / infra_failed` before any LLM
call — it looks like a model or provider problem but is actually a schema rejection.

### 12. Sibling Preset Embedded Prompts Go Stale Silently
The mandatory "Sibling prompt maintenance" rule requires you to update every existing
extractor's disk prompt with an Architecture Context boundary for the new agent. What's
not obvious: each disk prompt is **also** embedded as a JSON-encoded string in all 8
quickstart presets (`{Agent}.Prompt.prompt`). Editing the disk file does NOT update the
embedded copy.

A user who imports a quickstart preset *after* you ship will silently overwrite their
DB prompts with the stale embedded versions, rolling back your sibling updates. Mitigation
is mechanical — after updating disk prompts, regenerate the embedded copies:

```python
import json
from pathlib import Path
PRESET_DIR = Path("config/presets/AgentConfigs/quickstart")
PROMPT_DIR = Path("src/prompts")
AGENTS_TO_SYNC = ["CmdlineExtract", "ProcTreeExtract", "RegistryExtract",
                  "ServicesExtract", "HuntQueriesExtract", "{NewAgent}"]
src = {a: json.load(open(PROMPT_DIR / a)) for a in AGENTS_TO_SYNC}
for p in sorted(PRESET_DIR.glob("*.json")):
    d = json.load(open(p))
    for a in AGENTS_TO_SYNC:
        if a in d:
            d[a]["Prompt"]["prompt"] = json.dumps(src[a])
    json.dump(d, open(p, "w"), indent=2)
```

Then add the new agent to `MIGRATED_EXTRACT_AGENTS` in
`tests/config/test_subagent_traceability_contract.py` to lock against future drift
(see Pitfall #16 for envelope-shape caveats).

### 13. Fidelity Test Causes Phantom DisabledAgents
`tests/config/test_workflow_config_import_export_fidelity.py::_full_ui_ordered_preset`
must include the new agent's section. If you forget, `_backfill_ui_ordered_sub_agents`
injects it with `Enabled=False` (correct, by design), but `ui_ordered_to_v2` then lifts
that into `Execution.DisabledAgents`. The result: `test_import_enforces_all_settings`
fails with `AssertionError: ['NewAgent'] == []` — confusing because nothing in the
fixture explicitly disables anything. Fix: add a full agent block plus
`FIDELITY_<AGENT>_ENABLED = True` and `FIDELITY_<AGENT>_QA_ENABLED = True` constants.

### 14. E2E Test disabled_agents List
`tests/integration/test_lmstudio_minimal_e2e.py` (around line 189) hardcodes which
sub-agents to disable to keep the e2e fast and minimal. New agents must be appended
to that list, otherwise the e2e fans out to all extractors and the run gets slower
plus introduces a new failure surface.

### 15. Don't Full-String-Match `llm_service.py` Source in Tests
The original RegistryExtract wiring test had:
```python
assert 'for key in ["process_lineage", "sigma_queries", "registry_artifacts", "windows_services"]' in source
```
This shattered the moment ScheduledTasksExtract was added to that list. Every future
extractor would break the same assertion. Use **substring** assertions:
```python
assert '"registry_artifacts"' in source
assert '"scheduled_tasks"' in source
```
Durable across additions and still proves the key is referenced.

### 16. Three Coupled Edits in `test_subagent_traceability_contract.py`
Adding a QA agent here requires touching all three places, in order:
1. **`MIGRATED_QA_AGENTS`** list — add `{NewAgent}QA`
2. **`base_for_qa`** map at `test_preset_qa_prompt_synced` (~line 262) — add
   `"{NewAgent}QA": "{NewAgent}Extract"`. Missing entry causes `KeyError`, not a clean
   assertion failure.
3. **`MIGRATED_EXTRACT_AGENTS`** list — but **only if** the agent's `json_example`
   envelope uses `count` as the integer field. If it uses `query_count`, `task_count`,
   or any other variant, `test_json_example_has_expected_top_level_key` fails. If your
   agent diverges, leave it out and add a comment documenting why (HuntQueriesExtract
   is the precedent).

## What Works Automatically

These areas require **no per-agent code changes** once Layers 1–3 are complete:

- **Test button (Celery task)** — `src/worker/tasks/test_agents.py` resolves
  `{Agent}_provider` and `{Agent}_model` dynamically from `agent_models` in the
  saved config. Extract subagents always run at temperature=0.0 (deterministic);
  top_p is not configurable for extract agents. No per-agent code needed —
  but **verify** the Test button uses the correct provider after wiring a new agent.
  If it falls back to ExtractAgent's provider, the resolution keys don't match
  (check `{Agent}_provider` exists in the DB's `agent_models` JSONB).

- **Langfuse tracing** — `log_llm_completion` in `llm_service.py` traces every LLM call
  automatically. The agent name and model are captured from the call context. No
  per-agent Langfuse wiring needed.

- **Live execution view (SSE)** — The `/executions/{id}/stream` SSE endpoint streams
  generic execution state. Sub-agent results flow through the same state structure and
  appear in the live view automatically once the workflow engine (Layer 3b) is wired.

- **Error log capture** — `workflow_executions.py` routes errors generically via
  `agent_mapping`. As long as the new agent is in that map (checklist item 11), error
  logs appear in the execution detail view without further changes.

## Verification Steps

After all edits, verify in this order:

1. **Run wiring tests**: `python3 run_tests.py unit --paths tests/config/test_{agent}_wiring.py`
2. **Run all config tests**: `python3 run_tests.py unit --paths tests/config/`
3. **Preset backward compat**: Load a preset file saved *before* this agent was added
   (one without the `{Agent}` section) via the UI import flow or `load_workflow_config()`.
   Verify it imports without error and the new agent defaults to disabled.
4. **Test button verification**: Click "Test {Agent}" in the config panel with a known article.
   Verify the test uses the correct provider/model (not ExtractAgent's fallback). Check the
   test modal output — if it says "Invalid request to LMStudio" when you configured OpenAI,
   the `{Agent}_provider` key isn't being read from `agent_models` in the DB.
5. **Disk -> Preset -> DB -> Runtime chain** — the only verification that catches Pitfall #12 end-to-end:
   ```python
   import json
   from src.database.manager import DatabaseManager  # adapt to your DB access pattern
   db_prompt = json.loads(db_workflow_config["agent_prompts"]["{NewAgent}"]["prompt"])
   disk_prompt = json.load(open("src/prompts/{NewAgent}"))
   assert db_prompt == disk_prompt, "Disk prompt did not reach the live DB"
   ```
   Run this *after* importing one of the quickstart presets onto a fresh DB. If it fails,
   you forgot to regenerate the embedded preset prompt (see Pitfall #12).
6. **Browser verification** (requires running server at http://127.0.0.1:8001/workflow#config):
   - Workflow Overview shows correct sub-agent count
   - Selected Models panel shows new agent + QA with correct provider/model
   - Clicking Extract Agent → expanding new sub-agent shows provider dropdown, model dropdown, prompt editor, QA toggle, test button
   - **LMStudio model dropdown is populated** (not just "Use Extract Agents Fallback Model") when LMStudio is selected as provider — this confirms AGENT_CONFIG registration is correct and `loadAgentModels()` is calling the LMStudio API
   - No console errors mentioning the new agent name
7. **Check for console errors**: Open browser DevTools, reload, search for agent-related errors
8. **Preset export diff** (optional but useful): Export the live config from the UI, then run:
   ```
   EXPORT_FILE=~/Downloads/workflow-preset-*.json PRESET_NAME=Quickstart-LMStudio-Qwen3 \
   python3 run_tests.py unit --path tests/config/test_preset_export_comparison.py
   ```
   This diffs the live export against the named quickstart preset and flags any field
   divergence. Useful to confirm all 8 presets stayed in sync after adding the new agent.
