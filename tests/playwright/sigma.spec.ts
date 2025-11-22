import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const ARTICLE_ID = process.env.ARTICLE_ID || '836';

test.describe('SIGMA generation (LMStudio)', () => {
  test('API: POST /generate-sigma should not network-fail when ai_model=lmstudio', async () => {
    const api = await request.newContext({ baseURL: BASE, timeout: 120_000 });
    const resp = await api.post(`/api/articles/${ARTICLE_ID}/generate-sigma`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        include_content: true,
        force_regenerate: true,
        ai_model: 'lmstudio',
        temperature: 0.3,
        author_name: 'Playwright Test'
      }
    });
    if (!resp.ok()) {
      const status = resp.status();
      let text = '';
      try { text = await resp.text(); } catch {}
      throw new Error(`Non-OK response: ${status} body=${text}`);
    }
    const body = await resp.json();
    expect(body).toBeTruthy();
  });

  test('UI: Generate SIGMA via article page should POST and not fail fetch', async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto(`${BASE}/articles/${ARTICLE_ID}`);

    const sigmaButton = page.locator('button:has-text("Generate SIGMA Rules"), button:has-text("Display SIGMA Rules")');
    await expect(sigmaButton).toBeVisible({ timeout: 20_000 });
    await sigmaButton.click();

    const regenButton = page.locator('button:has-text("Regenerate SIGMA Rules")');
    try {
      if (await regenButton.isVisible({ timeout: 3000 })) {
        await regenButton.click();
      }
    } catch {}

    const response = await page.waitForResponse(
      (resp) => resp.url().includes(`/api/articles/${ARTICLE_ID}/generate-sigma`),
      { timeout: 120_000 }
    );
    expect(response.ok()).toBeTruthy();

    const errorToast = page.locator('text=Error: Failed to fetch');
    await expect(errorToast).toHaveCount(0);
  });

  test('UI: Similar Rules shows LMStudio attribution (provider and model)', async ({ page }) => {
    test.setTimeout(240_000);
    // Set Settings to lmstudio before page scripts run
    await page.addInitScript(() => {
      localStorage.setItem('ctiScraperSettings', JSON.stringify({
        aiModel: 'lmstudio',
        aiTemperature: '0.2'
      }));
    });

    await page.goto(`${BASE}/articles/${ARTICLE_ID}`);

    // Open assistant and show rules (use existing if present)
    const assistantBtn = page.getByRole('button', { name: '🤖 AL/ML Assistant' });
    await assistantBtn.click();
    const displaySigmaBtn = page.getByRole('button', { name: /Display SIGMA Rules|Generate SIGMA Rules/ });
    await displaySigmaBtn.click();

    // If not generated yet, a regenerate may be required; handle presence of "Regenerate"
    const regenBtn = page.getByRole('button', { name: '🔄 Regenerate' });
    if (await regenBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await regenBtn.click();
      const analyzeBtn = page.getByRole('button', { name: 'Analyze' });
      await analyzeBtn.click();
      // Wait for completion banner - check for banner text or modal opening
      await Promise.race([
        page.waitForSelector('text=SIGMA Rules Complete!', { timeout: 120_000 }).catch(() => null),
        page.waitForSelector('#sigmaRulesModal', { timeout: 120_000 }).catch(() => null),
        page.waitForSelector('text=🔍 SIGMA Detection Rules', { timeout: 120_000 }).catch(() => null)
      ]);
    }

    // Trigger similar rules search (first run)
    const checkSimilar = page.locator('#checkSimilarRulesBtn');
    await expect(checkSimilar).toBeVisible({ timeout: 20_000 });
    await checkSimilar.click();

    // Wait for Similar Rules modal
    await page.waitForSelector('text=Similar Rules in SigmaHQ Repository', { timeout: 120_000 });

    // Expect LMStudio attribution to appear when reranked by LLM
    const attribution = page.locator('text=Analysis by: lmstudio');
    await expect(attribution).toBeVisible({ timeout: 120_000 });
  });
});


