# Execution Modal Text Color Standardization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace all `text-gray-400` and dim gray classes in the execution detail modal with a consistent 4-level semantic palette so every text element meets WCAG AA contrast.

**Architecture:** Pure Tailwind class swaps across 7 locations in `workflow.html`. No new CSS rules, no behavior changes. The 4-level system: `white`=headings, `gray-100`=body, `gray-200`=secondary, `gray-300`=muted. Status colors (green/red/amber/purple) are untouched.

**Tech Stack:** Tailwind CSS utility classes in inline JS HTML template strings, `workflow.html`

**Design doc:** `docs/plans/2026-03-06-execution-modal-text-color-standardization-design.md`

---

## Context You Must Know

All 7 locations live in `src/web/templates/workflow.html`. The file is ~15k lines — use exact line offsets.

The execution detail modal renders inside `#executionDetailContent`. The render pipeline:
1. `viewExecution()` builds `headerHtml` + calls `renderExecutionTabbed(steps, exec)`
2. `renderExecutionTabbed()` calls `renderStepPanel()` for each step
3. `renderStepPanel()` calls `renderSubTabs()` if the step has `subSteps`
4. `switchExecTab()` / `switchExecSubTab()` re-apply classes on tab click (must mirror the render functions)
5. `traceabilitySection()` is appended after the tabbed content

**Server:** Docker at `http://localhost:8001` — no restart needed (Jinja2 hot-reloads templates). After each task, visually verify in browser.

**Playwright tests:** Run from project root: `npx playwright test --config=tests/playwright.config.ts tests/playwright/execution_detail_tabs.spec.ts --reporter=line`

---

## Task 1: `headerHtml` + empty state

**Files:**
- Modify: `src/web/templates/workflow.html:10998-11012`

These are HTML template strings inside `viewExecution()`.

**Step 1: Apply the changes**

Find (line ~11000-11006), replace ALL occurrences of `text-gray-300` in the `headerHtml` block with `text-gray-200`. Also update the error message span. And fix the empty state on line ~11012.

Old `headerHtml` metadata rows:
```
class="text-gray-300"
```
New:
```
class="text-gray-200"
```

Old error span (line ~11006):
```
<span class="text-gray-300">${escapeHtml(exec.error_message)}</span>
```
New:
```
<span class="text-gray-100">${escapeHtml(exec.error_message)}</span>
```

Old empty state (line ~11012):
```
'<div class="text-gray-400 py-4">No step data available for this execution.</div>'
```
New:
```
'<div class="text-gray-300 py-4">No step data available for this execution.</div>'
```

**Step 2: Visual check**

Open `http://localhost:8001/workflow` → Executions tab → View any execution. The header metadata (Execution ID, Article, Status, Created, Completed) should be noticeably brighter.

**Step 3: Commit**
```bash
git add src/web/templates/workflow.html
git commit -m "style: lighten execution modal header metadata text (gray-300→200)"
```

---

## Task 2: `renderStepPanel()`

**Files:**
- Modify: `src/web/templates/workflow.html:11265-11305`

**Step 1: Apply the changes**

Locate `function renderStepPanel(step)` (~line 11265).

| Old | New | Element |
|-----|-----|---------|
| `text-base font-bold text-gray-100` | `text-base font-bold text-white` | step title `<h4>` |
| `text-xl font-mono text-gray-200` | `text-xl font-mono text-gray-100` | step metric |
| `text-xs font-medium text-gray-400 hover:text-gray-200` | `text-xs font-medium text-gray-300 hover:text-white` | Inputs `<summary>` |
| `border-t border-gray-700 text-sm text-gray-300` | `border-t border-gray-700 text-sm text-gray-100` | Inputs content div |
| `text-sm font-medium text-gray-200 hover:bg-gray-700/30` | `text-sm font-medium text-gray-100 hover:bg-gray-700/30` | Output `<summary>` |
| `border-t border-gray-700 text-sm text-gray-300 space-y-3` | `border-t border-gray-700 text-sm text-gray-100 space-y-3` | Output content div |

**Step 2: Visual check**

Open any execution → Tab 1 (OS Detection). The step title should be white. "Inputs" toggle should be gray-300 (visible). "Output" toggle and content should be brighter.

**Step 3: Commit**
```bash
git add src/web/templates/workflow.html
git commit -m "style: lighten execution step panel text (gray-400/300/200→semantic levels)"
```

---

## Task 3: `renderExecutionTabbed()` — inactive tab classes

**Files:**
- Modify: `src/web/templates/workflow.html:11307-11342`

**Step 1: Apply the changes**

Locate `function renderExecutionTabbed(steps, exec)` (~line 11307).

Old inactive tab class string (line ~11316):
```js
const inactiveClass = `${baseClass} border border-gray-600 text-gray-300 hover:border-gray-400 hover:text-gray-100`;
```
New:
```js
const inactiveClass = `${baseClass} border border-gray-600 text-gray-200 hover:border-gray-300 hover:text-white`;
```

Old tab number span (line ~11320):
```html
<span class="opacity-60 font-mono">${i + 1}</span>
```
New:
```html
<span class="opacity-75 font-mono">${i + 1}</span>
```

**Step 2: Visual check**

Open any execution. Inactive tabs (2, 3, 4…) should be noticeably brighter. The tab numbers should be slightly more visible.

**Step 3: Commit**
```bash
git add src/web/templates/workflow.html
git commit -m "style: lighten inactive exec tab pills (gray-300→200, opacity 60→75)"
```

