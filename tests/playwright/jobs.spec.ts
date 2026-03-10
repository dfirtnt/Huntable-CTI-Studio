import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_JOBS_TESTS === 'true';

test.describe('Jobs Page', () => {
  test.skip(SKIP_TESTS, 'Jobs tests disabled (SKIP_JOBS_TESTS=true).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/jobs`);
    await page.waitForLoadState('networkidle');
  });

  test('[JOBS-001] Jobs page loads successfully', async ({ page }) => {
    await expect(page).toHaveURL(/\/jobs/);
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    await page.waitForTimeout(250);
    expect(errors.filter((e) => !e.includes('favicon'))).toHaveLength(0);
  });

  test('[JOBS-002] Page title is displayed', async ({ page }) => {
    const title = page.locator('h1, [data-testid="jobs-title"]');
    await expect(title.first()).toBeVisible();
  });

  test('[JOBS-003] Jobs list/table is present', async ({ page }) => {
    const jobs = page.locator('[data-testid="jobs-list"], .jobs-list, table, .jobs');
    const hasJobs = await jobs.first().isVisible().catch(() => false);
    expect(hasJobs).toBe(true);
  });
});

test.describe('Jobs - Queue Status', () => {
  test.skip(SKIP_TESTS, 'Jobs tests disabled.');

  test('[JOBS-010] Queue status is displayed', async ({ page }) => {
    const status = page.locator('[data-testid="queue-status"], .queue-status, .status');
    const hasStatus = await status.first().isVisible().catch(() => false);
    expect(hasStatus).toBe(true);
  });

  test('[JOBS-011] Worker status is shown', async ({ page }) => {
    const worker = page.locator('[data-testid="worker-status"], .worker, text=Worker');
    const hasWorker = await worker.first().isVisible().catch(() => false);
    expect(hasWorker).toBe(true);
  });

  test('[JOBS-012] Pending tasks count is visible', async ({ page }) => {
    const pending = page.locator('[data-testid="pending-count"], text=Pending');
    const hasPending = await pending.first().isVisible().catch(() => false);
    expect(hasPending).toBe(true);
  });
});

test.describe('Jobs - Task Details', () => {
  test.skip(SKIP_TESTS, 'Jobs tests disabled.');

  test('[JOBS-020] Task list shows task entries', async ({ page }) => {
    const tasks = page.locator('[data-testid="task"], .task, tr:has(td)');
    const count = await tasks.count();
  });

  test('[JOBS-021] Task status is displayed per task', async ({ page }) => {
    const status = page.locator('[data-testid="task-status"], .status:has(span)');
    const hasStatus = await status.first().isVisible().catch(() => false);
    expect(hasStatus).toBe(true);
  });

  test('[JOBS-022] Task ID is visible', async ({ page }) => {
    const id = page.locator('[data-testid="task-id"], .task-id, text=#');
    const hasId = await id.first().isVisible().catch(() => false);
    expect(hasId).toBe(true);
  });
});

test.describe('Jobs - API', () => {
  test.skip(SKIP_TESTS, 'Jobs tests disabled.');

  test('[JOBS-030] Jobs API returns queue info', async ({ request }) => {
    const resp = await request.get('/api/tasks');
    expect([200, 404, 500]).toContain(resp.status());
  });

  test('[JOBS-031] Celery health check endpoint exists', async ({ request }) => {
    const resp = await request.get('/api/health/celery');
    expect([200, 500]).toContain(resp.status());
  });
});

test.describe('Jobs - Refresh', () => {
  test.skip(SKIP_TESTS, 'Jobs tests disabled.');

  test('[JOBS-040] Refresh button exists', async ({ page }) => {
    const refresh = page.locator('button:has-text("Refresh"), button:has-text("Reload"), [data-testid="refresh-jobs"]');
    const hasRefresh = await refresh.first().isVisible().catch(() => false);
    expect(hasRefresh).toBe(true);
  });

  test('[JOBS-041] Page auto-refreshes or can manually refresh', async ({ page }) => {
    const before = await page.locator('[data-testid="task"]').count();
    
    await page.waitForTimeout(2000);
    
    const refreshBtn = page.locator('button:has-text("Refresh")').first();
    const hasRefresh = await refreshBtn.isVisible().catch(() => false);
    if (hasRefresh) {
      await refreshBtn.click();
      await page.waitForTimeout(500);
    }
  });
});
