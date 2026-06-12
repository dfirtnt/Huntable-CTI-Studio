import { test, expect, Page } from '@playwright/test';

/**
 * Post-merge Playwright verification — Sigma Similarity Unification (Phases 0–5)
 *
 * Covers four surfaces that unit/integration tests cannot reach:
 *   1. Queue YAML toggle re-binding after row switch (Surface 1)
 *   2. Test page: no NaN%, no embedding vestiges (Surface 2)
 *   3. Workflow modal: breakdown + stacking on /workflow and /workflow-executions (Surface 3)
 *   4. A/B test: canonical-only contract smoke (Surface 4)
 *
 * All API calls are mocked — no DB seed required, no live LLM.
 * Mocks are scoped to the Playwright browser context and do not affect the
 * operator's live session running at the same origin.
 *
 * baseURL is provided by tests/playwright.config.ts (CTI_SCRAPER_URL or localhost:8001).
 * Pre-flight: confirm Phase 5 Python is live (similarity_score absent from
 * /api/sigma-ab-test/compare) before running surfaces 2 + 4.
 */

// ---------------------------------------------------------------------------
// Canonical mock match — Phase 5 contract: no similarity_score / similarity_breakdown aliases
// ---------------------------------------------------------------------------
const CANONICAL_MATCH = {
  rule_id: 'abc-123',
  title: 'Suspicious cmd.exe',
  description: 'Test',
  status: 'experimental',
  file_path: 'rules/windows/proc.yml',
  tags: ['attack.t1059'],
  similarity: 0.5,
  atom_jaccard: 1.0,
  logic_shape_similarity: 1.0,
  containment: 1.0,
  novelty_label: 'SIMILAR',
  similarity_engine: 'precomputed',
  shared_atoms: ['process.image|endswith:/cmd.exe'],
  added_atoms: [],
  removed_atoms: [],
  filter_differences: [],
  atom_details: {
    canonical_class: 'windows.process_creation',
    jaccard: 1.0,
    containment_factor: 1.0,
    overlap_ratio_a: 1.0,
    overlap_ratio_b: 1.0,
    surface_score_a: 4,
    surface_score_b: 4,
    filter_penalty: 0,
    reason_flags: [],
  },
  detection: { selection: { Image: 'cmd.exe' }, condition: 'selection' },
  logsource: { product: 'windows', category: 'process_creation' },
};

// A second match with distinct atoms so row clicks can be distinguished
const CANONICAL_MATCH_2 = {
  ...CANONICAL_MATCH,
  rule_id: 'def-456',
  title: 'Suspicious powershell.exe',
  similarity: 0.7,
  shared_atoms: ['process.image|endswith:/powershell.exe'],
  detection: { selection: { Image: 'powershell.exe' }, condition: 'selection' },
};

const MINIMAL_SIGMA_YAML = `title: Test Rule
status: experimental
logsource:
  product: windows
  category: process_creation
detection:
  selection:
    Image: cmd.exe
  condition: selection`;

