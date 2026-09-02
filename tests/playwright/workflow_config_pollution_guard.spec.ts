import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  BASELINE_PATH,
  canonicalCmdlinePrompt,
  classifyPostRunDamage,
  clearBaseline,
  findConfigPollution,
  readBaseline,
  snapshotWorkflowConfig,
  TEST_SEED_MARKER,
  writeBaseline,
  WorkflowConfigSnapshot,
} from './workflow-config-snapshot';

/**
 * Unit coverage for the config-pollution detector that `global-setup.ts` uses to
 * heal damage left by a previous run that died before its teardown.
 *
 * Pure assertions over fixture payloads -- no browser, no server. The detector is
 * the thing standing between an interrupted UI run and a silently degraded live
 * CmdlineExtract prompt, so it is worth pinning directly rather than only through
 * the end-to-end path.
 */

function healthyConfig() {
  return {
    agent_prompts: {
      CmdlineExtract: { prompt: 'You are a LITERAL TEXT EXTRACTOR...', instructions: 'Return JSON.' },
      ProcTreeExtract: { prompt: 'You are a LITERAL TEXT EXTRACTOR...', instructions: 'Return JSON.' },
    },
    agent_models: { CmdlineExtract: 'qwen3' },
  };
}

test.describe('findConfigPollution', () => {
  test('reports nothing for a healthy config', () => {
    expect(findConfigPollution(healthyConfig())).toEqual([]);
  });

  test('detects the hermetic test seed left by an interrupted spec', () => {
    const cfg = healthyConfig();
    cfg.agent_prompts.CmdlineExtract.prompt =
      `${TEST_SEED_MARKER}. Extracts Windows command-line observables from articles.`;

    const damage = findConfigPollution(cfg);
    expect(damage.join(' ')).toContain(TEST_SEED_MARKER);
  });

  test('detects an empty prompt (partial-PUT residue)', () => {
    const cfg = healthyConfig();
    cfg.agent_prompts.CmdlineExtract.prompt = '';

    expect(findConfigPollution(cfg).join(' ')).toContain('CmdlineExtract.prompt is empty');
  });

  test('detects a JSON-null agent_prompts (the row-5396 wipe)', () => {
    const damage = findConfigPollution({ agent_prompts: null, agent_models: {} });
    expect(damage.join(' ')).toContain('agent_prompts is null');
  });

  test('ignores non-prompt entries such as ExtractAgentSettings', () => {
    const cfg: any = healthyConfig();
    // Real shape from the live config: a settings blob, not a prompt record.
    cfg.agent_prompts.ExtractAgentSettings = { disabled_agents: [] };
    expect(findConfigPollution(cfg)).toEqual([]);
  });

  test('detects a JSON-null agent_models', () => {
    const cfg: any = healthyConfig();
    cfg.agent_models = null;
    expect(findConfigPollution(cfg).join(' ')).toContain('agent_models is null');
  });

  /**
   * Anti-drift guard. The detector recognises seeded config by TEST_SEED_MARKER,
   * so a spec that hardcodes its own seed string instead of importing the marker
   * would write pollution the detector cannot see -- reintroducing exactly the
   * silent failure this module exists to prevent.
   */
  test('config-mutating specs build their seed from the shared marker', () => {
    const spec = path.join(__dirname, 'expanded_prompt_editor_save.spec.ts');
    const source = fs.readFileSync(spec, 'utf-8');

    expect(source).toContain('TEST_SEED_MARKER');
    // The literal must not appear outside the shared module.
    expect(source).not.toContain(`'${TEST_SEED_MARKER}`);
    expect(source).not.toContain(`"${TEST_SEED_MARKER}`);
  });
});

/** Minimal APIRequestContext stand-in: snapshotWorkflowConfig only issues a GET. */
function fakeRequest(payload: any) {
  return { get: async () => ({ ok: () => true, json: async () => payload }) } as any;
}

function storedConfig(cmdlinePrompt: string) {
  return {
    min_hunt_score: 40, ranking_threshold: 0.5, similarity_threshold: 0.7,
    junk_filter_threshold: 0.3, sigma_fallback_enabled: true, rank_agent_enabled: true,
    cmdline_attention_preprocessor_enabled: true, proc_tree_attention_preprocessor_enabled: true,
    agent_prompts: {
      CmdlineExtract: { prompt: cmdlinePrompt, instructions: 'stored instructions' },
    },
    agent_models: { CmdlineExtract: 'qwen3' },
  };
}

