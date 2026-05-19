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
    await page.route(/\/api\/workflow\/executions\?/, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ executions: [], total: 0 }) })
    );
    await page.route(`**/api/workflow/config`, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent_models: {}, ranking_threshold: 6.0 }) })
    );
    await page.goto(`${BASE}/workflow#executions`);
    await page.waitForLoadState('networkidle');
    // Guard against the context-destroyed race: the page may do a brief hash
    // re-navigation after networkidle, destroying the JS context.  Wait until
    // viewExecution is callable in a stable context before evaluating.
    await page.waitForFunction(
      () => typeof (window as any).viewExecution === 'function',
      { timeout: 5000 }
    );
    // Re-wait for networkidle: the workflow page sets window.location.hash in its
    // init code after DOMContentLoaded. That assignment can fire *after* waitForFunction
    // passes (viewExecution is hoisted), briefly destroying the JS execution context.
    // A second networkidle wait lets the hash navigation settle before we evaluate.
    await page.waitForLoadState('networkidle');
    // Open modal programmatically — retry once on context-destroyed from residual navigation
    try {
      await page.evaluate(() => (window as any).viewExecution(99999));
    } catch (e) {
      if (!String(e).includes('Execution context was destroyed')) throw e;
      await page.waitForLoadState('networkidle');
      await page.waitForFunction(() => typeof (window as any).viewExecution === 'function', { timeout: 5000 });
      await page.evaluate(() => (window as any).viewExecution(99999));
    }
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
    expect(await tabs.count()).toBeGreaterThanOrEqual(3);
  });

  test('clicking a tab shows only that panel', async ({ page }) => {
    const tabs = page.locator('button.exec-tab');
    expect(await tabs.count()).toBeGreaterThanOrEqual(2);

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
});

// ---------------------------------------------------------------------------
// warnReason display and similarity status logic
// ---------------------------------------------------------------------------

async function openExecutionWithData(page: any, execData: object) {
  await page.route(`**/api/workflow/executions/99999`, route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(execData) })
  );
  await page.route(`**/api/workflow/executions/99999/observables`, route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ execution_id: 99999, observables: { cmdline: [], process_lineage: [], hunt_queries: [] } }) })
  );
  await page.route(/\/api\/workflow\/executions\?/, route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ executions: [], total: 0 }) })
  );
  await page.route(`**/api/workflow/config`, route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent_models: {}, ranking_threshold: 6.0 }) })
  );
  await page.goto(`${BASE}/workflow#executions`);
  await page.waitForLoadState('networkidle');
  await page.waitForFunction(
    () => typeof (window as any).viewExecution === 'function',
    { timeout: 5000 }
  );
  // Retry once on context-destroyed from residual hash navigation: the workflow
  // page assigns window.location.hash in init code, which can fire after
  // waitForFunction passes and briefly destroy the JS execution context.
  try {
    await page.evaluate(() => (window as any).viewExecution(99999));
  } catch (e) {
    if (!String(e).includes('Execution context was destroyed')) throw e;
    await page.waitForLoadState('networkidle');
    await page.waitForFunction(() => typeof (window as any).viewExecution === 'function', { timeout: 5000 });
    await page.evaluate(() => (window as any).viewExecution(99999));
  }
  await page.waitForSelector('#executionModal:not(.hidden)', { timeout: 5000 });
}

const BASE_EXEC = { ...MOCK_EXEC };

test.describe('Execution Detail - warnReason labels', () => {
  test('extraction tab shows "nothing extracted" when 0 observables', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      extraction_result: {
        observables: [],
        summary: { count: 0, platforms_detected: [] },
        discrete_huntables_count: 0,
        content: '',
        subresults: {
          cmdline: { count: 0, items: [], raw: {} },
          process_lineage: { count: 0, items: [], raw: {} },
          hunt_queries: { count: 0, items: [], raw: {} }
        }
      },
      sigma_rules: [],
      similarity_results: [],
      queued_rules_count: 0,
      queued_rule_ids: []
    };
    await openExecutionWithData(page, exec);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const extractionTab = tabs.filter({ hasText: 'Extraction' });
    await expect(extractionTab).toContainText('nothing extracted');
    await expect(extractionTab).toHaveAttribute('data-status', 'warn');
  });

  test('extraction tab has no warnReason when observables exist', async ({ page }) => {
    await openExecutionWithData(page, BASE_EXEC);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const extractionTab = tabs.filter({ hasText: 'Extraction' });
    await expect(extractionTab).not.toContainText('nothing extracted');
    await expect(extractionTab).toHaveAttribute('data-status', 'pass');
  });

  test('sigma tab shows "agent produced nothing" when 0 rules and no errors', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      sigma_rules: [],
      similarity_results: [],
      queued_rules_count: 0,
      queued_rule_ids: []
    };
    await openExecutionWithData(page, exec);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const sigmaTab = tabs.filter({ hasText: 'SIGMA' });
    await expect(sigmaTab).toContainText('agent produced nothing');
    await expect(sigmaTab).toHaveAttribute('data-status', 'warn');
  });
});

