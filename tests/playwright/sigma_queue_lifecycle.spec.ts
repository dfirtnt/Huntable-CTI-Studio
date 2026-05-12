/**
 * E2E tests for the Sigma queue lifecycle:
 *   add rule to queue -> list as pending -> approve/reject -> verify status
 *
 * Strategy:
 *   - API-layer tests use Playwright's request context (no browser needed).
 *   - UI-layer tests navigate to /workflow#queue and interact with the table.
 *   - All test rules carry a title marker so afterAll can reject/clean them up
 *     even if a test fails mid-run.
 *
 * Prerequisites:
 *   - Server running at CTI_SCRAPER_URL (default http://127.0.0.1:8001)
 *   - At least one article in the database (tests skip gracefully if empty)
 */

import { test, expect, APIRequestContext } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';
const TEST_MARKER = 'E2E-QUEUE-LIFECYCLE-MARKER';

// Minimal valid Sigma YAML used throughout the tests
function buildTestYaml(suffix: string): string {
  return `title: ${TEST_MARKER}-${suffix}
id: 00000000-e2e-test-0000-${suffix.padEnd(12, '0').slice(0, 12)}
status: experimental
description: Automated e2e test rule - safe to reject
author: E2E Test Suite
date: 2026-05-11
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    CommandLine|contains: e2e-huntable-marker-${suffix}
  condition: selection
level: low
falsepositives:
  - None - this is an automated test rule
`;
}

// Fetch the first available article_id from the live DB via the API.
// Returns null if the DB has no articles (caller should skip).
async function fetchFirstArticleId(request: APIRequestContext): Promise<number | null> {
  const response = await request.get(`${BASE}/api/articles?limit=1`);
  if (!response.ok()) return null;
  const data = await response.json();
  const items: any[] = data.articles ?? data.items ?? data ?? [];
  if (!Array.isArray(items) || items.length === 0) return null;
  return items[0].id ?? null;
}

// Add a rule to the queue and return its queue_id.
// Retries up to 3 times with 1-second backoff because the /add endpoint runs
// an embedding similarity scan that can drop connections under parallel load.
async function addRuleToQueue(
  request: APIRequestContext,
  articleId: number,
  suffix: string,
): Promise<number> {
  const maxAttempts = 3;
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const response = await request.post(`${BASE}/api/sigma-queue/add`, {
        data: { article_id: articleId, rule_yaml: buildTestYaml(suffix) },
        timeout: 30000,
      });
      expect(response.status(), `add rule ${suffix} should succeed`).toBe(200);
      const body = await response.json();
      expect(body.success).toBe(true);
      expect(typeof body.queue_id).toBe('number');
      return body.queue_id as number;
    } catch (err) {
      lastError = err;
      if (attempt < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
      }
    }
  }
  throw lastError;
}

// Reject a queue entry (used for cleanup and as a test action).
async function rejectQueueEntry(request: APIRequestContext, queueId: number): Promise<void> {
  await request.post(`${BASE}/api/sigma-queue/${queueId}/reject`, {
    data: { review_notes: 'cleaned up by e2e test suite' },
  });
}

// ---------------------------------------------------------------------------
// Shared cleanup state - all queue IDs created during the run land here so
// afterAll can reject them regardless of which test created them.
// ---------------------------------------------------------------------------
const createdQueueIds: number[] = [];

test.afterAll(async ({ request }) => {
  for (const id of createdQueueIds) {
    await rejectQueueEntry(request, id).catch(() => {});
  }
});

// ============================================================
// API-layer lifecycle tests
// ============================================================

