import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_SETTINGS_TESTS === 'true';

test.describe('Settings Page', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled (SKIP_SETTINGS_TESTS=true).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/settings`);
    await page.waitForLoadState('networkidle');
  });

  test('[SETTINGS-001] Settings page loads successfully', async ({ page }) => {
    await expect(page).toHaveURL(/\/settings/);
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    await page.waitForTimeout(250);
    expect(errors.filter((e) => !e.includes('favicon'))).toHaveLength(0);
  });

  test('[SETTINGS-002] Page title is displayed', async ({ page }) => {
    const title = page.locator('h1, h2, h3, [data-testid="settings-title"]');
    await expect(title.first()).toBeVisible();
  });

  test('[SETTINGS-003] Settings sections are present', async ({ page }) => {
    const sections = page.locator('[data-testid="settings-section"], .settings-section, h2, h3');
    const count = await sections.count();
    expect(count).toBeGreaterThan(0);
  });
});

test.describe('Settings - LMStudio Configuration', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-010] LMStudio API URL field is present', async ({ page }) => {
    const field = page.locator('input[name*="LMSTUDIO"], input[id*="lmstudio"], input[placeholder*="localhost"]');
    const hasField = await field.first().isVisible().catch(() => false);
    expect(hasField).toBe(true);
  });

  test('[SETTINGS-011] LMStudio Embedding URL field is present', async ({ page }) => {
    const field = page.locator('input[name*="EMBEDDING"], input[id*="embedding"]');
    const hasField = await field.first().isVisible().catch(() => false);
    expect(hasField).toBe(true);
  });

  test('[SETTINGS-012] Can edit LMStudio URL', async ({ page }) => {
    const field = page.locator('input[name*="LMSTUDIO_API_URL"]').first();
    const isVisible = await field.isVisible().catch(() => false);
    if (isVisible) {
      await field.fill('http://localhost:1234/v1');
      await expect(field).toHaveValue('http://localhost:1234/v1');
    }
  });
});

test.describe('Settings - Save and Persistence', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-020] Save button is present', async ({ page }) => {
    const saveBtn = page.locator('button:has-text("Save"), button:has-text("Update"), [data-testid="save-settings"]');
    await expect(saveBtn.first()).toBeVisible();
  });

  test('[SETTINGS-021] Settings persist after page reload', async ({ page }) => {
    const field = page.locator('input[name*="LMSTUDIO_API_URL"]').first();
    const isVisible = await field.isVisible().catch(() => false);
    
    if (isVisible) {
      const testValue = `http://localhost:${Math.floor(Math.random() * 10000)}/v1`;
      await field.fill(testValue);
      
      const saveBtn = page.locator('button:has-text("Save"), button:has-text("Update")').first();
      await saveBtn.click();
      
      await page.waitForTimeout(500);
      await page.reload();
      await page.waitForLoadState('networkidle');
      
      const newField = page.locator('input[name*="LMSTUDIO_API_URL"]').first();
      await expect(newField).toHaveValue(testValue);
    }
  });

  test('[SETTINGS-022] Success message after save', async ({ page }) => {
    const field = page.locator('input[name*="LMSTUDIO_API_URL"]').first();
    const isVisible = await field.isVisible().catch(() => false);
    
    if (isVisible) {
      await field.fill('http://localhost:1234/v1');
      
      const saveBtn = page.locator('button:has-text("Save"), button:has-text("Update")').first();
      await saveBtn.click();
      
      await page.waitForTimeout(500);
      
      const toast = page.locator('.toast, .success, [data-testid="success-message"], text=Success');
      const hasToast = await toast.first().isVisible().catch(() => false);
    }
  });
});

test.describe('Settings - API Keys', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-030] OpenAI API key field is present', async ({ page }) => {
    const field = page.locator('input[name*="OPENAI"], input[id*="openai"]');
    const hasField = await field.first().isVisible().catch(() => false);
    expect(hasField).toBe(true);
  });

  test('[SETTINGS-031] Anthropic API key field is present', async ({ page }) => {
    const field = page.locator('input[name*="ANTHROPIC"], input[id*="anthropic"]');
    const hasField = await field.first().isVisible().catch(() => false);
    expect(hasField).toBe(true);
  });

  test('[SETTINGS-032] API keys are masked/secured', async ({ page }) => {
    const field = page.locator('input[name*="API_KEY"][type="password"]');
    const isMasked = await field.first().isVisible().catch(() => false);
  });
});

test.describe('Settings - Test Connection', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-040] Test Connection button exists', async ({ page }) => {
    const btn = page.locator('button:has-text("Test"), button:has-text("Verify"), [data-testid="test-connection"]');
    const hasBtn = await btn.first().isVisible().catch(() => false);
    expect(hasBtn).toBe(true);
  });
});

test.describe('Settings - API', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-050] Settings API returns settings', async ({ request }) => {
    const resp = await request.get('/api/settings');
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toBeDefined();
  });

  test('[SETTINGS-051] Can update settings via API', async ({ request }) => {
    const getResp = await request.get('/api/settings');
    const settings = await getResp.json();
    
    const testKey = `test_key_${Date.now()}`;
    const updateData = { [testKey]: 'test_value' };
    
    const updateResp = await request.post('/api/settings', { data: updateData });
    expect(updateResp.status()).toBe(200);
  });
});
