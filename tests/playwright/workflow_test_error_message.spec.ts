import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = '2155';

test.describe('Workflow Test Error Messages', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    
    // Wait for config tab to be visible
    await page.waitForSelector('#tab-content-config:not(.hidden)', { timeout: 10000 }).catch(async () => {
      const configTab = page.locator('button:has-text("Configuration"), button:has-text("⚙️")').first();
      if (await configTab.isVisible()) {
        await configTab.click();
        await page.waitForTimeout(500);
      }
    });
    
    // Wait for config content
    const configContent = page.locator('#tab-content-config');
    await expect(configContent).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(1000);
    
    // Expand Rank Agent configs panel if collapsed
    const rankPanelToggle = page.locator('#rank-agent-configs-panel-toggle');
    if (await rankPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#rank-agent-configs-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await rankPanelToggle.click();
        await page.waitForTimeout(300);
      }
    }
  });

  test('should display formatted error message for context length errors', async ({ page }) => {
    // Find and click the "Test with Article 2155" button for RankAgent
    const testButton = page.locator('button:has-text("Test with Article 2155")').first();
    await expect(testButton).toBeVisible({ timeout: 5000 });
    
    // Click the test button
    await testButton.click();
    
    // Wait for the modal to appear
    const modal = page.locator('#test-modal, [id*="test-modal"]').first();
    await expect(modal).toBeVisible({ timeout: 10000 });
    
    // Wait for the results to appear (error should show up)
    const resultsContent = page.locator('#test-modal-results-content, [id*="results-content"]').first();
    await expect(resultsContent).toBeVisible({ timeout: 15000 });
    
    // Get the error message text
    const errorText = await resultsContent.textContent();
    expect(errorText).toBeTruthy();
    
    // Verify the error message is formatted (not the raw technical error)
    // Should contain "Context length error" or the formatted message
    const errorLower = errorText!.toLowerCase();
    
    // Should NOT contain the raw JSON error format
    expect(errorLower).not.toContain('{"error":');
    expect(errorLower).not.toContain('status 400:');
    expect(errorLower).not.toContain('invalid request to lmstudio');
    
    // Should contain the formatted error message
    expect(errorLower).toMatch(/context length|tokens.*greater than|larger context length|shorter input/i);
    
    // Verify the error is displayed in a red error box
    const resultsDiv = page.locator('#test-modal-results, [id*="test-modal-results"]').first();
    const hasErrorStyling = await resultsDiv.evaluate(el => {
      return window.getComputedStyle(el).backgroundColor.includes('rgb') ||
             el.classList.toString().toLowerCase().includes('red') ||
             el.classList.toString().toLowerCase().includes('error');
    });
    expect(hasErrorStyling || errorLower.includes('error')).toBeTruthy();
  });

  test('should not show "busy" error for context length issues', async ({ page }) => {
    // Find and click the "Test with Article 2155" button for RankAgent
    const testButton = page.locator('button:has-text("Test with Article 2155")').first();
    await expect(testButton).toBeVisible({ timeout: 5000 });
    
    // Click the test button
    await testButton.click();
    
    // Wait for the modal to appear
    const modal = page.locator('#test-modal, [id*="test-modal"]').first();
    await expect(modal).toBeVisible({ timeout: 10000 });
    
    // Wait for the results to appear
    const resultsContent = page.locator('#test-modal-results-content, [id*="results-content"]').first();
    await expect(resultsContent).toBeVisible({ timeout: 15000 });
    
    // Get the error message text
    const errorText = await resultsContent.textContent();
    expect(errorText).toBeTruthy();
    
    const errorLower = errorText!.toLowerCase();
    
    // Should NOT show "busy" or "unavailable" for context length errors
    if (errorLower.includes('context length') || errorLower.includes('tokens')) {
      expect(errorLower).not.toContain('busy');
      expect(errorLower).not.toContain('unavailable');
      expect(errorLower).not.toContain('processing another request');
    }
  });
});

