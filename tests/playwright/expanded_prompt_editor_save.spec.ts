/**
 * Regression test: expanded prompt editor save flow.
 *
 * Before the fix, saveExpandedPrompt() relayed values through the inline
 * agent-card textarea ({prefix}-prompt-system-2) via a 200ms setTimeout.
 * If the inline card wasn't in edit mode when Save was clicked, saveAgentPrompt2()
 * would fire "Prompt elements not found" and silently abort without saving.
 *
 * After the fix, saveExpandedPrompt() reads directly from the modal textareas
 * and passes values as overrides to saveAgentPrompt2(), removing the DOM relay
 * and the race condition entirely.
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function navigateToConfig(page: any) {
  await page.goto(`${BASE}/workflow#config`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.evaluate(() => {
    if (typeof (window as any).switchTab === 'function') (window as any).switchTab('config');
  });
  await page.waitForSelector('#workflowConfigForm', { timeout: 10_000 });
  await page.waitForTimeout(1000);
}

/** Open the expanded editor for a given agent via JS — avoids panel visibility issues. */
async function openExpandedEditor(page: any, agentName: string) {
  await page.evaluate((name: string) => {
    if (typeof (window as any).openExpandedPromptEditor === 'function') {
      (window as any).openExpandedPromptEditor(name);
    }
  }, agentName);
  await page.locator('#prompt-expanded-overlay').waitFor({ state: 'visible', timeout: 5000 });
  await page.waitForTimeout(300);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Expanded prompt editor — save regression', () => {
  test.beforeEach(async ({ page }) => {
    await navigateToConfig(page);
  });

  /**
   * Core regression: save works even when the inline agent card is in VIEW
   * mode (i.e. {prefix}-prompt-system-2 textarea does NOT exist in DOM).
   *
   * Sequence:
   *   1. Open expanded editor via JS (inline card stays in view mode)
   *   2. Click "Edit" inside the modal
   *   3. Edit the system prompt
   *   4. Click "Save Prompt"
   *   5. Assert PUT /api/workflow/config/prompts was called with the new text
   */
  test('saves RankAgent prompt from expanded editor without inline textarea present', async ({ page }) => {
    // Intercept PUT before opening the editor
    const saveRequests: any[] = [];
    page.on('request', (req: any) => {
      if (req.url().includes('/api/workflow/config/prompts') && req.method() === 'PUT') {
        saveRequests.push(req);
      }
    });

    // Confirm inline edit textarea does NOT exist (card is in view mode)
    const inlineTextareaExists = await page.evaluate(() =>
      !!document.getElementById('rankagent-prompt-system-2')
    );
    expect(inlineTextareaExists).toBe(false);

    // Open expanded editor directly via JS — no panel expansion needed
    await openExpandedEditor(page, 'RankAgent');

    // Modal opens in read-only mode — click Edit
    const editBtn = page.locator('#prompt-exp-edit-btn');
    await editBtn.waitFor({ state: 'visible', timeout: 3000 });
    await editBtn.click();
    await page.waitForTimeout(300);

    // Save button is now visible
    const saveBtn = page.locator('#prompt-exp-save-btn');
    await saveBtn.waitFor({ state: 'visible', timeout: 3000 });

    // Edit the system prompt
    const sysTA = page.locator('#prompt-exp-system');
    await sysTA.fill('REGRESSION TEST CONTENT — expanded editor save');

    // Click Save — previously silently failed when inline textarea was absent
    // (editExpandedPrompt re-renders the inline panel as a side effect of clicking Edit,
    // so the textarea may now exist — but saveExpandedPrompt no longer relies on it)
    const saveResponsePromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/workflow/config/prompts') && resp.request().method() === 'PUT',
      { timeout: 10_000 }
    );
    await saveBtn.click();
    const saveResponse = await saveResponsePromise;

    // PUT must have gone through and succeeded
    expect(saveResponse.status()).toBe(200);

    // Payload must contain our edited text
    const body = JSON.parse(saveRequests[saveRequests.length - 1].postData() || '{}');
    expect(body.agent_name).toBe('RankAgent');
    const promptStr = typeof body.prompt === 'string' ? body.prompt : JSON.stringify(body.prompt);
    expect(promptStr).toContain('REGRESSION TEST CONTENT');

    // Modal should be closed after save
    const overlayVisible = await page.locator('#prompt-expanded-overlay').isVisible().catch(() => false);
    expect(overlayVisible).toBe(false);
  });

  /**
   * Extraction agent (CmdlineExtract): same regression scenario.
   * The inline card stays in view mode; save must go through via the overrides path.
   */
  test('saves CmdlineExtract prompt from expanded editor without inline textarea present', async ({ page }) => {
    const saveRequests: any[] = [];
    page.on('request', (req: any) => {
      if (req.url().includes('/api/workflow/config/prompts') && req.method() === 'PUT') {
        saveRequests.push(req);
      }
    });

    // Inline textarea must not exist yet
    const inlineAbsent = await page.evaluate(() =>
      !document.getElementById('cmdlineextract-prompt-system-2')
    );
    expect(inlineAbsent).toBe(true);

    await openExpandedEditor(page, 'CmdlineExtract');

    const editBtn = page.locator('#prompt-exp-edit-btn');
    await editBtn.waitFor({ state: 'visible', timeout: 3000 });
    await editBtn.click();
    await page.waitForTimeout(300);

    // For extraction agents the system prompt is a JSON blob — just verify the
    // PUT fires (not silently aborted). Restore original value after filling.
    const sysTA = page.locator('#prompt-exp-system');
    const originalVal = await sysTA.inputValue();
    await sysTA.fill(originalVal || '{}');

    const saveBtn = page.locator('#prompt-exp-save-btn');
    const saveResponsePromise = page.waitForResponse(
      (resp: any) => resp.url().includes('/api/workflow/config/prompts') && resp.request().method() === 'PUT',
      { timeout: 10_000 }
    );
    await saveBtn.click();
    const saveResponse = await saveResponsePromise;

    // Key assertion: save request was fired (not silently aborted)
    expect(saveRequests.length).toBeGreaterThan(0);
    expect(saveResponse.status()).toBe(200);

    const body = JSON.parse(saveRequests[saveRequests.length - 1].postData() || '{}');
    expect(body.agent_name).toBe('CmdlineExtract');
  });

  /**
   * Unit-level: verify saveExpandedPrompt passes systemOverride directly to
   * saveAgentPrompt2 rather than relying on DOM relay. Intercept the call and
   * inspect the arguments — this would have caught the original bug.
   */
  test('saveExpandedPrompt passes systemOverride directly to saveAgentPrompt2', async ({ page }) => {
    await openExpandedEditor(page, 'RankAgent');

    // Click Edit so save button is visible and modal is editable
    await page.locator('#prompt-exp-edit-btn').click();
    await page.waitForTimeout(300);

    // Set a known value
    await page.locator('#prompt-exp-system').fill('UNIT TEST VALUE XYZ');

    // Intercept saveAgentPrompt2 to capture its arguments before it fires
    const capturedArgs = await page.evaluate(() => {
      return new Promise<{ agentName: string; overrides: any }>((resolve) => {
        const orig = (window as any).saveAgentPrompt2;
        (window as any).saveAgentPrompt2 = function(agentName: string, overrides: any = {}) {
          resolve({ agentName, overrides });
          // Skip the real save — we only need the call signature
          return Promise.resolve();
        };
        if (typeof (window as any).saveExpandedPrompt === 'function') {
          (window as any).saveExpandedPrompt();
        }
      });
    });

    // systemOverride must be populated directly from the modal textarea
    expect(capturedArgs.overrides).toBeDefined();
    expect('systemOverride' in capturedArgs.overrides).toBe(true);
    expect(capturedArgs.overrides.systemOverride).toBe('UNIT TEST VALUE XYZ');
    // agentName must be passed through correctly
    expect(capturedArgs.agentName).toBe('RankAgent');
  });
});