---

## Task 4: `switchExecTab()` — must mirror Task 3

**Files:**
- Modify: `src/web/templates/workflow.html:11196-11219`

> ⚠️ This function re-applies classes on tab click. It MUST match the inactive class from `renderExecutionTabbed()` exactly, or tabs will flash to a different color on click.

**Step 1: Apply the changes**

Locate `function switchExecTab(index)` (~line 11196).

Old inactive class string (line ~11212):
```js
btn.className = 'exec-tab flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors border border-gray-600 text-gray-300 hover:border-gray-400 hover:text-gray-100';
```
New:
```js
btn.className = 'exec-tab flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors border border-gray-600 text-gray-200 hover:border-gray-300 hover:text-white';
```

**Step 2: Visual check**

Open any execution → click through the tabs. No color flash on click. Inactive tabs stay at the same brightness as the initial render.

**Step 3: Commit**
```bash
git add src/web/templates/workflow.html
git commit -m "style: sync switchExecTab inactive class with renderExecutionTabbed"
```

---

## Task 5: `renderSubTabs()` + `switchExecSubTab()`

**Files:**
- Modify: `src/web/templates/workflow.html:11221-11263`

> Same mirror pattern as Tasks 3+4 — render function and switch function must be identical for inactive state.

**Step 1: Apply the changes**

**In `renderSubTabs()` (~line 11225):**

Old inactive subtab class (in template literal):
```
border border-gray-600 text-gray-400 hover:text-gray-200
```
New:
```
border border-gray-600 text-gray-300 hover:text-white
```

Old "OUTPUT" label (~line 11235):
```html
<div class="text-xs text-gray-400 mb-1">OUTPUT</div>
```
New:
```html
<div class="text-xs text-gray-300 mb-1">OUTPUT</div>
```

**In `switchExecSubTab()` (~line 11257):**

Old inactive class:
```js
: 'exec-subtab flex items-center gap-1 px-2 py-1 rounded text-xs font-medium whitespace-nowrap transition-colors border border-gray-600 text-gray-400 hover:text-gray-200';
```
New:
```js
: 'exec-subtab flex items-center gap-1 px-2 py-1 rounded text-xs font-medium whitespace-nowrap transition-colors border border-gray-600 text-gray-300 hover:text-white';
```

**Step 2: Visual check**

Open any execution → click tab 3 (Extraction). The "Sub-Agents" / "Supervisor" sub-tabs should have brighter inactive text. The "OUTPUT" label above the content should be gray-300 (still muted, but readable).

**Step 3: Commit**
```bash
git add src/web/templates/workflow.html
git commit -m "style: lighten execution sub-tab inactive text and OUTPUT label"
```

---

## Task 6: `traceabilitySection()`

**Files:**
- Modify: `src/web/templates/workflow.html:10971-10995`

**Step 1: Apply the changes**

Locate `function traceabilitySection()` (~line 10971).

| Old | New | Element |
|-----|-----|---------|
| `dark:text-gray-300` (on h4 "Observable Traceability") | `dark:text-gray-100` | Section heading |
| `dark:text-gray-400` (unavailable fallback `<p>`) | `dark:text-gray-300` | Empty state |
| `dark:text-gray-300` (on `<summary>` — "▼ Process Tree", "▼ Hunt Queries") | `dark:text-gray-200` | Section headers |
| `dark:text-gray-300` (blockquote source evidence) | `dark:text-gray-200` | Quoted text |
| `dark:text-gray-300` (Reasoning paragraph) | `dark:text-gray-200` | Reasoning text |
| `dark:text-gray-400` (footer metadata — subagent, model, timestamp) | `dark:text-gray-300` | Footer line |

> Note: `traceabilitySection()` uses `dark:` prefixed classes because it was written before the modal was always dark-mode. Change the `dark:` variants only — leave any light-mode classes untouched.

**Step 2: Visual check**

Open execution 25 ("NotDoor Insights") → scroll to the bottom of the modal. The "Observable Traceability" heading should be bright. "▼ Process Tree (1)" and "▼ Hunt Queries (5)" should be clearly readable (this was the main complaint).

**Step 3: Commit**
```bash
git add src/web/templates/workflow.html
git commit -m "style: lighten traceability section headers and metadata text"
```

---

## Task 7: Regression check

**Step 1: Run the Playwright smoke tests**
```bash
npx playwright test --config=tests/playwright.config.ts tests/playwright/execution_detail_tabs.spec.ts --reporter=line
```
Expected: 6/6 pass. These tests don't check colors but do verify tab behavior wasn't broken.

**Step 2: Manual full-modal walkthrough**

Open execution 25. Verify:
- [ ] Header metadata is `gray-200` (clearly readable)
- [ ] Tab strip: active tab colored, inactive tabs `gray-200`
- [ ] Tab 1 (OS Detection): title is white, output content is bright
- [ ] Tab 2 (Junk Filter): same
- [ ] Tab 3 (Extraction): sub-tabs visible, "OUTPUT" label readable
- [ ] Traceability section: "▼ Process Tree (1)" and "▼ Hunt Queries (5)" headers are clearly readable
- [ ] Status colors (green CONTINUED badge, etc.) unchanged

**Step 3: Final commit if any touch-ups needed**
```bash
git add src/web/templates/workflow.html
git commit -m "style: final touch-ups from visual review"
```

**Step 4: Push**
```bash
git push
```
