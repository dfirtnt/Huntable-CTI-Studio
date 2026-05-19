import { test, expect, Page } from '@playwright/test';

/**
 * Regression: the AI-Assisted Rule Enrichment modal must not render the
 * original rule twice.
 *
 * The modal has two regions that each render the original YAML:
 *   - the standalone "Original Rule:" input block  (#enrichOriginalSection)
 *   - the comparison view's left pane              (#enrichOriginalComparison)
 *
 * Before the fix, the success path revealed #enrichResult (which contains the
 * comparison view) but never hid #enrichOriginalSection, so the original rule
 * appeared twice in the scrollable modal. These tests pin the full invariant
 * across every state transition of the enrich modal:
 *   - first enrichment success            -> standalone hidden
 *   - toggling to the editor sub-view      -> standalone stays hidden
 *   - reopening the modal for a new rule   -> standalone shown again, reset
 *   - enrichment failure                   -> standalone stays visible (no dup)
 *   - "Enrich Further" (iterative)         -> standalone stays hidden
 *
 * `queue` / `currentRuleId` are lexically-scoped module bindings (not window
 * properties), so the supported way to populate them is to mock the queue
 * list endpoint and drive the real loadQueue() -> previewRule() ->
 * openEnrichModal() path. The enrichment + A/B-compare endpoints are mocked
 * so the test is deterministic and never depends on a live LLM.
 */

const RULE_ID = 999999;

const ORIGINAL_YAML = `title: Discovery Command Redirecting Output to Admin Share
id: null
status: experimental
detection:
  selection:
    CommandLine: 'cmd.exe /Q /c dir c:\\temp\\1.bat'
  condition: selection
`;

const ENRICHED_YAML = `title: Discovery Command Output Redirected to ADMIN Share
id: 4d9bd92a-2b38-4f0d-9051-1e00add18ba5
status: experimental
detection:
  selection:
    CommandLine: 'cmd.exe /Q /c dir c:\\temp\\1.bat'
  condition: selection
`;

async function mockEnrichmentEndpoints(page: Page) {
  await page.route('**/api/sigma-queue/**/enrich', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        enriched_yaml: ENRICHED_YAML,
        raw_response: ENRICHED_YAML,
      }),
    }),
  );
  // The success path auto-runs an A/B diff; mock it so it stays deterministic.
  await page.route('**/api/sigma-ab-test/compare', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        overall_similarity: 0.9,
        novelty_score: 0.1,
        novelty_label: 'Low novelty',
      }),
    }),
  );
  // Queue list -> loadQueue() assigns this to the lexically-scoped `queue`.
  await page.route('**/api/sigma-queue/list**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: RULE_ID,
            rule_yaml: ORIGINAL_YAML,
            status: 'pending',
            article_id: 1,
            article_title: 'Test Article',
            rule_metadata: { title: 'Test Rule' },
            created_at: new Date().toISOString(),
          },
        ],
        total: 1,
        limit: 25,
        status_counts: { pending: 1, approved: 0, rejected: 0, submitted: 0 },
      }),
    }),
  );
}

// Drive the real loadQueue -> previewRule -> openEnrichModal path against the
// mocked queue entry. Returns once the enrich modal is visible.
async function openEnrichModal(page: Page) {
  await page.evaluate(async (ruleId) => {
    const w = window as any;
    await w.loadQueue();
    // previewRule sets currentRuleId before any throwing render, so guard the
    // render and continue regardless.
    try {
      await w.previewRule(ruleId);
    } catch (_) {
      /* render is not relevant to this regression */
    }
    await w.openEnrichModal();
    // Force provider/model so enrichRule() does not early-return on the
    // "select a provider and model" validation. lmstudio needs no API key.
    const setSelect = (id: string, val: string) => {
      const sel = document.getElementById(id) as HTMLSelectElement | null;
      if (!sel) return;
      if (![...sel.options].some((o) => o.value === val)) {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        sel.appendChild(opt);
      }
      sel.value = val;
    };
    setSelect('enrichProviderSelect', 'lmstudio');
    setSelect('enrichModelSelect', 'test-model');
  }, RULE_ID);

  await expect(page.locator('#enrichModal')).toBeVisible();
}

