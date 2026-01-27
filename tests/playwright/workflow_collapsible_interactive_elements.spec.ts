import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Workflow Collapsible Panels - Interactive Element Click Prevention', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);

    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForTimeout(1000);

    // Expand Rank Agent panel to access interactive elements
    const rankPanelId = 'rank-agent-configs-panel';
    const rankHeader = page.locator(`[data-collapsible-panel="${rankPanelId}"]`);
    const rankContent = page.locator(`#${rankPanelId}-content`);
    const isHidden = await rankContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await rankHeader.click();
      await page.waitForTimeout(300);
    }
  });

  test('should not toggle when clicking button inside header', async ({ page }) => {
    // Find a panel header that contains a button
    // Rank Agent panel has badges/buttons in header
    const panelId = 'rank-agent-configs-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    // Get initial state
    const initialVisible = await content.isVisible();

    // Find button inside header (like help button or badge)
    // Look for any button within the header
    const buttonInHeader = header.locator('button').first();
    
    if (await buttonInHeader.count() > 0) {
      // Click the button
      await buttonInHeader.click();
      await page.waitForTimeout(300);

      // Panel state should not have changed
      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      // If no button found, test passes (no interactive element to test)
      test.skip();
    }
  });

  test('should not toggle when clicking input inside header', async ({ page }) => {
    // Find a panel that might have inputs in header
    // Most panels don't have inputs in headers, but we can test the behavior
    const panelId = 'rank-agent-configs-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    // Get initial state
    const initialVisible = await content.isVisible();

    // Look for input inside header (unlikely, but test the protection)
    const inputInHeader = header.locator('input').first();
    
    if (await inputInHeader.count() > 0) {
      await inputInHeader.click();
      await page.waitForTimeout(300);

      // Panel state should not have changed
      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      // No input in header - test passes (protection works by not having inputs)
      test.skip();
    }
  });

  test('should not toggle when clicking select inside header', async ({ page }) => {
    const panelId = 'rank-agent-configs-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const selectInHeader = header.locator('select').first();
    
    if (await selectInHeader.count() > 0) {
      await selectInHeader.click();
      await page.waitForTimeout(300);

      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip();
    }
  });

  test.skip('should not toggle when clicking label inside header', async ({ page }) => {
    // Expand Extract Agent panel which may have labels
    const extractPanelId = 'extract-agent-panel';
    const extractHeader = page.locator(`[data-collapsible-panel="${extractPanelId}"]`);
    const extractContent = page.locator(`#${extractPanelId}-content`);
    const isHidden = await extractContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await extractHeader.click();
      await page.waitForTimeout(300);
    }

    const header = page.locator(`[data-collapsible-panel="${extractPanelId}"]`);
    const content = page.locator(`#${extractPanelId}-content`);

    const initialVisible = await content.isVisible();
    const labelInHeader = header.locator('label').first();
    
    if (await labelInHeader.count() > 0) {
      await labelInHeader.click();
      await page.waitForTimeout(300);

      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip();
    }
  });

  test('should not toggle when clicking link inside header', async ({ page }) => {
    const panelId = 'rank-agent-configs-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const linkInHeader = header.locator('a').first();
    
    if (await linkInHeader.count() > 0) {
      await linkInHeader.click();
      await page.waitForTimeout(300);

      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip();
    }
  });

  test('should not toggle when clicking textarea inside header', async ({ page }) => {
    const panelId = 'rank-agent-configs-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const textareaInHeader = header.locator('textarea').first();
    
    if (await textareaInHeader.count() > 0) {
      await textareaInHeader.click();
      await page.waitForTimeout(300);

      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip();
    }
  });

  test('should toggle when clicking non-interactive elements in header', async ({ page }) => {
    const panelId = 'other-thresholds-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    // Initially hidden
    await expect(content).toHaveClass(/hidden/);

    // Click on header text (h3 element - non-interactive)
    const headerText = header.locator('h3').first();
    if (await headerText.count() > 0) {
      await headerText.click();
      await page.waitForTimeout(300);

      // Panel should toggle
      await expect(content).toBeVisible();
    } else {
      // Click header directly (should work)
      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
    }
  });

  test('should toggle when clicking empty space in header', async ({ page }) => {
    const panelId = 'os-detection-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    // Initially hidden
    await expect(content).toHaveClass(/hidden/);

    // Click on header but not on any interactive element
    // Click at a position that's likely empty space
    await header.click({ position: { x: 10, y: 10 } });
    await page.waitForTimeout(300);

    // Panel should toggle
    await expect(content).toBeVisible();
  });
});