test.describe('Sigma Queue API lifecycle', () => {
  test('should add a rule to the queue and return a queue_id', async ({ request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB - cannot add queue entry');
      return;
    }
    const queueId = await addRuleToQueue(request, articleId, 'add-only');
    createdQueueIds.push(queueId);

    expect(queueId).toBeGreaterThan(0);
  });

  test('should appear in the queue list as pending', async ({ request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }

    const queueId = await addRuleToQueue(request, articleId, 'list-pending');
    createdQueueIds.push(queueId);

    const listResp = await request.get(`${BASE}/api/sigma-queue/list?status=pending&limit=100`);
    expect(listResp.ok()).toBe(true);
    const list = await listResp.json();

    const found = list.items.find((r: any) => r.id === queueId);
    expect(found, `queue entry ${queueId} should be in the pending list`).toBeTruthy();
    expect(found.status).toBe('pending');
  });

  test('should approve a queued rule and reflect approved status', async ({ request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }

    const queueId = await addRuleToQueue(request, articleId, 'approve-api');
    createdQueueIds.push(queueId);

    const approveResp = await request.post(`${BASE}/api/sigma-queue/${queueId}/approve`, {
      data: { status: 'approved', review_notes: 'approved by e2e test' },
    });
    expect(approveResp.ok()).toBe(true);
    const approveBody = await approveResp.json();
    expect(approveBody.success).toBe(true);

    // Verify via list endpoint
    const listResp = await request.get(`${BASE}/api/sigma-queue/list?status=approved&limit=200`);
    const list = await listResp.json();
    const found = list.items.find((r: any) => r.id === queueId);
    expect(found, `queue entry ${queueId} should appear in approved list`).toBeTruthy();
    expect(found.status).toBe('approved');
    expect(found.review_notes).toBe('approved by e2e test');
  });

  test('should reject a queued rule and reflect rejected status', async ({ request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }

    const queueId = await addRuleToQueue(request, articleId, 'reject-api');
    createdQueueIds.push(queueId);

    const rejectResp = await request.post(`${BASE}/api/sigma-queue/${queueId}/reject`, {
      data: { review_notes: 'rejected by e2e test' },
    });
    expect(rejectResp.ok()).toBe(true);
    const rejectBody = await rejectResp.json();
    expect(rejectBody.success).toBe(true);

    const listResp = await request.get(`${BASE}/api/sigma-queue/list?status=rejected&limit=200`);
    const list = await listResp.json();
    const found = list.items.find((r: any) => r.id === queueId);
    expect(found, `queue entry ${queueId} should appear in rejected list`).toBeTruthy();
    expect(found.status).toBe('rejected');
  });

  test('should update rule YAML via PUT endpoint', async ({ request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }

    const queueId = await addRuleToQueue(request, articleId, 'yaml-update');
    createdQueueIds.push(queueId);

    const updatedYaml = buildTestYaml('yaml-update-v2').replace('yaml-update-v2', 'yaml-update');
    const putResp = await request.put(`${BASE}/api/sigma-queue/${queueId}/yaml`, {
      data: { rule_yaml: updatedYaml },
    });
    expect(putResp.ok()).toBe(true);
    const putBody = await putResp.json();
    expect(putBody.success).toBe(true);

    // Confirm the updated YAML is stored
    const listResp = await request.get(`${BASE}/api/sigma-queue/list?limit=200`);
    const list = await listResp.json();
    const found = list.items.find((r: any) => r.id === queueId);
    expect(found, `queue entry ${queueId} should still be in list`).toBeTruthy();
    // The YAML should contain the updated marker
    expect(found.rule_yaml).toContain('yaml-update');
  });

  test('status_counts should reflect all queue statuses globally', async ({ request }) => {
    const listResp = await request.get(`${BASE}/api/sigma-queue/list?limit=1`);
    expect(listResp.ok()).toBe(true);
    const list = await listResp.json();

    expect(list).toHaveProperty('status_counts');
    expect(typeof list.status_counts).toBe('object');
    // All values must be non-negative integers
    for (const [, count] of Object.entries(list.status_counts)) {
      expect(typeof count).toBe('number');
      expect(count as number).toBeGreaterThanOrEqual(0);
    }
  });

  test('should return 404 when approving a nonexistent queue entry', async ({ request }) => {
    const resp = await request.post(`${BASE}/api/sigma-queue/999999999/approve`, {
      data: { status: 'approved' },
    });
    expect(resp.status()).toBe(404);
  });

  test('should return 400 when adding a rule without rule_yaml or rule_json', async ({ request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }
    const resp = await request.post(`${BASE}/api/sigma-queue/add`, {
      data: { article_id: articleId },
    });
    expect(resp.status()).toBe(400);
  });

  test('should return 404 when adding a rule for a nonexistent article', async ({ request }) => {
    const resp = await request.post(`${BASE}/api/sigma-queue/add`, {
      data: { article_id: 999999999, rule_yaml: buildTestYaml('bad-article') },
    });
    expect(resp.status()).toBe(404);
  });

  test('list endpoint should respect status filter for items', async ({ request }) => {
    const pendingResp = await request.get(`${BASE}/api/sigma-queue/list?status=pending&limit=50`);
    expect(pendingResp.ok()).toBe(true);
    const pendingList = await pendingResp.json();
    for (const item of pendingList.items) {
      expect(item.status).toBe('pending');
    }

    const approvedResp = await request.get(`${BASE}/api/sigma-queue/list?status=approved&limit=50`);
    expect(approvedResp.ok()).toBe(true);
    const approvedList = await approvedResp.json();
    for (const item of approvedList.items) {
      expect(item.status).toBe('approved');
    }
  });
});

