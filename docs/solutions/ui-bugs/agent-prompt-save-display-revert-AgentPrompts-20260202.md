---
module: Agent Prompt Management
date: "2026-02-02"
problem_type: ui_bug
component: assistant
symptoms:
  - "Saved agent prompts (all agents/sub-agents) revert in the UI to the previous version until user rolls back to 'latest'"
  - "User edits prompt, clicks Save, sees success, but displayed prompt reverts to old content; only way to see saved version was to open History and rollback to latest"
root_cause: async_timing
resolution_type: code_fix
severity: high
tags: [agent-prompts, race-condition, loadAgentPrompts, save-display, workflow-ui]
---

# Troubleshooting: Agent prompt save-display revert (race with loadAgentPrompts)

## Problem

After saving an agent prompt, the UI sometimes showed the previous version instead of the just-saved content. Save succeeded and the server had the new data, but the in-page `agentPrompts` state was overwritten by a stale async load that completed after the save.

## Environment

- Module: Agent Prompt Management
- Affected component: `src/web/templates/workflow.html` — `saveAgentPrompt`, `saveAgentPrompt2`, `loadAgentPrompts`, and rollback handler
- Stack: Python/Flask, vanilla JS (workflow config/prompts UI)
- Date: 2026-02-02

## Symptoms

- Saved agent prompts (all agents/sub-agents) could revert in the UI to the previous version until the user rolled back to "latest."
- User edits a prompt, clicks Save, sees success, but the displayed prompt reverts to the old content; the only way to see the saved version was to open History and rollback to the latest.

## Root cause

A race condition: `loadAgentPrompts` (started by `loadConfig` on page load) could complete **after** a save and overwrite `agentPrompts` with stale data, undoing the in-memory update from the save.

## Solution

Track `lastPromptSaveAt` and `lastSavedPromptAgent`. When `loadAgentPrompts` completes within 3 seconds of a save for that agent, preserve the saved agent's data instead of overwriting.

**1. Globals** (workflow.html, ~line 2246):

```javascript
let lastPromptSaveAt = 0;   // Timestamp of last prompt save (prevents loadAgentPrompts race from overwriting)
let lastSavedPromptAgent = null; // Agent name last saved
```

**2. After successful save in `saveAgentPrompt` and `saveAgentPrompt2`** (and in rollback handler when restoring latest):

```javascript
lastPromptSaveAt = Date.now();
lastSavedPromptAgent = agentName;
```

**3. In `loadAgentPrompts` when applying fetched data** (~line 6788):

```javascript
// CRITICAL: If we just saved a prompt, a stale loadAgentPrompts (from initial load) may
// complete after our save and overwrite with pre-save data. Preserve our saved agent.
if (lastSavedPromptAgent && (Date.now() - lastPromptSaveAt) < 3000) {
    agentPrompts = { ...fetched, [lastSavedPromptAgent]: agentPrompts[lastSavedPromptAgent] };
} else {
    agentPrompts = fetched;
}
```

Applied in: `saveAgentPrompt`, `saveAgentPrompt2`, and the rollback-to-latest handler. Do not call `loadConfig` immediately after save (it would trigger another load and can still race); the comment in code: "Do NOT call loadConfig - it can overwrite display with stale fetched data."

## Why this works

1. **Root cause:** Async timing — the initial `loadAgentPrompts()` from `loadConfig` can finish after the save response, so its result overwrites the in-memory state that was already updated from the save.
2. **Fix:** A short (3s) window after save where we treat the in-memory value for the saved agent as authoritative and merge it over the fetched payload, so the stale load no longer overwrites the saved content.
3. **Underlying issue:** Multiple async flows updating the same state without coordination; the fix adds a simple time-based guard instead of canceling or serializing the load.

## Prevention

- When multiple async flows can update the same UI state (e.g. load on page init and save handler), either serialize them (e.g. cancel in-flight load on save, or wait for load before applying save) or use a recency/authority rule (e.g. preserve recently saved data when a load completes).
- Avoid calling a full config/prompt reload immediately after a save; prefer updating local state from the save response and only reload when necessary.

## Related Issues

- See also: [agent-prompt-state-refactor-stop-recurring-save-display-20260311.md](../workflow-issues/agent-prompt-state-refactor-stop-recurring-save-display-20260311.md) — planned refactor to stop this bug recurring.
