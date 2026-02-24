import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const AGENT_EVALS_URL = `${BASE}/mlops/agent-evals`;

/**
 * Agent Evals – read-only checks.
 * No Run Evaluation: that mutates production (executions, eval records). Use Playwright MCP for manual E2E.
 */
test.describe('Agent Evals (read-only)', () => {
  test('Hunt Queries: Load Previous Results shows results/chart', async ({ page }) => {
    await page.goto(AGENT_EVALS_URL);
    await page.waitForLoadState('networkidle');

    await expect(page.getByRole('heading', { name: 'Agent Evaluations' })).toBeVisible();
    await page.locator('#subagentSelect').selectOption('hunt_queries');

    await page.locator('#loadPreviousResultsBtn').click();
    await page
      .waitForResponse(
        (r) =>
          r.url().includes('/api/evaluations/subagent-eval-results') ||
          r.url().includes('/api/evaluations/subagent-eval-aggregate'),
        { timeout: 20000 }
      )
      .catch(() => {});

    await page.waitForTimeout(1500);
    const resultsTable = page.locator('#resultsTable');
    const aggregateSection = page.locator('#aggregateScores');
    const chartContainer = page.locator('#chartScrollContainer');
    expect(
      (await resultsTable.isVisible()) || (await aggregateSection.isVisible()) || (await chartContainer.isVisible())
    ).toBeTruthy();
  });

  test('Load Previous Results: no duplicate article rows in table', async ({ page }) => {
    await page.goto(AGENT_EVALS_URL);
    await page.waitForLoadState('networkidle');
    await page.locator('#subagentSelect').selectOption('cmdline');
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/api/evaluations/subagent-eval-results') &&
          r.request().method() === 'GET',
        { timeout: 20000 }
      ),
      page.locator('#loadPreviousResultsBtn').click(),
    ]);
    await page.waitForTimeout(2000);

    const rows = page.locator('#resultsTable table tbody tr');
    const count = await rows.count();
    if (count === 0) {
      const msg = await page.locator('#resultsTable').textContent();
      const s = typeof msg === 'string' ? msg : '';
      if (s.includes('No previous results') || s.includes('No results available')) {
        test.skip();
      }
      return;
    }

    const data = await response.json().catch(() => ({ results: [], articles: [] }));
    const results: { article_id?: number; url?: string }[] = data.results || [];
    const articles = data.articles || [];
    const expectedRows = articles.length > 0 ? articles.length : new Set(results.map((r) => (r.article_id != null ? `id:${r.article_id}` : `url:${r.url}`))).size;
    expect(
      count,
      `Table should have one row per article (expected ${expectedRows} rows, got ${count}). Duplicates indicate grouping bug.`
    ).toBe(expectedRows);
  });
});
