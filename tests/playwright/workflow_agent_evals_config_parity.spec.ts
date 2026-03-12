import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';
const WORKFLOW_CONFIG_URL = `${BASE}/workflow#config`;
const AGENT_EVALS_URL = `${BASE}/mlops/agent-evals`;

function normalizeDisplayText(s: string): string {
  return s
    .replace(/\s+/g, ' ')
    .replace(/\s*:\s*/g, ': ')
    .trim();
}

function extractVersion(text: string): number | null {
  const m = text.match(/Version:\s*(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

function extractThresholds(text: string): { ranking?: string; junk?: string; similarity?: string } {
  const normalized = normalizeDisplayText(text);
  return {
    ranking: normalized.match(/Ranking Threshold:\s*([\d.]+)/)?.[1],
    junk: normalized.match(/Junk Filter Threshold:\s*([\d.]+)/)?.[1],
    similarity: normalized.match(/Similarity Threshold:\s*([\d.]+)/)?.[1],
  };
}

/**
 * Read-only: assert Workflow and Agent-evals "Current Configuration" show the same status.
 * No config mutation.
 */
test.describe('Workflow / Agent-evals config display parity', () => {
  test('Workflow and Agent-evals show same config status (version and thresholds)', async ({ page }) => {
    // Load Workflow config tab and wait for config display
    await page.goto(WORKFLOW_CONFIG_URL);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => {
      if (typeof switchTab === 'function') switchTab('config');
    });
    await page.waitForTimeout(1000);
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForFunction(
      () => typeof currentConfig !== 'undefined' && currentConfig !== null,
      { timeout: 10000 }
    );
    await page.waitForFunction(
      () => {
        const el = document.getElementById('configDisplay');
        return el && el.innerText.includes('Version') && /Version:\s*\d+/.test(el.innerText);
      },
      { timeout: 10000 }
    );

    const workflowDisplay = page.locator('#configDisplay');
    const workflowText = normalizeDisplayText(await workflowDisplay.innerText());
    const workflowVersion = extractVersion(workflowText);
    const workflowThresholds = extractThresholds(workflowText);

    expect(workflowVersion).not.toBeNull();
    expect(workflowText).toContain('Ranking Threshold');
    expect(workflowText).toContain('Junk Filter Threshold');
    expect(workflowText).toContain('Similarity Threshold');
    expect(workflowText).toContain('Updated');

    // Load Agent-evals and wait for config display (loadActiveConfig fetches /api/workflow/config)
    await page.goto(AGENT_EVALS_URL);
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('#configDisplay', { timeout: 10000 });
    await page.waitForFunction(
      () => {
        const el = document.getElementById('configDisplay');
        return el && el.innerText.includes('Version') && /Version:\s*\d+/.test(el.innerText);
      },
      { timeout: 15000 }
    );

    const evalsDisplay = page.locator('#configDisplay');
    const evalsText = normalizeDisplayText(await evalsDisplay.innerText());
    const evalsVersion = extractVersion(evalsText);
    const evalsThresholds = extractThresholds(evalsText);

    expect(evalsVersion).not.toBeNull();
    expect(evalsVersion).toBe(workflowVersion);
    expect(evalsThresholds.ranking).toBe(workflowThresholds.ranking);
    expect(evalsThresholds.junk).toBe(workflowThresholds.junk);
    expect(evalsThresholds.similarity).toBe(workflowThresholds.similarity);
    expect(evalsText).toContain('Ranking Threshold');
    expect(evalsText).toContain('Junk Filter Threshold');
    expect(evalsText).toContain('Similarity Threshold');
  });
});
