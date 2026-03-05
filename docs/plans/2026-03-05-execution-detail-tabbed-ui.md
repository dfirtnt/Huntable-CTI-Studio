# Execution Detail Tabbed UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the flat scrolling step list in the Execution Detail modal with a tab-per-step UI that gives instant orientation and navigation.

**Architecture:** Pure front-end change in `src/web/templates/workflow.html`. The existing `steps[]` array data-building logic stays intact; we add `status`, `metric`, `shortName`, and `id` fields to each step, consolidate sub-agent steps as nested `subSteps` on the Extraction step, and replace the flat renderer with a tabbed one. No backend changes.

**Tech Stack:** Vanilla JS, Tailwind CSS (via CDN in base.html), Playwright for tests.

---

## Background

The file is `src/web/templates/workflow.html` (15k lines). Key locations:

- **Modal HTML shell:** lines 1572–1593 — `#executionModal` / `#executionModalContent` / `#executionDetailContent`
- **`.modal-fullscreen` CSS:** lines 7–22
- **`viewExecution()` function:** starts at line 10005
- **OS Detection step push:** ~line 10130
- **Junk Filter step push:** ~line 10153
- **LLM Ranking step push:** ~line 10193
- **Extraction step push:** ~line 10296
- **Sub-Agents push (to become nested):** ~line 10422
- **ExtractionSupervisor push (to become nested):** ~line 10463
- **Flat renderer (`const content = ...`):** lines 10953–10992 — this is what we replace
- **`toggleModalFullscreen()`:** line 11141
- **`getStatusBadge()`, `describeTermination()`, `getStepBadge()`:** lines 9755–9820

Existing Playwright test file for executions (skipped): `tests/playwright/workflow_executions.spec.ts`

---

## Task 1: Add a new Playwright test file for tabbed execution modal

**Files:**
- Create: `tests/playwright/execution_detail_tabs.spec.ts`

**Step 1: Write the failing test**

Create `tests/playwright/execution_detail_tabs.spec.ts` with the following content. It mocks the API and opens the modal, then asserts the tab strip appears.

