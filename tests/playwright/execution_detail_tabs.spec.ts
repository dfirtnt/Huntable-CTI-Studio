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
});
