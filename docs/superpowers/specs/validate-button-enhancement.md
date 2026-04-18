# Spec: Validate Button Enhancement

**Status:** Approved for build
**Scope:** `src/web/templates/workflow.html`, `src/services/llm_service.py`, `src/web/routes/workflow_config.py`
**Contract IDs touched:** None (no contract-grade DOM IDs/JS functions renamed or removed)

---

## Problem

The "Validate" button in the expanded prompt editor (`#prompt-exp-validate-btn`, workflow.html line 2872) only validates extraction sub-agent prompts. Three categories of runtime hard-fail are invisible to the user until a workflow blows up mid-run:

1. QA prompt structural errors (missing `evaluation_criteria`, empty `system`/`role`, empty `instructions`)
2. Config-shape violations (enabled agent missing Provider/Model, orphan QA agent, missing prompt block)
3. Warn-only text tokens that should block saves for extraction agents

---

## Deliverables

Four changes, ordered by priority. Each is independently shippable.

---

### Change 1: QA prompt validation in `_collectPromptIssues()`

**What:** Add a QA branch to the existing `_collectPromptIssues(agentName, systemVal)` function (workflow.html line 2631).

**Where:** `src/web/templates/workflow.html`, inside `_collectPromptIssues()`, after the `_EXTRACTION_AGENTS` block (line 2716) and before the return (line 2720).

**Logic (mirrors `_validate_qa_prompt_config` in llm_service.py lines 90-134):**

```javascript
// After line 2716, before the closing return:

if (QA_AGENTS.includes(agentName)) {
  // QA agents store a JSON object in the system textarea (same as extraction).
  let parsed;
  try {
    parsed = JSON.parse(systemVal);
  } catch (e) {
    issues.push({ level: 'error', msg: 'System prompt is not valid JSON. Cannot validate QA structure.' });
    return issues;
  }

  // Hard fail: role/system must be non-empty.
  const roleContent = ((parsed.system || parsed.role) || '').trim();
  if (!roleContent) {
    issues.push({ level: 'error', msg: "Missing required 'role'/'system' key. QA agent will hard-fail at runtime." });
  }

  // Hard fail: instructions must be non-empty.
  const instructions = (parsed.instructions || '').trim();
  if (!instructions) {
    issues.push({ level: 'error', msg: "Missing required 'instructions' key. QA agent needs evaluation directives." });
  }

  // Hard fail: evaluation_criteria must be a non-empty array.
  const criteria = parsed.evaluation_criteria;
  if (!criteria || !Array.isArray(criteria) || criteria.length === 0) {
    issues.push({ level: 'error', msg: "Missing or empty 'evaluation_criteria' (must be non-empty list). QA retry loop uses this as its grading rubric." });
  }

  // Warn: objective should be present.
  if (!parsed.objective) {
    issues.push({ level: 'warn', msg: "Missing 'objective' key. Will fall back to generic 'Verify extraction.' string." });
  }
}
```

**Constants already available:** `QA_AGENTS` is defined at workflow.html line 3572 as `['RankAgentQA', 'CmdLineQA', 'ProcTreeQA', 'HuntQueriesQA', 'RegistryQA', 'ServicesQA']`.

**Test:** Open any QA prompt in the expanded editor. Delete `evaluation_criteria` from the JSON. Click Validate. Expect 1 error. Restore it, delete `role`. Expect 1 error. Empty the entire textarea. Expect "System prompt is empty" error.

---

### Change 2: Block prompt save on validation errors

**What:** Run `_collectPromptIssues()` inside `saveExpandedPrompt()` before calling `saveAgentPrompt2()`. If any issues have `level: 'error'`, render them in `#prompt-exp-validate-result` and abort the save.

**Where:** `src/web/templates/workflow.html`, function `saveExpandedPrompt()` at line 2551.