```typescript
import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

// Minimal mock execution to drive the modal
const MOCK_EXEC = {
  id: 99999,
  article_id: 1,
  article_title: 'Test Article',
  article_url: 'https://example.com',
  article_content: 'Windows test content',
  article_content_preview: '',
  status: 'completed',
  current_step: 'done',
  termination_reason: null,
  termination_details: null,
  error_message: null,
  error_log: {
    os_detection_result: {
      detected_os: 'Windows',
      detection_method: 'embedding',
      confidence: 'high',
      max_similarity: 0.95,
      similarities: { Windows: 0.95, Linux: 0.2 }
    }
  },
  junk_filter_result: {
    is_huntable: true,
    confidence: 0.92,
    original_length: 500,
    filtered_length: 480,
    chunks_kept: 4,
    chunks_removed: 1
  },
  ranking_score: 7.5,
  ranking_reasoning: 'High relevance.',
  extraction_result: {
    observables: [{ type: 'cmdline', value: 'cmd.exe', platform: 'Windows', source_context: '' }],
    summary: { count: 1, platforms_detected: ['Windows'] },
    discrete_huntables_count: 1,
    content: 'cmd.exe',
    subresults: {
      cmdline: { count: 1, items: ['cmd.exe'], raw: {} },
      process_lineage: { count: 0, items: [], raw: {} },
      hunt_queries: { count: 0, items: [], raw: {} }
    }
  },
  sigma_rules: [{ title: 'Test Rule', status: 'experimental', detection: {} }],
  similarity_results: [],
  config_snapshot: { ranking_threshold: 6.0, similarity_threshold: 0.5, agent_models: {} },
  created_at: '2026-03-05T10:00:00Z',
  completed_at: '2026-03-05T10:01:00Z'
};

test.describe('Execution Detail - Tabbed UI', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept API calls
    await page.route(`**/api/workflow/executions/99999`, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_EXEC) })
    );
    await page.route(`**/api/workflow/executions/99999/observables`, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ execution_id: 99999, observables: { cmdline: [], process_lineage: [], hunt_queries: [] } }) })
    );
    await page.route(`**/api/workflow/config`, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent_models: {}, ranking_threshold: 6.0 }) })
    );
    await page.goto(`${BASE}/workflow#executions`);
    await page.waitForLoadState('networkidle');
    // Open modal programmatically
    await page.evaluate(() => (window as any).viewExecution(99999));
    await page.waitForSelector('#executionModal:not(.hidden)', { timeout: 5000 });
  });

  test('modal opens fullscreen by default', async ({ page }) => {
    const modalContent = page.locator('#executionModalContent');
    await expect(modalContent).toHaveClass(/modal-fullscreen/);
  });

  test('tab strip is visible with one tab per step', async ({ page }) => {
    const tabStrip = page.locator('#exec-tab-strip');
    await expect(tabStrip).toBeVisible();
    // Expect at least 3 tabs (OS Detection, Junk Filter, Ranking)
    const tabs = tabStrip.locator('button.exec-tab');
    await expect(tabs).toHaveCount(await tabs.count());
    expect(await tabs.count()).toBeGreaterThanOrEqual(3);
  });

  test('first tab is active on open', async ({ page }) => {
    const firstTab = page.locator('button.exec-tab').first();
    await expect(firstTab).toHaveAttribute('data-active', 'true');
  });

  test('clicking a tab shows only that panel', async ({ page }) => {
    const tabs = page.locator('button.exec-tab');
    const count = await tabs.count();
    if (count < 2) test.skip();

    await tabs.nth(1).click();
    await expect(tabs.nth(1)).toHaveAttribute('data-active', 'true');

    const panels = page.locator('.exec-panel');
    const visiblePanels = await panels.evaluateAll(els =>
      els.filter(el => !el.classList.contains('hidden')).length
    );
    expect(visiblePanels).toBe(1);
  });

  test('each step panel has Output section expanded by default', async ({ page }) => {
    const firstPanel = page.locator('.exec-panel').first();
    const outputDetails = firstPanel.locator('details.exec-output');
    await expect(outputDetails).toHaveAttribute('open', '');
  });

  test('each step panel has Inputs section collapsed by default', async ({ page }) => {
    const firstPanel = page.locator('.exec-panel').first();
    const inputDetails = firstPanel.locator('details.exec-inputs');
    const isOpen = await inputDetails.getAttribute('open');
    expect(isOpen).toBeNull();
  });
});
```

**Step 2: Run to confirm it fails (modal doesn't have tabs yet)**

```bash
cd /Users/starlord/CTIScraper
npx playwright test tests/playwright/execution_detail_tabs.spec.ts --reporter=line 2>&1 | head -40
```

Expected: FAIL — `#exec-tab-strip` not found, modal not fullscreen.

**Step 3: Commit the failing test**

```bash
git add tests/playwright/execution_detail_tabs.spec.ts
git commit -m "test: failing Playwright tests for tabbed execution detail modal"
```

---

## Task 2: Add status/metric/shortName/id to each step push

**Files:**
- Modify: `src/web/templates/workflow.html` — the `steps.push()` calls inside `viewExecution()`

The current `steps.push()` objects have: `name`, `input`, `inputDetails`, `output`, `details`.
We add: `id`, `shortName`, `status`, `metric`.

**Status values:** `'pass'` | `'stopped'` | `'warn'` | `'error'` | `'skipped'`

**Step 1: Update OS Detection push (~line 10130)**

Find this block (search for `name: 'Step 0: OS Detection'`):
```js
steps.push({
    name: 'Step 0: OS Detection',
    input: `...`,
    inputDetails: osInputDetails,
    output: osOutput,
    details: similaritiesHtml
});
```

Replace with:
```js
steps.push({
    id: 'os_detection',
    shortName: 'OS Detection',
    name: 'Step 0: OS Detection',
    status: osDetectionError ? 'error' : isWindows ? 'pass' : 'stopped',
    metric: detectedOS || (osDetectionError ? 'Error' : 'Unknown'),
    input: `...`,        // leave unchanged
    inputDetails: osInputDetails,
    output: osOutput,
    details: similaritiesHtml
});
```

**Step 2: Update Junk Filter push (~line 10153)**

Find `name: 'Step 1: Junk Filter'`. Add:
```js
id: 'junk_filter',
shortName: 'Junk Filter',
status: exec.junk_filter_result.is_huntable ? 'pass' : 'stopped',
metric: (exec.junk_filter_result.confidence * 100).toFixed(0) + '%',
```

**Step 3: Update LLM Ranking push (~line 10193)**