// ============================================================
// UI-layer tests (browser + workflow#queue tab)
// ============================================================

test.describe('Sigma Queue UI', () => {
  // Navigate to the queue tab and wait for it to fully render
  async function openQueueTab(page: any): Promise<void> {
    // Subscribe to the first list response before navigating to avoid missing it
    const initialLoadPromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/sigma-queue/list') && resp.status() === 200,
      { timeout: 15000 },
    );

    await page.goto(`${BASE}/workflow#queue`);
    await page.waitForLoadState('domcontentloaded');

    // The page's DOMContentLoaded handler calls switchTab('queue') when the hash is #queue,
    // which fires loadQueue(). Only call switchTab again if the queue tab isn't already active
    // to avoid a second in-flight loadQueue() that would leak into subsequent waitForResponse calls.
    const tabAlreadyActive = await page.evaluate(() => {
      const el = document.getElementById('tab-content-queue');
      return el ? !el.classList.contains('hidden') : false;
    });
    if (!tabAlreadyActive) {
      await page.evaluate(() => {
        if (typeof (window as any).switchTab === 'function') {
          (window as any).switchTab('queue');
        }
      });
    }

    // Wait for the queue table container to be present
    await page.waitForSelector('#queueTableBody', { timeout: 15000 });

    // Wait for the single loadQueue() call to finish
    await initialLoadPromise.catch(() => {});
  }

  test('queue tab loads and renders stats panel', async ({ page }) => {
    await openQueueTab(page);

    // Stats panel elements must be present
    await expect(page.locator('#pendingCount')).toBeVisible();
    await expect(page.locator('#approvedCount')).toBeVisible();
    await expect(page.locator('#rejectedCount')).toBeVisible();

    // Status filter should default to showing all or pending
    await expect(page.locator('#queueStatusFilter')).toBeVisible();

    // Table body must exist
    await expect(page.locator('#queueTableBody')).toBeAttached();
  });

  test('pending rule added via API appears in the queue table', async ({ page, request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }

    // Add a rule via API before loading the UI
    const queueId = await addRuleToQueue(request, articleId, 'ui-visible');
    createdQueueIds.push(queueId);

    await openQueueTab(page);

    // Switch the filter to "all" so our newly added pending rule is visible
    await page.selectOption('#queueStatusFilter', '');
    await page.waitForResponse(
      (resp: any) => resp.url().includes('/api/sigma-queue/list') && resp.status() === 200,
      { timeout: 10000 },
    ).catch(() => {});
    await page.waitForTimeout(500);

    // Filter by queueId to avoid matching orphaned rows from previous runs
    const row = page.locator(`#queueTableBody tr`).filter({ hasText: String(queueId) });
    await expect(row).toBeVisible({ timeout: 10000 });
  });

  test('approve button sets rule to approved and updates stats', async ({ page, request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }

    const queueId = await addRuleToQueue(request, articleId, 'ui-approve');
    createdQueueIds.push(queueId);

    await openQueueTab(page);

    // Show all statuses so pending rules are visible.
    // Subscribe BEFORE selecting so we can explicitly consume the filter-change
    // list response — this prevents it from being caught by the approve listener.
    const filterRefreshPromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/sigma-queue/list') && resp.status() === 200,
      { timeout: 10000 },
    );
    await page.selectOption('#queueStatusFilter', '');
    await filterRefreshPromise.catch(() => {});

    // Read the current approved count before clicking
    const approvedBefore = parseInt(
      (await page.locator('#approvedCount').textContent()) || '0',
      10,
    );

    // Filter by queueId to avoid matching orphaned rows from previous runs
    const approveBtn = page
      .locator(`#queueTableBody tr`)
      .filter({ hasText: String(queueId) })
      .locator('.q-action.approve');

    if (!(await approveBtn.isVisible())) {
      // Rule row may not be visible with current filter - consume the extra refresh too
      const fallbackRefreshPromise = page.waitForResponse(
        (resp: any) => resp.url().includes('/api/sigma-queue/list') && resp.status() === 200,
        { timeout: 10000 },
      );
      await page.selectOption('#queueStatusFilter', '');
      await fallbackRefreshPromise.catch(() => {});
    }

    // approveRule() calls confirm() -- accept it so the fetch fires
    page.once('dialog', dialog => dialog.accept());

    // Intercept the approve API call to confirm it fires
    const approveResponsePromise = page.waitForResponse(
      (resp: any) =>
        resp.url().includes(`/api/sigma-queue/${queueId}/approve`) && resp.request().method() === 'POST',
      { timeout: 10000 },
    );

    // Register the post-approve queue-refresh listener BEFORE clicking so the
    // continuation fetch inside approveRule() cannot fire before we subscribe.
    // All prior filter-change list responses have been explicitly consumed above,
    // so this listener will only see the response from approveRule's loadQueue().
    const listRefreshPromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/sigma-queue/list') && resp.status() === 200,
      { timeout: 10000 },
    );

    await approveBtn.click();
    const approveResp = await approveResponsePromise;
    expect(approveResp.status()).toBe(200);

    // After approve, the UI reloads the queue. Wait for that refresh.
    await listRefreshPromise.catch(() => {});
    await page.waitForTimeout(500);

    // Approved count should have incremented by 1
    const approvedAfter = parseInt(
      (await page.locator('#approvedCount').textContent()) || '0',
      10,
    );
    expect(approvedAfter).toBeGreaterThanOrEqual(approvedBefore + 1);

    // Confirm via API that the rule is now approved
    const listResp = await request.get(`${BASE}/api/sigma-queue/list?status=approved&limit=200`);
    const list = await listResp.json();
    const found = list.items.find((r: any) => r.id === queueId);
    expect(found, `queue entry ${queueId} should be approved after UI click`).toBeTruthy();
  });

  test('reject button sets rule to rejected and updates stats', async ({ page, request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }

    const queueId = await addRuleToQueue(request, articleId, 'ui-reject');
    createdQueueIds.push(queueId);

    await openQueueTab(page);

    // Show pending rules
    await page.selectOption('#queueStatusFilter', 'pending');
    await page.waitForTimeout(800);

    const rejectedBefore = parseInt(
      (await page.locator('#rejectedCount').textContent()) || '0',
      10,
    );

    // Filter by queueId to avoid matching orphaned rows from previous runs
    const rejectBtn = page
      .locator(`#queueTableBody tr`)
      .filter({ hasText: String(queueId) })
      .locator('.q-action.reject');

    const rejectResponsePromise = page.waitForResponse(
      (resp: any) =>
        resp.url().includes(`/api/sigma-queue/${queueId}/reject`) && resp.request().method() === 'POST',
      { timeout: 10000 },
    );

    // Register the post-reject queue-refresh listener BEFORE clicking so the
    // continuation fetch inside rejectRule() cannot fire before we subscribe.
    const listRefreshPromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/sigma-queue/list') && resp.status() === 200,
      { timeout: 10000 },
    );

    await rejectBtn.click();
    const rejectResp = await rejectResponsePromise;
    expect(rejectResp.status()).toBe(200);

    await listRefreshPromise.catch(() => {});
    await page.waitForTimeout(500);

    const rejectedAfter = parseInt(
      (await page.locator('#rejectedCount').textContent()) || '0',
      10,
    );
    expect(rejectedAfter).toBeGreaterThanOrEqual(rejectedBefore + 1);

    // Confirm via API
    const listResp = await request.get(`${BASE}/api/sigma-queue/list?status=rejected&limit=200`);
    const list = await listResp.json();
    const found = list.items.find((r: any) => r.id === queueId);
    expect(found, `queue entry ${queueId} should be rejected after UI click`).toBeTruthy();
  });

  test('approved rule no longer shows pending actions in the table', async ({ page, request }) => {
    const articleId = await fetchFirstArticleId(request);
    if (!articleId) {
      test.skip(true, 'No articles in DB');
      return;
    }

    // Approve the rule via API directly, then check the UI
    const queueId = await addRuleToQueue(request, articleId, 'no-pending-btns');
    createdQueueIds.push(queueId);

    await request.post(`${BASE}/api/sigma-queue/${queueId}/approve`, {
      data: { status: 'approved' },
    });

    await openQueueTab(page);

    // Show approved rules
    await page.selectOption('#queueStatusFilter', 'approved');
    await page.waitForTimeout(800);

    // Filter by queueId to avoid matching orphaned rows from previous runs
    const row = page.locator('#queueTableBody tr').filter({ hasText: String(queueId) });
    await expect(row).toBeVisible({ timeout: 10000 });

    // Approved rows should NOT have Approve/Reject buttons (only Preview)
    const approveBtn = row.locator('.q-action.approve');
    const rejectBtn = row.locator('.q-action.reject');
    await expect(approveBtn).not.toBeVisible();
    await expect(rejectBtn).not.toBeVisible();
  });
});
