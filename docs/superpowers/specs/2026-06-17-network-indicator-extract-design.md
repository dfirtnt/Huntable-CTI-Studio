# NetworkIndicatorExtract -- Design Spec

- Date: 2026-06-17
- Status: Proposed (awaiting operator review)
- Branch: europa-dev
- Todoist: "Create a new extractor sub-agent for Network Observables" (task 6gH44H5VVCvHvwrV)
- Supersedes: an earlier "NetworkPatternExtract" synthesis design, rejected by adversarial
  review (verdict: design_fundamentally_flawed). See "Background" below.

---

## 1. Background and motivation

The request is a 7th extraction sub-agent for the ExtractAgent supervisor, covering network
observables: DNS, User-Agent strings, IP/port, and URI. An initial design proposed a
"NetworkPatternExtract" that would synthesize Sigma-compatible wildcard patterns
(re-fang, wildcard, regex-ify) directly in the extractor.

A 6-lens adversarial review against the live codebase rejected that design on three
independently-verified, load-bearing grounds:

1. **Doctrine collision (critical).** The extractor family contract
   `docs/contracts/extractor-standard.md:69` mandates "LITERAL EXTRACTION ONLY: No inference.
   No reconstruction. No synthesis. No normalization." A synthesized wildcard value is, by
   construction, none of the article's literal text and performs all four banned operations.
2. **Un-scorable eval (critical).** `src/services/eval_item_scorer.py` does exact
   set-intersection on lightly-normalized strings; ground truth is stored verbatim. Prompt-driven
   wildcarding is non-deterministic, so two correct runs score recall 0 against each other.
3. **Thin corpus at "patterns only" (high).** Over 5177 live articles, only ~0.75% carry strong,
   generalizable network patterns; the abundant material is *atomic* indicators, which the
   pattern-only design explicitly excluded.

**Resolution chosen by the operator:** reframe to a strictly **literal** extractor. Literal
extraction is doctrine-compliant, deterministically scorable by the existing verbatim scorer,
and the corpus thinness inverts (atomic indicators are abundant once they are no longer
excluded). The generalization-to-patterns the operator ultimately wants is already performed
one step downstream by **SigmaAgent** during rule generation -- it re-derives modifiers,
fields, and logsource from its own prompt regardless of extractor output shape.

---

## 2. Goals and non-goals

### Goals
- Add `NetworkIndicatorExtract` as a first-class peer of the existing 6 extractors.
- Extract network indicators (domain/DNS, IP [+ port], URL, URI path, User-Agent) **verbatim**,
  with a per-item detection-relevance gate and traceability fields.
- Ship it as a `_SIMPLE_EXTRACTORS` member so the `value` field carries the indicator and the
  existing eval-scoring and Sigma-observables handoff paths work unchanged.
- Follow the **current** (post-QA-deprecation) wiring contract; add zero QA artifacts.

### Non-goals
- No pattern synthesis / wildcarding / regex generation in the extractor (downstream SigmaAgent
  does generalization). No deterministic post-processor (that was the rejected alternative).
- No re-fanging or normalization of indicators (banned by doctrine; the eval scorer normalizes
  symmetrically).
- No QA sub-agent (`NetworkIndicatorQA`). QA was deprecated 2026-05-22 and is guarded by
  `tests/config/test_qa_full_deprecation.py`.
- Do not fix the pre-existing `registry_keys` vs `registry_artifacts` mismatch in
  `sigma_generation_service.py` (out of scope; noted in Risks).

---

## 3. Identifiers

| Field | Value |
|---|---|
| AgentName (PascalCase) | `NetworkIndicatorExtract` |
| canonical alias == LLM array key == result_key == eval dir | `network_indicators` |
| scope short-form | `network` (registered as a `SUBAGENT_CANONICAL` variant only) |
| agentPrefix (HTML/JS token) | `networkindicatorextract` |
| display name | "Network Indicators Extraction" |
| icon | globe glyph U+1F310, matching the eval-card emoji convention. **Source files are ASCII-only (AGENTS.md), so emit it ASCII-safe**: JS escape `'\u{1F310}'`, HTML entity `&#x1F310;`, or an existing SVG/icon helper -- never a raw multibyte character. |
| extractor class | `_SIMPLE_EXTRACTORS` (value-carrier) |

