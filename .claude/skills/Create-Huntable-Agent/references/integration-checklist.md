# Integration Checklist — Add a New Extraction Sub-Agent

This document lists every file and exact location that must be modified when adding a new
extraction sub-agent. Use an existing agent (e.g., `HuntQueriesExtract`) as the template
for each insertion.

Throughout this document:
- `{Agent}` = PascalCase agent name (e.g., `RegistryExtract`)
- `{QA}` = PascalCase QA name (e.g., `RegistryQA`)
- `{alias}` = snake_case canonical alias (e.g., `registry_artifacts`)
- `{scope}` = lowercase scope key (e.g., `registry`)
- `{prefix}` = lowercase prefix for HTML IDs (e.g., `registryextract`)
- `{qa_prefix}` = lowercase QA prefix (e.g., `registryqa`)
- `{display}` = human-readable display name (e.g., `Registry Artifacts`)
- `{icon}` = emoji icon (e.g., `🗝️`)

---

## Layer 1: Schema & Config Pipeline

### 1. `src/config/workflow_config_schema.py`

**4 insertion points:**

```python
# A) Add to AGENT_NAMES_SUB list
AGENT_NAMES_SUB = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "{Agent}"]

# B) Add to AGENT_NAMES_QA list
AGENT_NAMES_QA = ["RankAgentQA", "CmdlineQA", "ProcTreeQA", "HuntQueriesQA", "{QA}"]

# C) Add to BASE_AGENT_TO_QA mapping (CRITICAL — orphan detection depends on this)
BASE_AGENT_TO_QA = {
    ...
    "{Agent}": "{QA}",
}

# D) In flatten_for_llm_service(), add to both sub_agents and qa_agents sets
#    Search for "sub_agents = {" and "qa_agents = {"
```

### 2. `src/config/workflow_config_loader.py`

**7 insertion points:**

```python
# A) EXTRACT_AGENTS list
EXTRACT_AGENTS = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "{Agent}"]

# B) QA_AGENTS list
QA_AGENTS = ["RankAgentQA", "CmdlineQA", "ProcTreeQA", "HuntQueriesQA", "{QA}"]

# C) AGENTS_ORDER_UI list (insert before "SigmaAgent")
"HuntQueriesQA",
"{Agent}",
"{QA}",
"SigmaAgent",

# D) UI_ORDERED_TOP_LEVEL_ORDER list (insert before "SigmaAgent")
"HuntQueriesExtract",
"{Agent}",
"SigmaAgent",

# E) _UI_ORDERED_REQUIRED list — add tuple with required keys
(
    "{Agent}",
    ["Enabled", "Provider", "Model", "Temperature", "TopP", "Prompt",
     "QAEnabled", "QA", "QAPrompt"],
),

# F) v2_to_ui_ordered_export() — add to the base/qa_name loop
for base, qa_name in [
    ("CmdlineExtract", "CmdlineQA"),
    ("ProcTreeExtract", "ProcTreeQA"),
    ("HuntQueriesExtract", "HuntQueriesQA"),
    ("{Agent}", "{QA}"),
]:

# G) ui_ordered_to_v2() — same loop pattern exists there too, add the same tuple

# H) _OPTIONAL_SUB_AGENT_SECTIONS — add a default block so old presets import cleanly.
#    This list is consumed by _backfill_ui_ordered_sub_agents() which runs BEFORE
#    validate_ui_ordered_preset_strict(). Without it, any preset saved before this agent
#    was added will fail import with "missing or null: {Agent}".
_OPTIONAL_SUB_AGENT_SECTIONS: list[tuple[str, dict]] = [
    ...,
    (
        "{Agent}",
        {
            "Enabled": False,
            "Provider": "",
            "Model": "",
            "Temperature": 0.0,
            "TopP": 0.9,
            "Prompt": {"prompt": "", "instructions": ""},
            "QAEnabled": False,
            "QA": {"Provider": "", "Model": "", "Temperature": 0.1, "TopP": 0.9},
            "QAPrompt": {"prompt": "", "instructions": ""},
        },
    ),
]
```

### 3. `src/config/workflow_config_migrate.py`

**1 insertion point:**

```python
# Add two entries to _AGENT_FLAT_PREFIXES
_AGENT_FLAT_PREFIXES = [
    ...
    ("{Agent}", "{Agent}", "{Agent}_model"),
    ("{QA}", "{QA}", "{QA}"),
]
```

### 4. `src/utils/subagent_utils.py`

**2 insertion points:**

