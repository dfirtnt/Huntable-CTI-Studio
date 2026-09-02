import { request as playwrightRequest } from '@playwright/test';
import {
  classifyPostRunDamage,
  clearBaseline,
  readBaseline,
  restoreWorkflowConfig,
} from './workflow-config-snapshot';

/**
 * Restore the shared workflow config after the run, whatever happened during it.
 *
 * Specs already snapshot and restore around their own mutations, but every one
 * of those restores runs *inside* the test worker and most need a live `page`.
 * They therefore do not fire when a worker is killed, when the global timeout
 * trips, or when the browser context dies mid-test -- which is how the hermetic
 * CmdlineExtract seed from `expanded_prompt_editor_save.spec.ts` ended up as the
 * live prompt for two days (config row 7949, 2026-08-19).
 *
 * Global teardown is the process-level backstop: it runs once, in Node, with no
 * dependence on any page or worker surviving. It restores the baseline captured
 * by `global-setup.ts` and verifies the restore landed by read-back.
 *
 * The one failure mode it cannot cover is SIGKILL of the Playwright process
 * itself. That is handled from the other side: the next run's global-setup heals
 * known pollution before it snapshots, so damage survives at most one run.
 */
async function globalTeardown() {
  if (process.env.CTI_EXCLUDE_AGENT_CONFIG_TESTS === '1') {
    return; // No config-mutating spec ran; leave config untouched as requested.
  }

  const baseline = readBaseline();
  if (!baseline) {
    console.warn(
      '[config-teardown] no baseline captured by global-setup; leaving workflow config as-is. ' +
      'If this run mutated config, restore it manually or re-import a preset.'
    );
    return;
  }

  const baseURL = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
  const context = await playwrightRequest.newContext();
  try {
    await restoreWorkflowConfig(context, baseURL, baseline);

    const res = await context.get(`${baseURL}/api/workflow/config`);
    const { introduced, preExisting } = res.ok()
      ? classifyPostRunDamage(baseline, await res.json())
      : { introduced: [], preExisting: [] };

    if (introduced.length > 0) {
      console.error(
        `[config-teardown] ❌ config shows damage this run introduced: ${introduced.join('; ')}`
      );
      return;
    }

    console.log('[config-teardown] ✅ workflow config restored to the pre-run baseline');
    if (preExisting.length > 0) {
      console.log(
        `[config-teardown]    (pre-existing, not caused by this run: ${preExisting.join('; ')})`
      );
    }
    clearBaseline();
  } catch (err: any) {
    // Never fail the run here: the tests' own results are the signal. But make
    // the damage impossible to miss, and keep the baseline on disk so the next
    // global-setup can heal from it.
    console.error(
      `[config-teardown] ❌ FAILED to restore workflow config on ${baseURL}: ${err.message}\n` +
      '    The shared dev config may be left mutated. The baseline was kept for the next run.'
    );
  } finally {
    await context.dispose();
  }
}

export default globalTeardown;
