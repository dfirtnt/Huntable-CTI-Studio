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

import { TEST_SEED_MARKER } from './workflow-config-snapshot';
const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Post-load settle: select the config tab and wait for the form to render. */
async function settleConfigPage(page: any) {
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.evaluate(() => {
    if (typeof (window as any).switchTab === 'function') (window as any).switchTab('config');
  });
  await page.waitForSelector('#workflowConfigForm', { timeout: 10_000 });
  await page.waitForTimeout(1000);
}

async function navigateToConfig(page: any) {
  await page.goto(`${BASE}/workflow#config`);
  await settleConfigPage(page);
}

/**
 * Full page reload + settle. Used after seeding a prompt via the API so the
 * in-page `agentPrompts` global picks up the new value. `page.goto()` with the
 * same `#config` URL can resolve as a same-document navigation and skip the
 * reload entirely, so reload() is used explicitly.
 */
async function reloadConfig(page: any) {
  await page.reload();
  await settleConfigPage(page);
}

// ---------------------------------------------------------------------------
// Shared-DB hermeticity
//
// This spec runs against the live dev app on :8001, whose config is shared with
// every other Playwright project. The agent-config suite mutates that config —
// notably agent_config_presets.spec.ts, whose preset-import test restores via a
// partial `PUT /api/workflow/config` and leaves `agent_prompts.CmdlineExtract.prompt`
// as an empty string.
//
// An empty stored prompt is fatal to this spec: the expanded editor loads "" into
// its system textarea, and saveExpandedPrompt() runs _collectPromptIssues() before
// firing the PUT. An empty (or `{}`) envelope produces hard errors — missing
// role/system, instructions and json_example per the Extractor Contract — so the
// save is correctly refused and no request is ever sent. The test then times out
// waiting for a PUT that will never happen.
//
// So the tests below seed the prompt state they depend on rather than inheriting
// whatever the previous suite left behind, and restore the prior value afterwards.
// Same shared-DB hardening rationale as commits 22a05011 and 9638731f.
// ---------------------------------------------------------------------------

/**
 * Minimal CmdlineExtract system-prompt envelope that clears every hard-fail check
 * in _collectPromptIssues(): non-empty role (sec 1), non-empty instructions (sec 2),
 * and a json_example (sec 4) whose items carry all required traceability fields
 * (secs 3-4). Warn-level issues are expected and do not block a save — only errors do.
 *
 * Deliberately self-contained rather than read from config/presets/, so the test
 * cannot start failing because a shipped preset drifted.
 */
const CMDLINE_SEED_PROMPT = JSON.stringify({
  role: `${TEST_SEED_MARKER}. Extracts Windows command-line observables from articles.`,
  task: 'Extract literal, copy-pasteable Windows command lines.',
  json_example: JSON.stringify({
    commands: [
      {
        value: 'whoami /priv',
        source_evidence: 'seed evidence',
        extraction_justification: 'seed justification',
        confidence_score: 0.9,
      },
    ],
  }),
  instructions: `${TEST_SEED_MARKER} instructions. Return ONLY valid JSON.`,
});

/**
 * Read one agent's stored prompt record, for snapshot/restore.
 *
 * Retries on the same transient 404 as putPromptWithRetry: a read that lands in
 * another writer's deactivate/insert window sees no active config. Failing to
 * retry here is worse than a flaky assertion — an empty snapshot would make the
 * `finally` block "restore" the agent to a blank prompt.
 */
async function readAgentPrompt(page: any, agentName: string, attempts = 5): Promise<any> {
  for (let i = 0; i < attempts; i++) {
    const res = await page.request.get(`${BASE}/api/workflow/config/prompts`);
    if (res.ok()) {
      const body = await res.json().catch(() => ({}));
      return (body.prompts || {})[agentName] || {};
    }
    await page.waitForTimeout(300 * (i + 1));
  }
  throw new Error(`could not read stored prompt for ${agentName} (active config unavailable)`);
}

/**
 * PUT a prompt payload, retrying transient shared-DB contention.
 *
 * `update_agent_prompts` deactivates the current config row before inserting the
 * replacement, so a request that lands inside another writer's window finds no
 * active config and returns 404. With four Playwright workers hitting one uvicorn
 * that is routine, and it is not what any test here is asserting — so retry rather
 * than fail. Anything other than a 404 (e.g. a 400 for a malformed envelope) is a
 * real error and is returned immediately.
 */
async function putPromptWithRetry(page: any, data: Record<string, unknown>, attempts = 5) {
  let res: any;
  for (let i = 0; i < attempts; i++) {
    res = await page.request.put(`${BASE}/api/workflow/config/prompts`, { data });
    if (res.ok() || res.status() !== 404) return res;
    await page.waitForTimeout(300 * (i + 1));
  }
  return res;
}

/**
 * Write an extraction agent's stored prompt (legacy single-field `prompt` shape,
 * which the backend requires to be a valid JSON envelope).
 */
async function writeExtractionPrompt(page: any, agentName: string, prompt: string) {
  return putPromptWithRetry(page, {
    agent_name: agentName,
    prompt,
    instructions: null,
    change_description: null,
  });
}

/**
 * Restore an extraction agent's prompt captured by readAgentPrompt().
 *
 * Writes, reads back, and retries until the stored value matches. A single PUT is
 * not enough: `update_agent_prompts` read-modify-writes the whole `agent_prompts`
 * blob into a new config row, so a concurrent PUT for a *different* agent that
 * read the same starting row will write its own copy and drop this restore
 * (lost update). Reading back is the only way to know the restore actually stuck.
 *
 * An empty original cannot be written back — the backend rejects a non-JSON
 * `prompt` for extraction agents with a 400 — so in that case the seed is left in
 * place. A valid envelope is strictly closer to a working config than the empty
 * string that could not be restored anyway.
 */
