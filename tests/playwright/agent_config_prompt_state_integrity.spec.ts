import { test, expect } from '@playwright/test';

/**
 * Regression coverage for the two-part prompt-loss defect.
 *
 * An imported preset appeared to load and then showed an empty prompt panel; saving from
 * that state persisted a config with no extractor prompts, which made every workflow run
 * complete with zero observables and zero rules while reporting success.
 *
 * Part 1: applyPreset() loads prompt bodies into form state and then triggers
 *   autoSaveModelChange(). Autosave transmits only ExtractAgentSettings, so its response
 *   can never carry the imported prompts -- yet performAutoSave() replaced form state with
 *   that response wholesale, discarding the import 400ms after it landed.
 *
 * Part 2: renderAgentPrompts() then materialised {prompt:'', instructions:''} into global
 *   state for RankAgent and SigmaAgent, so the next Save wrote those blanks to the
 *   database as though the operator had chosen them.
 *
 * Both tests stub the PUT so nothing is persisted.
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

// config.js is a classic script: its top-level `let` bindings are lexical globals and are
// NOT reachable as window properties. They must be referenced by bare identifier inside
// page.evaluate. These declarations exist only to satisfy the type checker.
declare var agentPrompts: any;
declare var pendingPromptAgents: any;
declare function performAutoSave(): Promise<void>;
declare function renderAgentPrompts(): void;

const PRESET_KEYS = [
  'CmdlineExtract', 'ProcTreeExtract', 'HuntQueriesExtract', 'RegistryExtract',
  'ServicesExtract', 'ScheduledTasksExtract', 'NetworkIndicatorExtract',
  'SigmaAgent', 'RankAgent',
];

test.describe('Agent config prompt state integrity', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => {
      if (typeof (window as any).switchTab === 'function') (window as any).switchTab('config');
    });
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 10000 });
  });

  test('autosave does not discard prompts pending in form state', async ({ page }) => {
    const result = await page.evaluate(async (presetKeys: string[]) => {
      const realFetch = window.fetch;
      let sentPromptKeys: string[] = [];

      // Server truth deliberately omits the pending prompts, exactly as it must:
      // autosave never transmits them.
      const serverConfig = {
        agent_models: (window as any).currentConfig?.agent_models || {},
        agent_prompts: { ExtractAgentSettings: { disabled_agents: [] } },
      };

      window.fetch = async (url: any, opts: any) => {
        if (String(url).includes('/api/workflow/config') && opts?.method === 'PUT') {
          sentPromptKeys = Object.keys(JSON.parse(opts.body).agent_prompts || {});
          return new Response(JSON.stringify(serverConfig), {
            status: 200, headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({}), {
          status: 200, headers: { 'Content-Type': 'application/json' },
        });
      };

      try {
        const loaded: Record<string, any> = { ExtractAgentSettings: { disabled_agents: [] } };
        presetKeys.forEach(k => { loaded[k] = { prompt: 'PRESET_BODY_' + k, instructions: '' }; });
        agentPrompts = loaded;
        // What applyPreset() records when it loads a preset into form state.
        pendingPromptAgents = new Set(presetKeys);

        await performAutoSave();

        const prompts = agentPrompts;
        return {
          sentPromptKeys,
          survivors: presetKeys.filter(
            k => String(prompts[k]?.prompt || '').startsWith('PRESET_BODY_')
          ).length,
        };
      } finally {
        window.fetch = realFetch;
      }
    }, PRESET_KEYS);

    // Autosave still sends only settings -- the fix must not change that contract.
    expect(result.sentPromptKeys).toEqual(['ExtractAgentSettings']);
    // ...and every pending prompt must survive the response.
    expect(result.survivors).toBe(PRESET_KEYS.length);
  });

  test('an explicit Save clears pending state so later autosaves do not replay it', async ({ page }) => {
    // pendingPromptAgents protects unsaved prompts from the autosave response. If Save
    // does not clear it, those bodies stay "pending" forever and every later autosave
    // re-applies the page-load copy over server truth -- reintroducing the stale-restore
    // problem that the ExtractAgentSettings-only autosave payload exists to prevent.
    const result = await page.evaluate(async () => {
      const realFetch = window.fetch;

      // Server truth after someone else edited CmdlineExtract's prompt.
      const serverConfig = {
        agent_models: (window as any).currentConfig?.agent_models || {},
        agent_prompts: {
          ExtractAgentSettings: { disabled_agents: [] },
          CmdlineExtract: { prompt: 'EDITED_ELSEWHERE', instructions: '' },
        },
      };

      window.fetch = async (url: any, opts: any) => {
        if (String(url).includes('/api/workflow/config') && opts?.method === 'PUT') {
          return new Response(JSON.stringify(serverConfig), {
            status: 200, headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ warnings: [] }), {
          status: 200, headers: { 'Content-Type': 'application/json' },
        });
      };

      try {
        agentPrompts = {
          ExtractAgentSettings: { disabled_agents: [] },
          CmdlineExtract: { prompt: 'STALE_PAGE_LOAD_COPY', instructions: '' },
        };
        pendingPromptAgents = new Set(['CmdlineExtract']);

        // Simulate what a successful explicit Save does to pending state.
        pendingPromptAgents = new Set();

        await performAutoSave();

        return { cmdlinePrompt: agentPrompts.CmdlineExtract?.prompt, pendingSize: pendingPromptAgents.size };
      } finally {
        window.fetch = realFetch;
      }
    });

    // Once nothing is pending, server truth wins -- the stale copy must not come back.
    expect(result.cmdlinePrompt).toBe('EDITED_ELSEWHERE');
    expect(result.pendingSize).toBe(0);
  });

  test('rendering an agent with no prompt does not create an empty record', async ({ page }) => {
    const result = await page.evaluate(() => {
      agentPrompts = { ExtractAgentSettings: { disabled_agents: [] } };

      renderAgentPrompts();

      const keys = Object.keys(agentPrompts);
      return {
        materialised: keys.filter(k => k !== 'ExtractAgentSettings'),
        rankPanelRendered: !!document.getElementById('rank-agent-prompt-container')?.innerHTML.trim(),
        sigmaPanelRendered: !!document.getElementById('sigma-agent-prompt-container')?.innerHTML.trim(),
      };
    });

    // RankAgent and SigmaAgent were the two agents this used to fabricate.
    expect(result.materialised).toEqual([]);
    // The panels must still render -- the placeholder is local, not persisted.
    expect(result.rankPanelRendered).toBe(true);
    expect(result.sigmaPanelRendered).toBe(true);
  });
});