```python
# A) AGENT_TO_SUBAGENT — maps lowercase agent name to canonical alias
AGENT_TO_SUBAGENT = {
    ...
    "{prefix}": "{alias}",
}

# B) SUBAGENT_CANONICAL — add all reasonable aliases
SUBAGENT_CANONICAL = {
    ...
    "{alias}": "{alias}",                    # canonical form
    "{alias_no_underscores}": "{alias}",     # e.g., "registryartifacts"
    "{alias_with_hyphens}": "{alias}",       # e.g., "registry-artifacts"
    "{prefix}": "{alias}",                   # e.g., "registryextract"
    "{scope}": "{alias}",                    # e.g., "registry" (short form)
}
```

### 5. `src/utils/default_agent_prompts.py`

**1 insertion point:**

```python
AGENT_PROMPT_FILES = {
    ...
    "{Agent}": "{Agent}",
    "{QA}": "{QA}",
    ...
}
```

---

## Layer 2: Prompt Files

### 6. `src/prompts/{Agent}`

Create a JSON file (no extension) with this structure:

```json
{
  "role": "You are a deterministic {description} extraction agent for CTI articles...",
  "user_template": "Title: {title}\nURL: {url}\n\nContent:\n{content}\n\n{instructions}",
  "task": "Extract ONLY explicit {description} that appear in the provided content.",
  "json_example": "{ ... example output ... }",
  "instructions": "... detailed extraction rules, output schema, validation ..."
}
```

Copy the structure from an existing agent like `CmdlineExtract` or `RegistryExtract` and
adapt the extraction rules, output schema, and validation for the new domain.

Key requirements for the prompt:
- Define a clear output JSON schema with a named array (e.g., `registry_artifacts`, `cmdline_items`)
- Include a `count` field in the output schema
- Define the empty-result format: `{"{alias}":[],"count":0}`
- Specify explicit inclusion/exclusion criteria
- Include a final validation section
- Include `/no_think` in the `role` field — Qwen3 models emit `<think>...</think>` reasoning
  blocks before JSON output by default, which breaks `json.loads()`. The `/no_think` token
  suppresses this. All extraction prompts targeting LMStudio/Qwen3 must include it.

> **Prompt deployment**: `src/prompts/{Agent}` is only read on **first DB seed** (when no
> workflow config exists in the database). After that, the active prompt lives in the DB
> config and is edited via the UI prompt editor. If you change the prompt file after the DB
> is already seeded, the change has no effect unless you either:
> 1. Edit the prompt via the UI config panel, or
> 2. Delete the workflow config row from the DB to trigger a re-seed (destructive to all config)

### 7. `src/prompts/{QA}`

Similar JSON structure but focused on validating the extraction output:

```json
{
  "role": "You are a QA validation agent...",
  "user_template": "...",
  "task": "Validate the extraction output...",
  "json_example": "...",
  "instructions": "... validation rules ..."
}
```

---

## Layer 3: Services

### 8. `src/services/llm_service.py`

**5 insertion points:**

```python
# A) top_p fallback list (~line 318)
# Search for: "CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract"
if agent_name in ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "{Agent}"]:
    return self.top_p_extract

# B) Traceability block injection (~line 3196)
# Search for the same pattern
if user_prompt and agent_name in ("CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "{Agent}"):

# C) expected_keys list (~line 3442) — keys the JSON normalizer recognizes
#    Search for: "registry_artifacts" in the expected_keys list
expected_keys = [..., "registry_artifacts", "{alias}"]

# D) JSON normalization chain (~line 3492) — converts agent-specific key to "items"
#    Search for: elif "registry_artifacts" in last_result:
elif "{alias}" in last_result:
    count = len(last_result.get("{alias}", []))
    logger.info(f"{agent_name} found {count} {alias}")
    last_result["items"] = last_result.pop("{alias}")

# E) Langfuse output loop (~line 3557) — keys scanned for Langfuse output metadata
#    Search for: "process_lineage", "sigma_queries", "registry_artifacts"
for key in ["process_lineage", "sigma_queries", "registry_artifacts", "{alias}"]:
```

### 9. `src/services/lmstudio_model_loader.py`

**1 insertion point:**

```python
# Sub-agents list (~line 84)
sub_agents = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "{Agent}"]
```

### 10. `src/services/eval_bundle_service.py`

**5 insertion points — powers the "Export Bundle" download on the evals page:**

The eval bundle service generates JSON bundles containing all inputs, outputs, and
provenance data for a specific LLM call. The evals page has both single-execution
export and batch-by-config-version export. Both paths route through this service.