Find `name: 'Step 2: LLM Ranking'`. Add:
```js
id: 'ranking',
shortName: 'Ranking',
const rankThreshold = exec.config_snapshot?.ranking_threshold ?? 6.0;
// add these to the push:
status: exec.ranking_score >= rankThreshold ? 'pass' : 'stopped',
metric: exec.ranking_score.toFixed(1) + ' / ' + rankThreshold.toFixed(1),
```

Note: `rankThreshold` is already computed nearby as `(exec.config_snapshot?.ranking_threshold ?? 6.0)` inside the output template. Extract it to a variable before the push.

**Step 4: Update Extraction push (~line 10296)**

Find `name: 'Step 3: Extract Agents'`. Add:
```js
id: 'extraction',
shortName: 'Extraction',
status: discreteHuntablesCount > 0 ? 'pass' : 'warn',
metric: discreteHuntablesCount + ' obs',
subSteps: null,   // will be populated below
```

**Step 5: Update SIGMA push**

Find `name: 'Step 4: Generate SIGMA'` (search for this string). Add:
```js
id: 'sigma',
shortName: 'SIGMA',
status: sigmaRulesCount > 0 ? 'pass' : (sigmaErrors ? 'error' : 'warn'),
metric: sigmaRulesCount + (sigmaRulesCount === 1 ? ' rule' : ' rules'),
```

**Step 6: Update Similarity and Queue pushes** (find by searching `Step 5` / `Step 6` or `similarity` / `queue` in the step names)

Add analogous `id`, `shortName`, `status`, `metric` to each remaining push. Check the actual step names in the file (search for `steps.push` after line 10475).

**Step 7: Run the test (still failing, but at different point)**

```bash
npx playwright test tests/playwright/execution_detail_tabs.spec.ts --reporter=line 2>&1 | head -40
```

Expected: still FAIL — tabs don't exist yet, but no JS errors from the new fields.

**Step 8: Commit**

```bash
git add src/web/templates/workflow.html
git commit -m "refactor: add status/metric/shortName/id to execution steps array"
```

---

## Task 3: Consolidate sub-agent steps into extraction.subSteps

**Files:**
- Modify: `src/web/templates/workflow.html` — the sub-agent and supervisor push calls

**Step 1: Find the sub-agent push block (~line 10422)**

Currently this code does:
```js
steps.push({
    name: '<span ...>🔬 Sub-Agents (Individual Extraction)</span>',
    input: ...,
    output: ...,
    details: `<div class="space-y-4">${subAgentDetails}</div>`
});
```

**Replace** with: instead of pushing to `steps[]`, find the extraction step and set its `subSteps`:
```js
// Find the extraction step we already pushed and attach sub-agent data
const extractionStep = steps.find(s => s.id === 'extraction');
if (extractionStep) {
    extractionStep.subSteps = extractionStep.subSteps || [];
    extractionStep.subSteps.push({
        id: 'sub_agents',
        shortName: 'Sub-Agents',
        name: '🔬 Sub-Agents',
        status: Object.values(subresults).some(r => (r?.count || r?.items?.length || 0) > 0) ? 'pass' : 'warn',
        metric: Object.values(subresults).reduce((sum, r) => sum + (r?.count || r?.items?.length || 0), 0) + ' items',
        output: `<div class="space-y-4">${subAgentDetails}</div>`,
        input: `<div class="space-y-1 text-xs"><div>• ${Object.keys(subresults).length} sub-agents executed</div></div>`,
        inputDetails: '',
        details: ''
    });
}
```

**Step 2: Find the ExtractionSupervisor push block (~line 10463)**

Currently:
```js
steps.push({
    name: '<span ...>🎯 ExtractionSupervisorAgent (Aggregation)</span>',
    ...
    details: supervisorDetails
});
```

Replace with:
```js
if (extractionStep) {
    extractionStep.subSteps = extractionStep.subSteps || [];
    extractionStep.subSteps.push({
        id: 'supervisor',
        shortName: 'Supervisor',
        name: '🎯 Supervisor',
        status: discreteHuntablesCount > 0 ? 'pass' : 'warn',
        metric: discreteHuntablesCount + ' total',
        output: supervisorDetails,
        input: `<div class="space-y-1 text-xs"><div>• Sub-agent results from ${Object.keys(subresults).length} sub-agents</div></div>`,
        inputDetails: '',
        details: ''
    });
}
```

**Step 3: Commit**

```bash
git add src/web/templates/workflow.html
git commit -m "refactor: consolidate sub-agent steps as nested subSteps on extraction step"
```

---