The alias, the LLM JSON top-level array key, and the workflow `result_key` are deliberately
the **same token** (`network_indicators`) so that `_parse_agent_result`
(`agentic_workflow.py`) matches on `result_key in agent_result` and never falls through to the
fragile "first list" fallback.

---

## 4. Output schema and prompt

Simple extractor: every item carries a generic `value` plus the three mandatory traceability
fields, plus an `indicator_type` discriminator and optional `port`.

```json
{
  "network_indicators": [
    {
      "value": "evil[.]duckdns[.]org",
      "indicator_type": "domain",
      "source_evidence": "The implant beacons to evil[.]duckdns[.]org over HTTPS every 60 seconds.",
      "extraction_justification": "Attacker C2 domain stated verbatim; huntable via Sysmon EID 22 / Zeek dns.log.",
      "confidence_score": 0.9
    }
  ],
  "count": 1
}
```

- **value**: the indicator reproduced **exactly as written**, including any defanging
  (`evil[.]com`, `hxxp://...`). No normalization by the extractor. Scoring works because BOTH
  the extracted value and the ground truth are stored verbatim, so they string-match exactly.
  The eval scorer (`eval_item_scorer.py:15-27`) additionally normalizes only the bracket-defang
  forms `[.]` and `[:]` (symmetrically on expected and actual) -- it does **NOT** normalize
  `hxxp`/`hxxps` or any other defang style. Consequence: `ground_truth.json` MUST preserve the
  indicator exactly as it appears in the source (including `hxxp`). Do not assume `hxxp` is
  canonicalized; if cross-defang-style matching is ever needed, the scorer must be extended
  intentionally (out of scope here).
- **indicator_type** (enum, covers the 4 subtasks):
  - `domain` -- DNS names, FQDNs, DNS query names (subtask: DNS patterns)
  - `ip` -- IPv4/IPv6 address; literal CIDR allowed; optional sibling `port` field (subtask: IP/port)
  - `url` -- full URL with scheme + host (subtask: URI patterns)
  - `uri_path` -- bare path/endpoint without host, e.g. `/gate.php` (subtask: URI patterns)
  - `user_agent` -- User-Agent strings (subtask: UA String patterns)
- **port** (optional): present only when a port is explicitly associated in the text.
- **count**: integer length of the array. Empty result is exactly
  `{"network_indicators":[],"count":0}`.

### Detection-relevance gate (huntable doctrine -- map to telemetry or SKIP)
| indicator_type | Telemetry |
|---|---|
| domain | Sysmon EID 22 (DNS query), Zeek dns.log, DNS server logs |
| ip | Sysmon EID 3 (network connection), netflow, firewall, Zeek conn.log |
| url / uri_path | proxy/web logs, Zeek http.log (uri) |
| user_agent | proxy/web logs, Zeek http.log (user_agent) |

### Negative scope (precision over recall)
- Benign/legitimate infrastructure not tied to attacker behavior.
- Hypothetical or illustrative indicators (`example.com`, placeholder `1.2.3.4`,
  `attacker.com`-style examples).
- Defensive guidance not tied to observed attacker behavior.
- Reconstructed/inferred/normalized indicators (literal only).

### Confidence rubric (coherent because values are literal)
- 0.9+   -- indicator explicitly attacker-attributed (C2, payload host, exfil endpoint), verbatim.
- 0.6-0.89 -- present and clearly security-relevant; attribution slightly indirect.
- 0.5-0.59 -- present but thin context.
- below 0.5 -- SKIP (fail-closed).

### Soft-overlap boundary
`NetworkIndicatorExtract` owns the network indicator even when it appears inside a command
line (`curl http://evil[.]com/x`) or as a **complete** value inside a detection rule
(Sigma/KQL condition). `CmdlineExtract` keeps the full command line; `HuntQueriesExtract`
keeps the rule. Reciprocal Architecture Context clauses are added to all 6 sibling prompts.

### Prompt file structure
`src/prompts/NetworkIndicatorExtract` is a JSON file with keys `role`, `instructions`,
`json_example`, `task` -- matching the live `ScheduledTasksExtract` format (NOT the skill's
stale `user_template` shape). The `role` block carries PURPOSE, ARCHITECTURE CONTEXT (sibling
list + boundary rules), INPUT CONTRACT, POSITIVE/NEGATIVE scope, the detection gate, fidelity
(verbatim) requirements, count semantics, and a verification checklist.

---

## 5. Architecture and data flow

