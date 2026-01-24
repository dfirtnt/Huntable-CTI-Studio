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

async function expandPromptPanel(page: Page, panelId: string) {
  const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
  await header.waitFor({ state: 'attached', timeout: 15000 }).catch(() => {});
  const content = page.locator(`#${panelId}-content`);
  if (await content.count() === 0 || await header.count() === 0) {
    return;
  }
  const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
  if (isHidden) {
    await header.click();
    await page.waitForTimeout(300);
  }
}

async function expandAgentPanels(page: Page) {
  await expandPanel(page, 'qa-settings-panel');
  await expandPanel(page, 'os-detection-panel');
  await expandPanel(page, 'rank-agent-configs-panel');
  await expandPanel(page, 'extract-agent-panel');
  await expandPanel(page, 'cmdlineextract-agent-panel');
  await expandPanel(page, 'proctreeextract-agent-panel');
  await expandPanel(page, 'huntqueriesextract-agent-panel');
  await expandPanel(page, 'sigma-agent-panel');
}

async function ensureQATogglesEnabled(page: Page) {
  await page.evaluate(() => {
    const ids = ['qa-rankagent', 'qa-cmdlineextract', 'qa-proctreeextract', 'qa-huntqueriesextract'];
    ids.forEach(id => {
      const el = document.getElementById(id) as HTMLInputElement | null;
      if (el && !el.checked) {
        el.checked = true;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  });
  await page.waitForTimeout(500);
}

test.describe('Agent Config Full Coverage (10+ agents)', () => {
  test.beforeEach(async ({ page }) => {
    await gotoWorkflowConfig(page);
    await expandAgentPanels(page);
    await ensureQATogglesEnabled(page);
  });

  test('LLM prompt editors expose History buttons (10 agents)', async ({ page }) => {
    const promptEditors = [
      { name: 'RankAgent', container: '#rank-agent-prompt-container', panelId: 'rank-agent-prompt-panel' },
      { name: 'ExtractAgent', container: '#extract-agent-prompt-container', panelId: 'extract-agent-prompt-panel' },
      { name: 'SigmaAgent', container: '#sigma-agent-prompt-container', panelId: 'sigma-agent-prompt-panel' },
      { name: 'CmdlineExtract', container: '#cmdlineextract-agent-prompt-container', panelId: 'cmdlineextract-agent-prompt-panel' },
      { name: 'ProcTreeExtract', container: '#proctreeextract-agent-prompt-container', panelId: 'proctreeextract-agent-prompt-panel' },
      { name: 'HuntQueriesExtract', container: '#huntqueriesextract-agent-prompt-container', panelId: 'huntqueriesextract-agent-prompt-panel' },
      { name: 'QAAgent', container: '#rank-qa-agent-prompt-content', panelId: 'qaagent-qa-prompt-panel' },
      { name: 'CmdLineQA', container: '#cmdlineextract-agent-qa-prompt-container', panelId: 'cmdlineqa-qa-prompt-panel' },
      { name: 'ProcTreeQA', container: '#proctreeextract-agent-qa-prompt-container', panelId: 'proctreeqa-qa-prompt-panel' },
      { name: 'HuntQueriesQA', container: '#huntqueriesextract-agent-qa-prompt-container', panelId: 'huntqueriesqa-qa-prompt-panel' }
    ];

    for (const editor of promptEditors) {
      const container = page.locator(editor.container);
      await container.waitFor({ state: 'attached', timeout: 15000 });
      await expandPromptPanel(page, editor.panelId);
      const historyButton = container.locator('button', { hasText: 'History' }).first();
      await historyButton.waitFor({ state: 'attached', timeout: 15000 });
      await expect(historyButton, `${editor.name} history button`).toBeVisible();
    }
  });

  test('Enable/disable toggles are visible (10 agents)', async ({ page }) => {
    const toggles = [
      '#rank-agent-enabled',
      '#toggle-cmdlineextract-enabled',
      '#toggle-proctreeextract-enabled',
      '#toggle-huntqueriesextract-enabled',
      '#qa-rankagent',
      '#qa-cmdlineextract',
      '#qa-proctreeextract',
      '#qa-huntqueriesextract',
      '#sigma-fallback-enabled',
      '#osdetectionagent-fallback-enabled'
    ];

    for (const selector of toggles) {
      const toggle = page.locator(selector);
      await expect(toggle, `${selector} toggle`).toBeVisible();
    }
  });

  test('Temperature and top_p controls are editable (10 agents)', async ({ page }) => {
    const inputs = [
      { name: 'RankAgent', temp: '#rankagent-temperature', topP: '#rankagent-top-p' },
      { name: 'ExtractAgent', temp: '#extractagent-temperature', topP: '#extractagent-top-p' },
      { name: 'SigmaAgent', temp: '#sigmaagent-temperature', topP: '#sigmaagent-top-p' },
      { name: 'CmdlineExtract', temp: '#cmdlineextract-temperature', topP: '#cmdlineextract-top-p' },
      { name: 'ProcTreeExtract', temp: '#proctreeextract-temperature', topP: '#proctreeextract-top-p' },
      { name: 'HuntQueriesExtract', temp: '#huntqueriesextract-temperature', topP: '#huntqueriesextract-top-p' },
      { name: 'RankAgentQA', temp: '#rankqa-temperature', topP: '#rankqa-top-p' },
      { name: 'CmdLineQA', temp: '#cmdlineqa-temperature', topP: '#cmdlineqa-top-p' },
      { name: 'ProcTreeQA', temp: '#proctreeqa-temperature', topP: '#proctreeqa-top-p' },
      { name: 'HuntQueriesQA', temp: '#huntqueriesqa-temperature', topP: '#huntqueriesqa-top-p' }
    ];

    for (const input of inputs) {
      const tempInput = page.locator(input.temp);
      await tempInput.waitFor({ state: 'attached', timeout: 10000 });
      await tempInput.scrollIntoViewIfNeeded().catch(() => {});
      await expect(tempInput, `${input.name} temperature`).toBeVisible();
      await expect(tempInput, `${input.name} temperature`).toBeEditable();

      const topPInput = page.locator(input.topP);
      await topPInput.waitFor({ state: 'attached', timeout: 10000 });
      await topPInput.scrollIntoViewIfNeeded().catch(() => {});
      await expect(topPInput, `${input.name} top_p`).toBeVisible();
      await expect(topPInput, `${input.name} top_p`).toBeEditable();
    }
  });
});