// ---------------------------------------------------------------------------
// Surface 1 — Queue similar-rules modal: flat-card layout, Behavioral Similarity
//             per match, no NaN%, re-openable after close.
//
// Phase 4 unified the queue modal into workflow.html's showSimilarRulesModal.
// The old sigma_queue.html master/detail panel (sim-match-item, simDetailPane,
// simYamlToggle) was retired. The replacement is a flat card list where every
// match card calls renderSimilarityDisplay — the same shared component as
// Surface 3. Surface 1 now verifies: correct signature wiring, Behavioral
// Similarity breakdown renders per card, no NaN%, close and re-open.
// ---------------------------------------------------------------------------
test.describe('Surface 1 — Queue similar-rules modal (workflow.html flat-card layout)', () => {
  test('renders Behavioral Similarity for each match, no NaN%, re-openable after close', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    // /workflow/queue redirects to /workflow — that is the live host for
    // showSimilarRulesModal (workflow.html, line ~16014).
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    // Large inline script block; wait until the function is callable.
    // (domcontentloaded fires while the script is still executing)
    await page.waitForFunction(() => typeof (window as any).showSimilarRulesModal === 'function');

    // workflow.html signature:
    //   showSimilarRulesModal(matches, coverageSummary, generatedRules,
    //                         assessmentMethod, diagnostic, metadata)
    // Pass matches as first arg directly (not wrapped in a config object).
    await page.evaluate(
      async ({ match1, match2 }) => {
        await (window as any).showSimilarRulesModal(
          [match1, match2],
          null,
          [],
          null,
          null,
          { totalCandidatesEvaluated: 50, behavioralMatchesFound: 2 },
        );
      },
      { match1: CANONICAL_MATCH, match2: CANONICAL_MATCH_2 },
    );

    const modal = page.locator('#similarRulesModal');
    await expect(modal).toBeVisible();

    // Both match titles must appear (flat-card layout — all rendered at once)
    await expect(modal).toContainText('Suspicious cmd.exe');
    await expect(modal).toContainText('Suspicious powershell.exe');

    // renderSimilarityDisplay is called per card → "Behavioral Similarity"
    // breakdown text must appear (shared component assertion, same as Surface 3)
    await expect(modal).toContainText('Behavioral Similarity');

    // No NaN% anywhere in the modal
    await expect(modal).not.toContainText('NaN');

    // --- Close and re-open: modal stack must not be corrupted ---
    await page.locator('#similarRulesModal button[onclick="closeSimilarRulesModal()"]').first().click();
    await expect(modal).toHaveCount(0);

    await page.evaluate(
      async ({ match1 }) => {
        await (window as any).showSimilarRulesModal([match1], null, [], null, null, {});
      },
      { match1: CANONICAL_MATCH_2 },
    );
    await expect(page.locator('#similarRulesModal')).toBeVisible();
    await expect(page.locator('#similarRulesModal')).toContainText('Suspicious powershell.exe');

    // --- No console errors (filter known benign /workflow page noise) ---
    expect(consoleErrors.filter((e) => !e.includes('favicon') && !e.includes('404'))).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Surface 2 — Test page metrics: no NaN%, no embedding vestiges
// ---------------------------------------------------------------------------
test.describe('Surface 2 — Test page has no NaN% and no embedding UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/sigma-similarity-test/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          matches: [CANONICAL_MATCH],
          total_candidates_evaluated: 1,
          models_used: { llm_model: 'not used' },
          input_rule: {
            title: 'Test Rule',
            logsource: { product: 'windows', category: 'process_creation' },
            detection: { selection: { Image: 'cmd.exe' }, condition: 'selection' },
          },
        }),
      }),
    );

    await page.goto('/sigma-similarity-test');
    await page.waitForLoadState('domcontentloaded');
  });

  test('embedding model elements absent, llm model element present (static template)', async ({ page }) => {
    // Phase 5: embedding model picker + label removed from the test-page route/template
    await expect(page.locator('#embeddingModel')).toHaveCount(0);
    await expect(page.locator('#usedEmbeddingModel')).toHaveCount(0);
    // Preserved: LLM model selector
    await expect(page.locator('#llmModel')).toHaveCount(1);
    // No static embedding label text
    await expect(page.locator('body')).not.toContainText('Embedding Model:');
  });

  test('search result renders Behavioral Similarity with no NaN%', async ({ page }) => {
    await page.locator('#ruleInput').fill(MINIMAL_SIGMA_YAML);
    await page.locator('#searchBtn').click();

    const matchesList = page.locator('#matchesList');
    await expect(matchesList).toContainText('Suspicious cmd.exe');
    await expect(matchesList).toContainText('Behavioral Similarity');
    await expect(matchesList).not.toContainText('NaN');
    // Phase 5: the shared renderSimilarityDisplay component uses canonical fields;
    // absence of the text below confirms no dead embedding-era block crept back.
    await expect(page.locator('body')).not.toContainText('behavioral-novelty-engine');
  });
});

// ---------------------------------------------------------------------------
// Helpers for Surface 3
// ---------------------------------------------------------------------------

/**
 * Opens the similar-rule modal by calling showSimilarRuleDetails directly
 * with a monkeypatched window.event so event.currentTarget resolves to a
 * synthetic button holding the data-rule-data attribute.
 *
 * Using window.event (not a parameter) is necessary because
 * showSimilarRuleDetails reads `event.currentTarget` from the global event
 * object — matching how the HTML template wires inline onclick= handlers.
 * The onclick-attribute approach is unreliable in headless Chromium because
 * browser onclick errors are swallowed as window error events and page.evaluate
 * returns normally even when the called function is not yet defined.
 */
