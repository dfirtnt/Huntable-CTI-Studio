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

8. **`src/services/llm_service.py`** — top_p fallback, traceability block, JSON normalization, Langfuse output keys
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
    > leaves users with a broken agent after import.
21. **`config/eval_articles_data/{canonical_alias}/`** — Eval data directory

### Layer 7: Tests (5+ files)

22. **`tests/config/test_{agent}_wiring.py`** — New: full-stack wiring tests (schema, config, migration, subagent utils, prompts, presets, eval data, Langfuse keys)
23. **`tests/config/test_workflow_config_migrate.py`** — Update agent count assertion
24. **`tests/config/test_workflow_config_export.py`** — Add section to UI-ordered fixture
25. **`tests/config/test_backfill_sub_agents.py`** — Already exists; verify it covers the new agent's section in `_OPTIONAL_SUB_AGENT_SECTIONS` (backfill injection, immutability, strict validation integration)
26. **`tests/worker/test_test_agents_provider_resolution.py`** — Already exists; verify the parametrized cross-agent test includes the new agent name
27. **`tests/workflows/test_conversation_log_truncation.py`** — Already exists; no per-agent changes needed (truncation is agent-agnostic)

## Common Pitfalls

These are real bugs encountered during the RegistryExtract implementation:

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
in the database. After that, the active prompt lives in the DB and is edited via the UI.
If you iterate on the prompt file after the DB is seeded, the changes have no effect.
Fix: edit via the UI prompt editor, or delete the workflow config row to trigger re-seed
(destructive). Also: include `/no_think` in the `role` field for Qwen3 models — without
it, Qwen3 emits `<think>...</think>` reasoning blocks before JSON, breaking `json.loads()`.

## What Works Automatically

These areas require **no per-agent code changes** once Layers 1–3 are complete:

- **Test button (Celery task)** — `src/worker/tasks/test_agents.py` resolves
  `{Agent}_provider`, `{Agent}_model`, `{Agent}_temperature`, and `{Agent}_top_p`
  dynamically from `agent_models` in the saved config. No per-agent code needed —
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
5. **Browser verification** (requires running server at http://127.0.0.1:8001/workflow#config):
   - Workflow Overview shows correct sub-agent count
   - Selected Models panel shows new agent + QA with correct provider/model
   - Clicking Extract Agent → expanding new sub-agent shows provider dropdown, model dropdown, temperature, top_p, prompt editor, QA toggle, test button
   - **LMStudio model dropdown is populated** (not just "Use Extract Agents Fallback Model") when LMStudio is selected as provider — this confirms AGENT_CONFIG registration is correct and `loadAgentModels()` is calling the LMStudio API
   - No console errors mentioning the new agent name
5. **Check for console errors**: Open browser DevTools, reload, search for agent-related errors
