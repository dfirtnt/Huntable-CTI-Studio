# Design: Tabbed Execution Detail Modal

**Date:** 2026-03-05
**Status:** Approved
**Scope:** `src/web/templates/workflow.html` — front-end only, no backend changes

---

## Problem

The Execution Detail modal renders all workflow steps as a flat, identically-styled list of cards. There is no visual hierarchy, no at-a-glance status, and no way to navigate directly to a step. Users cannot quickly orient themselves — particularly when debugging failures or reviewing what each agent produced.

**Primary pain point (confirmed):** Finding the right step quickly. Everything looks the same.
**Usage pattern:** Both debugging failures and reviewing successful runs.

---

## Decision: Step Tabs (Option B)

Replace the flat scroll with a tab strip — one pill per step. Only the active step's content is shown. This forces clear orientation and eliminates the wall-of-cards problem.

---

## Design

### Modal Shell

Open **fullscreen by default**. Remove the current `lg:w-1/2` default width. The fullscreen toggle button remains for users who prefer windowed view.

### Tab Strip (Sticky)

A horizontally-scrollable pill strip pinned to the top of the modal content area. Tabs are generated only for steps that actually ran — skipped steps are omitted.

Each pill contains:
- **Step number badge** (small, monospace)
- **Step name** (short label, e.g. "Ranking", "Extraction")
- **Key metric** — single most informative value at a glance
- **Status color** — reflects pass/fail/warning/not-reached

```
[ 0 OS Detection  Windows ✅ ]  [ 1 Junk Filter  Huntable ✅ ]  [ 2 Ranking  7.2 🟡 ]  ...
```

Active tab: solid background fill.
Inactive tabs: bordered pills.

#### Key metric per step

| Step | Key metric |
|------|-----------|
| 0 OS Detection | Detected OS name, or "Error" |
| 1 Junk Filter | "Huntable" or "Filtered" + confidence |
| 2 LLM Ranking | Score / threshold (e.g. "7.2 / 6.0") |
| 3 Extraction | Observable count |
| 4 SIGMA | Rule count, or "0 (failed)" |
| 5 Similarity | Max similarity score |
| 6 Queue | "Promoted" or "Not promoted" |

#### Status color system

| Color | Meaning |
|-------|---------|
| Green | Step ran, workflow continued |
| Red | Step caused termination (threshold miss, non-Windows OS, etc.) |
| Amber | Step ran with warnings (QA warnings, partial results) |
| Gray | Step not reached — workflow stopped upstream |

### Step Content Panel

Below the tab strip, only the active step is rendered. Each step panel has a consistent three-section layout:

```
┌──────────────────────────────────────────────────┐
│  Step 2: LLM Ranking                 ✅ CONTINUED │  ← always-visible header
│  Score: 7.2 / 10  │  Threshold: 6.0              │  ← key metrics row
├──────────────────────────────────────────────────┤
│  ▸ Inputs  (collapsed by default)                 │
├──────────────────────────────────────────────────┤
│  ▾ Output  (expanded by default)                  │
│    Ranking Score: 7.2/10                          │
│    Threshold: 6.0/10                              │
│    Decision: ✅ Continue                          │
│  ▸ Ranking Reasoning  (collapsible)               │
└──────────────────────────────────────────────────┘
```

- **Header:** Step name + status badge — always visible, never collapses
- **Inputs:** Collapsed by default (less frequently needed)
- **Output:** Expanded by default (primary information)
- **Details/extras:** Collapsible within output section (raw LLM responses, conversation logs, etc.)

### Step 3 Extraction: Internal Sub-tabs

The Extraction step currently pushes 3 separate entries into the steps array (Sub-Agents panel, Supervisor panel). In the new design, these are consolidated into a single "Extraction" tab with its own internal sub-tab row:

```
Extraction tab selected →
[ CmdLine (8) ✅ ]  [ ProcTree (3) ✅ ]  [ HuntQueries (0) ⚠️ ]  [ Supervisor (11) ✅ ]
```

Same pill pattern and status coloring as the main tab strip.

---

## Implementation Scope

**File:** `src/web/templates/workflow.html`
**Function:** `viewExecution()` and its rendering helpers

### What changes
1. Modal default state → fullscreen
2. `viewExecution()` renders a tab strip from the `steps[]` array instead of rendering all steps as flat HTML
3. Tab click handlers swap the visible step panel
4. Each step panel rendered with the three-section layout (header, inputs collapsed, output expanded)
5. Step 3 sub-agents consolidated into one tab with internal sub-tabs
6. Status color derived from existing step data (termination_reason, scores, counts)

### What does NOT change
- The `steps[]` data structure and how it is populated
- All backend API endpoints
- The `<details>` elements within step content (they remain for drill-down)
- Any other modal (trigger workflow, rule preview, enrich, etc.)

---

## Open Questions

None — design is fully specified and approved.
