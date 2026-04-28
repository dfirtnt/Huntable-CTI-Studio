# workflow.html Integration Checklist

`src/web/templates/workflow.html` is the largest integration surface (~16,000 lines).
There are approximately **40 insertion points** spread across both HTML and inline JavaScript.

The best approach: search for an existing peer agent (e.g., `HuntQueriesExtract` or `huntqueriesextract`)
and add the new agent in every location where that peer appears.

This checklist uses the same placeholders as the parent document:
- `{Agent}` = PascalCase (e.g., `RegistryExtract`)
- `{QA}` = PascalCase QA (e.g., `RegistryQA`)
- `{prefix}` = lowercase (e.g., `registryextract`)
- `{qa_prefix}` = lowercase QA (e.g., `registryqa`)
- `{scope}` = scope key (e.g., `registry`)
- `{display}` = human label (e.g., `Registry Artifacts`)
- `{icon}` = emoji (e.g., `🗝️`)

---

## Category 1: HTML Structure

### 1.1 Workflow Overview Card
Search: `Sub-Agents` count text
- Update count: "3 Sub-Agents" → "4 Sub-Agents" (or N+1)
- Add a new sub-agent card in the overview section

### 1.2 Sub-Agent Config Panel
Search for an existing sub-agent panel (e.g., the HuntQueriesExtract collapsible section)
and duplicate the entire HTML block, replacing:
- Agent name references
- Toggle IDs (`toggle-{prefix}-enabled`)
- Model/provider dropdown IDs
- Temperature/Top_P slider IDs
- Prompt container IDs
- QA checkbox IDs
- Test button

The panel should include:
- Enable/Disable toggle
- Model Provider dropdown (OpenAI, Anthropic, Gemini, LMStudio)
- Model dropdown
- Temperature slider
- Top_P slider
- Prompt editor (expandable)
- QA Agent toggle
- QA Agent model/provider/temperature/top_p (conditionally shown)
- QA Prompt editor
- Test button
- Save/Load Preset buttons

---

## Category 2: JavaScript Agent Config Objects

### 2.1 Agent Config Registration
Search: `getAgentConfig` function or the block where agent config objects are defined.
Add two entries:

> **Critical for LMStudio model loading**: `loadAgentModels()` calls `getAgentConfigs()`
> to decide whether to hit the LMStudio API. If this entry is missing, the model dropdown
> will show only "Use Extract Agents Fallback Model" even when LMStudio is running.

```javascript
// Extract agent config
{prefix}: {
    providerKey: '{Agent}_provider',
    modelKey: '{Agent}_model',
    temperatureKey: '{Agent}_temperature',
    topPKey: '{Agent}_top_p',
    // ... other keys matching peer agents
}

// QA agent config
{qa_prefix}: {
    providerKey: '{QA}_provider',
    modelKey: '{QA}',
    temperatureKey: '{QA}_temperature',
    topPKey: '{QA}_top_p',
    // ... other keys matching peer QA agents
}
```

---

## Category 3: Scope Maps & Agent Lists

### 3.1 SUBAGENT_SCOPE_MAP
Search: `SUBAGENT_SCOPE_MAP`

```javascript
{scope}: {
    extract: '{Agent}',
    qa: '{QA}',
    qaEnabledKey: '{Agent}',
    extractPrefix: '{prefix}',
    qaPrefix: '{qa_prefix}'
}
```

### 3.2 SUBAGENT_SCOPES
Search: `SUBAGENT_SCOPES`
Add `'{scope}'` to the array.

### 3.3 extractSubAgents Array
Search: `extractSubAgents` — there are multiple occurrences (use `replace_all`)
Add `'{Agent}'` to every occurrence.

---

## Category 4: Agent Type Checks

### 4.1 isExtractionAgent Checks
Search: `isExtractionAgent` or inline checks like `=== 'CmdlineExtract' || === 'ProcTreeExtract'`
Add `|| agentName === '{Agent}'` and `|| agentName === '{QA}'` as appropriate.

### 4.2 isQAAgent Checks  
Search: `isQAAgent` or `'CmdLineQA'` checks
Add `|| agentName === '{QA}'`

---

## Category 5: Label & Display Maps

### 5.1 Agent Label Maps
Search for label/display name maps (e.g., `registryextract` → `Registry Artifacts`)
Add entries for both `{prefix}` and `{qa_prefix}`.

---

## Category 6: Toggle & Checkbox Bindings

### 6.1 Enable Toggle
Search: `toggle-cmdlineextract-enabled` or `toggle-huntqueriesextract-enabled`
Add corresponding `toggle-{prefix}-enabled` binding.

### 6.2 QA Checkbox
Search: `qa-cmdlineextract` or `qa-huntqueriesextract`
Add `qa-{prefix}` binding.