`NetworkIndicatorExtract` is a sub-agent dispatched by the ExtractAgent supervisor (Step 3 of
the 7-step LangGraph workflow). Its items are merged into the aggregated `extraction_result`
and reach SigmaAgent through the existing, generic channel:

- `agentic_workflow.py:1839` reads `item.get("value")` to build the observables list; because
  this agent is a value-carrier, its indicator surfaces cleanly as
  `[i] network_indicators: <value>` rather than a flattened dict blob.
- `sigma_generation_service.py` (`_build_observables_section`) injects that list into the Sigma
  prompt via `{observables_section}`. SigmaAgent then derives detection syntax itself.
- For the multi-rule expansion phase, `observable_to_category` (two copies in
  `sigma_generation_service.py`) gains network sub-type -> logsource-category entries.

No structured Sigma fields are emitted by the extractor; generalization is SigmaAgent's job.

---

## 6. Wiring map (implementation contract)

QA-free. Line anchors verified against the repo on 2026-06-17; re-confirm by grep before
editing (code drifts). The new agent is the **7th**; every "6" hard-count guard becomes "7".

### Layer 1 -- Config (5 files)
- `src/config/workflow_config_schema.py`: add `NetworkIndicatorExtract` to `AGENT_NAMES_SUB`
  (line 105) and `AGENT_DISPLAY_NAMES` (line 121). No QA entries.
- `src/config/workflow_config_loader.py`: add to `EXTRACT_AGENTS`, `AGENTS_ORDER_UI`,
  `UI_ORDERED_TOP_LEVEL_ORDER`, the `_UI_ORDERED_REQUIRED` tuple (keys: Enabled/Provider/Model/
  Temperature/TopP/Prompt -- NO QA keys), `_OPTIONAL_SUB_AGENT_SECTIONS` (QA-free default block),
  and the v2<->ui-ordered export/import loops.
- `src/config/workflow_config_migrate.py`: add ONE `_AGENT_FLAT_PREFIXES` tuple
  `("NetworkIndicatorExtract","NetworkIndicatorExtract","NetworkIndicatorExtract_model")`.
  No QA tuple.
- `src/utils/subagent_utils.py`: add `"networkindicatorextract": "network_indicators"` to
  `AGENT_TO_SUBAGENT`; add alias variants to `SUBAGENT_CANONICAL`
  (`network_indicators`, `networkindicators`, `network-indicators`, `networkindicatorextract`,
  and the short form `network`).
- `src/utils/default_agent_prompts.py`: add `"NetworkIndicatorExtract": "NetworkIndicatorExtract"`
  to `AGENT_PROMPT_FILES`. No QA key.

### Layer 2 -- Prompts (7 files)
- Create `src/prompts/NetworkIndicatorExtract` (schema in section 4).
- Update the 6 sibling prompts (`CmdlineExtract`, `ProcTreeExtract`, `RegistryExtract`,
  `ServicesExtract`, `ScheduledTasksExtract`, `HuntQueriesExtract`) Architecture Context blocks
  with the reciprocal network-indicator boundary clause.

### Layer 3 -- Services / engine (5 files)
- `src/services/llm_service.py`: add `"NetworkIndicatorExtract"` to `_SIMPLE_EXTRACTORS`
  (line 2454); add `"network_indicators"` to `expected_keys` (line 2743); add a normalization
  branch `elif "network_indicators" in last_result: last_result["items"] =
  last_result.pop("network_indicators")` to the ladder ending at line 2811; add
  `network_indicators` to the Langfuse output-key loop; add to the top_p_extract agent list.
  Note: `_SIMPLE_EXTRACTORS`/`_STRUCTURED_EXTRACTORS` are currently **function-local** tuples
  (not importable). RECOMMENDED implementation cleanup: promote both to module-scope constants
  so the simple/structured split is importable and directly assertable; if you do, the wiring
  test may assert membership directly. If you leave them function-local, the wiring test must
  instead be a behavior test (see Layer 7).
- `src/workflows/agentic_workflow.py`: add entries to `_AGENT_NAME_TO_SUBAGENT`, the
  `subresults` init dict (`"network_indicators": {"items": [], "count": 0}`), the `sub_agents`
  driver list, `subagent_to_agent`, and `cat_to_agent`/`cat_to_subagent_name`. The `value` path
  (`_extract_actual_items` line 425, handoff line 1839) needs no change because `value` is a
  recognized field.
