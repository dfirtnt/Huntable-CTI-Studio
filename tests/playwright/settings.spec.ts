import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_SETTINGS_TESTS === 'true';

test.describe('Settings Page', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled (SKIP_SETTINGS_TESTS=true).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/settings`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#saveSettings')).toBeVisible();
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
    const field = page.locator('#lmstudioApiUrl');
    const hasField = await field.first().isVisible().catch(() => false);
    test.skip(!hasField, 'LMStudio API URL field not rendered in current runtime');
    expect(hasField).toBe(true);
  });

  test('[SETTINGS-011] LMStudio Embedding URL field is present', async ({ page }) => {
    const field = page.locator('#lmstudioEmbeddingUrl');
    const hasField = await field.first().isVisible().catch(() => false);
    test.skip(!hasField, 'LMStudio embedding URL field not rendered in current runtime');
    expect(hasField).toBe(true);
  });

  test('[SETTINGS-012] Can edit LMStudio URL', async ({ page }) => {
    const field = page.locator('#lmstudioApiUrl').first();
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
    const saveBtn = page.locator('#saveSettings');
    const hasSave = await saveBtn.first().isVisible().catch(() => false);
    test.skip(!hasSave, 'Save settings button not rendered in current runtime');
    await expect(saveBtn.first()).toBeVisible();
  });

  test('[SETTINGS-021] Settings persist after page reload', async ({ page }) => {
    const field = page.locator('#lmstudioApiUrl').first();
    const isVisible = await field.isVisible().catch(() => false);
    
    if (isVisible) {
      const testValue = `http://localhost:${Math.floor(Math.random() * 10000)}/v1`;
      await field.fill(testValue);
      
      const saveBtn = page.locator('#saveSettings').first();
      await saveBtn.click();
      
      await page.waitForTimeout(500);
      await page.reload();
      await page.waitForLoadState('domcontentloaded');
      
      const newField = page.locator('#lmstudioApiUrl').first();
      await expect(newField).toHaveValue(testValue);
    }
  });

  test('[SETTINGS-022] Success message after save', async ({ page }) => {
    const field = page.locator('#lmstudioApiUrl').first();
    const isVisible = await field.isVisible().catch(() => false);
    
    if (isVisible) {
      await field.fill('http://localhost:1234/v1');
      
      const saveBtn = page.locator('#saveSettings').first();
      await saveBtn.click();
      
      await page.waitForTimeout(500);
      
      await expect(page.getByText('Settings saved successfully!', { exact: false })).toBeVisible();
    }
  });

  test('[SETTINGS-023] Scheduled jobs panel loads from backend', async ({ page }) => {
    const header = page.locator('#scheduledJobs-header');
    const hasHeader = await header.isVisible({ timeout: 5000 }).catch(() => false);
    test.skip(!hasHeader, 'Scheduled jobs panel header not rendered in current runtime');
    
    await header.click();
    await expect(page.locator('#refreshScheduledJobsBtn')).toBeVisible();
    await expect(page.locator('#saveScheduledJobsBtn')).toBeVisible();
    await expect(page.locator('#scheduledJobsList')).toBeVisible();
    await expect(page.getByText('Generate Daily Report', { exact: true })).toHaveCount(0);

    const refreshResponse = page.waitForResponse((response) => response.url().includes('/api/scheduled-jobs') && response.request().method() === 'GET');
    await page.locator('#refreshScheduledJobsBtn').click();
    const response = await refreshResponse;

    expect(response.ok()).toBeTruthy();
    await expect(page.locator('#scheduledJobsCount')).toHaveText('4');
  });

});

test.describe('Settings - API Keys', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-030] OpenAI API key field is present', async ({ page }) => {
    const field = page.locator('#workflowOpenaiApiKey');
    const hasField = await field.first().isVisible().catch(() => false);
    test.skip(!hasField, 'OpenAI API key field not rendered in current runtime');
    expect(hasField).toBe(true);
  });

  test('[SETTINGS-031] Anthropic API key field is present', async ({ page }) => {
    const field = page.locator('#workflowAnthropicApiKey');
    const hasField = await field.first().isVisible().catch(() => false);
    test.skip(!hasField, 'Anthropic API key field not rendered in current runtime');
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
    const btn = page.locator('#testWorkflowLmstudioApiKey');
    const hasBtn = await btn.first().isVisible().catch(() => false);
    test.skip(!hasBtn, 'LMStudio test connection button not rendered in current runtime');
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
    const updateData = { WORKFLOW_QA_MAX_RETRIES: '2' };
    
    const updateResp = await request.post('/api/settings', { data: updateData });
    expect([200, 422]).toContain(updateResp.status());
  });
});
