---
name: new-extractor
description: Scaffold a new extraction sub-agent end-to-end. Use when the user asks to add a new extractor sub-agent, a new extraction type, or says something like "add a new extractor", "create a new sub-agent", or names a new artifact type they want extracted. Covers all integration touchpoints: prompt seed, config schema, LLM service, workflow, routes, UI templates, eval data, contract doc, sibling prompt updates, preset updates, and wiring tests.
---

# New Extractor Sub-Agent Scaffold

This skill walks through every integration point required to add a new extraction sub-agent to the Huntable CTI pipeline. Follow the steps in order; each step has a verification checkpoint.

## Context

The extraction pipeline has five active sub-agents today:
`CmdlineExtract`, `ProcTreeExtract`, `HuntQueriesExtract`, `RegistryExtract`, `ServicesExtract`.

Each sub-agent has:
- A **result key** (snake_case, used in code): e.g. `windows_services`, `registry_artifacts`
- A **QA agent**: e.g. `ServicesQA`, `RegistryQA`
- A **prompt seed** in `src/prompts/`
- A **contract doc** in `docs/contracts/`
- **Eval data** in `config/eval_articles_data/{result_key}/`
- Entries in every integration file listed below

Authoritative references:
- Prompt standard: `docs/contracts/extractor-standard.md`
- Existing example: `docs/contracts/services-extract.md`, `src/prompts/ServicesExtract`
- Config contract: `src/config/workflow_config_schema.py`

---

## Step 0: Establish names before writing any code

Decide and record before proceeding:

| Slot | Value | Example |
|------|-------|---------|
| `{AgentName}` | PascalCase, ends in `Extract` | `NetworkExtract` |
| `{QAName}` | `{AgentName}` minus `Extract` + `QA` | `NetworkQA` |
| `{result_key}` | snake_case, plural noun | `network_observables` |
| `{display_name}` | Human-readable string | `"Network Observables Extraction"` |
| `{agent_prefix}` | lowercase of `{AgentName}` | `networkextract` |
| `{artifact_type}` | What the agent extracts | `network observables` |

`{agent_prefix}` is used in HTML `id`/`name` attributes throughout `workflow.html`.

---

## Step 1: Prompt seed

**File:** `src/prompts/{AgentName}`

Write the full 16-section prompt following `docs/contracts/extractor-standard.md`.

Required sections (in order):
1. ROLE BLOCK — persona only, includes "LITERAL TEXT EXTRACTOR"
2. PURPOSE — what downstream system consumes the output
3. ARCHITECTURE CONTEXT — list ALL siblings (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, RegistryExtract, ServicesExtract, **plus the new agent itself**); explicit boundary rules
4. INPUT CONTRACT — verbatim standard language
5. POSITIVE EXTRACTION SCOPE
6. NEGATIVE EXTRACTION SCOPE
7. DETECTION RELEVANCE GATE
8. FIDELITY REQUIREMENTS
9. MULTI-LINE HANDLING
10. COUNT SEMANTICS
11. EDGE CASES
12. VERIFICATION CHECKLIST
13. OUTPUT SCHEMA — JSON-only, concrete example with realistic values
14. FIELD RULES — all fields; traceability fields (value, source_evidence, extraction_justification, confidence_score) are MANDATORY
15. FAIL-SAFE / EMPTY OUTPUT — literal JSON, e.g. `{"{result_key}": [], "count": 0}`
16. FINAL REMINDER — ends with "When in doubt, OMIT."

**QA agent seed:** `src/prompts/{QAName}` — see `src/prompts/ServicesQA` for the pattern (evaluates single extraction items; system message with role, instructions, evaluation_criteria).

**Checkpoint:** The system message must be non-empty and `instructions` must contain the output schema and JSON enforcement or `llm_service.py` will hard-fail.

---

## Step 2: Contract doc

**File:** `docs/contracts/{lowercase-name}-extract.md`

Copy the structure from `docs/contracts/services-extract.md`. The contract doc is the **human-readable specification** of what the prompt implements. It should be independently readable.