async function restoreExtractionPrompt(page: any, agentName: string, record: any, attempts = 6) {
  const original = record?.prompt || '';
  if (!original) return true;
  for (let i = 0; i < attempts; i++) {
    await writeExtractionPrompt(page, agentName, original).catch(() => {});
    await page.waitForTimeout(200 * (i + 1));
    const current = await readAgentPrompt(page, agentName).catch(() => null);
    if (current && current.prompt === original) return true;
  }
  // Cleanup failure should not fail an otherwise-passing test, but must not be silent.
  console.warn(`[expanded_prompt_editor_save] could not restore ${agentName} prompt after ${attempts} attempts`);
  return false;
}

/** Write a canonical ({system, user}) agent prompt — RankAgent, SigmaAgent. */
async function writeCanonicalPrompt(page: any, agentName: string, system: string, user: string) {
  return putPromptWithRetry(page, {
    agent_name: agentName,
    system,
    user,
    instructions: null,
    change_description: null,
  });
}

/**
 * Restore a canonical-shape agent's prompt, verifying the write stuck.
 * Same lost-update hazard as restoreExtractionPrompt — see the note there.
 */
async function restoreCanonicalPrompt(page: any, agentName: string, record: any, attempts = 6) {
  const system = record?.system ?? record?.prompt ?? '';
  const user = record?.user ?? '';
  for (let i = 0; i < attempts; i++) {
    await writeCanonicalPrompt(page, agentName, system, user).catch(() => {});
    await page.waitForTimeout(200 * (i + 1));
    const current = await readAgentPrompt(page, agentName).catch(() => null);
    if (current && (current.system ?? current.prompt ?? '') === system) return true;
  }
  console.warn(`[expanded_prompt_editor_save] could not restore ${agentName} prompt after ${attempts} attempts`);
  return false;
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
  // NOTE on cleanup durability: the restores below are best-effort, not guaranteed.
  // `update_agent_prompts` read-modify-writes the whole agent_prompts blob into a new
  // config row, and the config autosave in workflow.html writes back the browser's
  // in-memory copy — so another spec whose page loaded while the seed was live can
  // resurrect the seed after this file has already restored. That is a server-side
  // lost update; a test cannot close it. Deliberately left in `fullyParallel` mode:
  // running this file sequentially keeps the seed live for longer in wall-clock terms
  // and measurably increases the leak rate rather than reducing it.

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
    // This test overwrites RankAgent's live system prompt with its marker string.
    // Snapshot it first and put it back in the `finally` below, so a run against
    // the shared dev app does not leave "REGRESSION TEST CONTENT" as the operator's
    // configured RankAgent prompt. No seeding is needed: the test fills its own
    // plain-text value, which never trips the validation gate.
    const originalRank = await readAgentPrompt(page, 'RankAgent');

    try {
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
      // saveAgentPrompt2 uses the canonical {system, user} shape for non-extraction agents
      // (RankAgent). The legacy single-field `prompt` shape is only used for extraction
      // agents. Check both to be robust against future shape changes.
      const promptStr = body.system ?? body.prompt ?? '';
      expect(promptStr).toContain('REGRESSION TEST CONTENT');

      // Modal should be closed after save
      const overlayVisible = await page.locator('#prompt-expanded-overlay').isVisible().catch(() => false);
      expect(overlayVisible).toBe(false);
    } finally {
      // RankAgent uses the canonical {system, user} shape. Unlike the extraction
      // path there is no JSON validation, so an empty original restores cleanly.
      await restoreCanonicalPrompt(page, 'RankAgent', originalRank);
    }
  });

  /**
   * Extraction agent (CmdlineExtract): same regression scenario.
   * The inline card stays in view mode; save must go through via the overrides path.
   */
  test('saves CmdlineExtract prompt from expanded editor without inline textarea present', async ({ page }) => {
    // Hermetic setup: seed a contract-valid envelope rather than inheriting
    // whatever the agent-config suite left in the shared config. Without this the
    // stored prompt can be "", the validation gate refuses the save, and the
    // waitForResponse below times out. See the "Shared-DB hermeticity" note above.
    const originalRecord = await readAgentPrompt(page, 'CmdlineExtract');

    // Everything after the snapshot — including the seed itself — runs inside the
    // try, so a failure while seeding or reloading still triggers the restore below.
    // (Seeding outside the try leaks the seed into the shared config whenever the
    // seed PUT reports a failure after the server has already applied it.)
    try {
      const seedRes = await writeExtractionPrompt(page, 'CmdlineExtract', CMDLINE_SEED_PROMPT);
      expect(seedRes.ok(), 'failed to seed CmdlineExtract prompt').toBeTruthy();
      await reloadConfig(page);

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
      // PUT fires (not silently aborted). Re-fill with the same value so the save
      // is a no-op content-wise.
      const sysTA = page.locator('#prompt-exp-system');
      const originalVal = await sysTA.inputValue();
      // Assert the seed actually reached the editor. Previously this fell back to
      // `originalVal || '{}'`, which silently turned an empty stored prompt into an
      // envelope that fails validation — converting a config problem into an opaque
      // 10s timeout on the save below.
      expect(
        originalVal,
        'expanded editor loaded an empty CmdlineExtract prompt — the seed did not take ' +
          '(a concurrent agent-config run may have overwritten the shared config)'
      ).not.toBe('');
      await sysTA.fill(originalVal);

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
    } finally {
      await restoreExtractionPrompt(page, 'CmdlineExtract', originalRecord);
    }
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