test.describe('Execution Detail - similarity step status logic', () => {
  test('similarity step is pass when results array is empty (novel rule)', async ({ page }) => {
    const exec = { ...BASE_EXEC, similarity_results: [] };
    await openExecutionWithData(page, exec);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const simTab = tabs.filter({ hasText: 'Similarity' });
    await expect(simTab).toHaveAttribute('data-status', 'pass');
    await expect(simTab).not.toContainText('above duplicate threshold');
  });

  test('similarity step is warn and shows reason when above threshold', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      similarity_results: [{ rule_id: 1, max_similarity: 0.92, title: 'Existing Rule' }],
      config_snapshot: { ranking_threshold: 6.0, similarity_threshold: 0.5, agent_models: {} }
    };
    await openExecutionWithData(page, exec);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const simTab = tabs.filter({ hasText: 'Similarity' });
    await expect(simTab).toHaveAttribute('data-status', 'warn');
    await expect(simTab).toContainText('above duplicate threshold');
  });

  test('similarity step is pass when below threshold', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      similarity_results: [{ rule_id: 1, max_similarity: 0.3, title: 'Distant Rule' }],
      config_snapshot: { ranking_threshold: 6.0, similarity_threshold: 0.5, agent_models: {} }
    };
    await openExecutionWithData(page, exec);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const simTab = tabs.filter({ hasText: 'Similarity' });
    await expect(simTab).toHaveAttribute('data-status', 'pass');
    await expect(simTab).not.toContainText('above duplicate threshold');
  });
});

test.describe('Execution Detail - queue warnReason', () => {
  test('queue tab shows "no rules generated" when sigma_rules is empty', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      extraction_result: {
        ...BASE_EXEC.extraction_result,
        discrete_huntables_count: 0,
        observables: [],
        subresults: {
          cmdline: { count: 0, items: [], raw: {} },
          process_lineage: { count: 0, items: [], raw: {} },
          hunt_queries: { count: 0, items: [], raw: {} }
        }
      },
      sigma_rules: [],
      similarity_results: [],
      queued_rules_count: 0,
      queued_rule_ids: []
    };
    await openExecutionWithData(page, exec);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const queueTab = tabs.filter({ hasText: 'Queue' });
    await expect(queueTab).toHaveAttribute('data-status', 'warn');
    await expect(queueTab).toContainText('no rules generated');
  });

  test('queue tab shows "filtered as duplicate" when similarity above threshold', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      sigma_rules: [{ title: 'Test Rule', status: 'experimental', detection: {} }],
      similarity_results: [{ rule_id: 1, max_similarity: 0.92, title: 'Existing Rule' }],
      config_snapshot: { ranking_threshold: 6.0, similarity_threshold: 0.5, agent_models: {} },
      queued_rules_count: 0,
      queued_rule_ids: []
    };
    await openExecutionWithData(page, exec);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const queueTab = tabs.filter({ hasText: 'Queue' });
    await expect(queueTab).toHaveAttribute('data-status', 'warn');
    await expect(queueTab).toContainText('filtered as duplicate');
  });

  test('queue tab has no warnReason when rules are queued', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      similarity_results: [{ rule_id: 1, max_similarity: 0.3, title: 'Distant Rule' }],
      queued_rules_count: 1,
      queued_rule_ids: [42]
    };
    await openExecutionWithData(page, exec);

    const tabs = page.locator('#exec-tab-strip button.exec-tab');
    const queueTab = tabs.filter({ hasText: 'Queue' });
    await expect(queueTab).toHaveAttribute('data-status', 'pass');
    // No warn reason text on a passing queue step
    const warnReasonSpans = queueTab.locator('span').filter({ hasText: /filtered|no rules|not queued|similarity/ });
    expect(await warnReasonSpans.count()).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Regression: ScheduledTasksExtract card must render in Sub-Agents section
