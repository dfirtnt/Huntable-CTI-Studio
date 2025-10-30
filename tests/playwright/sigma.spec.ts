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
});