- `src/services/sigma_generation_service.py`: add network sub-type -> category entries to BOTH
  copies of `observable_to_category` (domain->dns_query, ip->network_connection,
  url/uri_path->proxy or webserver, user_agent->proxy).
- `src/services/eval_bundle_service.py`: add the agent to its subagent/model maps (verify
  current anchors; skill line numbers are stale).
- `src/services/lmstudio_model_loader.py`: add to the sub-agent preload list.

### Layer 4 -- Routes (3 files)
- `src/web/routes/workflow_executions.py`: add `"network_indicators"` to `OBS_TYPES`
  (line 494). (The skill's `primary_agents`/`agent_mapping` symbols no longer exist -- skip.)
- `src/web/routes/evaluation_api.py`: add to `SUBAGENT_AGENT_MAP`, result-extraction branch,
  sub-agent model-display loop, and `SUBAGENT_RESULT_KEY_MAP` (verify current anchors).
- `src/web/routes/workflow_config.py`: add `NetworkIndicatorExtract` to every hard-coded
  extractor list -- used for JSON prompt validation, model assignment, and version-history
  save. As of 2026-06-17 there are ~5 occurrences near lines 489, 1114, 1279, 1883, and
  2271-2276 (two are `sub_agents = [...]` literals). Grep `CmdlineExtract` in this file to
  enumerate them all. **Missing this causes saved prompt/config behavior to diverge from the
  schema/UI wiring** (e.g. the new agent's prompt save mis-routes or its model is not assigned).

### Layer 5 -- UI (8 files)
- `src/web/static/js/components/workflow-config-display.js`: `workflowOrder`,
  `firstLevelSubAgents`, `subAgentOrder` ({id,name} only -- no qa).
- `src/web/templates/workflow.html`: append to `LOCKED_EXTRACTOR_AGENTS` (line 5827); add a
  subAgents render-array entry `{ key:'network_indicators', name:'NetworkIndicatorExtract',
  display:'Network Indicators Extraction', icon: '\u{1F310}', order:7 }` (ASCII-safe escape;
  NO qaName); plus the
  AGENT_CONFIG registration, sub-agent panel, model container, and prompt container per the
  workflow-html checklist -- minus all QA toggles.
- `src/web/static/js/components/observable-utils.js`: append `"network_indicators"` to
  `OBS_TYPE_ORDER` (line 11; it MUST stay in sync with AGENT_NAMES_SUB).
- `src/web/templates/agent_evaluation.html`: add eval card.
- `src/web/templates/agent_evals.html`: dropdown `<option>`, `SUBAGENT_MAP`, modal-title branch,
  count-noun ternary ("network indicator(s)"), and a **string** render path (value is a plain
  string, like cmdline). DROP the QA ternary.
- `src/web/templates/subagent_evaluation.html`: purpose-description block.
- `src/web/templates/workflow_executions.html`: `_DN` display-name entry + subAgents render
  array entry (NO qaName).
- `src/web/templates/base.html`: bump the `workflow-config-display.js?v=` cache-buster.

### Layer 6 -- Presets and eval data (10 items)
- 9 quickstart presets in `config/presets/AgentConfigs/quickstart/`: add a 6-field
  `NetworkIndicatorExtract` block (Enabled/Provider/Model/Temperature/TopP/Prompt) with
  `Prompt.prompt` populated from disk via script -- NO QA keys. After editing the 6 sibling
  prompts, re-sync their embedded preset copies so imports do not roll back the boundary clauses.
- `config/eval_articles_data/network_indicators/`: `articles.json` seeded from real DB articles
  rich in network indicators (abundant substrate); optional separate `ground_truth.json`.

### Layer 7 -- Tests (~9 files)
- NEW `tests/config/test_network_indicator_wiring.py`: schema/loader/migrate/subagent-utils/
  prompt-file/preset/eval-dir coverage. Assert `Prompt.prompt` non-empty in all presets and that
  the prompt `json_example` items carry a non-empty `value`. No QA assertions. For the
  simple/value semantics, assert it via **behavior** (function-local tuple is not importable):
  feed a `{"network_indicators":[...]}` payload through the normalization/traceability path and
  assert the array is renamed to `items` and each item retains/receives a `value`. (If the
  implementer promotes `_SIMPLE_EXTRACTORS` to a module constant, a direct membership assert is
  also acceptable -- see Layer 3.)
- NEW/extended `tests/api/` or `tests/services/` coverage for the route/service slices this
  spec touches (run under the `api` marker):
  - `evaluation_api.py`: subagent eval article loading + result extraction returns
    `network_indicators` items (not empty) for a fixture execution.
  - `eval_bundle_service.py`: bundle-export maps include `NetworkIndicatorExtract` /
    `network_indicators` (count + model + error-log key resolve).
  - `workflow_executions.py`: `_build_observables_response` groups `network_indicators` (mirror
    `test_observable_traceability_regressions.py` coverage for the new type).
- `tests/config/test_workflow_config_migrate.py`: change `len(config.Agents) == 9` (line 144)
  to `== 10` (+1, not the skill's +2). Audit the file for other count asserts.
- `tests/unit/test_workflow_locked_extractor_agents.py`: bump count 6 -> 7, add
  ('network_indicators','NetworkIndicatorExtract') to the expected render entries, change the
  "last entry" order assert to 7, add the agent to the LOCKED set test.
- `tests/unit/test_observable_traceability_regressions.py`: add `network_indicators` to the
  obs-type parametrize.
- `tests/playwright/execution_detail_tabs.spec.ts`: update "all six" -> seven, add the type to
  fixtures, fix offset-index math.
- `tests/config/test_workflow_config_export.py`: add UI-ordered fixture section.
- `tests/config/test_workflow_config_import_export_fidelity.py`: add a 6-field block (NO QA
  constants).
- `tests/config/test_backfill_sub_agents.py`: add to `BACKFILL_AGENTS`.
- `tests/config/test_subagent_traceability_contract.py`: add to `MIGRATED_EXTRACT_AGENTS`
  (json_example uses `count`). No QA additions.
- `tests/worker/test_test_agents_provider_resolution.py`: add to the parametrize list.
- `tests/integration/test_lmstudio_minimal_e2e.py`: append to the `disabled_agents` list.
- Confirm `tests/config/test_qa_full_deprecation.py` stays green (we add zero QA).

---

## 7. Testing strategy

1. `python3 run_tests.py unit --paths tests/config/test_network_indicator_wiring.py`
2. `python3 run_tests.py unit --paths tests/unit/test_workflow_locked_extractor_agents.py`
3. `python3 run_tests.py unit --paths tests/config/`
4. `python3 run_tests.py unit --paths tests/config/test_qa_full_deprecation.py` (must pass)
5. `python3 run_tests.py api` for the route/service slices: evaluation_api subagent eval
   loading + result extraction, eval_bundle_service export-map coverage, and
   workflow_executions observable grouping for `network_indicators`.
6. Preset backward-compat: import a preset lacking the `NetworkIndicatorExtract` section;
   expect clean import with the agent defaulted to disabled.
7. Browser verification at http://127.0.0.1:8001/workflow#config: sub-agent count = 7, new
   panel renders provider/model/temperature/top_p/prompt editor + Test button (no QA toggle),
   Selected Models panel shows the agent, LMStudio model dropdown populates, no console errors.
8. Test button uses the correct provider (reads `NetworkIndicatorExtract_provider` from
   `agent_models`).
9. Optional empirical gate: run the extractor on 5-10 indicator-rich articles and confirm
   verbatim values, non-empty `count`, items reaching the observables panel.

---

## 8. Risks and open questions

- **Pre-existing `observable_to_category` key mismatch.** The map uses `registry_keys` while the
  workflow emits `registry_artifacts`, so registry already misses Sigma expansion. Noted, NOT
  fixed here (out of scope; flag for a separate task).
- **Defanged values downstream.** Verbatim values may be defanged. SigmaAgent consumes them as
  text; if Sigma-rule quality suffers, a deterministic re-fang step is a *future* option
  (explicitly the rejected synthesis territory -- out of scope now).
- **Skill staleness.** `/Create-Huntable-Agent` documents a QA architecture that no longer
  exists. This spec, not the skill, is the implementation contract. Follow the skill only for
  non-QA structural patterns.
- **Line anchors drift.** All cited line numbers are 2026-06-17 snapshots; grep to confirm
  before each edit.

---

## 9. Verification / exit

Exit PASS when: all listed test suites pass (including the QA-deprecation guard), preset
backward-compat holds, and browser verification confirms a 7th panel with correct
provider/model wiring and observables flowing to the Sigma step.
