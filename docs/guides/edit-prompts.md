# Edit Agent Prompts

Agent prompts control what each extraction and QA agent asks the LLM to produce. You edit them through the **Workflow Config** UI; every save creates a new version you can roll back to.

This guide covers the day-to-day edit loop. For what the on-disk `src/prompts/` files do (seed defaults, not live prompts), see [`src/prompts/README.md`](https://github.com/dfirtnt/Huntable-CTI-Studio/blob/main/src/prompts/README.md).

## Where prompts live

- **Live prompts** — in the database, under the active workflow config's `agent_prompts`. These are what workflows actually use at runtime.
- **Seed defaults** — files in `src/prompts/`. Read only on first boot, when `agent_prompts` is empty, or when you click **Reset to Defaults**. Editing a seed file does **not** change a running install.

## The edit loop

1. **Open** `http://localhost:8001/workflow` → **Config** tab → select an agent (e.g., `ServicesExtract`).
2. **Edit** the prompt body and/or `instructions` field.
3. **Save**. The UI creates a new entry in `agent_prompt_versions` and bumps the workflow config version.
4. **Test** against an eval article (either the in-UI **Test Agent** button or `./scripts/run_prompt_test.sh` — see [Prompt Testing Script](https://github.com/dfirtnt/Huntable-CTI-Studio/blob/main/scripts/README_prompt_testing.md)).
5. **Roll back** if it regressed: same page, **Versions** → pick a prior version → **Rollback**.

## What the system expects from an extract prompt

Every extract sub-agent must emit **per-item traceability fields** on every extracted object. The runtime appends a reminder to your user prompt automatically (`_traceability_block` in `src/services/llm_service.py`), but your prompt body should reinforce it in the JSON schema and examples.

### Required fields on every item

| Field | Type | Purpose |
|-------|------|---------|
| `value` | string | The extracted artifact (command line, query, service name, etc.) |
| `source_evidence` | string | Verbatim paragraph from the article containing the artifact |
| `extraction_justification` | string | Which prompt rule or rubric triggered this extraction |
| `confidence_score` | number 0.0–1.0 | Model's self-reported confidence |

**Deprecated — do not reintroduce:** `raw_text_snippet`, `confidence_level`. The contract test (`tests/config/test_subagent_traceability_contract.py`) will fail CI if either name appears in a prompt file or preset.

### Confidence calibration (convention)

Use the same bands across prompts so scores stay comparable:

- **0.9+** — all key fields explicitly stated and attacker-attributed
- **0.6–0.89** — partial but clear attribution
- **0.3–0.59** — attribution present but specifics ambiguous

Confidence is **self-reported by the model**, not derived from log-probs. The runtime does not call any token-probability API (providers differ; Anthropic doesn't expose them). If you omit the calibration guide, scores drift per model.

### What the runtime normalizes for you

You do not need to defend against these in the prompt:

- Numeric coercion of `confidence_score` and range-clamping to `[0.0, 1.0]`.
- Fallback mapping of a stray `confidence_level` string (`high`/`medium`/`low`) to `0.95`/`0.7`/`0.4`.
- Wrapping bare-string items into `{"value": ..., "confidence_score": None}`.

See `_normalize_traceability_item` in `src/services/llm_service.py`.

## Envelope shape (migrated agents)

`RegistryExtract`, `ServicesExtract`, and `ProcTreeExtract` use a shared template envelope. If you are creating or heavily rewriting one of these (or a new extract agent), follow the same shape:

| Key | Role |
|-----|------|
| `role` | System prompt — who the agent is and what it will *not* do |
| `user_template` | String containing `{content}` and `{instructions}` placeholders |
| `task` | One-line statement of the extraction goal |
| `json_example` | A populated JSON example matching the required output schema |
| `instructions` | Long-form rules: extraction scope, field rules, exclusions, validation checklist. If absent, the runtime substitutes `"Output valid JSON only."` — no schema constraints are enforced. |

**`role` is required.** If the parsed prompt config contains neither `role` nor `system`, `_validate_preprocess_invariants` in `src/services/llm_service.py` raises a `PreprocessInvariantError` and aborts the call before it reaches the model. This is classified as `infra_failed`, not a model failure, so it does not consume QA retries. The symptom is a silent extraction failure with no LLM response logged.

`CmdlineExtract` and `HuntQueriesExtract` retain their older envelope style; they are field-compliant but not shape-migrated. Don't add new agents in the old style.

## Extract ↔ QA pairing

Most extract agents ship with a QA counterpart (`ServicesExtract` ↔ `ServicesQA`). When you change one side of the pair, the other usually needs a matching edit:

- **Add a field to extract output** → add it to the QA `evaluation_criteria`.
- **Tighten an extraction rule** → have the QA prompt flag violations as `issues`.
- **Rename a field** → rename it in both; the contract test checks QA criteria reference `source_evidence` and `extraction_justification`.

## Versioning and rollback

- Every save writes to `agent_prompt_versions` with an auto-incrementing version number and the workflow config version at save time.
- Evals pin the workflow config version, so historical eval runs are stable against prompt edits made afterward.
- Rollback creates a *new* version that restores the older content; it does not delete history.

Relevant API endpoints:

- `GET  /api/workflow/config/prompts/{agent_name}/versions`
- `GET  /api/workflow/config/prompts/{agent_name}/by-config-version/{config_version}`
- `POST /api/workflow/config/prompts/{agent_name}/rollback`
- `POST /api/workflow/config/prompts/bootstrap` — re-seed from `src/prompts/` (creates a new version; nothing is lost)

## Common mistakes

- **Editing `src/prompts/` expecting the running app to change.** It won't. Those are seed defaults. Edit through the UI instead.
- **Dropping the traceability block from the schema.** Downstream UI renders `source_evidence` and `extraction_justification`; items missing them render as bare values.
- **Asking for `confidence_level` (high/medium/low).** Deprecated. Ask for numeric `confidence_score` with calibration bands.
- **Forgetting the QA prompt.** If extract adds a field, QA must know about it — otherwise QA will either ignore the field or flag every item as non-compliant.
- **Loosening precision rules.** Extract prompts favor under-extraction ("when uncertain → EXCLUDE"). Loosening this floods the Sigma generator with junk candidates.

## Related

- [Agents and Responsibilities](../concepts/agents.md) — which agents run in what order
- [Extract Observables](extract-observables.md) — observable shape and downstream consumers
- [Evaluate Models](evaluate-models.md) — measuring prompt changes against eval articles
- [Agent Config Schema](../architecture/agent-config-schema.md) — Pydantic contract for the broader config
- Contract test: `tests/config/test_subagent_traceability_contract.py` — authoritative schema enforcement