//
// Omission root cause: workflow.html had a parallel copy of the sub-agents
// rendering array that was missing ScheduledTasksExtract after the agent was
// wired.  The card rendered in workflow_executions.html but silently vanished
// in the /workflow#executions modal view.
// ---------------------------------------------------------------------------

test.describe('Execution Detail - ScheduledTasksExtract card regression', () => {
  test('Scheduled Tasks Extraction card renders with item count when scheduled_tasks in subresults', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      extraction_result: {
        observables: [{ type: 'scheduled_tasks', value: 'My Task', platform: 'Windows', source_context: '' }],
        summary: { count: 1, platforms_detected: ['Windows'] },
        discrete_huntables_count: 1,
        content: 'My Task',
        subresults: {
          cmdline: { count: 0, items: [], raw: {} },
          process_lineage: { count: 0, items: [], raw: {} },
          hunt_queries: { count: 0, items: [], raw: {} },
          registry_artifacts: { count: 0, items: [], raw: {} },
          windows_services: { count: 0, items: [], raw: {} },
          scheduled_tasks: {
            count: 1,
            items: [{ task_name: 'My Task', task_path: '\\My Task', operation_type: 'created', confidence_score: 0.9 }],
            raw: {}
          }
        }
      }
    };
    await openExecutionWithData(page, exec);

    // Navigate to the Extraction tab
    const extractionTab = page.locator('#exec-tab-strip button.exec-tab').filter({ hasText: 'Extraction' });
    await extractionTab.click();

    // The Sub-Agents details section -- expand it
    const subAgentsDetails = page.locator('details').filter({ hasText: /Sub-Agents.*Individual/ });
    if (await subAgentsDetails.count() > 0) {
      await subAgentsDetails.first().evaluate((el: HTMLDetailsElement) => { el.open = true; });
    }

    // The Scheduled Tasks Extraction card must be present
    const schedCard = page.locator('summary').filter({ hasText: 'Scheduled Tasks Extraction' });
    await expect(schedCard).toBeVisible({ timeout: 3000 });

    // And it must show 1 item (not 0)
    await expect(schedCard).toContainText('(1 item)');
  });

  test('all six sub-agent cards render even when only one type has results', async ({ page }) => {
    const exec = {
      ...BASE_EXEC,
      extraction_result: {
        observables: [{ type: 'scheduled_tasks', value: 'My Task', platform: 'Windows', source_context: '' }],
        summary: { count: 1, platforms_detected: ['Windows'] },
        discrete_huntables_count: 1,
        content: 'My Task',
        subresults: {
          cmdline: { count: 0, items: [], raw: {} },
          process_lineage: { count: 0, items: [], raw: {} },
          hunt_queries: { count: 0, items: [], raw: {} },
          registry_artifacts: { count: 0, items: [], raw: {} },
          windows_services: { count: 0, items: [], raw: {} },
          scheduled_tasks: { count: 1, items: [{ task_name: 'My Task', task_path: '\\My Task' }], raw: {} }
        }
      }
    };
    await openExecutionWithData(page, exec);

    const extractionTab = page.locator('#exec-tab-strip button.exec-tab').filter({ hasText: 'Extraction' });
    await extractionTab.click();

    const subAgentsDetails = page.locator('details').filter({ hasText: /Sub-Agents.*Individual/ });
    if (await subAgentsDetails.count() > 0) {
      await subAgentsDetails.first().evaluate((el: HTMLDetailsElement) => { el.open = true; });
    }

    const expectedCards = [
      'Command Line Extraction',
      'Process Lineage Extraction',
      'Hunt Queries Extraction',
      'Registry Artifacts Extraction',
      'Windows Services Extraction',
      'Scheduled Tasks Extraction',
    ];
    for (const cardTitle of expectedCards) {
      const card = page.locator('summary').filter({ hasText: cardTitle });
      await expect(card).toBeVisible({ timeout: 3000 });
    }
  });
});

