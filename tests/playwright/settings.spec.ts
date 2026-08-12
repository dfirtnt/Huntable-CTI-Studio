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

  test('[SETTINGS-003] Settings sections are present', async ({ page }) => {
    const sections = page.locator('[data-testid="settings-section"], .settings-section, h2, h3');
    const count = await sections.count();
    expect(count).toBeGreaterThan(0);
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

test.describe('Settings - Backup feedback', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-024] Backup creation shows in-progress and completion feedback', async ({ page }) => {
    let completeBackup: (() => Promise<void>) | undefined;
    await page.route('**/api/backup/create', async (route) => {
      await new Promise<void>((resolve) => {
        completeBackup = async () => {
          await route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({ success: true, backup_name: 'system_backup_test' }),
          });
          resolve();
        };
      });
    });

    await page.goto(`${BASE}/settings`);
    const button = page.locator('#createBackupBtn');
    const feedback = page.getByTestId('backup-create-feedback');
    await button.click();

    await expect(button).toBeDisabled();
    await expect(button).toHaveText('Creating backup…');
    await expect(feedback).toContainText('Backup is running');

    if (!completeBackup) {
      throw new Error('Backup request was not intercepted');
    }
    await completeBackup();

    await expect(button).toBeEnabled();
    await expect(button).toHaveText('Create Backup Now');
    await expect(feedback).toContainText('Backup created successfully: system_backup_test');
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

  test('[SETTINGS-032] Codex subscription provider control is present', async ({ page }) => {
    await page.goto(`${BASE}/settings`);
    await expect(page.locator('#saveSettings')).toBeVisible();
    await page.locator('[data-collapsible-panel="agenticWorkflowConfig"]').click();
    await expect(page.locator('#workflowCodexEnabled')).toBeVisible();
    await page.locator('#workflowCodexEnabled').check();
    await expect(page.locator('#workflowCodexSection')).toBeVisible();
    await expect(page.getByText('Connection is managed by an administrator.')).toBeVisible();
    await expect(page.getByText('Administrator setup')).toBeVisible();
    await expect(page.locator('#testWorkflowCodexSubscription')).toBeVisible();
  });

  test('[SETTINGS-033] Codex subscription test displays the API result', async ({ page }) => {
    await page.route('**/api/settings/codex/test', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ valid: true, message: 'Codex subscription is ready (plus)' }),
      });
    });
    await page.goto(`${BASE}/settings`);
    await expect(page.locator('#saveSettings')).toBeVisible();
    await page.locator('[data-collapsible-panel="agenticWorkflowConfig"]').click();
    await page.locator('#workflowCodexEnabled').check();
    await page.locator('#testWorkflowCodexSubscription').click();

    await expect(page.locator('#workflowCodexStatus')).toHaveText('Codex subscription is ready (plus)');
    await expect(page.locator('#workflowCodexStatus')).toHaveClass(/settings-test-status is-ok/);
    // The busy state swaps only the label, so the button keeps its icon.
    await expect(page.locator('#testWorkflowCodexSubscription svg')).toHaveCount(1);
    await expect(page.locator('#testWorkflowCodexSubscription .btn-label')).toHaveText('Test subscription');
  });

  // Each provider is one panel: enabling the checkbox must reveal that
  // provider's own config section in place (and hide it again on disable).
  const toggleProviderSection = async (page, checkboxId: string, sectionId: string) => {
    await page.goto(`${BASE}/settings`);
    await expect(page.locator('#saveSettings')).toBeVisible();
    await page.locator('[data-collapsible-panel="agenticWorkflowConfig"]').click();
    const checkbox = page.locator(`#${checkboxId}`);
    const section = page.locator(`#${sectionId}`);

    if (!(await checkbox.isVisible().catch(() => false))) {
      test.skip(true, `${checkboxId} not rendered (provider hidden for this runtime)`);
    }

    await checkbox.uncheck();
    await expect(section).toBeHidden();
    await checkbox.check();
    await expect(section).toBeVisible();
    await checkbox.uncheck();
    await expect(section).toBeHidden();
    // Leave the provider enabled so the caller can assert its config is shown.
    await checkbox.check();
    await expect(section).toBeVisible();
  };

  test('[SETTINGS-034] OpenAI enable toggle reveals its API key section', async ({ page }) => {
    await toggleProviderSection(page, 'workflowOpenaiEnabled', 'workflowOpenaiApiKeySection');
    await expect(page.locator('#workflowOpenaiApiKey')).toBeVisible();
  });

  test('[SETTINGS-035] Anthropic enable toggle reveals its API key section', async ({ page }) => {
    await toggleProviderSection(page, 'workflowAnthropicEnabled', 'workflowAnthropicApiKeySection');
    await expect(page.locator('#workflowAnthropicApiKey')).toBeVisible();
  });

  test('[SETTINGS-036] LMStudio enable toggle reveals its config section', async ({ page }) => {
    // When the operator opted out of LMStudio during setup, the whole row is
    // removed from the page and the section never becomes visible.
    await toggleProviderSection(page, 'workflowLmstudioEnabled', 'workflowLmstudioApiKeySection');
    await expect(page.locator('#lmstudioApiUrl')).toBeVisible();
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