**Current code (lines 2551-2574):**
```javascript
function saveExpandedPrompt() {
  if (!_expandedPromptAgent) return;
  const agentName = _expandedPromptAgent;
  const sysTA = document.getElementById('prompt-exp-system');
  if (!sysTA) return;
  // ... reads values ...
  closeExpandedPromptEditor();
  if (typeof saveAgentPrompt2 === 'function') {
    saveAgentPrompt2(agentName, { systemOverride: sysTA.value, userOverride: userOverride });
  }
}
```

**New code:**
```javascript
function saveExpandedPrompt() {
  if (!_expandedPromptAgent) return;
  const agentName = _expandedPromptAgent;
  const sysTA = document.getElementById('prompt-exp-system');
  if (!sysTA) return;

  // Gate: run validation before saving. Block on errors.
  const systemVal = (sysTA.value || '').trim();
  const issues = _collectPromptIssues(agentName, systemVal);
  const errors = issues.filter(i => i.level === 'error');
  if (errors.length > 0) {
    const resultDiv = document.getElementById('prompt-exp-validate-result');
    if (resultDiv) _renderValidateResult(resultDiv, issues);
    return;  // Do NOT save. Do NOT close modal.
  }

  const userLocked = (typeof isLockedExtractorPrompt === 'function' && isLockedExtractorPrompt(agentName))
                  || (typeof isLockedQAPrompt === 'function' && isLockedQAPrompt(agentName));
  const usrTA = document.getElementById('prompt-exp-user');
  const userOverride = (!userLocked && usrTA) ? usrTA.value : null;

  closeExpandedPromptEditor();
  if (typeof saveAgentPrompt2 === 'function') {
    saveAgentPrompt2(agentName, { systemOverride: sysTA.value, userOverride: userOverride });
  }
}
```

**Behavior change:** Previously, clicking "Save Prompt" with a structurally broken prompt would close the modal and fire the API call (which might succeed at the HTTP level but produce a config that hard-fails at workflow runtime). Now it stays open, shows the validation result, and does not save.

**Warnings do NOT block save.** Only `level: 'error'` issues block. Warn-only token mismatches still allow saving.

**Test:** Open a CmdlineExtract prompt, delete the `json_example` key, click Save Prompt. Modal should stay open with the error displayed. Fix it, click Save Prompt again -- should save and close normally.

---

### Change 3: "Validate All" API endpoint + UI button

**What:** Add a new GET endpoint that runs the full Pydantic `WorkflowConfigV2` validator against the current active config and returns structured issues. Add a "Validate All" button to the config tab header.

#### Backend: new endpoint

**Where:** `src/web/routes/workflow_config.py`

**Endpoint:** `GET /api/workflow/config/validate`

**Logic:**
```python
@router.get("/api/workflow/config/validate")
async def validate_workflow_config(db_session: Session = Depends(get_db_session)):
    """Dry-run the full Pydantic validator against the active config. Returns issues list."""
    issues = []

    current_config = (
        db_session.query(AgenticWorkflowConfigTable)
        .filter_by(is_active=True)
        .order_by(AgenticWorkflowConfigTable.version.desc())
        .first()
    )
    if not current_config:
        return {"issues": [{"level": "error", "msg": "No active workflow config found."}]}

    # 1. Try loading through the normalized schema (catches all Pydantic validators)
    try:
        from src.config.workflow_config_loader import load_workflow_config
        v2 = load_workflow_config(current_config)
        # load succeeded -- Pydantic validators passed
    except Exception as e:
        issues.append({"level": "error", "msg": f"Schema validation failed: {e}"})
        return {"issues": issues}

    # 2. Check each agent prompt against runtime validators
    from src.services.llm_service import (
        _validate_extraction_prompt_config,
        _validate_qa_prompt_config,
        PromptConfigValidationError,
    )

    EXTRACTION_AGENTS = {"CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract", "RegistryExtract", "ServicesExtract"}
    QA_AGENTS = {"RankAgentQA", "CmdLineQA", "ProcTreeQA", "HuntQueriesQA", "RegistryQA", "ServicesQA"}

    agent_prompts = current_config.agent_prompts or {}
    for agent_name, prompt_data in agent_prompts.items():
        if agent_name == "ExtractAgentSettings":
            continue
        prompt_str = prompt_data.get("prompt", "") if isinstance(prompt_data, dict) else ""
        if not prompt_str:
            # Check if agent is enabled -- missing prompt for enabled agent is an error
            agent_cfg = v2.Agents.get(agent_name)
            if agent_cfg and agent_cfg.Enabled:
                issues.append({"level": "error", "msg": f"{agent_name}: prompt is empty but agent is enabled."})
            continue

        try:
            parsed = json.loads(prompt_str)
        except (json.JSONDecodeError, TypeError):
            # Non-JSON prompts (RankAgent, SigmaAgent) -- just check non-empty
            continue

        if agent_name in EXTRACTION_AGENTS:
            try:
                _validate_extraction_prompt_config(agent_name, parsed)
            except PromptConfigValidationError as e:
                issues.append({"level": "error", "msg": str(e)})

        if agent_name in QA_AGENTS:
            try:
                _validate_qa_prompt_config(agent_name, parsed)
            except PromptConfigValidationError as e:
                issues.append({"level": "error", "msg": str(e)})

    # 3. Check for enabled agents missing Provider/Model (redundant with Pydantic but gives per-agent detail)
    for name, cfg in v2.Agents.items():
        if cfg.Enabled and (not cfg.Provider or not cfg.Model):
            issues.append({"level": "error", "msg": f"{name}: enabled but missing Provider or Model."})

    return {"issues": issues}
```