// ---------------------------------------------------------------------------
// Regression: Observable Traceability panel must count all six observable
// types, not just cmdline/process_lineage/hunt_queries.
//
// Root cause (recurred 3x): the be80168c fix expanded the traceability panel
// to all six types in workflow_executions.html and sigma_queue.html but never
// touched workflow.html — the template the /workflow#executions modal actually
// uses. Its traceabilitySection() computed totalObs over only the original
// three types, so an execution whose observables were ENTIRELY
// registry_artifacts / windows_services / scheduled_tasks summed to
// totalObs === 0 and rendered "Traceability unavailable (legacy execution or
// no observables)" even though the /observables API returned them correctly.
//
// The 18 backend tests in test_observable_traceability_regressions.py exercise
// _build_observables_response directly and CANNOT catch this template drift —
// hence the recurrence. These tests mock /observables and assert the rendered
// panel, which is the only layer that regresses.
// ---------------------------------------------------------------------------

async function openExecutionWithObservables(page: any, execData: object, observablesPayload: object) {
  await page.route(`**/api/workflow/executions/99999`, (route: any) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(execData) })
  );
  await page.route(`**/api/workflow/executions/99999/observables`, (route: any) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(observablesPayload) })
  );
  await page.route(/\/api\/workflow\/executions\?/, (route: any) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ executions: [], total: 0 }) })
  );
  await page.route(`**/api/workflow/config`, (route: any) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent_models: {}, ranking_threshold: 6.0 }) })
  );
  await page.goto(`${BASE}/workflow#executions`);
  await page.waitForLoadState('networkidle');
  await page.waitForFunction(
    () => typeof (window as any).viewExecution === 'function',
    { timeout: 5000 }
  );
  try {
    await page.evaluate(() => (window as any).viewExecution(99999));
  } catch (e) {
    if (!String(e).includes('Execution context was destroyed')) throw e;
    await page.waitForLoadState('networkidle');
    await page.waitForFunction(() => typeof (window as any).viewExecution === 'function', { timeout: 5000 });
    await page.evaluate(() => (window as any).viewExecution(99999));
  }
  await page.waitForSelector('#executionModal:not(.hidden)', { timeout: 5000 });
}

// Mirrors execution 2615 from the bug report: observables are ENTIRELY in the
// three types that the broken workflow.html panel never counted, plus a
// scheduled_tasks item to lock the third regressed type in one assertion.
const REGRESSED_TYPES_OBSERVABLES = {
  execution_id: 99999,
  observables: {
    cmdline: [],
    process_lineage: [],
    hunt_queries: [],
    registry_artifacts: [
      {
        observable_value: 'HKLM\\System\\CurrentControlSet\\Control\\Lsa',
        observable_type: 'registry_artifacts',
        source_evidence: 'REGRESSION-MARKER-2615 reg add HKLM Lsa /v DisableRestrictedAdmin',
        extraction_justification: 'Hive-rooted registry modification observable via Sysmon EID 13.',
        confidence_score: 0.95,
        subagent_name: 'Registry Extractor',
        model_version: 'test/model-x',
        extraction_timestamp: '2026-05-18T14:54:41Z',
      },
      {
        observable_value: 'HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest',
        observable_type: 'registry_artifacts',
        source_evidence: 'reg add WDigest /v UseLogonCredential /t REG_DWORD /d 1 /f',
        extraction_justification: 'Forces plaintext credential storage.',
        confidence_score: 0.9,
        subagent_name: 'Registry Extractor',
        model_version: 'test/model-x',
        extraction_timestamp: '2026-05-18T14:54:41Z',
      },
    ],
    windows_services: [
      {
        observable_value: 'WebrootCheck',
        observable_type: 'windows_services',
        source_evidence: 'created a service titled WebrootCheck running cmd.exe /c c:\\temp\\1.bat',
        extraction_justification: 'Service creation for persistence.',
        confidence_score: 0.96,
        subagent_name: 'Windows Services Extractor',
        model_version: 'test/model-x',
        extraction_timestamp: '2026-05-18T14:54:41Z',
      },
    ],
    scheduled_tasks: [
      {
        observable_value: 'EvilTask',
        observable_type: 'scheduled_tasks',
        source_evidence: 'schtasks /create /tn EvilTask /tr c:\\temp\\evil.exe',
        extraction_justification: 'Persistence via scheduled task.',
        confidence_score: 0.88,
        subagent_name: 'Scheduled Tasks Extractor',
        model_version: 'test/model-x',
        extraction_timestamp: '2026-05-18T14:54:41Z',
      },
    ],
  },
};

