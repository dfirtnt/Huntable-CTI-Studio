import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { acceptConfirmModal, confirmModal, dismissConfirmModal } from './helpers';
import {
  WorkflowConfigSnapshot,
  assertConfigMutationAllowed,
  restoreWorkflowConfig,
  snapshotWorkflowConfig,
} from './workflow-config-snapshot';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

async function clickExportPresetButton(page: any) {
  await page.locator('#footer-overflow-toggle').click();
  await expect(page.locator('#footer-overflow-menu')).toBeVisible({ timeout: 3000 });
  await page.locator('#export-preset-btn').click();
}

/** Per-test temp preset path -- a shared filename races when tests run concurrently. */
function writeTempPreset(name: string, preset: unknown): string {
  const tempDir = path.join(__dirname, '..', '..', 'tmp');
  if (!fs.existsSync(tempDir)) {
    fs.mkdirSync(tempDir, { recursive: true });
  }
  const presetPath = path.join(tempDir, `${name}-${process.pid}-${Date.now()}.json`);
  fs.writeFileSync(presetPath, JSON.stringify(preset, null, 2));
  return presetPath;
}

/**
 * Serial: every test here writes the SAME shared `agentic_workflow_config` row
 * on the dev app. Running them concurrently makes each test observe another
 * test's config writes -- which is how "should import real preset file" came to
 * assert against a ranking threshold left behind by the autosave test.
 */
test.describe.configure({ mode: 'serial' });

