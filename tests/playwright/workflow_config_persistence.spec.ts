import { test, expect, Page } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

async function switchToConfigTab(page: Page) {
  await page.evaluate(() => {
    if (typeof switchTab === 'function') {
      switchTab('config');
    }
  });
  await page.waitForTimeout(1000);
}

async function waitForConfigReady(page: Page) {
  await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
  await page.waitForFunction(() => {
    return typeof currentConfig !== 'undefined' && currentConfig !== null;
  }, { timeout: 10000 });
  await page.waitForTimeout(1000);
}

async function gotoWorkflowConfig(page: Page) {
  await page.goto(`${BASE}/workflow#config`);
  await page.waitForLoadState('networkidle');
  await switchToConfigTab(page);
  await waitForConfigReady(page);
}

async function reloadWorkflowConfig(page: Page) {
  await page.reload();
  await page.waitForLoadState('networkidle');
  await switchToConfigTab(page);
  await waitForConfigReady(page);
}

/** Open a step-section by index (pipeline stages s0-s5). */
async function openStep(page: Page, n: number) {
  await page.evaluate((idx) => {
    if (typeof scrollToStep === 'function') scrollToStep(idx);
    else if (typeof toggle === 'function') toggle(`s${idx}`);
  }, n);
  await page.waitForTimeout(600);
}

/** Expand a `data-collapsible-panel` sub-panel (prompt / QA panels). */
async function expandPanel(page: Page, panelId: string) {
  const content = page.locator(`#${panelId}-content`);
  const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
  if (await content.count() === 0 || await header.count() === 0) {
    return;
  }
  const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
  if (isHidden) {
    await header.click();
    await page.waitForTimeout(300);
  }
}

async function ensureRankAgentPanel(page: Page) {
  // Step 2 = LLM Ranking (rank agent section)
  await openStep(page, 2);
  await page.waitForSelector('#rank-agent-model-container', { state: 'attached', timeout: 10000 });
}

async function ensureRankPromptPanel(page: Page) {
  await page.waitForSelector('#rank-agent-prompt-container', { state: 'attached', timeout: 10000 });
  await page.waitForFunction(() => {
    return document.querySelector('[data-collapsible-panel="rank-agent-prompt-panel"]') !== null;
  }, { timeout: 10000 });
  await expandPanel(page, 'rank-agent-prompt-panel');
}

async function getConfigVersion(page: Page) {
  await page.waitForFunction(() => {
    const display = document.getElementById('configDisplay');
    return Boolean(display && display.innerText.includes('Version'));
  }, { timeout: 10000 });
  const text = await page.locator('#configDisplay').innerText();
  const match = text.match(/Version:\s*(\d+)/);
  if (!match) {
    throw new Error(`Config version not found in display: ${text}`);
  }
  return parseInt(match[1], 10);
}

async function waitForConfigUpdate(page: Page, oldVersion: number) {
  await page.waitForFunction((version) => {
    const text = document.getElementById('configDisplay')?.innerText || '';
    const match = text.match(/Version:\s*(\d+)/);
    if (!match) return false;
    return parseInt(match[1], 10) > version;
  }, oldVersion, { timeout: 15000 });
}