## Task 4: Add helper functions for tabbed rendering

**Files:**
- Modify: `src/web/templates/workflow.html` — add functions near `toggleModalFullscreen()` (line ~11141)

**Step 1: Add `switchExecTab()` function**

Insert after `toggleModalFullscreen()` (around line 11165):

```js
function switchExecTab(index) {
    // Update tab buttons
    document.querySelectorAll('#exec-tab-strip button.exec-tab').forEach((btn, i) => {
        const isActive = i === index;
        btn.setAttribute('data-active', isActive ? 'true' : 'false');
        if (isActive) {
            // Apply status color
            const statusColors = {
                pass: 'bg-green-600 text-white border-transparent',
                stopped: 'bg-red-600 text-white border-transparent',
                warn: 'bg-amber-500 text-white border-transparent',
                error: 'bg-red-600 text-white border-transparent',
                skipped: 'bg-gray-600 text-white border-transparent'
            };
            const status = btn.dataset.status || 'skipped';
            btn.className = `exec-tab flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${statusColors[status] || statusColors.skipped}`;
        } else {
            btn.className = 'exec-tab flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors border border-gray-600 text-gray-300 hover:border-gray-400 hover:text-gray-100';
        }
    });
    // Update panels
    document.querySelectorAll('#executionDetailContent .exec-panel').forEach((panel, i) => {
        panel.classList.toggle('hidden', i !== index);
    });
}
```

**Step 2: Add `renderSubTabs()` function**

```js
function renderSubTabs(subSteps) {
    if (!subSteps || subSteps.length === 0) return '';
    const statusColors = { pass: 'bg-green-700', stopped: 'bg-red-700', warn: 'bg-amber-600', error: 'bg-red-700', skipped: 'bg-gray-700' };
    const tabButtons = subSteps.map((sub, i) => `
        <button class="exec-subtab flex items-center gap-1 px-2 py-1 rounded text-xs font-medium whitespace-nowrap transition-colors ${i === 0 ? (statusColors[sub.status] || 'bg-gray-700') + ' text-white' : 'border border-gray-600 text-gray-400 hover:text-gray-200'}"
                data-subtab="${i}" data-status="${sub.status}"
                onclick="switchExecSubTab(this.closest('.exec-subtab-container'), ${i})">
            ${sub.shortName}${sub.metric ? `<span class="opacity-75 font-mono">${sub.metric}</span>` : ''}
        </button>
    `).join('');

    const panels = subSteps.map((sub, i) => `
        <div class="exec-subpanel ${i === 0 ? '' : 'hidden'}" data-subpanel="${i}">
            <div class="text-sm space-y-3 pt-3">
                <div class="text-xs text-gray-400 mb-1">OUTPUT</div>
                ${sub.output}
            </div>
        </div>
    `).join('');

    return `
        <div class="exec-subtab-container mt-4 border-t border-gray-700 pt-4">
            <div class="flex gap-2 overflow-x-auto pb-2 mb-3">${tabButtons}</div>
            ${panels}
        </div>
    `;
}

function switchExecSubTab(container, index) {
    const statusColors = { pass: 'bg-green-700', stopped: 'bg-red-700', warn: 'bg-amber-600', error: 'bg-red-700', skipped: 'bg-gray-700' };
    container.querySelectorAll('button.exec-subtab').forEach((btn, i) => {
        const isActive = i === index;
        const status = btn.dataset.status || 'skipped';
        btn.className = isActive
            ? `exec-subtab flex items-center gap-1 px-2 py-1 rounded text-xs font-medium whitespace-nowrap transition-colors ${statusColors[status] || 'bg-gray-700'} text-white`
            : 'exec-subtab flex items-center gap-1 px-2 py-1 rounded text-xs font-medium whitespace-nowrap transition-colors border border-gray-600 text-gray-400 hover:text-gray-200';
        btn.setAttribute('data-active', isActive ? 'true' : 'false');
    });
    container.querySelectorAll('.exec-subpanel').forEach((panel, i) => {
        panel.classList.toggle('hidden', i !== index);
    });
}
```

**Step 3: Add `renderStepPanel()` function**