test.describe('snapshotWorkflowConfig healing', () => {
  test('heals a seeded CmdlineExtract prompt from the canonical preset', async () => {
    const seeded = JSON.stringify({ role: `${TEST_SEED_MARKER}. Extracts things.` });
    const snap = await snapshotWorkflowConfig(fakeRequest(storedConfig(seeded)), 'http://stub');

    expect(snap.agent_prompts.CmdlineExtract.prompt).toBe(canonicalCmdlinePrompt().prompt);
    expect(JSON.stringify(snap.agent_prompts)).not.toContain(TEST_SEED_MARKER);
    // A baseline built from this snapshot must be clean, or teardown launders the damage.
    expect(findConfigPollution(snap)).toEqual([]);
  });

  test('heals an empty CmdlineExtract prompt from the canonical preset', async () => {
    const snap = await snapshotWorkflowConfig(fakeRequest(storedConfig('')), 'http://stub');
    expect(snap.agent_prompts.CmdlineExtract.prompt).toBe(canonicalCmdlinePrompt().prompt);
  });

  test('preserves a healthy prompt verbatim (never overwrites operator edits)', async () => {
    const custom = 'You are a LITERAL TEXT EXTRACTOR. Operator-customised build.';
    const snap = await snapshotWorkflowConfig(fakeRequest(storedConfig(custom)), 'http://stub');

    expect(snap.agent_prompts.CmdlineExtract.prompt).toBe(custom);
    expect(snap.agent_prompts.CmdlineExtract.prompt).not.toBe(canonicalCmdlinePrompt().prompt);
  });
});

test.describe('baseline persistence', () => {
  /**
   * Regression guard for a defect this change actually shipped and had to fix:
   * the baseline was first written under `test-results/`, which is Playwright's
   * outputDir. Playwright clears that directory at run start, deleting the
   * baseline between global setup and global teardown -- so teardown silently
   * found nothing to restore and the run left config mutated.
   */
  test('baseline is stored outside Playwright-managed output directories', () => {
    const normalized = BASELINE_PATH.split(path.sep).join('/');
    expect(normalized).not.toContain('/test-results/');
    expect(normalized).not.toContain('/playwright-report/');
    expect(normalized).not.toContain('/allure-results/');
  });

  /*
   * These exercise a TEMP path, never BASELINE_PATH: writing or clearing the
   * real baseline would destroy the one global-setup captured for this very
   * run, leaving global-teardown with nothing to restore. (Observed -- an
   * earlier draft of this spec did exactly that.)
   */
  const tmpBaseline = path.join(os.tmpdir(), `cti-baseline-test-${process.pid}.json`);
  test.afterEach(() => clearBaseline(tmpBaseline));

  test('round-trips a snapshot through disk', () => {
    const snap = { agent_prompts: { A: { prompt: 'p' } }, agent_models: {} } as any as WorkflowConfigSnapshot;
    writeBaseline(snap, tmpBaseline);
    expect(readBaseline(tmpBaseline)).toEqual(snap);
  });

  test('returns null when no baseline exists so teardown declines to guess', () => {
    clearBaseline(tmpBaseline);
    expect(readBaseline(tmpBaseline)).toBeNull();
    expect(fs.existsSync(tmpBaseline)).toBe(false);
  });

  test('the real baseline is untouched by this spec', () => {
    // Guards the invariant above: if a future edit points these at
    // BASELINE_PATH, teardown stops restoring and nothing else would notice.
    // Skipped when global-setup itself never captured a baseline (this spec
    // isn't in playwright.config.ts's CTI_EXCLUDE_AGENT_CONFIG_TESTS
    // testIgnore list, so it still runs in that mode) -- there is nothing to
    // assert "untouched" about in that case.
    test.skip(process.env.CTI_EXCLUDE_AGENT_CONFIG_TESTS === '1', 'global-setup does not capture a baseline in this mode');
    expect(readBaseline()).not.toBeNull();
  });
});

test.describe('classifyPostRunDamage', () => {
  const clean = { agent_prompts: { A: { prompt: 'ok' } }, agent_models: {} } as any;

  test('attributes new damage to the run', () => {
    const after = { agent_prompts: { A: { prompt: '' } }, agent_models: {} };
    const { introduced, preExisting } = classifyPostRunDamage(clean, after);

    expect(introduced.join(' ')).toContain('A.prompt is empty');
    expect(preExisting).toEqual([]);
  });

  test('does not blame the run for damage the baseline already carried', () => {
    const damaged = { agent_prompts: { A: { prompt: '' } }, agent_models: {} } as any;
    const { introduced, preExisting } = classifyPostRunDamage(damaged, damaged);

    expect(introduced).toEqual([]);
    expect(preExisting.join(' ')).toContain('A.prompt is empty');
  });

  test('reports nothing when the restore landed clean', () => {
    expect(classifyPostRunDamage(clean, clean)).toEqual({ introduced: [], preExisting: [] });
  });
});
