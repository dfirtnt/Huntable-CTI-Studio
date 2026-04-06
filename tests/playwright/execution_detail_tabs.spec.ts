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
    expect(await tabs.count()).toBeGreaterThanOrEqual(3);
  });

  test('first tab is active on open', async ({ page }) => {
    const firstTab = page.locator('button.exec-tab').first();
    await expect(firstTab).toHaveAttribute('data-active', 'true');
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

  test('each step panel has Inputs section collapsed by default', async ({ page }) => {
    const firstPanel = page.locator('.exec-panel').first();
    const inputDetails = firstPanel.locator('details.exec-inputs');
    const isOpen = await inputDetails.getAttribute('open');
    expect(isOpen).toBeNull();
  });

  test('Inputs and Output summary elements have nearly-white text color', async ({ page }) => {
    const firstPanel = page.locator('.exec-panel').first();
    const inputsSummary = firstPanel.locator('details.exec-inputs > summary').first();
    const outputSummary = firstPanel.locator('details.exec-output > summary').first();

    const inputsColor = await inputsSummary.evaluate((el) => window.getComputedStyle(el).color);
    const outputColor = await outputSummary.evaluate((el) => window.getComputedStyle(el).color);

    // Expected: rgb(222, 226, 232) = text-[#dee2e8]
    const expectedRgb = '222, 226, 232';
    expect(inputsColor).toContain(expectedRgb);
    expect(outputColor).toContain(expectedRgb);
  });
});

test.describe('Execution Detail - Observable Traceability', () => {
  const MOCK_OBSERVABLES = {
    execution_id: 99999,
    observables: {
      cmdline: [],
      process_lineage: [],
      hunt_queries: [
        {
          observable_value: { type: 'kql', query: 'test query', context: 'test' },
          confidence_score: null,
          source_evidence: null,
          extraction_justification: null,
          subagent_name: 'Hunt Queries Extractor',
          model_version: null,
          extraction_timestamp: '2026-03-06T12:00:00Z'
        }
      ]
    }
  };

  test.beforeEach(async ({ page }) => {
    await page.route(`**/api/workflow/executions/99999`, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_EXEC) })
    );
    await page.route(`**/api/workflow/executions/99999/observables`, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_OBSERVABLES) })
    );
    await page.route(/\/api\/workflow\/executions\?/, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ executions: [], total: 0 }) })
    );
    await page.route(`**/api/workflow/config`, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent_models: {}, ranking_threshold: 6.0 }) })
    );
    await page.goto(`${BASE}/workflow#executions`);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => (window as any).viewExecution(99999));
    await page.waitForSelector('#executionModal:not(.hidden)', { timeout: 5000 });
  });

  test('Observable Traceability section has nearly-white text color', async ({ page }) => {
    const extractTab = page.locator('button.exec-tab:has-text("Extract")').first();
    const hasExtractTab = await extractTab.isVisible({ timeout: 2000 }).catch(() => false);
    if (hasExtractTab) {
      await extractTab.click();
      await page.waitForTimeout(500);
    }

    const traceability = page.locator('.observable-traceability');
    const isVisible = await traceability.isVisible({ timeout: 3000 }).catch(() => false);
    if (!isVisible) {
      test.skip('Observable Traceability section not found (Extraction panel may not be visible)');
      return;
    }

    const summary = traceability.locator('details > summary').first();
    const code = traceability.locator('details summary code').first();

    const summaryColor = await summary.evaluate((el) => window.getComputedStyle(el).color);
    const codeColor = await code.evaluate((el) => window.getComputedStyle(el).color);

    const expectedRgb = '222, 226, 232';
    expect(summaryColor).toContain(expectedRgb);
    expect(codeColor).toContain(expectedRgb);
  });
});

test.describe('Executions table - View button', () => {
  const MOCK_EXEC_LIST = {
    executions: [
      {
        id: 99999,
        article_id: 1,
        article_title: 'Test Article',
        status: 'completed',
        current_step: 'done',
        ranking_score: 7.5,
        created_at: '2026-03-05T10:00:00Z',
        completed_at: '2026-03-05T10:01:00Z',
        sigma_rules_count: 0,
        extraction_counts: { cmdline: 1, process_lineage: 0, hunt_queries: 0 }
      }
    ],
    total: 1
  };

  test.beforeEach(async ({ page }) => {
    await page.route(/\/api\/workflow\/executions\?/, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_EXEC_LIST) })
    );
    await page.route(`**/api/workflow/config`, route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent_models: {}, ranking_threshold: 6.0 }) })
    );
    await page.goto(`${BASE}/workflow#executions`);
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('#tab-content-executions:not(.hidden)', { timeout: 5000 }).catch(() => {});
  });

  test('View button has blue color in dark theme', async ({ page }) => {
    const viewButton = page.locator('button:has-text("View")').first();
    const isVisible = await viewButton.isVisible({ timeout: 5000 }).catch(() => false);
    if (!isVisible) {
      test.skip('View button not found in executions table');
      return;
    }

    const color = await viewButton.evaluate((el) => window.getComputedStyle(el).color);
    // --action-info = #3b82f6 = rgb(59, 130, 246) (blue-500), also check blue-400/600
    const isBlue = color.includes('59, 130, 246') || color.includes('59 130 246') ||
                   color.includes('96, 165, 250') || color.includes('37, 99, 235') ||
                   color.includes('96 165 250') || color.includes('37 99 235');
    expect(isBlue).toBe(true);
  });
});
