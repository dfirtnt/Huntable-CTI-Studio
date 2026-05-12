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
  await page.evaluate(() => (window as any).viewExecution(99999));
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