test.describe('Sigma enrich modal — no duplicate Original Rule', () => {
  test.beforeEach(async ({ page }) => {
    await mockEnrichmentEndpoints(page);
    await page.goto('/workflow#queue');
    await page.waitForLoadState('domcontentloaded');
  });

  test('hides the standalone Original Rule once the comparison view is shown, and keeps it hidden in the editor sub-view', async ({ page }) => {
    await openEnrichModal(page);

    const originalSection = page.locator('#enrichOriginalSection');
    const enrichResult = page.locator('#enrichResult');

    // Before enrichment: standalone block visible, result hidden.
    await expect(originalSection).toBeVisible();
    await expect(enrichResult).toBeHidden();

    await page.locator('#enrichBtn').click();

    // Result + comparison view appear.
    await expect(enrichResult).toBeVisible();
    await expect(page.locator('#enrichComparisonView')).toBeVisible();

    // Regression assertion: the standalone Original Rule block must now be
    // hidden so the original is not rendered twice.
    await expect(originalSection).toBeHidden();

    // The original still lives inside the comparison view's left pane.
    await expect(page.locator('#enrichOriginalComparison')).toContainText(
      'Discovery Command Redirecting Output to Admin Share',
    );
    await expect(page.locator('#enrichedComparison')).toContainText(
      'Discovery Command Output Redirected to ADMIN Share',
    );

    // Toggling to the editor sub-view (toggleEnrichView) must not bring the
    // standalone block back — it stays hidden across both sub-views.
    await page.locator('#toggleViewBtn').click();
    await expect(page.locator('#enrichComparisonView')).toBeHidden();
    await expect(page.locator('#enrichedRuleYaml')).toBeVisible();
    await expect(originalSection).toBeHidden();
  });

  test('re-shows the standalone Original Rule when the modal is reopened', async ({ page }) => {
    // First pass: enrich, which hides the standalone block.
    await openEnrichModal(page);
    await page.locator('#enrichBtn').click();
    await expect(page.locator('#enrichResult')).toBeVisible();
    await expect(page.locator('#enrichOriginalSection')).toBeHidden();

    // Close and reopen — the input block must return and the stale result
    // must be reset.
    await page.evaluate(() => (window as any).closeEnrichModal());
    await openEnrichModal(page);

    await expect(page.locator('#enrichOriginalSection')).toBeVisible();
    await expect(page.locator('#enrichResult')).toBeHidden();
  });

  test('keeps the standalone Original Rule visible when enrichment fails (no result, no duplicate)', async ({ page }) => {
    // Override the success route with a failure (last-registered route wins).
    await page.route('**/api/sigma-queue/**/enrich', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Upstream model error' }),
      }),
    );

    await openEnrichModal(page);

    const originalSection = page.locator('#enrichOriginalSection');
    await expect(originalSection).toBeVisible();

    await page.locator('#enrichBtn').click();

    // Failure path: error shown, result/comparison never revealed, and the
    // standalone original stays visible so the user does not lose their input.
    await expect(page.locator('#enrichError')).toBeVisible();
    await expect(page.locator('#enrichResult')).toBeHidden();
    await expect(originalSection).toBeVisible();
  });

  test('keeps the standalone Original Rule hidden through an "Enrich Further" iteration', async ({ page }) => {
    await openEnrichModal(page);

    await page.locator('#enrichBtn').click();
    await expect(page.locator('#enrichResult')).toBeVisible();
    await expect(page.locator('#enrichOriginalSection')).toBeHidden();

    // enrichRuleFurther() opens a window.prompt() for extra instructions;
    // a real user types here. Playwright auto-dismisses dialogs (returns
    // null, which aborts the flow), so accept it with instruction text.
    page.once('dialog', (dialog) => dialog.accept('add MITRE technique mapping'));

    // Iterative enrichment goes through the separate enrichRuleFurther()
    // success path, which must also leave the standalone block hidden.
    await page.locator('#enrichFurtherBtn').click();
    await expect(page.locator('#enrichIterationInfo')).toContainText(
      'iteration #2',
    );
    await expect(page.locator('#enrichOriginalSection')).toBeHidden();
    await expect(page.locator('#enrichResult')).toBeVisible();
  });
});
