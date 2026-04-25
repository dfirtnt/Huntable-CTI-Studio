---
title: Settings page master Save button silently omits Source Auto-Healing checkbox
date: "2026-04-24"
category: ui-bugs
module: Settings Page
problem_type: ui_bug
component: frontend_stimulus
symptoms:
  - "User unchecks 'Enable Source Auto-Healing', clicks bottom 'Save Settings', sees success toast, then after Cmd+R the checkbox is checked again"
  - "DB row app_settings.SOURCE_HEALING_ENABLED keeps its old value with no updated_at bump after the master Save click"
  - "Same edit saved via the smaller 'Save Source Auto-Healing Settings' button inside the healing card works correctly"
root_cause: missing_workflow_step
resolution_type: code_fix
severity: medium
tags: [settings-page, save-button, source-auto-healing, persistence, form-handler, multiple-save-buttons]
---

# Settings page master Save button silently omits Source Auto-Healing checkbox

## Problem

The Settings page had two Save buttons: a small per-card `Save Source Auto-Healing Settings` and a big bottom `Save Settings`. Users naturally expect the bottom button to save everything visible on the page. It didn't — its payload-assembly function never included `SOURCE_HEALING_ENABLED` (or any other healing field). The click appeared successful (toast shown, no console error) but the value was never sent to the server, so a refresh reverted the checkbox.

## Symptoms

- Uncheck `Enable Source Auto-Healing`, click bottom `Save Settings`, refresh — checkbox reverts to checked.
- Live DB query confirms the row was never written:
  ```
  SELECT key, value, updated_at FROM app_settings WHERE key = 'SOURCE_HEALING_ENABLED';
  --> updated_at matches the prior save, not the recent click
  ```
- Clicking the smaller in-card `Save Source Auto-Healing Settings` button on the same edit works correctly and bumps `updated_at`.

## What Didn't Work

Two earlier fixes were deployed targeting this same perceived symptom and both had to be verified end-to-end before ruling them out:

1. **`Cache-Control: no-store` on `GET /api/settings`** ([`settings.py:55`](src/web/routes/settings.py:55)) — legitimate fix for a different failure mode (browsers serving a cached pre-save body). Header confirmed present in response. Not the cause here because the payload never reached the server in the first place.
2. **Adding `auto_trigger_hunt_score_threshold` to the `configs_identical` short-circuit** ([`workflow_config.py:472`](src/web/routes/workflow_config.py:472)) — also a legitimate fix for a threshold-only-edit no-op. Verified via a PUT 85→77 round-trip. Not the cause here because this path handles workflow config, not the healing checkbox.

Both earlier fixes were verified via Playwright automation driving the page. Playwright tests clicked the correct per-card save button, which masked the master-button bug. The bug only surfaced when a human clicked the button a human naturally clicks: the big one at the bottom.

## Solution

Delegate from the master save to the existing per-card save handler, so every Save button on the page covers every persisted field that is visible above it.

In [`src/web/templates/settings.html`](src/web/templates/settings.html) inside `saveSettings()`, after the backup-settings save and before the GitHub PR block:

```js
try {
    await persistBackupSettingsToServer(false);
} catch (error) {
    console.error('Error saving backup settings:', error);
}

try {
    await saveSourceHealingSettings();
} catch (error) {
    console.error('Error saving source healing settings from master save:', error);
}

// Save GitHub PR settings to backend API
try {
    const githubPRSettings = [ ... ];
```

## Why This Works

The root cause was a **missing step in the master save's payload assembly**, not a race condition or caching bug. `saveSettings()` built its payload manually field-by-field and simply never included `SOURCE_HEALING_ENABLED` (or any of the other six healing keys). The per-card handler `saveSourceHealingSettings()` already wrote all seven healing fields correctly; delegating to it from the master save closes the gap with no duplication.

Delegation beats copying the payload:
- If a new healing field is added later, the master save inherits it automatically.
- The per-card handler already handles the API key separately (write-only field), status toast, and error state — all preserved for free.
- Isolating the delegated call in its own `try/catch` keeps a healing-save failure from aborting sibling saves (langfuse, backup, GitHub PR), matching the existing pattern used elsewhere in `saveSettings()`.

## Prevention

- **Pages with multiple Save buttons should either (a) have one truly global Save that delegates to every per-section handler, or (b) have only per-section Saves with the global button removed.** A global Save that silently skips fields is worse than no global Save at all — it lies to the user.
- **When adding a new settings section with its own Save button, audit the master `saveSettings()` and delegate to the new handler.** Grep for all Save handler functions in the template and confirm each is reachable from the master save.
- **UI verification for settings pages must click the button a human clicks.** Playwright tests that target element IDs tend to hit the closest save button to the field, which masks master-save bugs. Add an explicit test that edits a field in each section and clicks *only* the bottom `#saveSettings` button, then reloads and asserts persistence.
- **Persistence verification must include a DB check, not just a re-fetch through the app's own API.** If there is a caching or response-shaping bug layered in, the API re-fetch can look correct while the row is stale. Query the underlying store directly (`docker exec cti_postgres psql ...`) to close the loop.

## Related Issues

- Related (different root cause, same broad surface): [`ui-bugs/agent-prompt-save-display-revert-AgentPrompts-20260202.md`](docs/solutions/ui-bugs/agent-prompt-save-display-revert-AgentPrompts-20260202.md) — agent prompt save-display revert caused by an async race, not a missing payload field.
- Same commit as the `Cache-Control: no-store` and `configs_identical` fixes (`fe8b6463`, `2de6890a`). Those two fixes were correct but insufficient.