```python
# A) agent_to_subagent_map (~line 179) — maps agent to canonical alias for count lookup
"{Agent}": "{alias}",

# B) agent_key_map (~line 308) — maps agent name to error_log key
"{Agent}": "extract_agent",

# C) model_key_map (~line 518) — maps agent name to model config key
"{Agent}": "ExtractAgent",

# D) sub_agents list (~line 527) — identifies sub-agent for flat key lookup
sub_agents = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "{Agent}"]

# E) sub_agents list (~line 1268) — second occurrence in config snapshot extraction
sub_agents = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "{Agent}"]
```

**Bundle export chain**: The evals page modal sets `agentName` from a ternary chain
in `agent_evals.html` (see item 16.D), stores it on the export button, and passes it
to `POST /api/evaluations/evals/{id}/export-bundle`. The API route calls
`EvalBundleService.generate_bundle(execution_id, agent_name)`. The batch export uses
the subagent dropdown value and passes it through `SUBAGENT_RESULT_KEY_MAP` to resolve
the agent name.

---

## Layer 3b: Workflow Engine

### 10b. `src/workflows/agentic_workflow.py`

**5 insertion points — the LangGraph execution engine:**

```python
# A) subagent_to_agent mapping (~line 967) — maps canonical alias to agent name
#    This appears in multiple locations (search for all occurrences)
subagent_to_agent = {
    "cmdline": "CmdlineExtract",
    "process_lineage": "ProcTreeExtract",
    "hunt_queries": "HuntQueriesExtract",
    "{alias}": "{Agent}",
}

# B) Default empty results dict (~line 989) — initial state for all sub-agents
{
    "cmdline": {"items": [], "count": 0},
    "process_lineage": {"items": [], "count": 0},
    "hunt_queries": {"items": [], "count": 0},
    "{alias}": {"items": [], "count": 0},
}

# C) QA agent name mapping (~line 1048) — maps extract agent to its QA agent
qa_names = {
    "CmdlineExtract": "CmdLineQA",
    "ProcTreeExtract": "ProcTreeQA",
    "HuntQueriesExtract": "HuntQueriesQA",
    "{Agent}": "{QA}",
}

# D) Any additional subagent_to_agent mappings (search for all occurrences ~line 1032)
#    The same mapping may appear 2-3 times in different functions.

# E) Disabled agents check — the agent reads DisabledAgents from config to skip agents.
#    No code change needed if DisabledAgents is handled generically, but verify the agent
#    name is recognized by the supervisor dispatch logic.
```

---

## Automatic Integrations (No Code Changes Required)

Once Layers 1–3 are complete, these work without any per-agent wiring:

- **Langfuse tracing** — `log_llm_completion` in `llm_service.py` traces every LLM call
  automatically using the `agent_name` passed at call time. No Langfuse-specific code
  needed per agent.

- **Live execution view (SSE)** — `/executions/{id}/stream` streams generic execution
  state. Sub-agent results appear automatically once the workflow engine (Layer 3b) is
  integrated.

- **Error log capture** — As long as `{Agent}` and `{QA}` are in the `agent_mapping`
  dict in `workflow_executions.py` (item 11), errors flow into the execution detail view.

---

## Layer 4: Web Routes

### 11. `src/web/routes/workflow_executions.py`

**2 insertion points:**

```python
# A) agent_mapping dict — maps agent names to error_log keys
agent_mapping = {
    ...
    "{Agent}": "extract_agent",
    "{QA}": "extract_agent",
}

# B) primary_agents set
primary_agents = {
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "{Agent}",
}
```

### 12. `src/web/routes/evaluation_api.py`

**5 insertion points:**

```python
# A) SUBAGENT_AGENT_MAP (top of file, ~line 34)
"{alias}": "{Agent}",

# B) Result extraction block (~line 619) — extracts items from workflow results
#    Add an elif branch for the new alias:
elif result_key == "{alias}":
    agent_result = subresults.get("{alias}", {}) or subresults.get(
        "{Agent}", {}
    )
    if isinstance(agent_result, dict):
        items = agent_result.get("items", [])
        if items:
            commandlines = items if isinstance(items, list) else [items]

# C) Sub-agent model display loop (~line 1558)
for agent in ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "{Agent}"]:

# D) _extract_actual_count helper — parses count from workflow results
#    Search for the function that extracts actual counts from execution results.
#    Ensure it handles "{alias}" as a result key.

# E) SUBAGENT_RESULT_KEY_MAP (bottom of file, ~line 1722)
"{alias}": "{Agent}",
```

