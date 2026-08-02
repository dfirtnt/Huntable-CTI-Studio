/**
 * Snapshot / restore helpers for the shared workflow config on the dev app.
 *
 * Playwright specs in the `agent-config` project mutate the SAME
 * `agentic_workflow_config` row that the live dev app on :8001 reads. A spec
 * that mutates config and does not put it back leaves the operator's dev
 * environment damaged.
 *
 * The historical failure this module exists to prevent:
 *
 *   `agent_config_presets.spec.ts` restored config with a PARTIAL
 *   `PUT /api/workflow/config` carrying only the three thresholds. The backend
 *   carries omitted fields forward from the currently-active row
 *   (`workflow_config.py` `final_agent_prompts` / `merged_agent_models`), but
 *   that fallback resolves to `None` when the active-config lookup returns
 *   nothing -- which happens in the window where a concurrent PUT has
 *   deactivated the active row and not yet committed its replacement. Because
 *   `agent_prompts` / `agent_models` are JSONB columns, SQLAlchemy persists a
 *   Python `None` as JSON `null` rather than SQL NULL, so the partial restore
 *   silently wiped every omitted field. Config row 5396 is the surviving
 *   artifact: JSON-`null` `agent_prompts` AND `agent_models`, plus
 *   `sigma_fallback_enabled` reset to the no-current-config default.
 *
 * The defence is to always send a COMPLETE payload and to verify by read-back
 * that the restore actually landed, rather than trusting the PUT's status code.
 */