**Note:** `_validate_extraction_prompt_config` and `_validate_qa_prompt_config` are module-private (underscore prefix). They are being imported within the same package. If you prefer not to cross that boundary, extract both into a `src/services/prompt_validation.py` module and import from there in both `llm_service.py` and the route. Either approach is fine -- just keep the logic in one place.

#### Frontend: "Validate All" button

**Where:** `src/web/templates/workflow.html`, in the config tab header area near `#save-config-button`.

**DOM:**
```html
<button type="button" id="validate-all-btn" onclick="validateAllConfig()"
  class="px-3 py-1.5 text-xs rounded"
  style="background: #ca8a04; color: white; cursor: pointer;">
  Validate All
</button>
```

**This is NOT a contract-grade DOM ID** -- it is new UI within a step's content area and does not require a spec per AGENTS.md rules ("Changes within a step's content do not require a spec").

**JS function:**
```javascript
async function validateAllConfig() {
  const btn = document.getElementById('validate-all-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Validating...'; }

  try {
    const resp = await fetch('/api/workflow/config/validate');
    const data = await resp.json();
    const issues = data.issues || [];

    if (issues.length === 0) {
      showNotification('Config validation passed. All agents, prompts, and thresholds are valid.', 'success');
    } else {
      const errorCount = issues.filter(i => i.level === 'error').length;
      const warnCount = issues.filter(i => i.level === 'warn').length;
      const summary = [];
      if (errorCount) summary.push(errorCount + ' error' + (errorCount > 1 ? 's' : ''));
      if (warnCount) summary.push(warnCount + ' warning' + (warnCount > 1 ? 's' : ''));
      const detail = issues.map(i => '[' + i.level.toUpperCase() + '] ' + i.msg).join('\n');
      showNotification('Validation: ' + summary.join(', ') + '\n' + detail, 'error');
    }
  } catch (e) {
    showNotification('Validation request failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Validate All'; }
  }
}
```

**Note on `showNotification`:** If the current notification toast truncates multi-line content, consider rendering results in a modal instead. Check `showNotification` behavior with long strings before deciding. If it truncates, use `pushModal` to render a "Validation Results" modal with the same `_renderValidateResult` HTML pattern from the prompt validator.

**Test:** 
- With a clean config: click Validate All, expect success toast.
- Disable a QA agent from the Agents dict (via direct DB edit or by removing it from a preset), reload, click Validate All -- expect "Missing QA agent for X" error.
- Empty an extraction agent's `role` key in its prompt JSON, save, click Validate All -- expect the `_validate_extraction_prompt_config` error for that agent.