const ALL_EMPTY_OBSERVABLES = {
  execution_id: 99999,
  observables: {
    cmdline: [], process_lineage: [], hunt_queries: [],
    registry_artifacts: [], windows_services: [], scheduled_tasks: [],
  },
};

test.describe('Execution Detail - Observable Traceability type coverage regression', () => {
  test('panel renders registry/services/scheduled observables (does NOT show "Traceability unavailable")', async ({ page }) => {
    await openExecutionWithObservables(page, BASE_EXEC, REGRESSED_TYPES_OBSERVABLES);

    const extractionTab = page.locator('#exec-tab-strip button.exec-tab').filter({ hasText: 'Extraction' });
    await extractionTab.click();

    const trace = page.locator('.observable-traceability');
    await expect(trace).toBeVisible({ timeout: 3000 });

    // The exact regression symptom from the bug report — must be ABSENT.
    await expect(trace).not.toContainText('Traceability unavailable (legacy execution or no observables)');

    // All three previously-uncounted types must surface with correct counts.
    await expect(trace).toContainText('Registry Artifacts (2)');
    await expect(trace).toContainText('Windows Services (1)');
    await expect(trace).toContainText('Scheduled Tasks (1)');

    // Traceability detail fields (source_evidence) must render, not just headers.
    await expect(trace).toContainText('REGRESSION-MARKER-2615');
  });

  test('panel still shows "Traceability unavailable" when all six types are empty (boundary guard)', async ({ page }) => {
    await openExecutionWithObservables(page, BASE_EXEC, ALL_EMPTY_OBSERVABLES);

    const extractionTab = page.locator('#exec-tab-strip button.exec-tab').filter({ hasText: 'Extraction' });
    await extractionTab.click();

    const trace = page.locator('.observable-traceability');
    await expect(trace).toBeVisible({ timeout: 3000 });
    await expect(trace).toContainText('Traceability unavailable (legacy execution or no observables)');
  });
});

// ---------------------------------------------------------------------------
// Regression: per-SIGMA-rule "Observables Used" (filterObservablesForRule /
// observablesUsedSection) must resolve observables_used indices across all six
// observable types using offset math matching the backend
// _build_observables_section flat order.
//
// Twin of the be80168c sigma_queue.html fix that workflow.html missed.
// workflow.html built `flat` from only cmdline/process_lineage/hunt_queries
// and used hand-rolled cmdLen/procLen offsets, so a SIGMA rule whose
// observables_used indices point into registry/services/scheduled (flat idx
// past the 3-type length) resolved to "No observables for this execution" —
// silently MIS-ATTRIBUTING the rule's real provenance (worse than the panel
// bug: wrong data, not merely hidden). These tests call the shipped global
// functions directly (no modal) — they fail before the fix, pass after.
// ---------------------------------------------------------------------------

async function gotoWorkflowWithGlobals(page: any) {
  await page.route(/\/api\/workflow\/executions\?/, (route: any) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ executions: [], total: 0 }) })
  );
  await page.route(`**/api/workflow/config`, (route: any) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent_models: {}, ranking_threshold: 6.0 }) })
  );
  await page.goto(`${BASE}/workflow`);
  await page.waitForLoadState('networkidle');
  await page.waitForFunction(
    () => typeof (window as any).filterObservablesForRule === 'function'
       && typeof (window as any).observablesUsedSection === 'function',
    { timeout: 5000 }
  );
  // Settle the post-DOMContentLoaded hash navigation (same race the modal
  // tests guard) before evaluating in the page context.
  await page.waitForLoadState('networkidle');
}

// 6-type payload. Flat order per OBS_TYPE_ORDER / _build_observables_section:
//   cmdline[0,1]=flat 0,1 | process_lineage()= | hunt_queries[0]=flat 2
//   registry_artifacts[0,1]=flat 3,4 | windows_services[0]=flat 5
//   scheduled_tasks[0]=flat 6
const OBS_6 = {
  cmdline: [
    { observable_value: 'cmd-A', observable_type: 'cmdline' },
    { observable_value: 'cmd-B', observable_type: 'cmdline' },
  ],
  process_lineage: [],
  hunt_queries: [{ observable_value: 'hunt-A', observable_type: 'hunt_queries' }],
  registry_artifacts: [
    { observable_value: 'REG-IDX3', observable_type: 'registry_artifacts', source_evidence: 'ev', confidence_score: 0.9 },
    { observable_value: 'REG-IDX4', observable_type: 'registry_artifacts' },
  ],
  windows_services: [{ observable_value: 'SVC-IDX5', observable_type: 'windows_services', source_evidence: 'ev', confidence_score: 0.95 }],
  scheduled_tasks: [{ observable_value: 'TASK-IDX6', observable_type: 'scheduled_tasks' }],
};