---

## Layer 5: UI Templates

### 13. `src/web/static/js/components/workflow-config-display.js`

**3 insertion points:**

```javascript
// A) workflowOrder array
const workflowOrder = [
    ...
    '{Agent}',
    '{QA}',
    'SIGMA',
    ...
];

// B) firstLevelSubAgents set
const firstLevelSubAgents = new Set([
    ...
    '{Agent}',
]);

// C) secondLevelSubAgents set
const secondLevelSubAgents = new Set([
    ...
    '{QA}'
]);

// D) subAgentOrder array (inside renderWorkflowConfigDisplay)
const subAgentOrder = [
    ...
    { id: '{Agent}', name: '{Agent}', qa: '{QA}' }
];
```

### 14. `src/web/templates/workflow.html`

This is the largest integration — **~40 insertion points**. See `references/workflow-html-checklist.md`.

### 15. `src/web/templates/agent_evaluation.html`

**1 insertion point — add eval card:**

```html
<a href="/evaluations/ExtractAgent/{Agent}" class="bg-blue-50 dark:bg-blue-900 rounded-lg p-4 hover:bg-blue-100 dark:hover:bg-blue-800 transition-colors">
    <div class="flex items-center justify-between mb-2">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white">{Agent}</h3>
        <span class="text-2xl">{icon}</span>
    </div>
    <p class="text-sm text-gray-600 dark:text-gray-400">{description}</p>
</a>
```

### 16. `src/web/templates/agent_evals.html`

**7 insertion points — this is a significant eval page integration:**

```javascript
// A) Subagent dropdown — add <option> to the subagent select element
<option value="{alias}">{Display}</option>

// B) SUBAGENT_MAP — maps dropdown value to agent name
const SUBAGENT_MAP = {
    ...
    '{alias}': '{Agent}'
};

// C) QA agent name ternary — maps agent name to QA agent for config display
agentName === '{Agent}' ? '{QA}' : null;

// D) Result type modal title — sets modal header when viewing results
} else if (resultType === '{alias}' || subagentEval === '{alias}') {
    modalTitle.textContent = 'Extracted {Display}';
    agentName = '{Agent}';
}

// E) Empty message for result type (if needed for custom wording)
} else if (resultType === '{alias}' || subagentEval === '{alias}') {
    emptyMessage = 'No {display} found for this execution.';
}

// F) Count display text ternary — the "Found N item(s)" text
// Add to the ternary chain that picks the noun (e.g., "commandline(s)", "hunt query/queries")
resultType === '{alias}' ? '{item_noun}(s)' :

// G) Display content format — how individual items render in the modal
// If your output schema uses objects (not plain strings), add a rendering branch
// similar to the hunt_queries object renderer
```

**Key insight**: The agent_evals page is the **most complex eval integration** because
it handles article loading, result rendering, count-based eval scoring, and config
version comparison. Copy the patterns from `hunt_queries` or `registry_artifacts` —
they show the full object-rendering path rather than the simpler string path used
by `cmdline`.

### 17. `src/web/templates/subagent_evaluation.html`

**1 insertion point — purpose description block:**

```html
{% elif subagent_name == '{Agent}' %}
<div class="mt-4 p-4 bg-blue-50 dark:bg-blue-900 rounded-lg">
    <p class="text-sm text-gray-700 dark:text-gray-300">
        <strong>Purpose:</strong> {description of what this agent extracts}.
    </p>
</div>
```

### 18. `src/web/templates/workflow_executions.html`

**1 insertion point — execution results entry:**

```javascript
{ key: '{alias}', name: '{Agent}', qaName: '{QA}',
  display: '{Display} Extraction', icon: '{icon}', order: N }
```

### 19. `src/web/templates/base.html`

**1 edit — bump cache-busting version:**

```html
<script src="/static/js/components/workflow-config-display.js?v=YYYYMMDD"></script>
```

---

## Layer 6: Config & Data

### 20. Quickstart Presets

Edit every file in `config/presets/AgentConfigs/quickstart/`:

Add a section matching the UI-ordered export format. **The `Prompt.prompt` and `QAPrompt.prompt`
fields must be populated with the full content of the prompt files** — presets are self-contained
snapshots that must carry the prompt language so users get a working config on import.

Use a script to avoid manual copy-paste errors:

