import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Collapsible Sections', () => {
  
  test.describe('Settings Page', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto(`${BASE}/settings`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000); // Wait for JavaScript to initialize
    });

    test('should expand and collapse Backup Configuration section', async ({ page }) => {
      const content = page.locator('#backupConfigContent');
      const chevron = page.locator('#backupConfigChevron');
      const header = page.locator('h2:has-text("💾 Backup Configuration")').locator('..');

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);

      // Click to expand
      await header.click();
      await page.waitForTimeout(300); // Wait for animation

      // Should be visible now
      await expect(content).toBeVisible();
      // Check transform value (browser may normalize to matrix, so check it's not the default)
      const expandedTransform = await chevron.evaluate(el => window.getComputedStyle(el).transform);
      expect(expandedTransform).not.toBe('none');
      expect(expandedTransform).not.toBe('matrix(1, 0, 0, 1, 0, 0)');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300); // Wait for animation

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
    });
  });

  test.describe('Workflow Config Page', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto(`${BASE}/workflow#config`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000); // Wait for page to fully load

      // Switch to config tab using JavaScript if needed
      await page.evaluate(() => {
        if (typeof switchTab === 'function') {
          switchTab('config');
        }
      });
      await page.waitForTimeout(1000);

      // Wait for config form to be visible
      await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
      await page.waitForTimeout(1000);
    });

    test('should expand and collapse Junk Filter panel', async ({ page }) => {
      const panelId = 'other-thresholds-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick*="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse OS Detection Agent panel', async ({ page }) => {
      const panelId = 'os-detection-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick*="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse Rank Agent Configs panel', async ({ page }) => {
      const panelId = 'rank-agent-configs-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick*="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse Extract Agent panel', async ({ page }) => {
      const panelId = 'extract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick="toggleCollapsible('${panelId}')"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse CmdlineExtract Sub-Agent panel', async ({ page }) => {
      // First expand Extract Agent panel
      const extractPanelId = 'extract-agent-panel';
      const extractButton = page.locator(`button[onclick="toggleCollapsible('${extractPanelId}')"]`);
      await extractButton.click();
      await page.waitForTimeout(300);

      // Now test CmdlineExtract sub-panel
      const panelId = 'cmdlineextract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick="toggleCollapsible('${panelId}')"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse SigExtract Sub-Agent panel', async ({ page }) => {
      // First expand Extract Agent panel
      const extractPanelId = 'extract-agent-panel';
      const extractButton = page.locator(`button[onclick="toggleCollapsible('${extractPanelId}')"]`);
      await extractButton.click();
      await page.waitForTimeout(300);

      // Now test SigExtract sub-panel
      const panelId = 'sigextract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick="toggleCollapsible('${panelId}')"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse EventCodeExtract Sub-Agent panel', async ({ page }) => {
      // First expand Extract Agent panel
      const extractPanelId = 'extract-agent-panel';
      const extractButton = page.locator(`button[onclick="toggleCollapsible('${extractPanelId}')"]`);
      await extractButton.click();
      await page.waitForTimeout(300);

      // Now test EventCodeExtract sub-panel
      const panelId = 'eventcodeextract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick="toggleCollapsible('${panelId}')"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse ProcTreeExtract Sub-Agent panel', async ({ page }) => {
      // First expand Extract Agent panel
      const extractPanelId = 'extract-agent-panel';
      const extractButton = page.locator(`button[onclick="toggleCollapsible('${extractPanelId}')"]`);
      await extractButton.click();
      await page.waitForTimeout(300);

      // Now test ProcTreeExtract sub-panel
      const panelId = 'proctreeextract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick="toggleCollapsible('${panelId}')"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse RegexExtract Sub-Agent panel', async ({ page }) => {
      // First expand Extract Agent panel
      const extractPanelId = 'extract-agent-panel';
      const extractButton = page.locator(`button[onclick="toggleCollapsible('${extractPanelId}')"]`);
      await extractButton.click();
      await page.waitForTimeout(300);

      // Now test RegexExtract sub-panel
      const panelId = 'regextract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick="toggleCollapsible('${panelId}')"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse Sigma Agent panel', async ({ page }) => {
      const panelId = 'sigma-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const button = page.locator(`button[onclick*="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await button.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await button.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });
  });
});


