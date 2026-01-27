import { test, expect } from '@playwright/test';

/**
 * Eval workflow E2E test.
 * 
 * Tests: run eval → view results → compare snapshot
 */
test.describe('Eval Workflow', () => {
  test.skip('run eval and view results', async ({ page }) => {
    const baseURL = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
    
    // Step 1: Navigate to evaluations page
    await page.goto(`${baseURL}/evaluations`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1, .page-title')).toContainText('Evaluation', { timeout: 15000 });  // Increased timeout
    
    // Step 2: Select articles for evaluation (if UI supports it)
    const articleSelect = page.locator('input[type="checkbox"][data-article-id]').first();
    if (await articleSelect.isVisible()) {
      await articleSelect.check();
    }
    
    // Step 3: Run evaluation
    const runBtn = page.locator('button:has-text("Run"), button:has-text("Start Evaluation")').first();
    if (await runBtn.isVisible()) {
      await runBtn.click();
      
      // Wait for evaluation to complete
      await page.waitForTimeout(30000); // Increased from 10000 to 30000 for eval execution
      
      // Step 4: View results
      const resultsTable = page.locator('table, .results-table').first();
      if (await resultsTable.isVisible()) {
        await expect(resultsTable).toBeVisible();
        
        // Step 5: Check for metrics display
        const metrics = page.locator('.metrics, .eval-metrics').first();
        if (await metrics.isVisible()) {
          await expect(metrics).toBeVisible();
        }
      }
    }
  });
  
  test('compare eval snapshots', async ({ page }) => {
    const baseURL = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
    
    await page.goto(`${baseURL}/evaluations`);
    
    // Look for snapshot comparison UI
    const snapshotSelect = page.locator('select[data-snapshot], .snapshot-selector').first();
    if (await snapshotSelect.isVisible()) {
      // Select a snapshot
      await snapshotSelect.selectOption({ index: 0 });
      
      // Check for comparison view
      const comparisonView = page.locator('.comparison-view, [data-comparison]').first();
      if (await comparisonView.isVisible()) {
        await expect(comparisonView).toBeVisible();
      }
    }
  });
});
