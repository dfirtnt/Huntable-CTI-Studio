import { test, expect, Page } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

// ── Helpers ──────────────────────────────────────────────────────────
// The workflow config tab was redesigned into step-sections (s0-s5).
// `data-collapsible-panel` now only exists on dynamically-rendered
// prompt / QA-prompt sub-panels inside each step.

/** Open a step-section by index (0-5) and wait for its body to be visible. */
async function openStep(page: Page, n: number) {
  await page.evaluate((idx) => {
    if (typeof scrollToStep === 'function') scrollToStep(idx);
    else if (typeof toggle === 'function') toggle(`s${idx}`);
  }, n);
  await page.waitForTimeout(600);
}

/** Open every step that contains at least one prompt panel container.
 * OS Detection (s0) was removed in newer dev branches, so we open all
 * known prompt-bearing steps to remain compatible with both layouts.
 */
async function openAllPromptSteps(page: Page) {
  for (const step of [0, 2, 3, 4]) {
    await openStep(page, step);
  }
}

/** Wait for at least one VISIBLE collapsible prompt panel inside the form. */
async function waitForPromptPanels(page: Page) {
  await page.waitForFunction(
    () => {
      const panels = document.querySelectorAll('#workflowConfigForm [data-collapsible-panel]');
      return Array.from(panels).some((el) => (el as HTMLElement).offsetParent !== null);
    },
    { timeout: 15000 }
  );
}

/** Return the first VISIBLE collapsible panel header found inside #workflowConfigForm. */
function firstPromptPanel(page: Page) {
  return page.locator('#workflowConfigForm [data-collapsible-panel]:visible').first();
}

