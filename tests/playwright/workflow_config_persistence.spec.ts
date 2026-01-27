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
  await expandPanel(page, 'rank-agent-configs-panel');
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
      await page.evaluate(() => {
        const input = document.getElementById('rank-agent-enabled') as HTMLInputElement | null;
        if (!input) throw new Error('Rank Agent toggle not found');
        input.checked = !input.checked;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      });

      const expectedValue = !originalValue;
      const saveButton = page.locator('#save-config-button');
      await expect(saveButton).toBeEnabled();
      await Promise.all([
        page.waitForResponse(response =>
          response.url().includes('/api/workflow/config') && response.request().method() === 'PUT'
        ),
        saveButton.click()
      ]);

      await reloadWorkflowConfig(page);
      await ensureRankAgentPanel(page);

      await expect(page.locator('#rank-agent-enabled')).toHaveJSProperty('checked', expectedValue);
    } finally {
      await page.evaluate((value) => {
        const input = document.getElementById('rank-agent-enabled') as HTMLInputElement | null;
        if (!input) return;
        input.checked = value;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }, originalValue);

      const saveButton = page.locator('#save-config-button');
      if (await saveButton.isEnabled()) {
        await Promise.all([
          page.waitForResponse(response =>
            response.url().includes('/api/workflow/config') && response.request().method() === 'PUT'
          ),
          saveButton.click()
        ]);
      }
    }
  });

  test.skip('Rank Agent temperature + top_p persist after refresh', async ({ page }) => {
    await gotoWorkflowConfig(page);
    await ensureRankAgentPanel(page);

    const tempInput = page.locator('#rankagent-temperature');
    const topPInput = page.locator('#rankagent-top-p');

    await expect(tempInput).toBeVisible();
    await expect(topPInput).toBeVisible();

    const originalTemp = parseFloat(await tempInput.inputValue());
    const originalTopP = parseFloat(await topPInput.inputValue());

    const newTemp = originalTemp >= 1.9 ? 0.1 : parseFloat((originalTemp + 0.1).toFixed(2));
    const newTopP = originalTopP >= 0.95 ? 0.85 : parseFloat((originalTopP + 0.05).toFixed(2));

    try {
      const tempSave = page.waitForResponse(response =>
        response.url().includes('/api/workflow/config') && response.request().method() === 'PUT',
        { timeout: 15000 }  // Increased timeout
      );
      await tempInput.fill(newTemp.toString());
      await tempInput.blur();  // Use blur instead of dispatchEvent for autosave
      await page.waitForTimeout(500);  // Wait for debouncing
      await tempSave;

      const topPSave = page.waitForResponse(response =>
        response.url().includes('/api/workflow/config') && response.request().method() === 'PUT',
        { timeout: 15000 }  // Increased timeout
      );
      await topPInput.fill(newTopP.toString());
      await topPInput.blur();  // Use blur instead of dispatchEvent for autosave
      await page.waitForTimeout(500);  // Wait for debouncing
      await topPSave;

      await reloadWorkflowConfig(page);
      await ensureRankAgentPanel(page);

      const updatedTemp = parseFloat(await tempInput.inputValue());
      const updatedTopP = parseFloat(await topPInput.inputValue());

      expect(Math.abs(updatedTemp - newTemp)).toBeLessThan(0.01);
      expect(Math.abs(updatedTopP - newTopP)).toBeLessThan(0.01);
    } finally {
      const tempSave = page.waitForResponse(response =>
        response.url().includes('/api/workflow/config') && response.request().method() === 'PUT'
      );
      await tempInput.fill(originalTemp.toString());
      await tempInput.dispatchEvent('change');
      await tempSave;

      const topPSave = page.waitForResponse(response =>
        response.url().includes('/api/workflow/config') && response.request().method() === 'PUT'
      );
      await topPInput.fill(originalTopP.toString());
      await topPInput.dispatchEvent('change');
      await topPSave;
    }
  });

  test.skip('Rank Agent prompt edit persists and version increments', async ({ page }) => {
    await gotoWorkflowConfig(page);
    await ensureRankAgentPanel(page);
    await ensureRankPromptPanel(page);

    const userPromptDisplay = page.locator('#rankagent-prompt-user-display-2');
    await expect(userPromptDisplay).toBeVisible();
    const userPromptText = (await userPromptDisplay.textContent())?.trim() || '';
    test.skip(!userPromptText || userPromptText === '(empty)', 'RankAgent prompt not available in UI.');

    const initialVersion = await getConfigVersion(page);
    const rankEnabled = await page.locator('#rank-agent-enabled').isChecked();

    const editButton = page.locator('#rank-agent-prompt-container button', { hasText: 'Edit' });
    await editButton.click();

    const userInput = page.locator('#rankagent-prompt-user-2');
    await expect(userInput).toBeVisible();
    const originalUser = await userInput.inputValue();
    const marker = `UI_PERSIST_${Date.now()}`;
    const updatedUser = originalUser ? `${originalUser}\n${marker}` : marker;

    try {
      const saveResponse = page.waitForResponse(response =>
        response.url().includes('/api/workflow/config/prompts') && response.request().method() === 'PUT',
        { timeout: 15000 }  // Increased timeout
      );
      await userInput.fill(updatedUser);
      const saveButton = page.locator('#rank-agent-prompt-container button', { hasText: 'Save' });
      await saveButton.click();
      await page.waitForTimeout(500);  // Wait for API call
      await saveResponse;

      await waitForConfigUpdate(page, initialVersion);

      await ensureRankPromptPanel(page);
      await expect(page.locator('#rankagent-prompt-user-display-2')).toContainText(marker);

      await reloadWorkflowConfig(page);
      await ensureRankAgentPanel(page);
      await ensureRankPromptPanel(page);
      await expect(page.locator('#rankagent-prompt-user-display-2')).toContainText(marker);

      const rankEnabledAfterReload = await page.locator('#rank-agent-enabled').isChecked();
      expect(rankEnabledAfterReload).toBe(rankEnabled);

      const historyButton = page.locator('#rank-agent-prompt-container button', { hasText: 'History' });
      await historyButton.click();
      const historyModal = page.locator('#promptHistoryModal');
      await expect(historyModal).toBeVisible();
      await expect(historyModal).toContainText(marker);
      await page.locator('#promptHistoryModal button', { hasText: '✕' }).click();
    } finally {
      await ensureRankPromptPanel(page);
      await page.locator('#rank-agent-prompt-container button', { hasText: 'Edit' }).click();
      const restoreInput = page.locator('#rankagent-prompt-user-2');
      await expect(restoreInput).toBeVisible();
      const restoreResponse = page.waitForResponse(response =>
        response.url().includes('/api/workflow/config/prompts') && response.request().method() === 'PUT'
      );
      await restoreInput.fill(originalUser);
      await page.locator('#rank-agent-prompt-container button', { hasText: 'Save' }).click();
      await restoreResponse;
    }
  });
});