```python
import json, glob

with open("src/prompts/{Agent}") as f:
    extract_prompt = f.read().strip()
with open("src/prompts/{QA}") as f:
    qa_prompt = f.read().strip()

for path in glob.glob("config/presets/AgentConfigs/quickstart/*.json"):
    with open(path) as f:
        data = json.load(f)
    data["{Agent}"] = {
        "Enabled": True,
        "Provider": "{provider}",
        "Model": "{model}",
        "Temperature": 0.0,
        "TopP": 0.9,
        "Prompt": {"prompt": extract_prompt, "instructions": ""},
        "QAEnabled": False,
        "QA": {
            "Provider": "{qa_provider}",
            "Model": "{qa_model}",
            "Temperature": 0.1,
            "TopP": 0.9
        },
        "QAPrompt": {"prompt": qa_prompt, "instructions": ""}
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
```

**Verification**: after running the script, load one preset and confirm both prompt fields are
non-empty strings containing valid JSON (`json.loads(data["{Agent}"]["Prompt"]["prompt"])` must
succeed without error).

> **Why populated prompts matter**: `src/prompts/{Agent}` is only read on first DB seed. Once a
> user has an existing DB, the prompt lives in the DB. Quickstart presets are the only reliable
> way to ship the canonical prompt to users who import rather than fresh-seed. An empty
> `Prompt.prompt` in a preset silently leaves the agent with no instructions after import.

### 21. Eval Data Directory

```bash
mkdir -p config/eval_articles_data/{alias}/
```

### 22. Verify Preset Backward Compatibility

After adding the agent, test that presets saved **before** this agent existed still import
cleanly. This is the "old preset" scenario — a JSON file that has no `{Agent}` section.

1. Take any existing quickstart preset and **remove** the `{Agent}` block from it.
2. Import it via `load_workflow_config()` (or the UI import flow).
3. Verify no validation error is raised and the agent defaults to `Enabled: false`.

If this fails with `"missing or null: {Agent}"`, ensure the agent's default block is in
`_OPTIONAL_SUB_AGENT_SECTIONS` in `workflow_config_loader.py` (insertion H above).

---

## Layer 7: Tests

### 22. `tests/config/test_{agent}_wiring.py` (NEW)

Create a comprehensive test file covering:

| Test Class | Tests |
|-----------|-------|
| TestSchemaConstants | AGENT_NAMES_SUB, AGENT_NAMES_QA, ALL_AGENT_NAMES, BASE_AGENT_TO_QA, QA_AGENT_TO_BASE |
| TestSchemaValidation | valid v2 config, orphan QA rejection, missing prompt rejection, flatten keys, disabled agents |
| TestLoaderConstants | EXTRACT_AGENTS, QA_AGENTS, AGENTS_ORDER_UI |
| TestMigration | v1→v2, QA migration, round-trip flatten |
| TestSubagentUtils | AGENT_TO_SUBAGENT, alias normalizations (parametrized), unknown returns None |
| TestUIOrderedRoundTrip | load accepts agent, export round-trip |
| TestPromptFiles | files exist, valid JSON, output schema |
| TestPresetFiles | quickstart presets include agent; `Prompt.prompt` and `QAPrompt.prompt` are non-empty |
| TestEvalArticlesPlaceholder | eval data directory exists |
| TestDefaultAgentPrompts | AGENT_PROMPT_FILES mapping |

Use `tests/config/test_registry_extract_wiring.py` as the template.

### 23. `tests/config/test_workflow_config_migrate.py`

Update the agent count assertion. Adding extract + QA = increment by 2.

### 24. `tests/config/test_workflow_config_export.py`

Add agent section to the UI-ordered preset fixture with all required keys from
`_UI_ORDERED_REQUIRED`.

### 25. `tests/config/test_backfill_sub_agents.py` (UPDATE)

This file already tests the `_backfill_ui_ordered_sub_agents()` function generically.
When adding a new agent to `_OPTIONAL_SUB_AGENT_SECTIONS`, verify:

- The `test_injected_section_matches_default_block` test still passes (it reads from
  `_OPTIONAL_SUB_AGENT_SECTIONS` dynamically).
- If the new agent has different default keys than RegistryExtract, add a dedicated
  test for its specific defaults.

### 26. `tests/worker/test_test_agents_provider_resolution.py` (UPDATE)

The `TestCrossAgentResolution` class has a parametrized test covering all sub-agents.
Add the new agent name to the `@pytest.mark.parametrize` list:

```python
@pytest.mark.parametrize("agent_name", [
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "{Agent}",  # <-- add here
])
```

### 27. `tests/workflows/test_conversation_log_truncation.py` (NO CHANGE)

Truncation logic is agent-agnostic — no per-agent updates needed.