```js
function renderStepPanel(step) {
    const statusLabels = { pass: 'CONTINUED', stopped: 'TERMINATED', warn: 'WARNING', error: 'FAILED', skipped: 'SKIPPED' };
    const statusBadgeColors = {
        pass: 'bg-green-900/40 text-green-300 border-green-700',
        stopped: 'bg-red-900/40 text-red-300 border-red-700',
        warn: 'bg-amber-900/40 text-amber-300 border-amber-700',
        error: 'bg-red-900/40 text-red-300 border-red-700',
        skipped: 'bg-gray-900/40 text-gray-400 border-gray-600'
    };
    const badgeClass = statusBadgeColors[step.status] || statusBadgeColors.skipped;
    const label = statusLabels[step.status] || (step.status || '').toUpperCase();

    return `
        <div class="space-y-3">
            <div class="flex items-center justify-between flex-wrap gap-2">
                <h4 class="text-base font-bold text-gray-100">${step.name}</h4>
                <span class="px-2.5 py-1 rounded border text-xs font-semibold ${badgeClass}">${label}</span>
            </div>
            ${step.metric ? `<div class="text-xl font-mono text-gray-200">${step.metric}</div>` : ''}
            <details class="exec-inputs border border-gray-700 rounded-lg overflow-hidden">
                <summary class="px-4 py-2.5 cursor-pointer text-xs font-medium text-gray-400 hover:text-gray-200 hover:bg-gray-700/30 select-none">
                    Inputs
                </summary>
                <div class="px-4 py-3 border-t border-gray-700 text-sm text-gray-300">
                    ${step.input || ''}
                    ${step.inputDetails || ''}
                </div>
            </details>
            <details open class="exec-output border border-gray-700 rounded-lg overflow-hidden">
                <summary class="px-4 py-2.5 cursor-pointer text-sm font-medium text-gray-200 hover:bg-gray-700/30 select-none">
                    Output
                </summary>
                <div class="px-4 py-3 border-t border-gray-700 text-sm text-gray-300 space-y-3">
                    ${step.output || ''}
                    ${step.details || ''}
                </div>
            </details>
            ${step.subSteps ? renderSubTabs(step.subSteps) : ''}
        </div>
    `;
}
```

**Step 4: Add `renderExecutionTabbed()` function**

```js
function renderExecutionTabbed(steps, exec) {
    const statusColors = { pass: 'bg-green-600', stopped: 'bg-red-600', warn: 'bg-amber-500', error: 'bg-red-600', skipped: 'bg-gray-600' };

    const tabButtons = steps.map((step, i) => {
        const color = statusColors[step.status] || statusColors.skipped;
        const isFirst = i === 0;
        const baseClass = 'exec-tab flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors';
        const activeClass = `${baseClass} ${color} text-white`;
        const inactiveClass = `${baseClass} border border-gray-600 text-gray-300 hover:border-gray-400 hover:text-gray-100`;
        return `<button class="${isFirst ? activeClass : inactiveClass}"
                        data-tab="${i}" data-status="${step.status}" data-active="${isFirst ? 'true' : 'false'}"
                        onclick="switchExecTab(${i})">
                    <span class="opacity-60 font-mono">${i}</span>
                    <span>${step.shortName || step.name}</span>
                    ${step.metric ? `<span class="font-mono opacity-80">${step.metric}</span>` : ''}
                </button>`;
    }).join('');

    const panels = steps.map((step, i) => `
        <div class="exec-panel ${i === 0 ? '' : 'hidden'}" data-panel="${i}">
            ${renderStepPanel(step)}
        </div>
    `).join('');

    return `
        <div id="exec-tab-strip" class="sticky top-0 bg-gray-800 border-b border-gray-700 -mx-5 px-5 py-2 mb-4 z-10">
            <div class="flex gap-2 overflow-x-auto pb-1" style="scrollbar-width:none">
                ${tabButtons}
            </div>
        </div>
        <div id="exec-panels">
            ${panels}
        </div>
    `;
}
```

**Step 5: Commit the helper functions**

```bash
git add src/web/templates/workflow.html
git commit -m "feat: add renderExecutionTabbed, renderStepPanel, renderSubTabs, switchExecTab helpers"
```

---

## Task 5: Wire up the new renderer and auto-fullscreen

**Files:**
- Modify: `src/web/templates/workflow.html` — two changes inside `viewExecution()`

**Step 1: Replace the flat renderer (lines ~10953–10992)**

Find the block starting with:
```js
const content = `
    <div class="space-y-4">
        <div class="border-b pb-2 border-gray-200 dark:border-gray-700">
