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

    // other-thresholds-panel: removed - Junk Filter (s1) has no such collapsible panel in current UI

    test('should expand and collapse OS Detection prompt panel', async ({ page }) => {
      // s0 is open by default; os-detection-prompt-panel is in s0
      const panelId = 'os-detection-prompt-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      await expect(header).toBeVisible({ timeout: 10000 });
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse Rank Agent prompt panel', async ({ page }) => {
      // Expand s2 first so rank-agent-prompt-panel is in DOM
      await page.locator('#s2 .section-header').click();
      await page.waitForTimeout(500);
      await expect(page.locator('#s2')).toHaveClass(/open/);

      const panelId = 'rank-agent-prompt-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      await expect(header).toBeVisible({ timeout: 10000 });
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse Extract Agent prompt panel', async ({ page }) => {
      // Expand s3 first so extract-agent-prompt-panel is in DOM
      await page.locator('#s3 .section-header').click();
      await page.waitForTimeout(500);
      await expect(page.locator('#s3')).toHaveClass(/open/);

      const panelId = 'extract-agent-prompt-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      await expect(header).toBeVisible({ timeout: 10000 });
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse CmdlineExtract Sub-Agent prompt panel', async ({ page }) => {
      // Expand s3 first, then expand sa-cmdline (CmdlineExtract sub-agent) so prompt container is rendered
      await page.locator('#s3 .section-header').click();
      await page.waitForTimeout(500);
      await page.locator('#sa-cmdline .sa-header').click();
      await page.waitForTimeout(500);

      const panelId = 'cmdlineextract-agent-prompt-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      await expect(header).toBeVisible({ timeout: 10000 });
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('should expand and collapse ProcTreeExtract Sub-Agent prompt panel', async ({ page }) => {
      await page.locator('#s3 .section-header').click();
      await page.waitForTimeout(500);
      await page.locator('#sa-proctree .sa-header').click();
      await page.waitForTimeout(500);

      const panelId = 'proctreeextract-agent-prompt-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      await expect(header).toBeVisible({ timeout: 10000 });
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });


    test('should expand and collapse Sigma Agent prompt panel', async ({ page }) => {
      await page.locator('#s4 .section-header').click();
      await page.waitForTimeout(500);

      const panelId = 'sigma-agent-prompt-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      await expect(header).toBeVisible({ timeout: 10000 });
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
      await expect(toggle).toHaveText('▲');

      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toHaveClass(/hidden/);
      await expect(toggle).toHaveText('▼');
    });

    test('accordion: only one step section open at a time', async ({ page }) => {
      const s0 = page.locator('#s0.step-section');
      const s2 = page.locator('#s2.step-section');
      const s3 = page.locator('#s3.step-section');
      const header0 = page.locator('#s0 .section-header');
      const header2 = page.locator('#s2 .section-header');
      const header3 = page.locator('#s3 .section-header');

      await expect(s0).toHaveClass(/open/);
      await expect(s2).not.toHaveClass(/open/);
      await expect(s3).not.toHaveClass(/open/);

      await header2.click();
      await page.waitForTimeout(300);
      await expect(s0).not.toHaveClass(/open/);
      await expect(s2).toHaveClass(/open/);
      await expect(s3).not.toHaveClass(/open/);

      await header3.click();
      await page.waitForTimeout(300);
      await expect(s0).not.toHaveClass(/open/);
      await expect(s2).not.toHaveClass(/open/);
      await expect(s3).toHaveClass(/open/);

      await header0.click();
      await page.waitForTimeout(300);
      await expect(s0).toHaveClass(/open/);
      await expect(s2).not.toHaveClass(/open/);
      await expect(s3).not.toHaveClass(/open/);
    });

    test('accordion: rail nav expands target step and closes others', async ({ page }) => {
      const s0 = page.locator('#s0.step-section');
      const s3 = page.locator('#s3.step-section');
      const railStep3 = page.locator('.rail-item').filter({ has: page.locator('.rail-node', { hasText: '3' }) });

      await expect(s0).toHaveClass(/open/);
      await expect(s3).not.toHaveClass(/open/);

      await railStep3.click();
      await page.waitForTimeout(300);

      await expect(s0).not.toHaveClass(/open/);
      await expect(s3).toHaveClass(/open/);
    });

    test('accordion: only one agent panel open at a time', async ({ page }) => {
      // Ensure step sections s0 (OS Detection) and s2 (Rank Agent) are expanded so prompt panels are visible
      await page.evaluate(() => {
        ['s0', 's2'].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.classList.add('open');
        });
      });
      await page.waitForTimeout(200);

      const panelA = 'os-detection-prompt-panel';
      const panelB = 'rank-agent-prompt-panel';
      const contentA = page.locator(`#${panelA}-content`);
      const contentB = page.locator(`#${panelB}-content`);
      const headerA = page.locator(`[data-collapsible-panel="${panelA}"]`);
      const headerB = page.locator(`[data-collapsible-panel="${panelB}"]`);

      await expect(headerA).toBeVisible({ timeout: 10000 });
      await expect(headerB).toBeVisible({ timeout: 10000 });
      await expect(contentA).toHaveClass(/hidden/);
      await expect(contentB).toHaveClass(/hidden/);

      // Expand A
      await headerA.click();
      await page.waitForTimeout(300);
      await expect(contentA).toBeVisible();
      await expect(contentB).toHaveClass(/hidden/);

      // Expand B — A should collapse (accordion)
      await headerB.click();
      await page.waitForTimeout(300);
      await expect(contentB).toBeVisible();
      await expect(contentA).toHaveClass(/hidden/);

      // Expand A again — B should collapse
      await headerA.click();
      await page.waitForTimeout(300);
      await expect(contentA).toBeVisible();
      await expect(contentB).toHaveClass(/hidden/);
    });
  });
});