### 6.3 QA Checkbox Maps
Search for maps that link agent names to QA checkbox IDs (usually 2 occurrences).
Add `{Agent}` entries.

---

## Category 7: Temperature & Top_P Sliders

### 7.1 Temperature Slider Registration
Search for temperature slider arrays/maps that list `CmdlineExtract`, `ProcTreeExtract`, etc.
Add entries for both `{Agent}` and `{QA}`.

### 7.2 Top_P Slider Registration
Same pattern as temperature — add both entries.

---

## Category 8: Model & Provider Lists

### 8.1 Sub-Agent Model Lists
Search for arrays listing sub-agents for model dropdown population.
Add `{Agent}`.

### 8.2 QA Agent Model Lists
Search for arrays listing QA agents for model dropdown population.
Add `{QA}`.

---

## Category 9: getCurrentModelForAgent Function

Search: `getCurrentModelForAgent`

This function resolves the active model for any agent — used by the prompt header display,
the Test button, and config save. It has **three hardcoded maps** that must include the new agent:

```javascript
// A) agentPrefixMap — maps PascalCase name to lowercase HTML ID prefix
'{Agent}': '{prefix}',
'{QA}': '{qa_prefix}',

// B) providerSelectMap — maps PascalCase name to provider dropdown ID
'{Agent}': '{prefix}-provider',
'{QA}': '{qa_prefix}-provider',

// C) subAgentNames fallback list — agents that inherit ExtractAgent's model when empty
const subAgentNames = [..., '{Agent}', ..., '{QA}'];
```

> **If these are missing**: The prompt header shows "Model: Not configured" even when a model
> is selected in the dropdown, and the Test button sends requests to the wrong provider.

---

## Category 9: Prompt Editor

### 9.1 Prompt Container Registration
Search: `prompt-container` array/map entries
Add:
```javascript
{ name: '{Agent}', container: '{prefix}-agent-prompt-container', prefix: '{prefix}-agent' }
```

### 9.2 QA Prompt Container Registration
Add:
```javascript
{ name: '{QA}', container: '{prefix}-agent-qa-prompt-container', prefix: '{prefix}-agent-qa' }
```

### 9.3 QA Prompt Rendering Switch
Search for the `if/else if` chain that handles QA prompt rendering by `agentPrefix`.
Add:
```javascript
else if (agentPrefix === '{prefix}-agent') {
    // render QA prompt for {Agent}
}
```

---

## Category 10: updateQABadge Ternary

Search: `updateQABadge` — there's a ternary chain mapping agent prefixes to checkbox IDs.
Add:
```javascript
agentPrefix === '{prefix}-agent' ? 'qa-{prefix}' :
```

---

## Category 11: Execution Modal

Search: existing execution modal entries (e.g., `hunt_queries`)
Add:
```javascript
{ key: '{alias}', name: '{Agent}', qaName: '{QA}',
  display: '{Display} Extraction', icon: '{icon}', order: N }
```

---

## Category 12: Preset Save/Load

### 12.1 QA Agent Maps for Save
Search for QA agent maps used during config save (usually maps agent names to QA model IDs).
Add `{QA}` entries.

### 12.2 QA Agent Maps for Load
Same pattern for config load — add `{QA}` entries.

### 12.3 applyPreset QA Model Fields
Search: `applyPreset` function, QA model field arrays
Add:
```javascript
{ name: '{QA}', id: '{qa_prefix}-model', tempId: '{qa_prefix}-temperature', topPId: '{qa_prefix}-top-p' }
```

---

## Category 13: Config Backfill Logic

### 13.1 Extract Sub-Agent Backfill
The existing backfill logic uses `extractSubAgents.forEach(...)` — if {Agent} is already
in the `extractSubAgents` array (from Category 3.3), this is automatic.

### 13.2 QA Agent Backfill
Search: `qaAgents` backfill array
Add `'{QA}'` to the QA agents array so empty QA model/provider values are populated
from a peer QA agent.

---

## Verification Approach

After completing all insertions:

1. **Grep for completeness**: Search workflow.html for an existing peer agent name
   (e.g., `HuntQueriesExtract`) and count occurrences. Then search for `{Agent}` and
   verify the count matches (minus any agent-specific entries like CmdlineExtract's
   AttentionPreprocessor).

2. **Browser console check**: Open DevTools, reload the page, and search console for
   any errors mentioning `{prefix}` or `{Agent}`.

3. **Visual parity check**: Expand the new sub-agent panel and compare side-by-side
   with an existing sub-agent. Every UI element should be present:
   - Enable toggle
   - Provider dropdown (with LMStudio option)
   - Model dropdown
   - Temperature slider
   - Top_P slider
   - Prompt editor button
   - QA toggle
   - Test button
   - Save/Load Preset buttons

4. **Selected Models panel**: Verify both {Agent} and {QA} appear with correct
   model/provider values.
