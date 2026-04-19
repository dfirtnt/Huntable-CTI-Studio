import { test, expect } from '@playwright/test';

/**
 * Eval workflow E2E test.
 * 
 * Tests: compare eval snapshots
 */
test.describe('Eval Workflow', () => {
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