test.describe('Observables Used (per-SIGMA-rule) type coverage regression', () => {
  test('filterObservablesForRule resolves indices across all 6 types via offset math', async ({ page }) => {
    await gotoWorkflowWithGlobals(page);

    const res = await page.evaluate((obs: any) => {
      // Rule grounded in flat idx 3 (registry[0]), 5 (services[0]), 6 (sched[0]).
      const rule = { id: 1, rule_metadata: { observables_used: [3, 5, 6] } };
      const out = (window as any).filterObservablesForRule(rule, { observables: obs }).observables;
      const counts = Object.fromEntries(Object.keys(obs).map(k => [k, (out[k] || []).length]));
      return {
        counts,
        regVal: (out.registry_artifacts || [])[0]?.observable_value,
        svcVal: (out.windows_services || [])[0]?.observable_value,
        taskVal: (out.scheduled_tasks || [])[0]?.observable_value,
      };
    }, OBS_6);

    expect(res.counts).toEqual({
      cmdline: 0, process_lineage: 0, hunt_queries: 0,
      registry_artifacts: 1, windows_services: 1, scheduled_tasks: 1,
    });
    // Must select the RIGHT registry item (flat idx 3 == registry_artifacts[0]).
    expect(res.regVal).toBe('REG-IDX3');
    expect(res.svcVal).toBe('SVC-IDX5');
    expect(res.taskVal).toBe('TASK-IDX6');
  });

  test('observablesUsedSection renders registry/services/scheduled (not "No observables")', async ({ page }) => {
    await gotoWorkflowWithGlobals(page);

    const html = await page.evaluate((obs: any) => {
      const rule = { id: 2, rule_metadata: { observables_used: [3, 5, 6] } };
      return (window as any).observablesUsedSection(rule, { observables: obs });
    }, OBS_6);

    expect(html).not.toContain('No observables for this execution');
    expect(html).toContain('Observables Used (3)');
    expect(html).toContain('Registry Artifacts (1)');
    expect(html).toContain('Windows Services (1)');
    expect(html).toContain('Scheduled Tasks (1)');
  });

  test('empty/missing/out-of-range observables_used -> all-6 empty buckets + "No observables" (boundary guard)', async ({ page }) => {
    await gotoWorkflowWithGlobals(page);

    const res = await page.evaluate((obs: any) => {
      const f = (window as any).filterObservablesForRule;
      const s = (window as any).observablesUsedSection;
      const countsOf = (r: any) => {
        const o = f(r, { observables: obs }).observables;
        return Object.values(o).reduce((n: number, a: any) => n + (a?.length || 0), 0);
      };
      const emptyRule = { id: 10, rule_metadata: { observables_used: [] } };
      const missingRule = { id: 11 };                                       // no rule_metadata
      const oorRule = { id: 12, rule_metadata: { observables_used: [99] } }; // out of range
      return {
        emptyKeys: Object.keys(f(emptyRule, { observables: obs }).observables).sort(),
        emptyCount: countsOf(emptyRule),
        missingCount: countsOf(missingRule),
        oorCount: countsOf(oorRule),
        oorHtml: s(oorRule, { observables: obs }),
      };
    }, OBS_6);

    // The fix changed the no-indices early return from 3 keys to all 6 — this
    // assertion fails pre-fix (so it is regression coverage, not just a guard).
    expect(res.emptyKeys).toEqual([
      'cmdline', 'hunt_queries', 'process_lineage',
      'registry_artifacts', 'scheduled_tasks', 'windows_services',
    ]);
    expect(res.emptyCount).toBe(0);
    expect(res.missingCount).toBe(0);
    expect(res.oorCount).toBe(0);
    expect(res.oorHtml).toContain('No observables for this execution');
  });
});
