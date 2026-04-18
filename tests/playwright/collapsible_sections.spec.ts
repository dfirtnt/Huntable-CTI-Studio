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

      // Switch to config tab using JavaScript if needed
      await page.evaluate(() => {
        if (typeof switchTab === 'function') switchTab('config');
      });

      // Wait for config form to be visible
      await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });

      // Wait for the specific prompt panels that the Workflow Config Page tests
      // need. These are injected dynamically by renderWorkflowConfigDisplay()
      // after the async loadConfig() API call resolves. The old fixed-sleep
      // approach raced with that call; this poll is deterministic.
      //
      // OS Detection no longer uses an LLM prompt panel (it uses embedding
      // similarity). The first real prompt panels are rank-agent (step 2) and
      // sigma-agent (step 4). renderWorkflowConfigDisplay() renders all
      // containers at once, so waiting for one is sufficient — both will be
      // in the DOM in the same JS tick.
      // Wait for the prompt panels to be fully initialized — not just present in
      // the DOM, but with their click handlers wired up. renderWorkflowConfigDisplay()
      // injects innerHTML and then calls initCollapsiblePanels() inside a
      // setTimeout(fn, 0). initCollapsiblePanels() sets data-collapsible-initialized
      // atomically with registering the click listener, so waiting for that
      // attribute is a reliable proxy for "handler is ready".
      await page.waitForSelector(
        '[data-collapsible-panel="rank-agent-prompt-panel"][data-collapsible-initialized]',
        { state: 'attached', timeout: 15000 }
      );
      await page.waitForSelector(
        '[data-collapsible-panel="sigma-agent-prompt-panel"][data-collapsible-initialized]',
        { state: 'attached', timeout: 5000 }
      );

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

      // Neutralize auto-save AND the re-render path so clicking a panel
      // header doesn't trigger a debounced performAutoSave() ->
      // renderWorkflowConfigDisplay() cycle mid-test. That call replaces
      // the prompt panel innerHTML, which (a) wipes the just-toggled
      // state and (b) detaches the click handlers we just registered via
      // initCollapsiblePanels(). Stubbing renderWorkflowConfigDisplay
      // here is safe because we already waited for
      // data-collapsible-initialized above, proving the initial render
      // has completed. These tests only verify collapsible toggle
      // behavior; dedicated auto-save specs cover that code path.
      await page.evaluate(() => {
        (window as any).autoSaveConfig = async () => {};
        (window as any).autoSaveModelChange = async () => {};
        (window as any).renderWorkflowConfigDisplay = () => {};
      });
    });

    test('should expand and collapse Rank Agent prompt panel (first LLM panel, step 2)', async ({ page }) => {
      // OS Detection was refactored to embedding-based (no LLM prompt). The
      // first configurable LLM prompt panel is Rank Agent in step 2.
      // Use scrollToStep() rather than a section-header click — same function
      // the UI calls for both rail clicks and header clicks.
      await page.evaluate(() => { if (typeof scrollToStep === 'function') scrollToStep(2); });
      await page.waitForTimeout(400);
      await expect(page.locator('#s2')).toHaveClass(/open/);

      const panelId = 'rank-agent-prompt-panel';
      const content = page.locator(`#${panelId}-content`);
      const toggle = page.locator(`#${panelId}-toggle`);
      const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

      // OS Detection step (s0) no longer exposes a prompt panel in newer builds.
      if (await header.count() === 0) {
        test.skip(true, 'OS Detection prompt panel not present in current workflow config layout');
      }
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
      // Use rank-agent (step 2) and sigma-agent (step 4) — both have real LLM
      // prompt panels. os-detection-prompt-panel no longer exists (OS Detection
      // switched to embedding similarity and lost its LLM prompt).
      await page.evaluate(() => {
        ['s2', 's4'].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.classList.add('open');
        });
      });
      await page.waitForTimeout(200);

      const panelA = 'rank-agent-prompt-panel';
      const panelB = 'sigma-agent-prompt-panel';
      const contentA = page.locator(`#${panelA}-content`);
      const contentB = page.locator(`#${panelB}-content`);
      const headerA = page.locator(`[data-collapsible-panel="${panelA}"]`);
      const headerB = page.locator(`[data-collapsible-panel="${panelB}"]`);

      // OS Detection prompt panel was removed in newer builds — accordion test requires both.
      if (await headerA.count() === 0) {
        test.skip(true, 'OS Detection prompt panel not present; accordion test requires two panels');
      }
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


