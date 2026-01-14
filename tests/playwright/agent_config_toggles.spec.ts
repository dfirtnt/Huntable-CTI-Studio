import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Toggle Interactions', () => {
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
    await page.waitForTimeout(2000);

    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
    await expandPanelIfNeeded(page, 'extract-agent-panel');
    await expandPanelIfNeeded(page, 'sigma-agent-panel');
  });

  test('should disable Rank QA when Rank Agent is disabled', async ({ page }) => {
    const rankAgentToggle = page.locator('#rank-agent-enabled');
    const rankQAToggle = page.locator('#qa-rankagent');

    await rankAgentToggle.waitFor({ state: 'attached', timeout: 10000 });
    await rankQAToggle.waitFor({ state: 'attached', timeout: 10000 });

    // Ensure Rank Agent is enabled and Rank QA is enabled
    if (!(await rankAgentToggle.isChecked())) {
      await page.evaluate(() => {
        const el = document.getElementById('rank-agent-enabled') as HTMLInputElement;
        if (el) {
          el.checked = true;
          el.dispatchEvent(new Event('change', { bubbles: true }));
          // Call update function if it exists
          if (typeof updateRankQAState === 'function') {
            updateRankQAState(false);
          }
        }
      });
      await page.waitForTimeout(1000);
    }
    if (!(await rankQAToggle.isChecked())) {
      await page.evaluate(() => {
        const el = document.getElementById('qa-rankagent') as HTMLInputElement;
        if (el) {
          el.checked = true;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
      await page.waitForTimeout(1000);
    }

    // Disable Rank Agent
    await page.evaluate(() => {
      const el = document.getElementById('rank-agent-enabled') as HTMLInputElement;
      if (el) {
        el.checked = false;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        // Call update function to disable QA
        if (typeof updateRankQAState === 'function') {
          updateRankQAState(false);
        }
      }
    });
    await page.waitForTimeout(1000); // Wait for UI update

    // Rank QA should be disabled and unchecked
    const isQADisabled = await rankQAToggle.isDisabled();
    const isQAChecked = await rankQAToggle.isChecked();

    expect(isQADisabled).toBe(true);
    expect(isQAChecked).toBe(false);
  });

  test('should enable Rank QA when Rank Agent is enabled', async ({ page }) => {
    const rankAgentToggle = page.locator('#rank-agent-enabled');
    const rankQAToggle = page.locator('#qa-rankagent');

    await rankAgentToggle.waitFor({ state: 'attached', timeout: 10000 });
    await rankQAToggle.waitFor({ state: 'attached', timeout: 10000 });

    // Disable Rank Agent first
    if (await rankAgentToggle.isChecked()) {
      await page.evaluate(() => {
        const el = document.getElementById('rank-agent-enabled') as HTMLInputElement;
        if (el) {
          el.checked = false;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
      await page.waitForTimeout(500);
    }

    // Verify QA is disabled
    expect(await rankQAToggle.isDisabled()).toBe(true);

    // Enable Rank Agent
    await page.evaluate(() => {
      const el = document.getElementById('rank-agent-enabled') as HTMLInputElement;
      if (el) {
        el.checked = true;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);

    // Rank QA should be enabled (but may not be checked)
    const isQADisabled = await rankQAToggle.isDisabled();
    expect(isQADisabled).toBe(false);
  });

  test('should update QA checkbox state when Extract sub-agent toggle changes', async ({ page }) => {
    await expandPanelIfNeeded(page, 'cmdlineextract-agent-panel');
    const extractToggle = page.locator('#toggle-cmdlineextract-enabled');
    const qaCheckbox = page.locator('#qa-cmdlineextract');

    await extractToggle.waitFor({ state: 'attached', timeout: 10000 });
    await qaCheckbox.waitFor({ state: 'attached', timeout: 10000 });

    // Ensure extract agent is enabled
    if (!(await extractToggle.isChecked())) {
      await page.evaluate(() => {
        const el = document.getElementById('toggle-cmdlineextract-enabled') as HTMLInputElement;
        if (el) {
          el.checked = true;
          el.dispatchEvent(new Event('change', { bubbles: true }));
          if (typeof handleExtractAgentToggle === 'function') {
            handleExtractAgentToggle('CmdlineExtract');
          }
        }
      });
      await page.waitForTimeout(500);
    }

    // Disable extract agent
    await page.evaluate(() => {
      const el = document.getElementById('toggle-cmdlineextract-enabled') as HTMLInputElement;
      if (el) {
        el.checked = false;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        if (typeof handleExtractAgentToggle === 'function') {
          handleExtractAgentToggle('CmdlineExtract');
        }
      }
    });
    await page.waitForTimeout(500);

    // QA checkbox should be disabled
    const isQADisabled = await qaCheckbox.isDisabled();
    expect(isQADisabled).toBe(true);
  });

  test('should autosave all toggles on change', async ({ page }) => {
    const rankAgentToggle = page.locator('#rank-agent-enabled');
    await rankAgentToggle.waitFor({ state: 'attached', timeout: 10000 });

    const initialChecked = await rankAgentToggle.isChecked();

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 5000 }
    );

    await page.evaluate(() => {
      const el = document.getElementById('rank-agent-enabled') as HTMLInputElement;
      if (el) {
        el.checked = !el.checked;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.rank_agent_enabled).toBe(!initialChecked);
  });

  test('should persist toggle states after page reload', async ({ page }) => {
    const rankAgentToggle = page.locator('#rank-agent-enabled');
    await rankAgentToggle.waitFor({ state: 'attached', timeout: 10000 });

    const initialChecked = await rankAgentToggle.isChecked();

    // Toggle it
    await page.evaluate(() => {
      const el = document.getElementById('rank-agent-enabled') as HTMLInputElement;
      if (el) {
        el.checked = !el.checked;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }
    );
    await page.waitForTimeout(2000); // Wait longer for autosave to complete

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);

    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForTimeout(3000); // Wait longer for config to load
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
    await page.waitForTimeout(1000);

    const rankAgentToggleAfterReload = page.locator('#rank-agent-enabled');
    await rankAgentToggleAfterReload.waitFor({ state: 'attached', timeout: 10000 });

    const persistedChecked = await rankAgentToggleAfterReload.isChecked();
    expect(persistedChecked).toBe(!initialChecked);
  });

  test('should update status badges when toggles change', async ({ page }) => {
    const rankAgentToggle = page.locator('#rank-agent-enabled');
    const rankAgentBadge = page.locator('#rank-agent-enabled-badge');

    await rankAgentToggle.waitFor({ state: 'attached', timeout: 10000 });
    await rankAgentBadge.waitFor({ state: 'visible', timeout: 10000 });

    const initialBadgeText = await rankAgentBadge.textContent();

    await page.evaluate(() => {
      const el = document.getElementById('rank-agent-enabled') as HTMLInputElement;
      if (el) {
        el.checked = !el.checked;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);

    const newBadgeText = await rankAgentBadge.textContent();
    expect(newBadgeText).not.toBe(initialBadgeText);
  });

  test('should hide model selection UI when extract agent is disabled', async ({ page }) => {
    await expandPanelIfNeeded(page, 'cmdlineextract-agent-panel');
    const extractToggle = page.locator('#toggle-cmdlineextract-enabled');
    await extractToggle.waitFor({ state: 'attached', timeout: 10000 });

    // Ensure it's enabled first
    if (!(await extractToggle.isChecked())) {
      await page.evaluate(() => {
        const el = document.getElementById('toggle-cmdlineextract-enabled') as HTMLInputElement;
        if (el) {
          el.checked = true;
          el.dispatchEvent(new Event('change', { bubbles: true }));
          if (typeof handleExtractAgentToggle === 'function') {
            handleExtractAgentToggle('CmdlineExtract');
          }
        }
      });
      await page.waitForTimeout(500);
    }

    // Check if model container exists when enabled
    const modelContainer = page.locator('#cmdlineextract-agent-model-container');
    const wasVisible = await modelContainer.isVisible().catch(() => false);

    // Disable extract agent
    await page.evaluate(() => {
      const el = document.getElementById('toggle-cmdlineextract-enabled') as HTMLInputElement;
      if (el) {
        el.checked = false;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        if (typeof handleExtractAgentToggle === 'function') {
          handleExtractAgentToggle('CmdlineExtract');
        }
      }
    });
    await page.waitForTimeout(500);

    // Model container should be hidden or not exist
    const isVisibleAfterDisable = await modelContainer.isVisible().catch(() => false);
    expect(isVisibleAfterDisable).toBe(false);
  });

  test('should autosave Sigma fallback toggle', async ({ page }) => {
    const sigmaToggle = page.locator('#sigma-fallback-enabled');
    await sigmaToggle.waitFor({ state: 'attached', timeout: 10000 });

    const initialChecked = await sigmaToggle.isChecked();

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 5000 }
    );

    await page.evaluate(() => {
      const el = document.getElementById('sigma-fallback-enabled') as HTMLInputElement;
      if (el) {
        el.checked = !el.checked;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.sigma_fallback_enabled).toBe(!initialChecked);
  });

  test('should autosave Extract sub-agent toggles', async ({ page }) => {
    // Ensure extract-agent-panel is expanded first
    await expandPanelIfNeeded(page, 'extract-agent-panel');
    await page.waitForTimeout(2000);
    // Then expand the nested proctreeextract panel
    await expandPanelIfNeeded(page, 'proctreeextract-agent-panel');
    await page.waitForTimeout(2000);
    
    const extractToggle = page.locator('#toggle-proctreeextract-enabled');
    await extractToggle.waitFor({ state: 'attached', timeout: 10000 });

    const initialChecked = await extractToggle.isChecked();

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 20000 }
    );

    // Trigger the change event which will call handleExtractAgentToggle
    await page.evaluate(async () => {
      const el = document.getElementById('toggle-proctreeextract-enabled') as HTMLInputElement;
      if (el) {
        el.checked = !el.checked;
        // Dispatch change event which triggers onchange handler
        el.dispatchEvent(new Event('change', { bubbles: true }));
        // handleExtractAgentToggle is called by onchange and it calls autoSaveConfig internally
      }
    });
    // Wait for debounce (300ms) + API call
    await page.waitForTimeout(500);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    const disabledAgents = responseData.agent_prompts?.ExtractAgentSettings?.disabled_agents || [];
    const isDisabled = disabledAgents.includes('ProcTreeExtract');
    expect(isDisabled).toBe(!initialChecked);
  });
});

async function expandPanelIfNeeded(page: any, panelId: string) {
  const content = page.locator(`#${panelId}-content`);
  const toggle = page.locator(`#${panelId}-toggle, button[onclick*="${panelId}"]`).first();

  if (await toggle.isVisible({ timeout: 2000 }).catch(() => false)) {
    const isHidden = await content.evaluate((el: HTMLElement) => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await toggle.click();
      await page.waitForTimeout(300);
    }
  }
}