test.describe('Workflow Config Persistence', () => {
  test('workflow#config loads with scroll at top', async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForFunction(
      () => typeof currentConfig !== 'undefined' && currentConfig !== null,
      { timeout: 10000 }
    );
    await page.waitForTimeout(600);
    const scrollY = await page.evaluate(() => window.scrollY);
    expect(scrollY).toBeLessThanOrEqual(50);
  });

  test('config display updates after save using shared component', async ({ page }) => {
    await gotoWorkflowConfig(page);
    await ensureRankAgentPanel(page);
    const display = page.locator('#configDisplay');
    await expect(display).toBeVisible();
    await page.waitForFunction(() => {
      const el = document.getElementById('configDisplay');
      return el && el.innerText.includes('Version') && el.innerText.includes('Ranking Threshold');
    }, { timeout: 10000 });

    const rankingThreshold = page.locator('#rankingThreshold');
    await expect(rankingThreshold).toBeVisible();
    const initialValue = await rankingThreshold.inputValue();
    const newValue = Math.min((parseFloat(initialValue) || 6.0) + 0.5, 10);

    // rankingThreshold is a range input with oninput="autoSaveConfig()".
    // Changing the value triggers debounced autosave — wait for the PUT response.
    const savePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 15000 }
    );
    await rankingThreshold.evaluate((el, val) => {
      (el as HTMLInputElement).value = val.toString();
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, newValue);
    await savePromise;

    await page.waitForTimeout(500);
    const text = await display.innerText();
    expect(text).toContain('Version');
    expect(text).toContain('Ranking Threshold');
    expect(text).toContain('Junk Filter Threshold');
    expect(text).toContain('Similarity Threshold');
    expect(text).toContain('Updated');
  });

  test('config display includes RankAgentQA when Rank is disabled', async ({ page }) => {
    await gotoWorkflowConfig(page);
    await ensureRankAgentPanel(page);
    const toggle = page.locator('#rank-agent-enabled');
    const initiallyEnabled = await toggle.isChecked();

    try {
      if (initiallyEnabled) {
        // Toggling #rank-agent-enabled triggers autoSaveConfig via onchange
        const savePromise = page.waitForResponse(
          (r) => r.url().includes('/api/workflow/config') && r.request().method() === 'PUT',
          { timeout: 15000 }
        );
        await page.evaluate(() => {
          const input = document.getElementById('rank-agent-enabled') as HTMLInputElement | null;
          if (!input) throw new Error('Rank Agent toggle not found');
          input.checked = false;
          input.dispatchEvent(new Event('change', { bubbles: true }));
        });
        await savePromise;
        await page.waitForTimeout(500);
      }
      const displayText = await page.locator('#configDisplay').innerText();
      expect(displayText).toContain('RankAgentQA');
    } finally {
      if (initiallyEnabled) {
        const restorePromise = page.waitForResponse(
          (r) => r.url().includes('/api/workflow/config') && r.request().method() === 'PUT',
          { timeout: 15000 }
        ).catch(() => {});
        await page.evaluate(() => {
          const input = document.getElementById('rank-agent-enabled') as HTMLInputElement | null;
          if (!input) return;
          input.checked = true;
          input.dispatchEvent(new Event('change', { bubbles: true }));
        });
        await restorePromise;
      }
    }
  });

  test('Rank Agent enabled toggle persists after save + refresh', async ({ page }) => {
    await gotoWorkflowConfig(page);
    await ensureRankAgentPanel(page);

    const rankModel = await page.evaluate(() => {
      if (typeof getAgentProvider !== 'function' || typeof getAgentModel !== 'function') {
        return null;
      }
      const provider = getAgentProvider('rankagent');
      return getAgentModel('rankagent', provider);
    });
    test.skip(!rankModel, 'RankAgent model not set; cannot save config.');

    const toggle = page.locator('#rank-agent-enabled');
    const originalValue = await toggle.isChecked();

    try {
      const savePromise = page.waitForResponse(
        response => response.url().includes('/api/workflow/config') && response.request().method() === 'PUT',
        { timeout: 15000 }
      );
      await page.evaluate(() => {
        const input = document.getElementById('rank-agent-enabled') as HTMLInputElement | null;
        if (!input) throw new Error('Rank Agent toggle not found');
        input.checked = !input.checked;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      });
      await savePromise;

      const expectedValue = !originalValue;
      await reloadWorkflowConfig(page);
      await ensureRankAgentPanel(page);

      await expect(page.locator('#rank-agent-enabled')).toHaveJSProperty('checked', expectedValue);
    } finally {
      const restorePromise = page.waitForResponse(
        response => response.url().includes('/api/workflow/config') && response.request().method() === 'PUT',
        { timeout: 15000 }
      ).catch(() => {});
      await page.evaluate((value) => {
        const input = document.getElementById('rank-agent-enabled') as HTMLInputElement | null;
        if (!input) return;
        input.checked = value;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }, originalValue);
      await restorePromise;
    }
  });

});