```

And ending with:
```js
document.getElementById('executionDetailContent').innerHTML = content;
document.getElementById('executionModal').classList.remove('hidden');
```

Replace the entire `const content = ...` template literal and the two lines after it with:

```js
// Build execution header (article info, status, error — always shown above tabs)
const headerHtml = `
    <div class="border-b pb-3 mb-4 border-gray-700">
        <div class="text-gray-300"><strong>Execution ID:</strong> ${exec.id}</div>
        <div class="text-gray-300"><strong>Article:</strong> <a href="/articles/${exec.article_id}" class="text-purple-400 hover:text-purple-300">${escapeHtml(exec.article_title || '')}</a></div>
        <div class="text-gray-300"><strong>Status:</strong> ${getStatusBadge(exec.status)}</div>
        ${exec.termination_reason ? `<div class="text-gray-300"><strong>Completion Reason:</strong> ${escapeHtml(describeTermination(exec.termination_reason, exec.termination_details))}</div>` : ''}
        <div class="text-gray-300"><strong>Created:</strong> ${parseUTCDate(exec.created_at).toLocaleString('en-US', { dateStyle: 'short', timeStyle: 'short' })}</div>
        ${exec.completed_at ? `<div class="text-gray-300"><strong>Completed:</strong> ${parseUTCDate(exec.completed_at).toLocaleString('en-US', { dateStyle: 'short', timeStyle: 'short' })}</div>` : ''}
        ${exec.error_message ? `<div class="bg-red-900/20 p-3 rounded mt-2 border border-red-700"><strong class="text-red-300">Error:</strong> <span class="text-gray-300">${escapeHtml(exec.error_message)}</span></div>` : ''}
    </div>
`;

const tabbedHtml = steps.length > 0
    ? renderExecutionTabbed(steps, exec)
    : '<div class="text-gray-400">No step data available for this execution.</div>';

const content = headerHtml + tabbedHtml + traceabilitySection();

document.getElementById('executionDetailContent').innerHTML = content;
document.getElementById('executionModal').classList.remove('hidden');
```

**Step 2: Auto-fullscreen the modal when opening**

Immediately after `document.getElementById('executionModal').classList.remove('hidden');`, add:

```js
// Auto-fullscreen if not already
const modalContent = document.getElementById('executionModalContent');
if (modalContent && !modalContent.classList.contains('modal-fullscreen')) {
    toggleModalFullscreen();
}
```

**Step 3: Re-attach jump-to-article listeners**

The existing `jump-to-article-btn` listener code (lines ~10994–11019) stays unchanged — it runs after innerHTML is set and still works.

**Step 4: Run the Playwright tests**

```bash
npx playwright test tests/playwright/execution_detail_tabs.spec.ts --reporter=line 2>&1 | tail -20
```

Expected: all 5 tests PASS.

If any test fails, read the error and fix the implementation. Common issues:
- `#exec-tab-strip` not found: check `renderExecutionTabbed()` is called and returns correct HTML
- Tab not switching: check `switchExecTab()` selector matches `button.exec-tab`
- `details.exec-output` not matching: ensure class `exec-output` is on the details element in `renderStepPanel()`

**Step 5: Smoke-test manually in browser**

Open `http://localhost:8001/workflow#executions`, click any execution row. Confirm:
1. Modal opens fullscreen
2. Tab strip appears at top with colored pills
3. Only one panel is visible at a time
4. Clicking a tab switches the panel
5. Inputs section is collapsed, Output section is expanded by default
6. Extraction tab shows sub-tabs for CmdLine / ProcTree / HuntQueries / Supervisor

**Step 6: Commit**

```bash
git add src/web/templates/workflow.html
git commit -m "feat: tabbed execution detail modal with auto-fullscreen and step navigation"
```

---

## Task 6: Verify all existing Playwright tests still pass

**Step 1: Run the full Playwright test suite**

```bash
npx playwright test --reporter=line 2>&1 | tail -30
```

Expected: existing tests pass. The only new failures should be pre-existing skipped tests.

If `modal_escape_key.spec.ts` or `modal_stack_and_enter.spec.ts` fail, check whether they reference `#executionDetailContent` directly — the modal structure hasn't changed, only the inner HTML, so these should be fine.

**Step 2: Fix any regressions**

Common regression: if a test checks for `h4:has-text("Step-by-Step Inputs & Outputs")`, that heading is now gone. Update those assertions to check for `#exec-tab-strip` instead.

**Step 3: Final commit**

```bash
git add tests/
git commit -m "test: update playwright tests for tabbed execution detail modal"
```