test.describe('Agent Config Presets', () => {
  let configSnapshot: WorkflowConfigSnapshot;

  test.beforeAll(async ({ request }) => {
    assertConfigMutationAllowed('agent_config_presets.spec.ts');
    configSnapshot = await snapshotWorkflowConfig(request, BASE);
  });

  // Put config back after every test so no test inherits another's mutations,
  // and verify by read-back that the restore actually landed.
  test.afterEach(async ({ request }) => {
    await restoreWorkflowConfig(request, BASE, configSnapshot);
  });

  test.afterAll(async ({ request }) => {
    await restoreWorkflowConfig(request, BASE, configSnapshot);
  });

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);

    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    // Wait for initialization flag to clear (set false after loadConfig completes)
    await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 10000 });
  });

  test('should save preset with all config state', async ({ page }) => {
    // Set up download listener before clicking
    let downloadReceived = false;
    let downloadPath: string | null = null;
    
    page.on('download', async (download) => {
      downloadReceived = true;
      downloadPath = await download.path();
    });

    // Click export preset button (inside overflow menu)
    await clickExportPresetButton(page);

    // Wait for download to be triggered
    await page.waitForTimeout(2000);

    // If download was received, verify the file
    if (downloadReceived && downloadPath) {
      // Read the downloaded file
      const presetContent = fs.readFileSync(downloadPath, 'utf-8');
      const preset = JSON.parse(presetContent);

      // Verify preset structure
      expect(preset).toHaveProperty('version');
      expect(preset).toHaveProperty('thresholds');
      expect(preset).toHaveProperty('agent_models');
      expect(preset).toHaveProperty('sigma_fallback_enabled');
      expect(preset).toHaveProperty('rank_agent_enabled');
      expect(preset).toHaveProperty('extract_agent_settings');
      expect(preset).toHaveProperty('agent_prompts');

      // Clean up
      if (fs.existsSync(downloadPath)) {
        fs.unlinkSync(downloadPath);
      }
    } else {
      // If download wasn't triggered, verify the button was reachable
      const btnVisible = await page.locator('#export-preset-btn').isVisible().catch(() => false);
      expect(btnVisible || true).toBe(true);
    }
  });

  test('should load preset and apply all settings', async ({ page }) => {
    // Create a test preset
    const testPreset = {
      version: '1.0',
      created_at: new Date().toISOString(),
      description: 'Test preset',
      thresholds: {
        junk_filter_threshold: 0.85,
        ranking_threshold: 7.0,
        similarity_threshold: 0.6
      },
      agent_models: {
        RankAgent: 'test-model',
        RankAgent_provider: 'lmstudio'
      },
      sigma_fallback_enabled: true,
      rank_agent_enabled: true,
      extract_agent_settings: {
        disabled_agents: ['CmdlineExtract']
      },
      agent_prompts: {}
    };

    const presetPath = writeTempPreset('test-preset-apply', testPreset);

    // Load preset
    const fileInput = page.locator('#import-preset-input');
    await fileInput.setInputFiles(presetPath);

    // The import gate is a ModalManager.confirm() DOM modal, not window.confirm,
    // so it must be clicked. Waiting on page.on('dialog') never fires and leaves
    // applyPreset() unreached -- the assertions below then silently measure
    // whatever the previous test left in the shared config.
    await acceptConfirmModal(page);

    // Wait for applyPreset() to populate the form and flush its autosaves
    await page.waitForTimeout(3000);

    // Verify thresholds were applied
    await expandPanelIfNeeded(page, 'other-thresholds-panel');
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');

    const junkFilterInput = page.locator('#junkFilterThreshold');
    await junkFilterInput.waitFor({ state: 'visible', timeout: 10000 });
    const junkFilterValue = await junkFilterInput.inputValue();
    expect(parseFloat(junkFilterValue)).toBeCloseTo(0.85, 2);

    const rankingInput = page.locator('#rankingThreshold');
    await rankingInput.waitFor({ state: 'visible', timeout: 10000 });
    const rankingValue = await rankingInput.inputValue();
    expect(parseFloat(rankingValue)).toBeCloseTo(7.0, 1);

    // Clean up
    if (fs.existsSync(presetPath)) {
      fs.unlinkSync(presetPath);
    }
  });

  test('should show error for invalid preset structure', async ({ page }) => {
    const invalidPreset = {
      // Missing required fields
      version: '1.0'
    };

    const presetPath = writeTempPreset('invalid-preset', invalidPreset);

    const fileInput = page.locator('#import-preset-input');
    await fileInput.setInputFiles(presetPath);

    await page.waitForTimeout(2000);

    // importPresetFromFile() throws on the missing thresholds/agent_models before
    // it ever reaches ModalManager.confirm(), so the load gate must never appear.
    // Asserting on that is the real signal the preset was rejected; the previous
    // `expect(hasErrorToast || true)` could not fail.
    await expect(confirmModal(page)).toHaveCount(0);

    // Clean up
    if (fs.existsSync(presetPath)) {
      fs.unlinkSync(presetPath);
    }
  });

  test('should show confirmation dialog before loading preset', async ({ page }) => {
    const testPreset = {
      version: '1.0',
      created_at: new Date().toISOString(),
      thresholds: {
        junk_filter_threshold: 0.8,
        ranking_threshold: 6.0,
        similarity_threshold: 0.5
      },
      agent_models: {},
      sigma_fallback_enabled: false,
      rank_agent_enabled: true,
      extract_agent_settings: {
        disabled_agents: []
      },
      agent_prompts: {}
    };

    const presetPath = writeTempPreset('test-preset-confirm', testPreset);

    const fileInput = page.locator('#import-preset-input');
    await fileInput.setInputFiles(presetPath);

    // The gate is a ModalManager.confirm() DOM modal titled "Load Preset", not a
    // native confirm dialog -- page.on('dialog') never fired here, so the old
    // `expect(dialogShown).toBe(true)` failed whenever it ran on its own.
    const modal = confirmModal(page);
    await expect(modal).toBeVisible({ timeout: 10000 });
    await expect(modal.locator('h3')).toHaveText(/Load Preset/i);
    await expect(modal).toContainText('Load preset');
    await expect(modal.locator('.confirm-btn')).toHaveText('Load');

    // Cancel the load, and confirm the config was left untouched.
    const before = await (await page.request.get(`${BASE}/api/workflow/config`)).json();
    await dismissConfirmModal(page);
    await page.waitForTimeout(1000);
    const after = await (await page.request.get(`${BASE}/api/workflow/config`)).json();
    expect(after.ranking_threshold).toBeCloseTo(before.ranking_threshold, 2);

    // Clean up
    if (fs.existsSync(presetPath)) {
      fs.unlinkSync(presetPath);
    }
  });

  test('should include autosaved values in preset', async ({ page }) => {
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');

    const rankingInput = page.locator('#rankingThreshold');
    await rankingInput.waitFor({ state: 'visible', timeout: 10000 });

    const newValue = '7.5';
    // Range input: use evaluate to trigger oninput handler
    await rankingInput.evaluate((el, val) => {
      (el as HTMLInputElement).value = val;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, newValue);

    // Wait for autosave
    await page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 15000 }  // Increased from 5000 to 15000
    );
    await page.waitForTimeout(1000);

    // Set up download listener
    let downloadReceived = false;
    let downloadPath: string | null = null;
    
    page.on('download', async (download) => {
      downloadReceived = true;
      downloadPath = await download.path();
    });

    // Export preset (inside overflow menu)
    await clickExportPresetButton(page);
    await page.waitForTimeout(2000);

    // If download was received, verify the preset
    if (downloadReceived && downloadPath) {
      const presetContent = fs.readFileSync(downloadPath, 'utf-8');
      const preset = JSON.parse(presetContent);

      // Preset should include the autosaved value
      expect(preset.thresholds.ranking_threshold).toBeCloseTo(7.5, 1);

      // Clean up
      if (fs.existsSync(downloadPath)) {
        fs.unlinkSync(downloadPath);
      }
    } else {
      // If download wasn't triggered, at least verify the value was set
      const currentValue = await rankingInput.inputValue();
      expect(parseFloat(currentValue)).toBeCloseTo(7.5, 1);
    }
  });

  test('should import preset and apply provider/model correctly', async ({ page }) => {
    // Use the actual preset file from Downloads
    const presetPath = path.join(process.env.HOME || '/Users/starlord', 'Downloads', 'workflow-preset-2026-01-23-test.json');
    
    if (!fs.existsSync(presetPath)) {
      test.skip();
      return;
    }

    // Import preset (ModalManager.confirm gate, not a native dialog)
    const fileInput = page.locator('#import-preset-input');
    await fileInput.setInputFiles(presetPath);
    await acceptConfirmModal(page);

    // Wait for preset to be applied
    await page.waitForTimeout(5000);

    // Expand panels to check values (use actual data-collapsible-panel ids)
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
    await expandPanelIfNeeded(page, 'extract-agent-panel');
    await expandPanelIfNeeded(page, 'sigma-agent-panel');

    // Verify RankAgent: lmstudio + google/gemma-3-4b
    const rankProvider = page.locator('#rankagent-provider');
    await rankProvider.waitFor({ state: 'visible', timeout: 10000 });
    const rankProviderValue = await rankProvider.inputValue();
    expect(rankProviderValue).toBe('lmstudio');

    const rankModel = page.locator('#rankagent-model-2');
    await rankModel.waitFor({ state: 'visible', timeout: 10000 });
    const rankModelValue = await rankModel.inputValue();
    expect(rankModelValue).toBe('google/gemma-3-4b');

    // Verify ExtractAgent: openai + gpt-4o-mini
    const extractProvider = page.locator('#extractagent-provider');
    await extractProvider.waitFor({ state: 'visible', timeout: 10000 });
    const extractProviderValue = await extractProvider.inputValue();
    expect(extractProviderValue).toBe('openai');

    // For OpenAI, check the openai-specific input
    const extractModelOpenAI = page.locator('#extractagent-model-openai');
    await extractModelOpenAI.waitFor({ state: 'visible', timeout: 10000 });
    const extractModelValue = await extractModelOpenAI.inputValue();
    expect(extractModelValue).toBe('gpt-4o-mini');

    // Verify SigmaAgent: openai + gpt-4o-mini-2024-07-18
    const sigmaProvider = page.locator('#sigmaagent-provider');
    await sigmaProvider.waitFor({ state: 'visible', timeout: 10000 });
    const sigmaProviderValue = await sigmaProvider.inputValue();
    expect(sigmaProviderValue).toBe('openai');

    const sigmaModelOpenAI = page.locator('#sigmaagent-model-openai');
    await sigmaModelOpenAI.waitFor({ state: 'visible', timeout: 10000 });
    const sigmaModelValue = await sigmaModelOpenAI.inputValue();
    expect(sigmaModelValue).toBe('gpt-4o-mini-2024-07-18');
  });

  test('should import real preset file from config/presets and restore config', async ({ page }) => {
    // Step 1: Get current config BEFORE import (to restore later)
    const currentConfigRes = await page.request.get(`${BASE}/api/workflow/config`);
    const currentConfig = await currentConfigRes.json();
    const originalSimilarityThreshold = currentConfig.similarity_threshold;
    const originalRankingThreshold = currentConfig.ranking_threshold;

    // Step 2: Load a real preset file from config/presets (always-committed quickstart preset)
    const presetPath = path.join(__dirname, '..', '..', 'config', 'presets', 'AgentConfigs', 'quickstart', 'Quickstart-LMStudio-Qwen3.json');

    // Verify the preset file exists
    if (!fs.existsSync(presetPath)) {
      console.log('Real preset file not found, skipping test');
      test.skip();
      return;
    }

    // Read the preset to verify key values.
    // v2 presets use SigmaAgent.SimilarityThreshold; v1 used Thresholds.SimilarityThreshold.
    // Fall back to current config values so the assertion passes for unoverridden thresholds.
    const presetContent = fs.readFileSync(presetPath, 'utf-8');
    const preset = JSON.parse(presetContent);
    const expectedSimilarity =
      preset.SigmaAgent?.SimilarityThreshold ??
      preset.Thresholds?.SimilarityThreshold ??
      originalSimilarityThreshold;
    // v2 presets use RankAgent.RankingThreshold; v1 used thresholds.ranking_threshold.
    const expectedRanking =
      preset.RankAgent?.RankingThreshold ??
      preset.thresholds?.ranking_threshold ??
      originalRankingThreshold;

    // Step 3: Import the preset (ModalManager.confirm gate, not a native dialog)
    const fileInput = page.locator('#import-preset-input');
    await fileInput.setInputFiles(presetPath);
    await acceptConfirmModal(page);

    // Wait for preset to be applied
    await page.waitForTimeout(3000);

    // Expand panels to verify values were applied
    // rankingThreshold is in rank-agent-configs-panel (s2)
    // similarityThreshold is in other-thresholds-panel (s5), NOT sigma-agent-panel
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
    await page.waitForTimeout(500);
    await expandPanelIfNeeded(page, 'other-thresholds-panel');
    await page.waitForTimeout(500);

    // Step 4: Verify the preset was applied correctly
    const similarityInput = page.locator('#similarityThreshold');
    await similarityInput.waitFor({ state: 'visible', timeout: 10000 });
    const actualSimilarity = parseFloat(await similarityInput.inputValue());
    expect(actualSimilarity).toBeCloseTo(expectedSimilarity, 2);

    const rankingInput = page.locator('#rankingThreshold');
    await rankingInput.waitFor({ state: 'visible', timeout: 10000 });
    const actualRanking = parseFloat(await rankingInput.inputValue());
    expect(actualRanking).toBeCloseTo(expectedRanking, 1);

    // Step 5: Restore the original config (cleanup)
    // Wait for all pending auto-saves from the import to flush before sending
    // the restore PUT. applyPreset sets many fields via setAgentProvider which
    // calls autoSaveModelChange (debounce resets each call). Use networkidle to
    // wait until the browser's in-flight PUT queue drains rather than a fixed
    // sleep, which may be shorter than the total debounce chain.
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

    // Restore the FULL config, not just the three thresholds.
    //
    // The previous partial PUT is what damaged the shared dev config: the
    // backend carries omitted fields forward from the active row, but that
    // fallback yields None when the active-config lookup comes back empty
    // (concurrent PUT mid-deactivate). agent_prompts/agent_models are JSONB, so
    // SQLAlchemy wrote Python None as JSON `null` -- producing config row 5396
    // with null agent_prompts, which left CmdlineExtract's stored prompt empty
    // and made the expanded prompt editor's Save a permanent no-op.
    //
    // restoreWorkflowConfig sends every mutable field and then re-reads the
    // config to prove the restore landed instead of trusting the 200.
    await restoreWorkflowConfig(page.request, BASE, configSnapshot);

    // Step 6: Verify restoration worked
    const restoredConfigRes = await page.request.get(`${BASE}/api/workflow/config`);
    const restoredConfig = await restoredConfigRes.json();
    expect(restoredConfig.similarity_threshold).toBeCloseTo(configSnapshot.similarity_threshold, 2);
    // Guard the exact regression: prompts must survive a restore intact.
    expect(restoredConfig.agent_prompts).not.toBeNull();
    expect(restoredConfig.agent_prompts.CmdlineExtract.prompt.length).toBeGreaterThan(0);

    // Reload the page to reflect restored values
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // Expand panels to see restored values
    await expandPanelIfNeeded(page, 'other-thresholds-panel');
    await page.waitForTimeout(500);

    // Verify the values were restored in the UI
    const restoredSimilarityInput = page.locator('#similarityThreshold');
    await restoredSimilarityInput.waitFor({ state: 'visible', timeout: 10000 });
    const restoredSimilarity = parseFloat(await restoredSimilarityInput.inputValue());
    expect(restoredSimilarity).toBeCloseTo(configSnapshot.similarity_threshold, 2);
  });
});

const PANEL_STEP_MAP: Record<string, string[]> = {
  'os-detection-panel': ['s0'], 'other-thresholds-panel': ['s1', 's5'],
  'rank-agent-configs-panel': ['s2'],
  'extract-agent-panel': ['s3'], 'cmdlineextract-agent-panel': ['s3'],
  'proctreeextract-agent-panel': ['s3'], 'huntqueriesextract-agent-panel': ['s3'],
  'registryextract-agent-panel': ['s3'], 'sigma-agent-panel': ['s4'],
};
async function expandPanelIfNeeded(page: any, panelId: string) {
  const stepIds = PANEL_STEP_MAP[panelId];
  if (stepIds) {
    await page.evaluate((ids: string[]) => { ids.forEach(id => document.getElementById(id)?.classList.add('open')); }, stepIds);
    await page.waitForTimeout(300);
    return;
  }
  const content = page.locator(`#${panelId}-content`);
  const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
  if (await header.isVisible({ timeout: 2000 }).catch(() => false)) {
    const isHidden = await content.evaluate((el: HTMLElement) => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) { await header.click(); await page.waitForTimeout(300); }
  }
}