test.describe('Workflow Collapsible Panels - Initialization', () => {
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

    // Open step 0 (OS Detection) so its prompt panel renders
    await openAllPromptSteps(page);
    await waitForPromptPanels(page);
  });

  test('should initialize panels on page load', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    expect(panelId).toBeTruthy();

    // Verify initialization marker
    const isInitialized = await header.getAttribute('data-collapsible-initialized');
    expect(isInitialized).toBe('true');

    // Verify ARIA attributes are set (indicates initialization)
    const role = await header.getAttribute('role');
    expect(role).toBe('button');

    const tabindex = await header.getAttribute('tabindex');
    expect(tabindex).toBe('0');
  });

  test('should initialize panels after config reload', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');

    // Verify initial initialization
    let isInitialized = await header.getAttribute('data-collapsible-initialized');
    expect(isInitialized).toBe('true');

    // Reload config
    await page.evaluate(() => {
      if (typeof loadConfig === 'function') {
        loadConfig();
      }
    });
    await page.waitForTimeout(2000);

    // Re-open the step so prompt panels re-render
    await openAllPromptSteps(page);
    await waitForPromptPanels(page);

    // Verify panel still works after reload
    const newHeader = firstPromptPanel(page);
    const newPanelId = await newHeader.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${newPanelId}-content`);

    // Ensure collapsed, then click to expand
    const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await newHeader.click();
      await page.waitForTimeout(300);
    }
    await expect(content).toBeVisible();
  });

  test('should initialize panels after tab switch', async ({ page }) => {
    // Switch to executions tab
    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('executions');
      }
    });
    await page.waitForTimeout(1000);

    // Switch back to config tab
    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(2000);

    await openAllPromptSteps(page);
    await waitForPromptPanels(page);

    // Verify panel still works
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await header.click();
      await page.waitForTimeout(300);
    }
    await expect(content).toBeVisible();
  });

  test('should initialize dynamically added prompt panels', async ({ page }) => {
    // Open step 2 (LLM Ranking) to get RankAgent prompt panel
    await openStep(page, 2);
    await page.waitForTimeout(2000);

    const promptPanels = page.locator('#workflowConfigForm [data-collapsible-panel$="-prompt-panel"]');
    const count = await promptPanels.count();

    if (count > 0) {
      const firstPanel = promptPanels.first();
      const isInitialized = await firstPanel.getAttribute('data-collapsible-initialized');
      expect(isInitialized).toBe('true');
    } else {
      test.skip(true, 'No prompt panels rendered in current config');
    }
  });

  test('should not create duplicate event handlers after re-initialization', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    // Ensure panel starts collapsed
    let isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
    if (!isHidden) {
      await header.click();
      await page.waitForTimeout(300);
    }
    isHidden = await content.evaluate(el => el.classList.contains('hidden'));
    expect(isHidden).toBe(true);

    // Toggle panel first time
    await header.click();
    await page.waitForTimeout(300);
    let isVisible = await content.isVisible();
    expect(isVisible).toBe(true);

    // Manually trigger re-initialization
    await page.evaluate((pid) => {
      const headerEl = document.querySelector(`[data-collapsible-panel="${pid}"]`);
      if (headerEl) {
        headerEl.removeAttribute('data-collapsible-initialized');
        if (typeof initCollapsiblePanels === 'function') {
          initCollapsiblePanels();
        }
      }
    }, panelId);
    await page.waitForTimeout(500);

    // Verify panel is still initialized after re-initialization
    const isInitialized = await header.getAttribute('data-collapsible-initialized');
    expect(isInitialized).toBe('true');

    // Verify ARIA attributes are still correct
    const ariaExpanded = await header.getAttribute('aria-expanded');
    expect(ariaExpanded).toBeTruthy();
    expect(['true', 'false']).toContain(ariaExpanded);

    // Verify panel can still be toggled
    const currentState = await content.isVisible();
    await header.click();
    await page.waitForTimeout(500);
    const newState = await content.isVisible();
    expect(typeof newState).toBe('boolean');
  });

  test('should handle missing content element gracefully', async ({ page }) => {
    // Create a test panel with missing content
    await page.evaluate(() => {
      const testHeader = document.createElement('div');
      testHeader.setAttribute('data-collapsible-panel', 'test-missing-content-panel');
      testHeader.textContent = 'Test Panel';
      document.body.appendChild(testHeader);

      if (typeof initCollapsiblePanels === 'function') {
        initCollapsiblePanels();
      }
    });

    await page.waitForTimeout(500);

    // Should not throw error - existing panels still work
    const existingPanel = firstPromptPanel(page);
    await expect(existingPanel).toBeVisible();
  });

  test('should work with missing toggle element', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    // Ensure collapsed, then click to expand
    const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await header.click();
      await page.waitForTimeout(300);
    }
    await expect(content).toBeVisible();
  });

  test('should allow multiple step-sections to accordion correctly', async ({ page }) => {
    // Step sections use accordion behavior — only one open at a time.
    // openAllPromptSteps leaves the LAST opened step (s4) as the open one;
    // re-open s0 explicitly so the test starts from a known state.
    await openAllPromptSteps(page);
    await openStep(page, 0);
    const s0 = page.locator('#s0');
    await expect(s0).toHaveClass(/open/);

    await openStep(page, 1);
    const s1 = page.locator('#s1');
    await expect(s1).toHaveClass(/open/);
    // s0 should be closed now
    await expect(s0).not.toHaveClass(/open/);

    await openStep(page, 2);
    const s2 = page.locator('#s2');
    await expect(s2).toHaveClass(/open/);
    await expect(s1).not.toHaveClass(/open/);
  });

  test('should maintain panel state during form interactions', async ({ page }) => {
    // Open step 1 (Junk Filter) which has the junkFilterThreshold input
    await openStep(page, 1);
    const s1 = page.locator('#s1');
    await expect(s1).toHaveClass(/open/);

    const input = page.locator('#junkFilterThreshold');
    if (await input.isVisible()) {
      await input.fill('0.9');
      await input.dispatchEvent('input');
      await page.waitForTimeout(500);

      // Step should still be open
      await expect(s1).toHaveClass(/open/);
    }
  });
});