---

## Step 3: Config schema

**File:** `src/config/workflow_config_schema.py`

Four additions:

```python
# 1. AGENT_NAMES_SUB (around line 112)
AGENT_NAMES_SUB = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract",
                   "RegistryExtract", "ServicesExtract", "{AgentName}"]

# 2. AGENT_NAMES_QA (around line 113)
AGENT_NAMES_QA = [..., "{QAName}"]

# 3. AGENT_DISPLAY_NAMES (around line 131)
"{AgentName}": "{display_name}",
"{QAName}": "{display_name} QA",   # or appropriate QA display name

# 4. sub_agents set in the SubAgentConfig validator (around line 240)
sub_agents = {"CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract",
              "RegistryExtract", "ServicesExtract", "{AgentName}"}
```

Also add the QA pair mapping (search for `"ServicesExtract": "ServicesQA"` to find the dict):
```python
"{AgentName}": "{QAName}",
```

**Checkpoint:** Run `python3 -c "from src.config.workflow_config_schema import ALL_AGENT_NAMES; print(ALL_AGENT_NAMES)"` inside the container. `{AgentName}` and `{QAName}` must appear.

---

## Step 4: LLM service

**File:** `src/services/llm_service.py`

Search for `"ServicesExtract"` to find every location. Add `{AgentName}` and `{result_key}` in parallel with the ServicesExtract pattern at each location:

1. **Agent dispatch list** (sub-agent name → run extraction): add `{AgentName}` to the list that includes `"ServicesExtract"`.

2. **Result key list** (keys to normalize from raw LLM output): add `"{result_key}"` alongside `"windows_services"`.

3. **Count extraction block** — the block that reads `last_result.get("windows_services", [])`:
   ```python
   elif "{result_key}" in last_result:
       count = len(last_result.get("{result_key}", []))
       logger.info(f"{agent_name} found {count} {result_key}")
       last_result["items"] = last_result.pop("{result_key}")
   ```

4. **Normalization keys list** — the list `["process_lineage", "sigma_queries", "registry_artifacts", "windows_services"]`: add `"{result_key}"`.

**Checkpoint:** No `AttributeError` or `KeyError` when a workflow run that includes the new agent completes. Verify via `docker-compose logs workflow_worker`.

---

## Step 5: Workflow engine

**File:** `src/workflows/agentic_workflow.py`

Search for `("ServicesExtract", "windows_services", "ServicesQA")` to find the extraction tuple list. Add:
```python
("{AgentName}", "{result_key}", "{QAName}"),
```

Search for `"windows_services": {"items": [], "count": 0}` to find the subresults initialization. Add:
```python
"{result_key}": {"items": [], "count": 0},
```

Search for the dict that maps subagent name → result key (e.g. `"ServicesExtract": "windows_services"`). Add:
```python
"{AgentName}": "{result_key}",
```

**Checkpoint:** After a workflow run with the new agent enabled, `extraction_result.subresults` in the database should contain a `{result_key}` key.

---

## Step 6: Routes

### `src/web/routes/evaluation_api.py`

Search for `"windows_services": "ServicesExtract"` — there are multiple dicts. Add `"{result_key}": "{AgentName}"` to each.

Also find the result-key-specific item extraction block (the `if subagent_name == "windows_services":` branch) and add a matching branch:
```python
if subagent_name == "{result_key}":
    items = agent_result.get("{result_key}") or agent_result.get("items", [])
```

### `src/web/routes/workflow_config.py`

Find the list that includes `"ServicesExtract"` (around line 2044) and add `"{AgentName}"`.

### `src/web/routes/workflow_executions.py`

Find the dicts mapping agent name to log category (e.g. `"ServicesExtract": "extract_agent"`) and the list of sub-agent names. Add `"{AgentName}"` in parallel.

**Checkpoint:** `GET /api/workflow/config` returns `{AgentName}` in the agents list. `GET /api/workflow/executions/{id}` includes `{result_key}` in `extraction_result.subresults`.