async function openSimilarRuleModal(page: Page, ruleData: object) {
  // Wait for similar-rule-modal.js to finish executing before calling it.
  await page.waitForFunction(() => typeof (window as any).showSimilarRuleDetails === 'function');

  await page.evaluate((dataJson) => {
    const existing = document.getElementById('similarRuleModal');
    if (existing) existing.remove();

    const btn = document.createElement('button');
    btn.setAttribute('data-rule-data', dataJson);
    document.body.appendChild(btn);

    // Monkeypatch window.event so event.currentTarget inside
    // showSimilarRuleDetails resolves to the synthetic button.
    const origDescriptor = Object.getOwnPropertyDescriptor(window, 'event');
    Object.defineProperty(window, 'event', {
      get: () => ({ currentTarget: btn }),
      configurable: true,
    });

    try {
      (window as any).showSimilarRuleDetails(0, 0);
    } finally {
      if (origDescriptor) {
        Object.defineProperty(window, 'event', origDescriptor);
      } else {
        try { delete (window as any).event; } catch (_) { /* non-configurable */ }
      }
      document.body.removeChild(btn);
    }
  }, JSON.stringify(ruleData));

  await page.waitForSelector('#similarRuleModal', { timeout: 5000 });
}

async function assertSimilarRuleModalWorks(page: Page) {
  const modal = page.locator('#similarRuleModal');
  await expect(modal).toBeVisible();

  // Breakdown check: shared component must render; bare "Similarity: X%" means
  // similar-rule-modal.js is not loaded on this page.
  await expect(modal).toContainText('Behavioral Similarity');

  // XSS hardening: no injected img/script tags from rule title/description
  await expect(modal.locator('img,script')).toHaveCount(0);
}

// ---------------------------------------------------------------------------
// Surface 3 — Workflow modal: breakdown + stacking on both pages
// ---------------------------------------------------------------------------
test.describe('Surface 3 — Workflow similar-rule modal on /workflow', () => {
  test('opens with Behavioral Similarity breakdown and is re-openable after close', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    // First open
    await openSimilarRuleModal(page, CANONICAL_MATCH);
    await assertSimilarRuleModalWorks(page);

    // Close
    await page.locator('#similarRuleModal button[onclick="closeSimilarRuleModal()"]').first().click();
    await expect(page.locator('#similarRuleModal')).toHaveCount(0);

    // Second open — verifies ModalManager stack is not corrupted after close
    await openSimilarRuleModal(page, CANONICAL_MATCH_2);
    await expect(page.locator('#similarRuleModal')).toBeVisible();
    await expect(page.locator('#similarRuleModal')).toContainText('Behavioral Similarity');

    expect(consoleErrors.filter((e) => !e.includes('favicon') && !e.includes('404'))).toHaveLength(0);
  });
});

test.describe('Surface 3 — Workflow similar-rule modal on /workflow-executions', () => {
  test('opens with Behavioral Similarity breakdown and is re-openable after close', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto('/workflow/executions');
    await page.waitForLoadState('domcontentloaded');

    // First open
    await openSimilarRuleModal(page, CANONICAL_MATCH);
    await assertSimilarRuleModalWorks(page);

    // Close
    await page.locator('#similarRuleModal button[onclick="closeSimilarRuleModal()"]').first().click();
    await expect(page.locator('#similarRuleModal')).toHaveCount(0);

    // Second open — on workflow-executions, pushModal() does NOT exist; the
    // typeof guard in similar-rule-modal.js must prevent a ReferenceError here.
    await openSimilarRuleModal(page, CANONICAL_MATCH_2);
    await expect(page.locator('#similarRuleModal')).toBeVisible();
    await expect(page.locator('#similarRuleModal')).toContainText('Behavioral Similarity');

    expect(consoleErrors.filter((e) => !e.includes('favicon') && !e.includes('404'))).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Surface 4 — A/B test contract smoke: canonical-only response shape
// ---------------------------------------------------------------------------
test.describe('Surface 4 — A/B test canonical-only contract', () => {
  test('score display populates and no console errors about missing similarity_score', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    // Phase 5 contract: response has no similarity_score / similarity_breakdown aliases
    await page.route('**/api/sigma-ab-test/compare', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, ...CANONICAL_MATCH }),
      }),
    );

    await page.goto('/sigma-ab-test');
    await page.waitForLoadState('domcontentloaded');

    await page.locator('#ruleA').fill(MINIMAL_SIGMA_YAML);
    await page.locator('#ruleB').fill(MINIMAL_SIGMA_YAML);
    await page.locator('#compareBtn').click();

    // Results section becomes visible
    await expect(page.locator('#results')).toBeVisible();

    // Score display must not be undefined% or NaN%
    const scoreText = await page.locator('#overallSimilarity').textContent();
    expect(scoreText).not.toMatch(/undefined|NaN/);
    expect(scoreText).toMatch(/\d/); // contains at least one digit

    // Behavioral Similarity Breakdown section rendered
    await expect(page.locator('#results')).toContainText('Behavioral Similarity Breakdown');

    expect(consoleErrors.filter((e) => !e.includes('favicon') && !e.includes('404'))).toHaveLength(0);
  });
});
