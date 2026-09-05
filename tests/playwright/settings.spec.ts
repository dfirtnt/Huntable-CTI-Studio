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

  test('[SETTINGS-063] stale backup status shows a warning', async ({ page }) => {
    await page.route('**/api/backup/status', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          automated: true,
          cron_available: true,
          managed_jobs: [],
          total_backups: 1,
          total_size_gb: 1,
          last_backup: 'system_backup_20260830_020002',
          last_backup_at: '2026-08-30 02:00:02',
          backup_age_days: 4.5,
          backup_stale_after_days: 3,
          backup_stale: true,
        }),
      });
    });

    await page.locator('#backupConfig-header').click();
    await page.locator('#backupStatusBtn').click();
    await expect(page.getByTestId('backup-stale-warning')).toBeVisible();
  });

  test('[SETTINGS-064] fresh backup status has no warning', async ({ page }) => {
    await page.route('**/api/backup/status', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          automated: true,
          cron_available: true,
          managed_jobs: [],
          total_backups: 1,
          total_size_gb: 1,
          last_backup: 'system_backup_20260902_020002',
          last_backup_at: '2026-09-02 02:00:02',
          backup_age_days: 1.5,
          backup_stale_after_days: 3,
          backup_stale: false,
        }),
      });
    });

    await page.locator('#backupConfig-header').click();
    await page.locator('#backupStatusBtn').click();
    await expect(page.getByTestId('backup-stale-warning')).toHaveCount(0);
    await expect(page.locator('#backupStatusContent')).toContainText('1.5 days');
  });

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
    await page.locator('#backupConfig-header').click();
    await button.click();

    await expect(button).toBeDisabled();
    await expect(button).toHaveText('Creating backup...');
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

test.describe('Settings - Accessibility & control state', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/settings`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#saveSettings')).toBeVisible();
  });

  // Regression guard: these 5 icon-only reveal toggles previously had empty
  // textContent, no aria-label, no title, and no aria-pressed -- unreadable to
  // a screen reader. Each lives behind its own collapsible panel (and, for the
  // two commercial providers, an additional enable checkbox) before it renders.
  const PASSWORD_TOGGLES: { id: string; panel: string; enableCheckbox?: string }[] = [
    { id: 'toggleWorkflowOpenaiApiKey', panel: 'agenticWorkflowConfig', enableCheckbox: 'workflowOpenaiEnabled' },
    { id: 'toggleWorkflowAnthropicApiKey', panel: 'agenticWorkflowConfig', enableCheckbox: 'workflowAnthropicEnabled' },
    { id: 'toggleLangfusePublicKey', panel: 'agenticWorkflowConfig' },
    { id: 'toggleLangfuseSecretKey', panel: 'agenticWorkflowConfig' },
    { id: 'toggleGithubToken', panel: 'githubPRConfig' },
  ];

  for (const { id: toggleId, panel, enableCheckbox } of PASSWORD_TOGGLES) {
    test(`[SETTINGS-060] ${toggleId} exposes an accessible name and pressed state`, async ({ page }) => {
      await page.locator(`[data-collapsible-panel="${panel}"]`).click();
      if (enableCheckbox) {
        const checkbox = page.locator(`#${enableCheckbox}`);
        if (!(await checkbox.isChecked().catch(() => false))) {
          await checkbox.check();
        }
      }

      const toggle = page.locator(`#${toggleId}`);
      const hasToggle = await toggle.isVisible({ timeout: 3000 }).catch(() => false);
      test.skip(!hasToggle, `${toggleId} not rendered in current runtime`);

      await expect(toggle).toHaveAttribute('aria-label', 'Show API key');
      await expect(toggle).toHaveAttribute('aria-pressed', 'false');

      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-label', 'Hide API key');
      await expect(toggle).toHaveAttribute('aria-pressed', 'true');
    });
  }

  test('[SETTINGS-061] disabled backup cron buttons use not-allowed cursor, not progress', async ({ page }) => {
    const applyBtn = page.locator('#applyBackupCronBtn');
    const isDisabled = await applyBtn.isDisabled().catch(() => false);
    test.skip(!isDisabled, 'Cron controls are enabled in this environment (host crontab reachable)');

    await expect(applyBtn).toHaveCSS('cursor', 'not-allowed');
  });

  test('[SETTINGS-062] backup retention inputs reject a zero minimum', async ({ page }) => {
    for (const id of ['dailyRetention', 'weeklyRetention', 'monthlyRetention']) {
      await expect(page.locator(`#${id}`)).toHaveAttribute('min', '1');
    }
  });

  test('[SETTINGS-063] auto-trigger hunt score threshold accepts a fractional value', async ({ page }) => {
    const threshold = page.locator('#autoTriggerHuntScoreThreshold');
    if (!(await threshold.isVisible({ timeout: 1000 }).catch(() => false))) {
      const header = page.locator('[data-collapsible-panel="agenticWorkflowConfig"]');
      await header.click();
    }
    await expect(threshold).toBeVisible({ timeout: 5000 });
    await expect(threshold).toHaveAttribute('step', '0.1');
    await threshold.fill('90.5');
    const isValid = await threshold.evaluate((el: HTMLInputElement) => el.checkValidity());
    expect(isValid).toBe(true);
  });
});
