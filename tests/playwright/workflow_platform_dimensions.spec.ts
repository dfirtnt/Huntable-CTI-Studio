/**
 * Per-execution trace — Domains + Products dimensions (Phase D).
 *
 * The platform classifier now also emits security Domains and named Products
 * (stored in error_log.os_detection_result). This spec mocks an execution carrying
 * those fields and asserts they render in the Platform Detection step of the trace.
 *
 * In goal-mode the surfacing counts as delivered only when this prints green.
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

const MOCK_EXEC = {
  id: 88888,
  article_id: 1,
  article_title: 'Linux Intrusion via F5 and Confluence',
  article_url: 'https://example.com',
  article_content: 'Linux intrusion content',
  status: 'completed',
  current_step: 'done',
  termination_reason: null,
  termination_details: null,
  error_message: null,
  error_log: {
    os_detection_result: {
      detected_os: 'Linux',
      platforms_detected: ['Linux'],
      domains: ['Network', 'Identity', 'Endpoint'],
      products: ['F5 BIG-IP', 'Atlassian Confluence', 'Active Directory'],
      detection_method: 'kb_scoring',
      confidence: 'high',
      similarities: { Linux: 0.71, Windows: 0.29, MacOS: 0.0 },
    },
  },
  junk_filter_result: { is_huntable: true, confidence: 0.9, original_length: 1000, filtered_length: 800, chunks_removed: 1 },
  ranking_score: 7.5,
  extraction_result: { observables: [], summary: { count: 0, platforms_detected: ['Linux'] }, discrete_huntables_count: 0, subresults: {} },
  sigma_rules: [],
  similarity_results: [],
  config_snapshot: { agent_models: {} },
  created_at: '2026-06-19T10:00:00Z',
  completed_at: '2026-06-19T10:01:00Z',
};

test.describe('Execution trace - Domains/Products dimensions', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`**/api/workflow/executions/88888`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_EXEC) }),
    );
    await page.route(`**/api/workflow/executions/88888/observables`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ execution_id: 88888, observables: {} }) }),
    );
    await page.route(/\/api\/workflow\/executions\?/, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ executions: [], total: 0 }) }),
    );
    await page.route(`**/api/workflow/config`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent_models: {}, ranking_threshold: 6.0 }) }),
    );
    await page.goto(`${BASE}/workflow#executions`);
    await page.waitForLoadState('networkidle');
    await page.waitForFunction(() => typeof (window as any).viewExecution === 'function', { timeout: 5000 });
    await page.waitForLoadState('networkidle');
    try {
      await page.evaluate(() => (window as any).viewExecution(88888));
    } catch (e) {
      if (!String(e).includes('Execution context was destroyed')) throw e;
      await page.waitForLoadState('networkidle');
      await page.evaluate(() => (window as any).viewExecution(88888));
    }
    await page.waitForSelector('#executionModal:not(.hidden)', { timeout: 5000 });
  });

  test('platform detection step shows Domains and Products', async ({ page }) => {
    const platformTab = page.locator('#exec-tab-strip button.exec-tab').filter({ hasText: 'Platform Detection' });
    await platformTab.click();
    const panel = page.locator('.exec-panel:not(.hidden)').first();
    await expect(panel).toContainText('Domains:');
    await expect(panel).toContainText('Network');
    await expect(panel).toContainText('Products:');
    await expect(panel).toContainText('F5 BIG-IP');
    await expect(panel).toContainText('Atlassian Confluence');
  });
});