import { APIRequestContext, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/** Every field `WorkflowConfigUpdate` accepts that a restore must repopulate. */
export interface WorkflowConfigSnapshot {
  min_hunt_score: number;
  ranking_threshold: number;
  similarity_threshold: number;
  junk_filter_threshold: number;
  sigma_fallback_enabled: boolean;
  rank_agent_enabled: boolean;
  cmdline_attention_preprocessor_enabled: boolean;
  proc_tree_attention_preprocessor_enabled: boolean;
  agent_prompts: Record<string, any>;
  agent_models: Record<string, any>;
}

/**
 * Canonical CmdlineExtract prompt, byte-identical across all nine committed
 * quickstart presets. Used only to repair an already-empty stored prompt --
 * never to overwrite a prompt the operator has legitimately customised.
 */
const CANONICAL_PRESET = path.join(
  __dirname, '..', '..', 'config', 'presets', 'AgentConfigs', 'quickstart',
  'Quickstart-LMStudio-Qwen3.json'
);

/**
 * Guard mirroring the pytest `agent_config_mutation` protection in
 * `tests/conftest.py`. Playwright specs had no equivalent, so a run that the
 * operator explicitly asked to leave config alone could still mutate it when a
 * spec was invoked directly by path.
 *
 * Call this in `beforeAll` of any spec that writes workflow config.
 */
export function assertConfigMutationAllowed(specName: string): void {
  if (process.env.CTI_EXCLUDE_AGENT_CONFIG_TESTS === '1') {
    throw new Error(
      `${specName} mutates shared workflow config, but CTI_EXCLUDE_AGENT_CONFIG_TESTS=1 ` +
      `requests that config be left untouched. Refusing to run. ` +
      `Unset the variable to allow this spec to snapshot/mutate/restore config.`
    );
  }
}

/** Read the canonical CmdlineExtract prompt envelope from the committed preset. */
export function canonicalCmdlinePrompt(): { prompt: string; instructions: string } {
  const preset = JSON.parse(fs.readFileSync(CANONICAL_PRESET, 'utf-8'));
  const envelope = preset?.CmdlineExtract?.Prompt;
  if (!envelope || typeof envelope.prompt !== 'string' || envelope.prompt.length === 0) {
    throw new Error(`Canonical preset ${CANONICAL_PRESET} has no usable CmdlineExtract.Prompt`);
  }
  return { prompt: envelope.prompt, instructions: envelope.instructions ?? '' };
}

/**
 * Capture the full active config.
 *
 * If the stored CmdlineExtract prompt is empty -- the residue of the historical
 * partial-restore bug -- repair it from the canonical preset so the snapshot we
 * later restore is a HEALTHY config rather than a faithful copy of the damage.
 * A non-empty prompt is always preserved verbatim.
 */
export async function snapshotWorkflowConfig(
  request: APIRequestContext,
  baseUrl: string
): Promise<WorkflowConfigSnapshot> {
  const res = await request.get(`${baseUrl}/api/workflow/config`);
  expect(res.ok(), 'snapshot GET /api/workflow/config must succeed').toBeTruthy();
  const cfg = await res.json();

  const agentPrompts: Record<string, any> = cfg.agent_prompts ?? {};
  const cmdline = agentPrompts.CmdlineExtract;
  if (!cmdline || typeof cmdline.prompt !== 'string' || cmdline.prompt.trim() === '') {
    const canonical = canonicalCmdlinePrompt();
    console.warn(
      '[config-snapshot] stored CmdlineExtract prompt is empty (legacy partial-restore ' +
      'pollution); seeding snapshot from the canonical quickstart preset so restore heals it.'
    );
    agentPrompts.CmdlineExtract = { ...(cmdline ?? {}), ...canonical };
  }

  return {
    min_hunt_score: cfg.min_hunt_score,
    ranking_threshold: cfg.ranking_threshold,
    similarity_threshold: cfg.similarity_threshold,
    junk_filter_threshold: cfg.junk_filter_threshold,
    sigma_fallback_enabled: cfg.sigma_fallback_enabled,
    rank_agent_enabled: cfg.rank_agent_enabled,
    cmdline_attention_preprocessor_enabled: cfg.cmdline_attention_preprocessor_enabled,
    proc_tree_attention_preprocessor_enabled: cfg.proc_tree_attention_preprocessor_enabled,
    agent_prompts: agentPrompts,
    agent_models: cfg.agent_models ?? {},
  };
}

/**
 * Restore a snapshot and PROVE it landed.
 *
 * `agent_models` is merged (not replaced) by the backend, so keys a preset
 * import added since the snapshot are explicitly nulled to delete them.
 * `agent_prompts` is replaced wholesale, so sending it whole is sufficient.
 *
 * Retries on mismatch: a concurrent autosave from another spec can overwrite us
 * between the PUT and the read-back. Throws if the config still does not match
 * after `attempts` tries -- a silent restore failure is exactly the damage this
 * module exists to prevent.
 */
export async function restoreWorkflowConfig(
  request: APIRequestContext,
  baseUrl: string,
  snapshot: WorkflowConfigSnapshot,
  attempts: number = 3
): Promise<void> {
  let lastMismatch = '';

  for (let attempt = 1; attempt <= attempts; attempt++) {
    // Null out agent_models keys added since the snapshot so the merge deletes them.
    const currentRes = await request.get(`${baseUrl}/api/workflow/config`);
    const current = currentRes.ok() ? await currentRes.json() : {};
    const agentModels: Record<string, any> = { ...snapshot.agent_models };
    for (const key of Object.keys(current.agent_models ?? {})) {
      if (!(key in snapshot.agent_models)) agentModels[key] = null;
    }

    const putRes = await request.put(`${baseUrl}/api/workflow/config`, {
      data: {
        ...snapshot,
        agent_models: agentModels,
        description: 'Restored by Playwright config snapshot helper',
      },
    });

    if (!putRes.ok()) {
      lastMismatch = `PUT failed: ${putRes.status()} ${await putRes.text()}`;
      continue;
    }

    lastMismatch = await verifyRestored(request, baseUrl, snapshot);
    if (lastMismatch === '') return;
  }

  throw new Error(
    `Workflow config restore did not land after ${attempts} attempts: ${lastMismatch}. ` +
    `The shared dev config on ${baseUrl} may be left in a mutated state.`
  );
}

/** Read the config back and report the first field that does not match, or '' if clean. */
async function verifyRestored(
  request: APIRequestContext,
  baseUrl: string,
  snapshot: WorkflowConfigSnapshot
): Promise<string> {
  const res = await request.get(`${baseUrl}/api/workflow/config`);
  if (!res.ok()) return `read-back GET failed: ${res.status()}`;
  const cfg = await res.json();

  const numeric: (keyof WorkflowConfigSnapshot)[] = [
    'min_hunt_score', 'ranking_threshold', 'similarity_threshold', 'junk_filter_threshold',
  ];
  for (const field of numeric) {
    const want = snapshot[field] as number;
    const got = cfg[field];
    if (typeof got !== 'number' || Math.abs(got - want) > 1e-6) {
      return `${field}: expected ${want}, got ${got}`;
    }
  }

  const booleans: (keyof WorkflowConfigSnapshot)[] = [
    'sigma_fallback_enabled', 'rank_agent_enabled',
    'cmdline_attention_preprocessor_enabled', 'proc_tree_attention_preprocessor_enabled',
  ];
  for (const field of booleans) {
    if (cfg[field] !== snapshot[field]) {
      return `${field}: expected ${snapshot[field]}, got ${cfg[field]}`;
    }
  }

  // The regression that motivated this module: agent_prompts arriving as JSON null.
  if (cfg.agent_prompts === null || cfg.agent_prompts === undefined) {
    return 'agent_prompts is null after restore (the exact row-5396 pollution)';
  }
  for (const agent of Object.keys(snapshot.agent_prompts)) {
    const want = snapshot.agent_prompts[agent];
    const got = cfg.agent_prompts[agent];
    if (JSON.stringify(got) !== JSON.stringify(want)) {
      return `agent_prompts.${agent} not restored (expected ${JSON.stringify(want).length}B, ` +
        `got ${JSON.stringify(got ?? null).length}B)`;
    }
  }

  if (cfg.agent_models === null || cfg.agent_models === undefined) {
    return 'agent_models is null after restore';
  }
  for (const key of Object.keys(snapshot.agent_models)) {
    if (JSON.stringify(cfg.agent_models[key]) !== JSON.stringify(snapshot.agent_models[key])) {
      return `agent_models.${key}: expected ${snapshot.agent_models[key]}, got ${cfg.agent_models[key]}`;
    }
  }

  return '';
}
