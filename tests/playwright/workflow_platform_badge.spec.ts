/**
 * Shared review queue -- platform badge (spec §7).
 *
 * Linux-generated rules enter the SAME review queue as Windows rules, distinguished
 * only by a platform badge (phase one adds a badge, not filters). This spec mocks
 * the queue list endpoint with a Linux rule carrying rule_metadata.platform and
 * asserts the badge renders in the queue row.
 *
 * In goal-mode the badge counts as delivered only when this spec prints green
 * (the evaluator cannot see a browser) -- spec §0.1/§7.
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

const LINUX_RULE = {
  id: 987654,
  article_id: 1,
  article_title: 'Linux Telemetry Test Article',
  workflow_execution_id: null,
  rule_yaml:
    'title: Suspicious Linux Process\nlogsource:\n  product: linux\n  category: process_creation\ndetection:\n  selection:\n    CommandLine|contains: id\n  condition: selection\n',
  rule_metadata: {
    title: 'Suspicious Linux Process',
    platform: 'linux',
    telemetry_category: 'process_creation',
    generation_basis: 'process_creation_generic',
    detection_readiness: 'generic',
  },
  similarity_scores: [],
  max_similarity: 0.1,
  behavioral_matches_found: 0,
  total_candidates_evaluated: 5,
  status: 'pending',
  reviewed_by: null,
  review_notes: null,
  pr_submitted: false,
  pr_url: null,
  created_at: '2026-06-19T01:00:00Z',
  reviewed_at: null,
};

test.describe('Review queue - platform badge', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/api\/sigma-queue\/list/, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [LINUX_RULE], total: 1, limit: 50, offset: 0 }),
      }),
    );
    await page.goto(`${BASE}/workflow#queue`);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => {
      if (typeof (window as any).switchTab === 'function') (window as any).switchTab('queue');
    });
    await page.waitForSelector('#queueTableBody', { timeout: 15000 });
  });

  test('renders a platform badge on a Linux queue rule', async ({ page }) => {
    const row = page.locator('#queue-row-987654');
    await expect(row).toBeVisible({ timeout: 15000 });
    // The badge is a dedicated span, distinct from the rule title text.
    const badge = row.locator('.q-badge.platform');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText('Linux');
  });

  test('rule detail view shows the platform', async ({ page }) => {
    await page.waitForSelector('#queue-row-987654', { timeout: 15000 });
    await page.evaluate(() => (window as any).previewRule(987654));
    const modal = page.locator('#ruleModal');
    await expect(modal).toBeVisible({ timeout: 10000 });
    await expect(modal).toContainText('Platform:');
    await expect(modal.locator('.q-badge.platform')).toHaveText('Linux');
  });
});
