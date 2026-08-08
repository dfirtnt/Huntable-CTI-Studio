import { expect, test } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test('[AGENT-CONFIG-077] Codex subscription models populate the shared selector renderer', async ({ page }) => {
  await page.goto(`${BASE}/workflow#config`);
  await page.waitForSelector('#workflowConfigForm', { timeout: 15000 });
  await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 15000 });
  await page.waitForFunction(() => {
    const html = typeof buildCommercialProviderInput === 'function'
      ? buildCommercialProviderInput('codex-model-probe', 'codex', 'codex', '')
      : '';
    return html.includes('<option') && html.includes('gpt-5.6-luna');
  });
  await page.evaluate(() => {
    const fixture = document.createElement('div');
    fixture.id = 'codex-model-fixture';
    fixture.innerHTML = buildCommercialProviderInput('codex-model-probe', 'codex', 'codex', '');
    document.body.append(fixture);
  });

  const model = page.locator('#codex-model-probe-model-codex');
  await expect(model).toBeVisible();
  const modelOptions = await model.locator('option').allTextContents();
  expect(modelOptions).toEqual(expect.arrayContaining([
    'gpt-5.6-sol',
    'gpt-5.6-terra',
    'gpt-5.6-luna',
  ]));
  expect(modelOptions).not.toContain('gpt-5.5');
});
