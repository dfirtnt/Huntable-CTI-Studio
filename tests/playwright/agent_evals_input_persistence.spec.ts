import { test, expect, Page } from '@playwright/test';

/**
 * The Agent Evals page has two numeric controls whose values must persist
 * globally across page reloads (and across subagent switches):
 *   - "Runs per article" (#evalMultiplier)   -> localStorage['eval.runs_per_article']
 *   - "Concurrency Throttle (s)"              -> localStorage['eval.concurrency_throttle_seconds']
 *
 * Persistence lets users keep a TPM-safe throttle setting after a fresh
 * reload rather than re-discovering it every time 429s appear.
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

const THROTTLE_KEY = 'eval.concurrency_throttle_seconds';
const MULTIPLIER_KEY = 'eval.runs_per_article';

async function gotoEvals(page: Page) {
  await page.goto(`${BASE}/mlops/agent-evals`);
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('#evalConcurrencyThrottle', { timeout: 10000 });
  await page.waitForSelector('#evalMultiplier', { timeout: 10000 });
}

test.beforeEach(async ({ page }) => {
  // Start every test from a known state so runs don't leak into each other.
  await page.goto(`${BASE}/mlops/agent-evals`);
  await page.evaluate(
    ({ t, m }) => {
      localStorage.removeItem(t);
      localStorage.removeItem(m);
    },
    { t: THROTTLE_KEY, m: MULTIPLIER_KEY },
  );
});

test('Concurrency Throttle input persists across reload', async ({ page }) => {
  await gotoEvals(page);

  // Default value rendered from the template is 5.
  const initial = await page.inputValue('#evalConcurrencyThrottle');
  expect(initial).toBe('5');

  // Set to 12 and fire change so the persist-on-change listener runs.
  await page.fill('#evalConcurrencyThrottle', '12');
  await page.dispatchEvent('#evalConcurrencyThrottle', 'change');

  // Value is now in localStorage under the global key.
  const stored = await page.evaluate((k) => localStorage.getItem(k), THROTTLE_KEY);
  expect(stored).toBe('12');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('#evalConcurrencyThrottle');

  const rehydrated = await page.inputValue('#evalConcurrencyThrottle');
  expect(rehydrated).toBe('12');
});

test('Runs per article input persists across reload', async ({ page }) => {
  await gotoEvals(page);

  const initial = await page.inputValue('#evalMultiplier');
  expect(initial).toBe('1');

  // The multiplier hooks 'input' (not 'change'), so fill() is enough.
  await page.fill('#evalMultiplier', '3');
  await page.dispatchEvent('#evalMultiplier', 'input');

  const stored = await page.evaluate((k) => localStorage.getItem(k), MULTIPLIER_KEY);
  expect(stored).toBe('3');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('#evalMultiplier');

  const rehydrated = await page.inputValue('#evalMultiplier');
  expect(rehydrated).toBe('3');
});

test('Persisted values survive a subagent switch (global scope)', async ({ page }) => {
  await gotoEvals(page);

  // Seed both values, then switch subagents.
  await page.fill('#evalConcurrencyThrottle', '8');
  await page.dispatchEvent('#evalConcurrencyThrottle', 'change');
  await page.fill('#evalMultiplier', '4');
  await page.dispatchEvent('#evalMultiplier', 'input');

  // Switch to a different subagent -- the page doesn't full-reload, so the
  // input values should simply remain (they live in a top-level control
  // panel, not inside the per-subagent results). If a future change ever
  // per-subagent-scopes either value, this test will catch it.
  const subagentSelect = page.locator('#subagentSelect');
  const optionCount = await subagentSelect.locator('option').count();
  if (optionCount > 1) {
    const currentValue = await subagentSelect.inputValue();
    const otherOption = await subagentSelect
      .locator(`option:not([value="${currentValue}"])`)
      .first()
      .getAttribute('value');
    if (otherOption) {
      await subagentSelect.selectOption(otherOption);
      await page.waitForTimeout(500);
    }
  }

  expect(await page.inputValue('#evalConcurrencyThrottle')).toBe('8');
  expect(await page.inputValue('#evalMultiplier')).toBe('4');

  // And they must still be in localStorage (so a *reload* after switching
  // continues to rehydrate correctly).
  const stored = await page.evaluate(
    ({ t, m }) => ({
      t: localStorage.getItem(t),
      m: localStorage.getItem(m),
    }),
    { t: THROTTLE_KEY, m: MULTIPLIER_KEY },
  );
  expect(stored.t).toBe('8');
  expect(stored.m).toBe('4');
});

test('Out-of-range stored throttle values are ignored on hydrate', async ({ page }) => {
  // Defensive: a stale or hand-edited localStorage entry outside the 0-60
  // range should be ignored (input shows the default 5) rather than crash
  // or clamp silently.
  await page.goto(`${BASE}/mlops/agent-evals`);
  await page.evaluate((k) => localStorage.setItem(k, '999'), THROTTLE_KEY);

  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('#evalConcurrencyThrottle');

  const val = await page.inputValue('#evalConcurrencyThrottle');
  expect(val).toBe('5');
});