---

### Change 4: Promote warn-only tokens to hard-fail (deferred -- needs prompt audit first)

**What:** Move tokens from `_SYSTEM_WARN_ONLY` / `_INSTRUCTIONS_WARN_ONLY` to `_SYSTEM_HARD_FAIL` / `_INSTRUCTIONS_HARD_FAIL` in `src/services/llm_service.py` (lines 70-83). Mirror the change in the JS `_SYSTEM_WARN_TOKENS` / `_INSTRUCTIONS_WARN_TOKENS` arrays (workflow.html lines 2585-2595) by creating corresponding `_SYSTEM_ERROR_TOKENS` / `_INSTRUCTIONS_ERROR_TOKENS` arrays checked as `level: 'error'`.

**Why deferred:** The Python code comments say "promote to hard-fail after prompts conform to extractor-standard.md v1.1". This means the seed prompts in `src/prompts/` and any saved DB prompts may not yet contain all the required tokens. Promoting now would break existing configs.

**Pre-requisite before implementing:**
1. Run `Validate All` (Change 3) against the live config.
2. Check which warn-only tokens are actually present in all 5 extraction agent prompts.
3. For tokens present in all prompts, move them to `_HARD_FAIL`. For tokens missing from any prompt, fix the prompt first, then promote.

**When ready, the change is mechanical:**

In `llm_service.py`:
```python
# Move entries from _SYSTEM_WARN_ONLY to _SYSTEM_HARD_FAIL:
_SYSTEM_HARD_FAIL: list[tuple[str, str]] = [
    ("LITERAL TEXT EXTRACTOR", "ROLE block (sec 1)"),
    # ... whichever tokens are confirmed present in all prompts
]

# Remove those same entries from _SYSTEM_WARN_ONLY.
```

In `workflow.html`, create parallel arrays:
```javascript
var _SYSTEM_ERROR_TOKENS = [
  ['LITERAL TEXT EXTRACTOR', 'ROLE block (sec 1)'],
  // ... matching the Python _SYSTEM_HARD_FAIL list
];
```

And in `_collectPromptIssues`, check `_SYSTEM_ERROR_TOKENS` with `level: 'error'` before the existing `_SYSTEM_WARN_TOKENS` with `level: 'warn'`.

**Do NOT implement this change until the prompt audit is complete.**

---

## Files modified (Changes 1-3)

| File | Change |
|---|---|
| `src/web/templates/workflow.html` | QA branch in `_collectPromptIssues()`, save gate in `saveExpandedPrompt()`, `validateAllConfig()` function, "Validate All" button HTML |
| `src/web/routes/workflow_config.py` | New `GET /api/workflow/config/validate` endpoint |
| `src/services/llm_service.py` | No changes (validators imported as-is) |

## Files NOT modified

| File | Why |
|---|---|
| `src/config/workflow_config_schema.py` | Schema validators are consumed, not changed |
| `src/services/llm_service.py` | Runtime validators consumed via import; no signature changes |
| Any contract-grade DOM ID or JS function | No renames or removals -- new code only |

---

## Verification

```bash
python3 run_tests.py unit    # No regressions
python3 run_tests.py api     # New endpoint returns 200 with issues array
python3 run_tests.py ui      # Expanded editor save-gate works; Validate All button renders
```

Browser verification required for:
- QA prompt validation (open QA prompt, break it, click Validate, confirm error)
- Save gate (break a prompt, click Save Prompt, confirm modal stays open)
- Validate All (click button, confirm toast/modal with results)

---

## Out of scope

- Refactoring `_validate_extraction_prompt_config` / `_validate_qa_prompt_config` into a shared module (nice-to-have, not required)
- Promoting warn-only tokens to hard-fail (Change 4 -- deferred pending prompt audit)
- Adding validation for non-extraction, non-QA agents beyond "prompt non-empty" (RankAgent, SigmaAgent have no structural contract today)
- Inline editor validation (only the expanded editor has the Validate button; adding it to inline cards is a separate effort)
