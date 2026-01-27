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
});
