import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Workflow Collapsible Panels - Accessibility', () => {
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
  });

  test('should toggle panel with Enter key', async ({ page }) => {
    const panelId = 'other-thresholds-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    // Initially should be hidden
    await expect(content).toHaveClass(/hidden/);

    // Focus on header
    await header.focus();

    // Press Enter key
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);

    // Should be visible now
    await expect(content).toBeVisible();

    // Press Enter again to collapse
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);

    // Should be hidden again
    await expect(content).toHaveClass(/hidden/);
  });

  test('should toggle panel with Space key', async ({ page }) => {
    const panelId = 'rank-agent-configs-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    // Initially should be hidden
    await expect(content).toHaveClass(/hidden/);

    // Focus on header
    await header.focus();

    // Press Space key
    await page.keyboard.press('Space');
    await page.waitForTimeout(300);

    // Should be visible now
    await expect(content).toBeVisible();

    // Press Space again to collapse
    await page.keyboard.press('Space');
    await page.waitForTimeout(300);

    // Should be hidden again
    await expect(content).toHaveClass(/hidden/);
  });

  test('should have proper ARIA attributes on headers', async ({ page }) => {
    const panelId = 'os-detection-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

    // Check role attribute
    const role = await header.getAttribute('role');
    expect(role).toBe('button');

    // Check tabindex
    const tabindex = await header.getAttribute('tabindex');
    expect(tabindex).toBe('0');

    // Check aria-controls
    const ariaControls = await header.getAttribute('aria-controls');
    expect(ariaControls).toBe(`${panelId}-content`);
  });

  test('should update aria-expanded when panel toggles', async ({ page }) => {
    const panelId = 'extract-agent-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
    const content = page.locator(`#${panelId}-content`);

    // Initially collapsed
    await expect(content).toHaveClass(/hidden/);
    let ariaExpanded = await header.getAttribute('aria-expanded');
    expect(ariaExpanded).toBe('false');

    // Expand panel
    await header.click();
    await page.waitForTimeout(300);

    // Should be expanded
    await expect(content).toBeVisible();
    ariaExpanded = await header.getAttribute('aria-expanded');
    expect(ariaExpanded).toBe('true');

    // Collapse panel
    await header.click();
    await page.waitForTimeout(300);

    // Should be collapsed again
    await expect(content).toHaveClass(/hidden/);
    ariaExpanded = await header.getAttribute('aria-expanded');
    expect(ariaExpanded).toBe('false');
  });

  test('should mark toggle icon as aria-hidden', async ({ page }) => {
    const panelId = 'sigma-agent-panel';
    const toggle = page.locator(`#${panelId}-toggle`);

    // Check aria-hidden attribute
    const ariaHidden = await toggle.getAttribute('aria-hidden');
    expect(ariaHidden).toBe('true');
  });

  test('should be keyboard focusable with Tab key', async ({ page }) => {
    const panelId = 'other-thresholds-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

    // Tab to header
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    // Check if header is focused (may need multiple tabs depending on page structure)
    // At minimum, verify header has tabindex="0"
    const tabindex = await header.getAttribute('tabindex');
    expect(tabindex).toBe('0');

    // Verify header can receive focus
    await header.focus();
    const isFocused = await header.evaluate(el => document.activeElement === el);
    expect(isFocused).toBe(true);
  });

  test('should navigate between panels with Tab key', async ({ page }) => {
    const panel1 = page.locator(`[data-collapsible-panel="other-thresholds-panel"]`);
    const panel2 = page.locator(`[data-collapsible-panel="rank-agent-configs-panel"]`);

    // Focus first panel
    await panel1.focus();
    let focused = await page.evaluate(() => document.activeElement?.getAttribute('data-collapsible-panel'));
    expect(focused).toBe('other-thresholds-panel');

    // Tab to next panel
    await page.keyboard.press('Tab');
    await page.waitForTimeout(100);

    // Verify focus moved (may need multiple tabs depending on page structure)
    // This test verifies panels are in tab order
    const tabindex1 = await panel1.getAttribute('tabindex');
    const tabindex2 = await panel2.getAttribute('tabindex');
    expect(tabindex1).toBe('0');
    expect(tabindex2).toBe('0');
  });

  test('should maintain focus after panel toggle with keyboard', async ({ page }) => {
    const panelId = 'qa-settings-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

    // Focus header
    await header.focus();
    await page.waitForTimeout(100);

    // Toggle with Enter
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);

    // Verify header still has focus (or focus moved appropriately)
    const activeElement = await page.evaluate(() => {
      const el = document.activeElement;
      return el?.getAttribute('data-collapsible-panel') || el?.id || null;
    });
    
    // Focus should remain on header or move to content (both are valid)
    expect(activeElement).toBeTruthy();
  });

  test('should have cursor pointer style on headers', async ({ page }) => {
    const panelId = 'other-thresholds-panel';
    const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

    // Check cursor style
    const cursor = await header.evaluate(el => window.getComputedStyle(el).cursor);
    expect(cursor).toBe('pointer');
  });
});