---

## Step 7: UI templates

### `src/web/templates/workflow.html`

Copy the ServicesExtract sub-agent card block (search for `<!-- ServicesExtract -->`). Replace every occurrence of:
- `ServicesExtract` → `{AgentName}`
- `servicesextract` → `{agent_prefix}`
- `ServicesQA` → `{QAName}`

The block includes:
- Enable/disable toggle (`id="toggle-{agent_prefix}-enabled"`)
- Provider select (`id="{agent_prefix}-provider"`)
- Model select/input for lmstudio/openai/anthropic
- Temperature slider (`id="{agent_prefix}-temperature"`)
- Top_P slider (`id="{agent_prefix}-top-p"`)
- QA enable toggle

### `src/web/templates/agent_evals.html`

Three places:
1. `<option value="{result_key}">{Display Name}</option>` in the subagent selector
2. `'{result_key}': '{AgentName}'` in the JS result-key-to-agent-name map
3. `agentName === '{AgentName}' ? '{QAName}' : null` in the QA agent lookup

### `src/web/templates/workflow_executions.html`

Add display name entry and extraction tuple:
```js
'{AgentName}': '{display_name}'
// and:
{ key: '{result_key}', name: '{AgentName}', qaName: '{QAName}',
  display: _DN['{AgentName}'], icon: '🔍', order: N }
```
(set `order` to one more than the last sub-agent's order)

### `src/web/templates/agent_evaluation.html`

Add a card link:
```html
<a href="/evaluations/ExtractAgent/{AgentName}" ...>
  {display_name}
</a>
```

### `src/web/templates/subagent_evaluation.html`

Find the `{% elif subagent_name == 'ServicesExtract' %}` block and add:
```jinja
{% elif subagent_name == '{AgentName}' %}
  {# display logic for {AgentName} results #}
```

**Checkpoint:** `http://localhost:8001/workflow` — the new agent card appears under Extract Agent sub-agents. Toggle enable/disable; provider and model dropdowns function.

---

## Step 8: Eval data

### `config/eval_articles.yaml`

Add a new section:
```yaml
{result_key}:
  - url: "https://..."
    expected_count: N
  - url: "https://..."
    expected_count: N
```

Use 3–5 high-quality CTI articles known to contain the target artifact type.

### `config/eval_articles_data/{result_key}/articles.json`

Fetch and commit article snapshots. Two options:

**Option A — Fetch from URLs (articles must be publicly accessible):**
```bash
python3 scripts/fetch_eval_articles_static.py
```

**Option B — Dump from database (articles already ingested):**
```bash
python3 scripts/dump_eval_articles_static.py
```

Each entry in `articles.json`:
```json
{
  "url": "https://...",
  "title": "Article title",
  "content": "Full article body...",
  "filtered_content": "Optional junk-filtered text",
  "expected_count": N
}
```

**Checkpoint:** `http://localhost:8001/mlops/agent-evals` — click "Load Eval Articles", select `{result_key}` subagent, run an eval. Articles load and results appear.

---

## Step 9: Quickstart presets

**Files:** `config/presets/AgentConfigs/quickstart/*.json`

Each quickstart preset must include a config entry for `{AgentName}` and `{QAName}`. Copy the ServicesExtract block from each preset and replace names. The minimum structure per agent:

```json
"{AgentName}": {
  "Enabled": true,
  "Provider": "lmstudio",
  "Model": "",
  "Temperature": 0.0,
  "TopP": 0.9,
  "QAEnabled": false,
  "Prompt": {
    "prompt": { "role": "...", "system": "...", "instructions": "...", "json_example": {} }
  }
},
"{QAName}": {
  "Enabled": true,
  "Provider": "lmstudio",
  "Model": "",
  "Temperature": 0.0,
  "TopP": 0.9,
  "Prompt": {
    "prompt": { "role": "...", "system": "...", "instructions": "...", "evaluation_criteria": [] }
  }
}
```

**Checkpoint:** Load a quickstart preset in the Workflow UI. The new agent card shows the loaded provider and model.

---

## Step 10: Update all sibling extractor prompts

**Files:** `src/prompts/CmdlineExtract`, `src/prompts/ProcTreeExtract`, `src/prompts/HuntQueriesExtract`, `src/prompts/RegistryExtract`, `src/prompts/ServicesExtract`

In the ARCHITECTURE CONTEXT section of every existing extractor, add `{AgentName}` to the sibling list and define boundary rules:

```
- **{AgentName}** -- {one-line scope description}
  Do NOT extract {what belongs to the new agent}. ({AgentName} owns it.)
```

Also update the new agent's ARCHITECTURE CONTEXT to correctly reference all current siblings.

**Checkpoint:** Review each sibling prompt's ARCHITECTURE CONTEXT. Every prompt should list all six agents.

After updating seed prompts, run the migration script so existing stored configs are updated:

```bash
docker-compose exec web python3 scripts/migrate_prompts_to_traceability_fields.py
```

---

## Step 11: Tests

### Wiring tests (`tests/config/test_subagent_traceability_contract.py`)

Add `{AgentName}` to every agent list in this file. The test suite validates prompt contract compliance across all sub-agents.

### Schema tests

Any test that asserts `AGENT_NAMES_SUB` or `ALL_AGENT_NAMES` exact contents needs `{AgentName}` added.

### Eval smoke test (optional but recommended)

Add a test that verifies `config/eval_articles_data/{result_key}/articles.json` exists and is valid JSON with the required fields.

**Run the full test suite:**
```bash
python3 run_tests.py unit
python3 run_tests.py api
python3 run_tests.py integration
```

---

## Step 12: Documentation

Update these docs to include `{AgentName}`:

| File | What to add |
|------|------------|
| `docs/concepts/agents.md` | Add `{AgentName}` and `{QAName}` to the sub-agent and QA lists |
| `docs/reference/api.md` | Add `{AgentName}` and `{QAName}` to valid `agent_name` enum |
| `docs/architecture/agent-config-schema.md` | Add `{AgentName}` to sub-agents description |
| `docs/getting-started/installation.md` | Add `config/eval_articles_data/{result_key}/` to the eval data directory table |
| `docs/architecture/workflow-data-flow.md` | Add `{AgentName}` to sub-agents list |
| `docs/llm/model-selection.md` | Add `{AgentName}` to Active Agent Types |
| `docs/concepts/observables.md` | Add type emitted by `{AgentName}` |
| `docs/reference/schemas.md` | Add `{result_key}` row to subresults table |
| `docs/CHANGELOG.md` | Add entry under `[Unreleased]` describing the new agent |

---

## Step 13: Full verification

```bash
# 1. Unit and config tests
python3 run_tests.py unit

# 2. API tests (requires test containers)
python3 run_tests.py api

# 3. Integration test with live workflow
docker-compose exec web python3 -m pytest tests/integration/ -k "extract" -v

# 4. Browser smoke
# - Open http://localhost:8001/workflow
# - Confirm new agent card visible and toggle works
# - Trigger a workflow on a relevant article
# - Confirm extraction_result.subresults.{result_key} in the execution detail
# - Open http://localhost:8001/mlops/agent-evals, load articles, run eval
```

---

## Invariants — never skip these

- `json_example` in the prompt config MUST include all four traceability fields (`value`, `source_evidence`, `extraction_justification`, `confidence_score`). Missing fields cause QA to flag outputs as hallucinated.
- `instructions` config key MUST contain the output schema and JSON-only enforcement, or the pipeline hard-fails with `PreprocessInvariantError`.
- Every existing extractor's ARCHITECTURE CONTEXT must be updated. An extractor that doesn't know about the new sibling will trespass on its scope.
- The eval `articles.json` must be committed so evals work offline.
- Run `python3 run_tests.py unit` before pushing. `test_subagent_traceability_contract.py` will catch missing fields.
