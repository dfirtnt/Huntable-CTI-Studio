import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Collapsible Sections', () => {
  
  test.describe('Settings Page', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto(`${BASE}/settings`);
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(800); // Wait for JavaScript to initialize
    });

    test('should expand and collapse Backup Configuration section', async ({ page }) => {
      const panelId = 'backupConfig';
      const content = page.locator(`#${panelId}-content`);
      const chevron = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);

      // Click to expand
      await header.click();
      await page.waitForTimeout(300); // Wait for animation

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(header).toHaveAttribute('aria-expanded', 'true');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300); // Wait for animation

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(header).toHaveAttribute('aria-expanded', 'false');
    });
  });

  test.describe('Workflow Config Page', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto(`${BASE}/workflow#config`);
      await page.waitForLoadState('domcontentloaded');
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

      // Stabilize initial state so all panel tests start collapsed.
      await page.evaluate(() => {
        document.querySelectorAll('[data-collapsible-panel]').forEach((headerEl) => {
          const panelId = headerEl.getAttribute('data-collapsible-panel');
          if (!panelId) return;
          const content = document.getElementById(`${panelId}-content`);
          const toggle = document.getElementById(`${panelId}-toggle`);
          if (!content) return;
          content.classList.add('hidden');
          if (toggle) toggle.textContent = '▼';
          headerEl.setAttribute('aria-expanded', 'false');
        });
      });
    });

    test('should expand and collapse Junk Filter panel', async ({ page }) => {
      const panelId = 'other-thresholds-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await header.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse OS Detection Agent panel', async ({ page }) => {
      const panelId = 'os-detection-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await header.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse Rank Agent Configs panel', async ({ page }) => {
      const panelId = 'rank-agent-configs-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await header.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse Extract Agent panel', async ({ page }) => {
      const panelId = 'extract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await header.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse CmdlineExtract Sub-Agent panel', async ({ page }) => {
      // First expand Extract Agent panel
      const extractPanelId = 'extract-agent-panel';
      const extractHeader = page.locator(`[data-collapsible-panel="${extractPanelId}"]`);
      await extractHeader.click();
      await page.waitForTimeout(300);

      // Now test CmdlineExtract sub-panel
      const panelId = 'cmdlineextract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await header.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });



    test('should expand and collapse ProcTreeExtract Sub-Agent panel', async ({ page }) => {
      // First expand Extract Agent panel
      const extractPanelId = 'extract-agent-panel';
      const extractHeader = page.locator(`[data-collapsible-panel="${extractPanelId}"]`);
      await extractHeader.click();
      await page.waitForTimeout(300);

      // Now test ProcTreeExtract sub-panel
      const panelId = 'proctreeextract-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await header.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });


    test('should expand and collapse Sigma Agent panel', async ({ page }) => {
      const panelId = 'sigma-agent-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // Initially should be hidden
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      // Click to expand
      await header.click();
      await page.waitForTimeout(300);

      // Should be visible now
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      // Click to collapse
      await header.click();
      await page.waitForTimeout(300);

      // Should be hidden again
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });
  });
});


