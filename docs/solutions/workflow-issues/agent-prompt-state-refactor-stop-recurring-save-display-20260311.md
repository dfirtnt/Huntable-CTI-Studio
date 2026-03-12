---
module: Agent Prompt Management
date: "2026-03-11"
problem_type: workflow_issue
component: assistant
symptoms:
  - "Agent prompt save-display bug has been fixed multiple times; each fix adds another guard"
  - "Multiple async flows (loadAgentPrompts, saveAgentPrompt, performAutoSave, rollback) mutate shared agentPrompts global with no coordination"
  - "Stale load can overwrite just-saved prompt in UI; duplicate save/render paths (saveAgentPrompt vs saveAgentPrompt2, two renderAgentPrompts)"
root_cause: async_timing
resolution_type: workflow_improvement
severity: high
tags: [agent-prompts, refactor, state-management, mutex, playwright, workflow-config]
---

# Refactor: Agent prompt state to stop recurring save-display bug

## Problem

The agent prompt save-display bug has been fixed multiple times because multiple async flows (`loadAgentPrompts`, `saveAgentPrompt`, `performAutoSave`, `rollback`) all mutate the shared `agentPrompts` global with no coordination. Each fix adds another guard instead of fixing the design. A long-term solution is needed so this stops recurring.

## Environment

- Module: Agent Prompt Management
- Affected: `src/web/templates/workflow.html` — `saveAgentPrompt`, `saveAgentPrompt2`, `loadAgentPrompts`, `renderAgentPrompts`, rollback handler
- Stack: Python/Flask, vanilla JS (workflow config/prompts UI)
- Date: 2026-03-11 (refactor plan)

## Symptoms

- Save-display bug keeps reappearing; fixes are band-aids (e.g. `lastPromptSaveAt` / `lastSavedPromptAgent` guard).
- Multiple async flows update the same `agentPrompts` state with no single source of truth or serialization.
- Duplicate code paths: `saveAgentPrompt` and `saveAgentPrompt2`, and two `renderAgentPrompts` definitions — fixes must be applied in multiple places.
- Playwright prompt persistence test is skipped, so regressions are not caught in CI.

## Planned solution (refactor tasks)

From Todoist task *Refactor agent prompt state to stop recurring save-display bug* and subtasks:

1. **Centralize prompt state or add mutex**  
   Introduce a single source of truth or coordination so only one of load/save/autoSave can run at a time.

2. **Un-skip and fix Playwright prompt persistence test**  
   Enable `workflow_config_persistence.spec.ts` test "Rank Agent prompt edit persists" so regressions are caught in CI.

3. **Consolidate duplicate save/render paths**  
   Merge `saveAgentPrompt` and `saveAgentPrompt2`, and the two `renderAgentPrompts` definitions, so fixes apply everywhere.

## Why this addresses the root cause

- **Root cause:** Async timing — uncoordinated mutation of shared state by load, save, autoSave, and rollback.
- **Refactor:** Single source of truth or mutex ensures one writer at a time; consolidated paths prevent inconsistent fixes and missed call sites.
- **Regression safety:** Un-skipped Playwright test catches save-display regressions in CI.

## Prevention

- Prefer centralizing state or serializing access over adding time-based or one-off guards.
- Avoid duplicate handlers for the same domain (e.g. two save functions, two render functions); consolidate then fix.

## Related Issues

- See also: [agent-prompt-save-display-revert-AgentPrompts-20260202.md](../ui-bugs/agent-prompt-save-display-revert-AgentPrompts-20260202.md) — prior band-aid fix (lastPromptSaveAt / lastSavedPromptAgent guard).
