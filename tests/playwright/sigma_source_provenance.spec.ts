import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test('source-provided rule shows escaped provenance and no approval control', async ({ page }) => {
  const yaml = `title: Publisher Detection
id: 11111111-1111-1111-1111-111111111111
author: Publisher
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    Image|endswith: '\\publisher.exe'
  condition: selection
level: high
`;
  await page.route('**/api/sigma-queue/list**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [{
          id: 4242,
          article_id: 989,
          article_title: 'Publisher article',
          workflow_execution_id: null,
          rule_yaml: yaml,
          rule_metadata: { title: 'Publisher Detection' },
          rule_origin: 'source_provided',
          source_url: 'https://publisher.example/article',
          source_rule_id: '11111111-1111-1111-1111-111111111111',
          source_content_sha256: 'a'.repeat(64),
          source_extraction_start: 100,
          source_extraction_end: 400,
          declared_license: null,
          license_evidence: null,
          attribution: '<img src=x onerror="window.__sourceXss=true">Publisher',
          source_permission_granted_by: null,
          source_permission_basis: null,
          source_permission_granted_at: null,
          delivery_eligible: false,
          delivery_eligibility_reason: 'No explicit source license or permission is recorded.',
          similarity_scores: [],
          max_similarity: 0,
          behavioral_matches_found: 0,
          total_candidates_evaluated: 0,
          status: 'local_review_only',
          reviewed_by: null,
          review_notes: null,
          pr_submitted: false,
          pr_url: null,
          created_at: '2026-09-24T18:00:00',
          reviewed_at: null,
        }],
        total: 1,
        limit: 50,
        offset: 0,
        status_counts: { local_review_only: 1 },
      }),
    });
  });

  await page.goto(`${BASE}/workflow#queue`);
  await page.waitForSelector('#queue-row-4242');
  await expect(page.locator('#localReviewOnlyCount')).toHaveText('1');
  await expect(page.locator('#queue-row-4242')).toContainText('Source Provided');
  await expect(page.locator('#queue-row-4242 .q-action.approve')).toHaveCount(0);

  await page.locator('#queue-row-4242 .q-action.preview').click();
  const provenance = page.locator('[data-testid="source-rule-provenance"]');
  await expect(provenance).toBeVisible();
  await expect(provenance).toContainText('Publisher-authored source rule');
  await expect(provenance).toContainText('Local review only');
  await expect(provenance).toContainText('<img src=x');
  await expect(provenance.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__sourceXss)).toBeUndefined();
  await expect(page.getByRole('button', { name: 'Create Editable Copy' }).first()).toBeVisible();
  await expect(page.locator('#actionButtons').getByRole('button', { name: 'Approve' })).toHaveCount(0);
});
