# NetworkIndicatorExtract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `NetworkIndicatorExtract`, a doctrine-compliant *literal* network-indicator extraction sub-agent (the 7th extractor), wired as a first-class peer across schema, config, services, routes, UI, presets, eval data, and tests.

**Architecture:** A LangGraph sub-agent dispatched by the ExtractAgent supervisor. It extracts network indicators (domain/DNS, IP[+port], URL, URI path, User-Agent) VERBATIM with per-item traceability, as a `_SIMPLE_EXTRACTORS` value-carrier so the existing eval-scoring and Sigma-observables handoff paths work unchanged. Generalization to detection patterns happens downstream in SigmaAgent. No QA agent (QA was deprecated 2026-05-22).

**Tech Stack:** Python 3.10+ (Pydantic v2, FastAPI, LangGraph, Celery), Jinja2 templates + vanilla JS, pytest (`run_tests.py`), Docker Compose dev at :8001.

**Spec:** `docs/superpowers/specs/2026-06-17-network-indicator-extract-design.md` (committed f03a9fb0).

**Spec addendum (discovered during planning):** eval data requires a `subagents.network_indicators`
key in `config/eval_articles.yaml` in addition to `config/eval_articles_data/network_indicators/articles.json`,
and the wiring test enforces a yaml<->articles.json count match. Use `scripts/fetch_eval_articles_static.py`
to populate both consistently. (Covered in Task 13.)

**Identifiers (constant across all tasks):**
- AgentName: `NetworkIndicatorExtract`
- alias == LLM array key == result_key == eval dir: `network_indicators`
- scope short-form: `network` (a SUBAGENT_CANONICAL variant only)
- agentPrefix: `networkindicatorextract`
- display: `Network Indicators Extraction`
- icon: ASCII-safe globe escape `'\u{1F310}'` (JS) / `&#x1F310;` (HTML)
- extractor class: `_SIMPLE_EXTRACTORS`

**Conventions:**
- All source/config/shell content is ASCII-only (AGENTS.md). No raw multibyte chars.
- `.py` edits need `docker restart cti_web` (and worker containers for task code) to take effect at :8001; template/JS edits are live per-request but need a browser hard-reload + the `base.html` cache-bust bump.
- Line numbers below are 2026-06-17 snapshots -- `grep` to confirm before each edit.
- Commit after each task. Stage only the files you touched (never `git add -A` -- parallel sessions may fold in foreign edits).

---

## File Structure

**Create:**
- `src/prompts/NetworkIndicatorExtract` -- the extractor prompt (JSON, no extension).
- `tests/config/test_network_indicator_wiring.py` -- full-stack wiring test.
- `config/eval_articles_data/network_indicators/articles.json` -- eval article snapshots.

**Modify (grouped by responsibility):**
- Config contract: `workflow_config_schema.py`, `workflow_config_loader.py`, `workflow_config_migrate.py`, `subagent_utils.py`, `default_agent_prompts.py`.
- Prompts: the 6 sibling prompt files (Architecture Context boundary clause).
- Services/engine: `llm_service.py`, `agentic_workflow.py`, `sigma_generation_service.py`, `eval_bundle_service.py`, `lmstudio_model_loader.py`.
- Routes: `workflow_executions.py`, `evaluation_api.py`, `workflow_config.py`.
- UI: `workflow-config-display.js`, `workflow.html`, `observable-utils.js`, `agent_evaluation.html`, `agent_evals.html`, `subagent_evaluation.html`, `workflow_executions.html`, `base.html`.
- Presets: 9 files in `config/presets/AgentConfigs/quickstart/` + `config/eval_articles.yaml`.
- Tests: `test_workflow_config_migrate.py`, `test_workflow_locked_extractor_agents.py`, `test_observable_traceability_regressions.py`, `execution_detail_tabs.spec.ts`, `test_workflow_config_export.py`, `test_workflow_config_import_export_fidelity.py`, `test_backfill_sub_agents.py`, `test_subagent_traceability_contract.py`, `test_test_agents_provider_resolution.py`, `test_lmstudio_minimal_e2e.py`.

---

## Task 1: Create the extractor prompt file

**Files:**
- Create: `src/prompts/NetworkIndicatorExtract`

- [ ] **Step 1: Write the prompt file**

Create `src/prompts/NetworkIndicatorExtract` with this exact content (a literal extractor modeled on `src/prompts/ScheduledTasksExtract`, adapted for network indicators). The `json_example` value is a JSON-encoded string (escaped) exactly like the sibling prompts:

```json
{
  "role": "PURPOSE:\nYou extract network indicators (domains/DNS names, IP addresses and ports, URLs, URI paths, and User-Agent strings) from threat intelligence articles.\nYou are a LITERAL TEXT EXTRACTOR. You do NOT infer, reconstruct, normalize, synthesize, or generalize indicators.\nEDR/network observability overrides completeness. Only extract indicators that can drive network detection.\n\nARCHITECTURE CONTEXT:\nYou are a sub-agent of ExtractAgent. Sibling extractors:\n\n- CmdlineExtract        Windows command-line observables\n- ProcTreeExtract       Parent-child process creation relationships\n- RegistryExtract       Windows registry artifacts\n- ServicesExtract       Windows service artifacts\n- ScheduledTasksExtract Scheduled-task identity and scheduling metadata\n- HuntQueriesExtract    Finished detection logic (Sigma rules, KQL/SPL/EQL/XQL queries)\n\nBoundary rules:\n- You OWN network indicators (domain, ip, url, uri_path, user_agent) wherever they appear, INCLUDING inside a command line or inside a detection rule (soft-overlap).\n- Do NOT extract the surrounding command line itself -- CmdlineExtract owns the full command (e.g. extract the URL from `curl http://evil[.]com/x`, NOT the curl invocation).\n- Do NOT extract the finished detection-logic artifact (Sigma/KQL/SPL/EQL/XQL) itself -- HuntQueriesExtract owns the rule. A COMPLETE network indicator that appears as a literal value inside such a rule IS extractable here.\n- Do NOT extract process lineage, registry paths, service definitions, or scheduled-task identities (the respective siblings own those).\n\nINPUT CONTRACT:\n- A single article provided as {article_content}.\n- Treat as plain text. Do NOT interpret HTML, Markdown, or rendering semantics.\n- Extract ONLY from the provided text. Do NOT use prior knowledge or memory.\n- Do NOT fetch, browse, or access any URLs.\n\nPOSITIVE EXTRACTION SCOPE (by indicator_type):\n1) domain  -- DNS names, FQDNs, DNS query names (e.g. evil[.]duckdns[.]org). Telemetry: Sysmon EID 22, Zeek dns.log, DNS server logs.\n2) ip      -- IPv4/IPv6 addresses; literal CIDR ranges; optional sibling `port` when explicitly associated. Telemetry: Sysmon EID 3, netflow, firewall, Zeek conn.log.\n3) url     -- full URL with scheme + host (e.g. hxxp://evil[.]com/gate.php). Telemetry: proxy/web logs, Zeek http.log (uri).\n4) uri_path-- bare path/endpoint without host (e.g. /gate.php). Telemetry: proxy/web logs, Zeek http.log (uri).\n5) user_agent -- User-Agent strings (e.g. a malware UA). Telemetry: proxy/web logs, Zeek http.log (user_agent).\n\nNEGATIVE EXTRACTION SCOPE:\nDo NOT extract:\n- Benign/legitimate infrastructure not tied to attacker behavior.\n- Hypothetical/illustrative indicators (example.com, placeholder 1.2.3.4, attacker.com-style examples).\n- Defensive guidance not tied to observed attacker behavior.\n- Reconstructed, inferred, generalized, or normalized indicators (literal only).\n- The surrounding command line, detection rule, registry path, service, scheduled task, or process lineage (siblings own those).\n\nDETECTION RELEVANCE GATE:\nEvery extracted indicator must drive network detection via at least one of: Sysmon EID 22 (DNS), Sysmon EID 3 (network connection), Zeek dns.log/http.log/conn.log, proxy/web server logs, firewall/netflow. If an indicator has no detection-engineering value, SKIP.\n\nFIDELITY REQUIREMENTS:\n- Reproduce the indicator EXACTLY as written, including any defanging (evil[.]com, hxxp://, 8.8.8[.]8). Do NOT re-fang. Do NOT normalize.\n- Preserve original casing and punctuation.\n- value MUST be a literal substring of source_evidence.\n\nCOUNT SEMANTICS:\n- Unique indicator: each unique (indicator_type + value) pair = ONE item.\n- The same indicator mentioned multiple times = ONE item.\n- Two different indicator_types with the same string = TWO items only if both are literally present as distinct indicators.\n\nVERIFICATION CHECKLIST (apply to EVERY candidate before including it):\n- [ ] Is the indicator explicitly present in the text (not inferred, generalized, or hypothetical)?\n- [ ] Is it attacker-relevant (not benign infrastructure or defensive guidance)?\n- [ ] Does it have network detection value (one of the telemetry sources above)?\n- [ ] Is value a literal substring of source_evidence?\n- [ ] Is it NOT owned by a sibling (no command line, rule, registry, service, task, or lineage)?\n- [ ] Are all traceability fields populated (source_evidence, extraction_justification, confidence_score)?",
  "instructions": "OUTPUT SCHEMA:\nRespond with ONLY valid JSON. No prose, no markdown, no code fences, no explanations.\n\nSee REQUIRED JSON STRUCTURE in json_example below.\n\nFIELD RULES:\n\nTraceability fields (REQUIRED on every item):\n- source_evidence: REQUIRED. Exact excerpt from the article containing the indicator verbatim.\n- extraction_justification: REQUIRED. One sentence: why valid + which telemetry makes it huntable.\n- confidence_score: REQUIRED. Float 0.0-1.0.\n  0.9+     -- indicator explicitly attacker-attributed (C2, payload host, exfil endpoint), verbatim.\n  0.6-0.89 -- present and clearly security-relevant; attribution slightly indirect.\n  0.5-0.59 -- present but thin context.\n  below 0.5 -- DO NOT EXTRACT (fail-closed).\n\nDomain fields:\n- value: the indicator reproduced verbatim (a literal substring of source_evidence). REQUIRED.\n- indicator_type: one of domain, ip, url, uri_path, user_agent. REQUIRED.\n- port: integer or string port, ONLY when explicitly associated with an ip/url in the text. Omit entirely when absent.\n\nFAIL-SAFE / EMPTY OUTPUT:\nIf no valid network indicators exist, return exactly:\n{\"network_indicators\":[],\"count\":0}\n\nFINAL REMINDER:\nPrecision over recall. Network observability overrides completeness.\nExtract verbatim -- never re-fang or normalize.\nIf the indicator is benign, hypothetical, or defensive guidance, SKIP.\nIf only a command line/rule is present, extract just the network indicator inside it (not the wrapper).\nWhen in doubt, OMIT.\n\nARCHITECTURE CONTEXT:\nSee role field for sibling agent scope and boundary rules.",
  "json_example": "{\n  \"network_indicators\": [\n    {\n      \"value\": \"evil[.]duckdns[.]org\",\n      \"indicator_type\": \"domain\",\n      \"source_evidence\": \"The implant beacons to evil[.]duckdns[.]org over HTTPS every 60 seconds.\",\n      \"extraction_justification\": \"Attacker C2 domain stated verbatim; huntable via Sysmon EID 22 / Zeek dns.log.\",\n      \"confidence_score\": 0.9\n    }\n  ],\n  \"count\": 1\n}",
  "task": "Extract network indicators from the article verbatim. Precision over recall."
}
```

- [ ] **Step 2: Verify it parses as JSON and json_example defines the array**

Run:
```bash
python3 -c "import json; d=json.load(open('src/prompts/NetworkIndicatorExtract')); ex=json.loads(d['json_example']); assert 'network_indicators' in ex and ex['network_indicators'][0]['value']; print('OK', list(d.keys()))"
```
Expected: `OK ['role', 'instructions', 'json_example', 'task']`

- [ ] **Step 3: Commit**
```bash
git add src/prompts/NetworkIndicatorExtract
git commit -m "feat(prompts): add NetworkIndicatorExtract literal extractor prompt"
```

---

## Task 2: Add reciprocal boundary clauses to the 6 sibling prompts

**Files:**
- Modify: `src/prompts/CmdlineExtract`, `src/prompts/ProcTreeExtract`, `src/prompts/RegistryExtract`, `src/prompts/ServicesExtract`, `src/prompts/ScheduledTasksExtract`, `src/prompts/HuntQueriesExtract`

- [ ] **Step 1: Add the sibling line + boundary rule to each prompt's ARCHITECTURE CONTEXT (role field)**

In each of the 6 files, inside the `role` string's `ARCHITECTURE CONTEXT` sibling list, add this sibling entry (matching the existing list's `\n- Name   Description` format):
```
\n- NetworkIndicatorExtract  Network indicators (domain/DNS, IP+port, URL, URI path, User-Agent)
```
And add this boundary rule to that prompt's "Boundary rules:" block:
```
\n- Do NOT extract network indicators (domains, IPs, ports, URLs, URI paths, User-Agent strings) -- NetworkIndicatorExtract owns those, even when they appear inside your artifact (extract your artifact, leave the network indicator to NetworkIndicatorExtract).
```
For `CmdlineExtract` specifically, phrase it so it is clear Cmdline keeps the full command line and NetworkIndicatorExtract takes the embedded URL/host/IP. For `HuntQueriesExtract`, phrase it so HuntQueries keeps the rule and NetworkIndicatorExtract takes a complete network indicator value inside the rule.

- [ ] **Step 2: Verify all 6 still parse as JSON**

Run:
```bash
for f in CmdlineExtract ProcTreeExtract RegistryExtract ServicesExtract ScheduledTasksExtract HuntQueriesExtract; do python3 -c "import json,sys; json.load(open('src/prompts/$f')); print('$f OK')"; done
```
Expected: six `... OK` lines.

- [ ] **Step 3: Verify each now references the new sibling**
```bash
grep -l "NetworkIndicatorExtract" src/prompts/CmdlineExtract src/prompts/ProcTreeExtract src/prompts/RegistryExtract src/prompts/ServicesExtract src/prompts/ScheduledTasksExtract src/prompts/HuntQueriesExtract | wc -l
```
Expected: `6`

- [ ] **Step 4: Commit**
```bash
git add src/prompts/CmdlineExtract src/prompts/ProcTreeExtract src/prompts/RegistryExtract src/prompts/ServicesExtract src/prompts/ScheduledTasksExtract src/prompts/HuntQueriesExtract
git commit -m "feat(prompts): add NetworkIndicatorExtract boundary clauses to sibling extractors"
```

---

## Task 3: Write the failing config-layer wiring test

**Files:**
- Create: `tests/config/test_network_indicator_wiring.py`

- [ ] **Step 1: Write the wiring test** (mirrors `tests/config/test_scheduledtasks_wiring.py`, adapted; simple-extractor `value` semantics; QA-free)

```python
"""Full-stack wiring tests for the NetworkIndicatorExtract sub-agent (literal, no QA)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.workflow_config_loader import (
    AGENTS_ORDER_UI,
    EXTRACT_AGENTS,
    load_workflow_config,
)
from src.config.workflow_config_migrate import migrate_v1_to_v2
from src.config.workflow_config_schema import (
    AGENT_NAMES_SUB,
    ALL_AGENT_NAMES,
    WorkflowConfigV2,
)
from src.utils.subagent_utils import AGENT_TO_SUBAGENT, normalize_subagent_name

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parent.parent.parent


def _make_v2():
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "NetworkIndicatorExtract": {
            "Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True,
        },
    }
    prompts = {k: {"prompt": "", "instructions": ""} for k in agents}
    return {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "", "Description": ""},
        "Thresholds": {"MinHuntScore": 97.0, "RankingThreshold": 6.0, "SimilarityThreshold": 0.5, "JunkFilterThreshold": 0.8},
        "Agents": agents,
        "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": prompts,
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }


class TestSchemaConstants:
    def test_in_agent_names_sub(self):
        assert "NetworkIndicatorExtract" in AGENT_NAMES_SUB

    def test_in_all_agent_names(self):
        assert "NetworkIndicatorExtract" in ALL_AGENT_NAMES


class TestSchemaValidation:
    def test_valid_v2(self):
        config = WorkflowConfigV2.model_validate(_make_v2())
        assert "NetworkIndicatorExtract" in config.Agents

    def test_missing_prompt_rejected(self):
        raw = _make_v2()
        del raw["Prompts"]["NetworkIndicatorExtract"]
        with pytest.raises(ValidationError, match="Missing prompt block for agent NetworkIndicatorExtract"):
            WorkflowConfigV2.model_validate(raw)

    def test_flatten_keys(self):
        flat = WorkflowConfigV2.model_validate(_make_v2()).flatten_for_llm_service()
        assert flat["NetworkIndicatorExtract_model"] == "gpt-4"
        assert flat["NetworkIndicatorExtract_provider"] == "openai"


class TestLoaderConstants:
    def test_in_extract_agents(self):
        assert "NetworkIndicatorExtract" in EXTRACT_AGENTS

    def test_in_agents_order_ui(self):
        assert "NetworkIndicatorExtract" in AGENTS_ORDER_UI


class TestMigration:
    def test_v1_migrates(self):
        raw = {
            "version": "1.0",
            "agent_models": {
                "RankAgent_provider": "openai", "RankAgent": "gpt-4", "ExtractAgent": "gpt-4", "SigmaAgent": "gpt-4",
                "NetworkIndicatorExtract_provider": "anthropic",
                "NetworkIndicatorExtract_model": "claude-sonnet-4-5",
                "NetworkIndicatorExtract_temperature": 0.2,
                "NetworkIndicatorExtract_top_p": 0.95,
            },
            "agent_prompts": {n: {"prompt": "", "instructions": ""} for n in ALL_AGENT_NAMES},
        }
        config = WorkflowConfigV2.model_validate(migrate_v1_to_v2(raw))
        assert config.Agents["NetworkIndicatorExtract"].Model == "claude-sonnet-4-5"
        assert config.Agents["NetworkIndicatorExtract"].Provider == "anthropic"


class TestSubagentUtils:
    def test_agent_to_subagent(self):
        assert AGENT_TO_SUBAGENT["networkindicatorextract"] == "network_indicators"

    @pytest.mark.parametrize("alias", [
        "network_indicators", "networkindicators", "network-indicators",
        "networkindicatorextract", "network", "NetworkIndicatorExtract", "NETWORK_INDICATORS",
    ])
    def test_normalize_aliases(self, alias):
        assert normalize_subagent_name(alias) == "network_indicators"

    def test_unknown_returns_none(self):
        assert normalize_subagent_name("not_a_subagent") is None


class TestPromptFile:
    def test_exists_valid_and_value_field(self):
        path = _REPO / "src" / "prompts" / "NetworkIndicatorExtract"
        assert path.exists()
        data = json.loads(path.read_text())
        ex = data["json_example"]
        parsed = json.loads(ex) if isinstance(ex, str) else ex
        assert "network_indicators" in parsed
        assert parsed["network_indicators"][0]["value"], "simple extractor items must carry a non-empty value"


class TestDefaultAgentPrompts:
    def test_in_agent_prompt_files(self):
        from src.utils.default_agent_prompts import AGENT_PROMPT_FILES
        assert "NetworkIndicatorExtract" in AGENT_PROMPT_FILES
```

- [ ] **Step 2: Run it -- expect failure**

Run: `python3 run_tests.py unit --paths tests/config/test_network_indicator_wiring.py`
Expected: FAIL (e.g. `assert 'NetworkIndicatorExtract' in AGENT_NAMES_SUB`).

- [ ] **Step 3: Commit the failing test**
```bash
git add tests/config/test_network_indicator_wiring.py
git commit -m "test(config): add failing NetworkIndicatorExtract wiring test"
```

---

## Task 4: Implement the config-layer wiring (make Task 3 pass)

**Files:**
- Modify: `src/config/workflow_config_schema.py` (lines 105, 121)
- Modify: `src/config/workflow_config_loader.py` (EXTRACT_AGENTS, AGENTS_ORDER_UI, UI_ORDERED_TOP_LEVEL_ORDER, _UI_ORDERED_REQUIRED, _OPTIONAL_SUB_AGENT_SECTIONS, v2<->ui loops)
- Modify: `src/config/workflow_config_migrate.py` (_AGENT_FLAT_PREFIXES)
- Modify: `src/utils/subagent_utils.py` (AGENT_TO_SUBAGENT, SUBAGENT_CANONICAL)
- Modify: `src/utils/default_agent_prompts.py` (AGENT_PROMPT_FILES)
- Modify: `tests/config/test_workflow_config_migrate.py:144` (agent count 9 -> 10)

- [ ] **Step 1: schema** -- in `workflow_config_schema.py`, append `"NetworkIndicatorExtract"` to `AGENT_NAMES_SUB` (after `"ScheduledTasksExtract"`, line ~111) and add `"NetworkIndicatorExtract": "Network Indicators Extraction"` to `AGENT_DISPLAY_NAMES` (line ~121). Add NOTHING to `AGENT_NAMES_QA` / `BASE_AGENT_TO_QA`.

- [ ] **Step 2: loader** -- in `workflow_config_loader.py`:
  - Append `"NetworkIndicatorExtract"` to `EXTRACT_AGENTS`.
  - Insert `"NetworkIndicatorExtract"` into `AGENTS_ORDER_UI` immediately before `"SigmaAgent"`.
  - Insert `"NetworkIndicatorExtract"` into `UI_ORDERED_TOP_LEVEL_ORDER` immediately before `"SigmaAgent"`.
  - Add a `_UI_ORDERED_REQUIRED` tuple `("NetworkIndicatorExtract", ["Enabled","Provider","Model","Temperature","TopP","Prompt"])` (NO QA keys).
  - Add a default block to `_OPTIONAL_SUB_AGENT_SECTIONS` (QA-free):
    ```python
    ("NetworkIndicatorExtract", {
        "Enabled": False, "Provider": "", "Model": "", "Temperature": 0.0, "TopP": 0.9,
        "Prompt": {"prompt": "", "instructions": ""},
    }),
    ```
  - In both the `v2_to_ui_ordered_export()` and `ui_ordered_to_v2()` base-agent loops, add `"NetworkIndicatorExtract"` (these loops no longer pair a QA name -- match the current ScheduledTasksExtract entry shape, not the skill's `(base, qa)` tuple).

- [ ] **Step 3: migrate** -- in `workflow_config_migrate.py`, add ONE tuple to `_AGENT_FLAT_PREFIXES`:
  ```python
  ("NetworkIndicatorExtract", "NetworkIndicatorExtract", "NetworkIndicatorExtract_model"),
  ```

- [ ] **Step 4: subagent_utils** -- in `subagent_utils.py`:
  - `AGENT_TO_SUBAGENT["networkindicatorextract"] = "network_indicators"`
  - Add to `SUBAGENT_CANONICAL`: `"network_indicators"`, `"networkindicators"`, `"network-indicators"`, `"networkindicatorextract"`, and the short form `"network"` -> all map to `"network_indicators"`.

- [ ] **Step 5: default_agent_prompts** -- in `default_agent_prompts.py`, add `"NetworkIndicatorExtract": "NetworkIndicatorExtract"` to `AGENT_PROMPT_FILES` (no QA key).

- [ ] **Step 6: fix the migrate count assertion** -- in `tests/config/test_workflow_config_migrate.py:144`, change `assert len(config.Agents) == 9` to `== 10`. Grep the file for any other `== 9` agent-count assertions and bump them too.

- [ ] **Step 7: Run the wiring test + migrate test + full config suite**

Run:
```bash
python3 run_tests.py unit --paths tests/config/test_network_indicator_wiring.py tests/config/test_workflow_config_migrate.py
```
Expected: PASS. Then:
```bash
python3 run_tests.py unit --paths tests/config/
```
Expected: PASS (fix any UI-ordered export/import fixtures here -- see Task 14 if export/fidelity/backfill/traceability tests fail; they may, and are addressed there).

- [ ] **Step 8: Commit**
```bash
git add src/config/workflow_config_schema.py src/config/workflow_config_loader.py src/config/workflow_config_migrate.py src/utils/subagent_utils.py src/utils/default_agent_prompts.py tests/config/test_workflow_config_migrate.py
git commit -m "feat(config): wire NetworkIndicatorExtract into schema/loader/migrate/subagent-utils"
```

---

## Task 5: Wire llm_service + add normalization behavior test

**Files:**
- Modify: `src/services/llm_service.py` (lines ~2454 `_SIMPLE_EXTRACTORS`, ~2743 `expected_keys`, ~2808-2811 normalization ladder, Langfuse loop, top_p list)
- Test: `tests/config/test_network_indicator_wiring.py` (add `TestLLMServiceNormalization`)

- [ ] **Step 1: Add the normalization behavior test** (append to the wiring test file)

```python
class TestLLMServiceNormalization:
    def test_network_indicators_renames_to_items_and_keeps_value(self):
        # Behavior test: _SIMPLE_EXTRACTORS / _STRUCTURED_EXTRACTORS are function-local and
        # not importable, so assert the normalization behavior end-to-end instead.
        from src.services.llm_service import LLMService
        svc = LLMService.__new__(LLMService)  # no real init needed for the pure normalizer
        last_result = {"network_indicators": [
            {"value": "evil[.]com", "indicator_type": "domain",
             "source_evidence": "c2 evil[.]com", "extraction_justification": "x", "confidence_score": 0.9}
        ], "count": 1}
        out = svc._normalize_extraction_result(last_result, agent_name="NetworkIndicatorExtract")
        assert "items" in out and out["items"][0]["value"] == "evil[.]com"
        assert out.get("count") == 1
```

> Implementer note: confirm the exact normalizer method name/signature in `llm_service.py`
> (around lines 2769-2818). If the rename is not exposed as a callable method, instead assert
> via the public extraction entry point with a stubbed LLM response, or (preferred cleanup)
> promote `_SIMPLE_EXTRACTORS`/`_STRUCTURED_EXTRACTORS` to module-scope constants and assert
> `"NetworkIndicatorExtract" in _SIMPLE_EXTRACTORS`. Pick ONE and make the test concrete.

- [ ] **Step 2: Run it -- expect failure**

Run: `python3 run_tests.py unit --paths "tests/config/test_network_indicator_wiring.py::TestLLMServiceNormalization"`
Expected: FAIL (no `network_indicators` branch -> array not renamed to `items`).

- [ ] **Step 3: Implement llm_service edits**
  - Add `"NetworkIndicatorExtract"` to the `_SIMPLE_EXTRACTORS` tuple (line ~2454). (Optionally promote `_SIMPLE_EXTRACTORS`/`_STRUCTURED_EXTRACTORS` to module scope per Step 1 note.)
  - Add `"network_indicators"` to the `expected_keys` list (line ~2743).
  - Add a normalization branch to the if/elif ladder ending at line 2811:
    ```python
    elif "network_indicators" in last_result:
        last_result["items"] = last_result.pop("network_indicators")
    ```
  - Add `"network_indicators"` to the Langfuse output-key loop (the fixed list near line ~2873/2900) so Langfuse export captures it.
  - Add `"NetworkIndicatorExtract"` to the `top_p_extract` agent list.

- [ ] **Step 4: Run the behavior test + the source-substring assertions**

Run: `python3 run_tests.py unit --paths tests/config/test_network_indicator_wiring.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/services/llm_service.py tests/config/test_network_indicator_wiring.py
git commit -m "feat(llm_service): normalize network_indicators array + simple-extractor traceability"
```

---

## Task 6: Wire the workflow engine (agentic_workflow.py)

**Files:**
- Modify: `src/workflows/agentic_workflow.py` (`_AGENT_NAME_TO_SUBAGENT` ~520, `subresults` init ~1294, `sub_agents` ~1361, `subagent_to_agent` ~1279, `cat_to_agent`/`cat_to_subagent_name` ~1792/1800)
- Test: `tests/config/test_network_indicator_wiring.py` (add `TestWorkflowHelpers`)

- [ ] **Step 1: Add count/items helper tests** (append to wiring test)

```python
class TestWorkflowHelpers:
    def test_extract_actual_count(self):
        from src.workflows.agentic_workflow import _extract_actual_count
        subresults = {"network_indicators": {"items": [
            {"value": "evil[.]com", "indicator_type": "domain"},
            {"value": "8.8.8[.]8", "indicator_type": "ip"},
        ], "count": 2}}
        assert _extract_actual_count("network_indicators", subresults, execution_id=1) == 2

    def test_extract_actual_items_reads_value(self):
        from src.workflows.agentic_workflow import _extract_actual_items
        subresults = {"network_indicators": {"items": [{"value": "evil[.]com", "indicator_type": "domain"}], "count": 1}}
        items = _extract_actual_items("network_indicators", subresults)
        assert items == ["evil[.]com"]  # simple-extractor `value` is harvested by the existing field tuple
```

- [ ] **Step 2: Run -- expect failure** (`network_indicators` not in subresults/maps)

Run: `python3 run_tests.py unit --paths "tests/config/test_network_indicator_wiring.py::TestWorkflowHelpers"`
Expected: FAIL.

- [ ] **Step 3: Implement engine edits** -- add `NetworkIndicatorExtract`/`network_indicators` to each map, matching the ScheduledTasksExtract entries:
  - `_AGENT_NAME_TO_SUBAGENT`: `"NetworkIndicatorExtract": "network_indicators"`
  - `subresults` init dict: `"network_indicators": {"items": [], "count": 0}`
  - `sub_agents` driver list: add `("NetworkIndicatorExtract", "network_indicators")` (match the existing tuple shape)
  - `subagent_to_agent`: `"network_indicators": "NetworkIndicatorExtract"`
  - `cat_to_agent` / `cat_to_subagent_name`: add the network entries mirroring the others.

- [ ] **Step 4: Run -- expect pass**

Run: `python3 run_tests.py unit --paths "tests/config/test_network_indicator_wiring.py::TestWorkflowHelpers"`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/workflows/agentic_workflow.py tests/config/test_network_indicator_wiring.py
git commit -m "feat(workflow): dispatch + aggregate NetworkIndicatorExtract subresults"
```

---

## Task 7: Wire sigma_generation_service + eval_bundle_service + lmstudio_model_loader

**Files:**
- Modify: `src/services/sigma_generation_service.py` (both `observable_to_category` copies ~826, ~886)
- Modify: `src/services/eval_bundle_service.py` (subagent/model/error-log maps + the two `sub_agents` lists)
- Modify: `src/services/lmstudio_model_loader.py` (sub-agent preload list)

- [ ] **Step 1: sigma_generation_service** -- in BOTH `observable_to_category` dicts add network category routing:
  ```python
  "network_indicators": "network_connection",
  ```
  (If per-sub-type routing is wanted later, that is a follow-up; one alias->category entry is sufficient for expansion to trigger. Do NOT touch the pre-existing `registry_keys` vs `registry_artifacts` mismatch -- out of scope, noted in the spec.)

- [ ] **Step 2: eval_bundle_service** -- add `"NetworkIndicatorExtract"` / `"network_indicators"` entries to: the `agent_to_subagent_map`, the `agent_key_map` (-> `"extract_agent"`), the `model_key_map` (-> `"ExtractAgent"`), and BOTH `sub_agents` lists. Grep `ScheduledTasksExtract` in this file to find all five anchors.

- [ ] **Step 3: lmstudio_model_loader** -- append `"NetworkIndicatorExtract"` to the `sub_agents` preload list (grep `ScheduledTasksExtract`).

- [ ] **Step 4: Smoke-check imports**

Run:
```bash
python3 -c "import src.services.sigma_generation_service, src.services.eval_bundle_service, src.services.lmstudio_model_loader; print('import OK')"
```
Expected: `import OK`

- [ ] **Step 5: Commit**
```bash
git add src/services/sigma_generation_service.py src/services/eval_bundle_service.py src/services/lmstudio_model_loader.py
git commit -m "feat(services): route network_indicators through sigma observables, eval bundle, lmstudio preload"
```

---

## Task 8: Wire the routes (workflow_executions, evaluation_api, workflow_config) + API tests

**Files:**
- Modify: `src/web/routes/workflow_executions.py:494` (`OBS_TYPES`)
- Modify: `src/web/routes/evaluation_api.py` (`SUBAGENT_AGENT_MAP`, result-extraction branch, model-display loop, `SUBAGENT_RESULT_KEY_MAP`)
- Modify: `src/web/routes/workflow_config.py` (all hardcoded extractor lists ~489, 1114, 1279, 1883, 2271)
- Test: `tests/api/test_network_indicator_routes.py` (new)

- [ ] **Step 1: Write failing API tests** (new file `tests/api/test_network_indicator_routes.py`)

```python
"""API/route coverage for NetworkIndicatorExtract."""
import pytest
from pathlib import Path

pytestmark = pytest.mark.api

_REPO = Path(__file__).resolve().parent.parent.parent


def test_obs_types_includes_network_indicators():
    src = (_REPO / "src" / "web" / "routes" / "workflow_executions.py").read_text()
    assert '"network_indicators"' in src, "network_indicators missing from OBS_TYPES"


def test_workflow_config_lists_include_network_indicator():
    src = (_REPO / "src" / "web" / "routes" / "workflow_config.py").read_text()
    # Every hardcoded extractor list that mentions ScheduledTasksExtract must also mention the new agent.
    assert src.count("NetworkIndicatorExtract") >= src.count("ScheduledTasksExtract"), (
        "NetworkIndicatorExtract is under-represented vs ScheduledTasksExtract in workflow_config.py lists"
    )


def test_evaluation_api_maps_network_indicators():
    src = (_REPO / "src" / "web" / "routes" / "evaluation_api.py").read_text()
    assert '"network_indicators"' in src
```

> Implementer note: prefer behavior-level API tests (call the subagent-eval and observable
> endpoints with a fixture execution and assert `network_indicators` items are returned and
> grouped). The source-substring tests above are a floor; replace/augment them with endpoint
> tests following the existing `tests/api/` patterns for subagent eval + observable traceability.

- [ ] **Step 2: Run -- expect failure**

Run: `python3 run_tests.py api --paths tests/api/test_network_indicator_routes.py`
Expected: FAIL.

- [ ] **Step 3: Implement route edits**
  - `workflow_executions.py:494`: add `"network_indicators"` to `OBS_TYPES`.
  - `evaluation_api.py`: add `"network_indicators": "NetworkIndicatorExtract"` to `SUBAGENT_AGENT_MAP` and `SUBAGENT_RESULT_KEY_MAP`; add a result-extraction `elif result_key == "network_indicators"` branch mirroring an existing simple extractor; add `"NetworkIndicatorExtract"` to the sub-agent model-display loop.
  - `workflow_config.py`: add `"NetworkIndicatorExtract"` to EVERY hardcoded extractor list (grep `CmdlineExtract` to enumerate; ~5 spots incl. two `sub_agents = [...]`).

- [ ] **Step 4: Run -- expect pass**

Run: `python3 run_tests.py api --paths tests/api/test_network_indicator_routes.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/web/routes/workflow_executions.py src/web/routes/evaluation_api.py src/web/routes/workflow_config.py tests/api/test_network_indicator_routes.py
git commit -m "feat(routes): wire network_indicators into OBS_TYPES, eval API, workflow_config lists"
```

---

## Task 9: workflow.html render array + LOCKED list + locked-guard test bump

**Files:**
- Modify: `src/web/templates/workflow.html` (`LOCKED_EXTRACTOR_AGENTS` ~5827; subAgents render array; AGENT_CONFIG; sub-agent panel; model + prompt containers)
- Modify: `tests/unit/test_workflow_locked_extractor_agents.py` (`_EXPECTED_RENDER_ENTRIES` ~101; `count == 6` ~122; `test_scheduled_tasks_is_last` ~137; `test_actual_extraction_agents_remain` ~51)

- [ ] **Step 1: Update the locked-guard test FIRST (it will fail until workflow.html is edited)**
  - Append `("network_indicators", "NetworkIndicatorExtract")` to `_EXPECTED_RENDER_ENTRIES`.
  - Change `assert count == 6` to `== 7`.
  - Change `test_scheduled_tasks_is_last`: ScheduledTasksExtract is no longer last. Rewrite it to assert `"order: 7"` is present and that `NetworkIndicatorExtract` is the last entry (highest order). Keep a check that ScheduledTasksExtract is `order: 6`.
  - Add `"NetworkIndicatorExtract"` to the expected set in `test_actual_extraction_agents_remain`.

- [ ] **Step 2: Run -- expect failure** (workflow.html not yet edited)

Run: `python3 run_tests.py unit --paths tests/unit/test_workflow_locked_extractor_agents.py`
Expected: FAIL (count is 6 / entry missing in workflow.html).

- [ ] **Step 3: Edit workflow.html**
  - Append `"NetworkIndicatorExtract"` to the `LOCKED_EXTRACTOR_AGENTS` array literal (line ~5827).
  - Add to the subAgents render array (after the ScheduledTasksExtract entry):
    ```javascript
    { key: 'network_indicators', name: 'NetworkIndicatorExtract', display: 'Network Indicators Extraction', icon: '\u{1F310}', order: 7 },
    ```
  - Register the agent in `AGENT_CONFIG` (Category 2.1 in the workflow-html checklist) with the correct `providerKey` so `loadAgentModels()` populates the LMStudio dropdown.
  - Add the sub-agent panel (`#sa-networkindicator` or the convention used by siblings), the model container (`#networkindicatorextract-agent-model-container`), and the prompt container (`#networkindicatorextract-agent-prompt-container`), mirroring the ScheduledTasksExtract markup. NO QA toggle / NO `qaName`.

- [ ] **Step 4: Run -- expect pass**

Run: `python3 run_tests.py unit --paths tests/unit/test_workflow_locked_extractor_agents.py`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/web/templates/workflow.html tests/unit/test_workflow_locked_extractor_agents.py
git commit -m "feat(ui): add NetworkIndicatorExtract panel + render entry to workflow.html (6->7)"
```

---

## Task 10: Remaining UI wiring (display JS, observable-utils, eval templates, cache-bust)

**Files:**
- Modify: `src/web/static/js/components/workflow-config-display.js` (`workflowOrder`, `firstLevelSubAgents`, `subAgentOrder`)
- Modify: `src/web/static/js/components/observable-utils.js:11` (`OBS_TYPE_ORDER`)
- Modify: `src/web/templates/agent_evaluation.html` (eval card)
- Modify: `src/web/templates/agent_evals.html` (dropdown option, `SUBAGENT_MAP`, modal-title branch, count-noun ternary, string render path)
- Modify: `src/web/templates/subagent_evaluation.html` (purpose block)
- Modify: `src/web/templates/workflow_executions.html` (`_DN` entry + subAgents array entry)
- Modify: `src/web/templates/base.html` (cache-bust `?v=` bump for workflow-config-display.js)

- [ ] **Step 1: workflow-config-display.js** -- add `'NetworkIndicatorExtract'` to `workflowOrder` (before `'SIGMA'`) and to `firstLevelSubAgents`; add `{ id: 'NetworkIndicatorExtract', name: 'NetworkIndicatorExtract' }` to `subAgentOrder` (NO `qa:` key). Do NOT touch `secondLevelSubAgents` (it is empty/QA-only).

- [ ] **Step 2: observable-utils.js:11** -- append `'network_indicators'` to `OBS_TYPE_ORDER` (it MUST stay in sync with AGENT_NAMES_SUB).

- [ ] **Step 3: agent_evaluation.html** -- add an eval card linking to `/evaluations/ExtractAgent/NetworkIndicatorExtract` with the globe icon as an HTML entity `&#x1F310;` and the description "Network indicators (DNS, IP/port, URL/URI, User-Agent)."

- [ ] **Step 4: agent_evals.html** -- add `<option value="network_indicators">Network Indicators</option>`; add `'network_indicators': 'NetworkIndicatorExtract'` to `SUBAGENT_MAP`; add a modal-title branch (`else if (resultType === 'network_indicators' ...) { modalTitle.textContent = 'Extracted Network Indicators'; agentName = 'NetworkIndicatorExtract'; }`); add a `'network indicator(s)'` arm to the count-noun ternary. Because items are simple `{value, indicator_type}`, use the STRING/value render path (like cmdline) -- show `value` with the `indicator_type` as a small label. DROP any QA ternary (agent_evals.html is QA-free).

- [ ] **Step 5: subagent_evaluation.html** -- add `{% elif subagent_name == 'NetworkIndicatorExtract' %}` purpose block: "Purpose: extracts network indicators (domain/DNS, IP+port, URL, URI path, User-Agent) verbatim; downstream SigmaAgent generalizes them into detection rules."

- [ ] **Step 6: workflow_executions.html** -- add `'NetworkIndicatorExtract': 'Network Indicators Extraction'` to the `_DN` dict and a subAgents render-array entry `{ key:'network_indicators', name:'NetworkIndicatorExtract', display: _DN['NetworkIndicatorExtract'], icon:'\u{1F310}', order: 7 }` (NO qaName). Grep `ServicesExtract` to find both locations.

- [ ] **Step 7: base.html** -- bump the `workflow-config-display.js?v=YYYYMMDD` query string to today's date (`20260617`).

- [ ] **Step 8: Smoke-check the JS files parse** (node if available, else skip)
```bash
node --check src/web/static/js/components/observable-utils.js && echo "obs-utils OK" || echo "(node unavailable -- verify in browser)"
```

- [ ] **Step 9: Commit**
```bash
git add src/web/static/js/components/workflow-config-display.js src/web/static/js/components/observable-utils.js src/web/templates/agent_evaluation.html src/web/templates/agent_evals.html src/web/templates/subagent_evaluation.html src/web/templates/workflow_executions.html src/web/templates/base.html
git commit -m "feat(ui): wire NetworkIndicatorExtract into config display, observables, eval templates"
```

---

## Task 11: Observable-traceability + Playwright test bumps (6->7)

**Files:**
- Modify: `tests/unit/test_observable_traceability_regressions.py` (obs-type parametrize ~122-133)
- Modify: `tests/playwright/execution_detail_tabs.spec.ts` (`all six` wording ~377/557, OBS_TYPE_ORDER offset math ~604-628, subresults fixtures)

- [ ] **Step 1: Add `network_indicators` to the obs-type parametrize** in `test_observable_traceability_regressions.py` (`TestObservableTypeCoverage`).

- [ ] **Step 2: Run the regression test**

Run: `python3 run_tests.py unit --paths tests/unit/test_observable_traceability_regressions.py`
Expected: PASS (asserts `network_indicators` appears in `_build_observables_response`).

- [ ] **Step 3: Update `execution_detail_tabs.spec.ts`** -- add `network_indicators` to the subresults fixtures, change "all six" -> "all seven" wording, and fix the OBS_TYPE_ORDER flat-index offset math for 7 types.

- [ ] **Step 4: Run the playwright spec** (requires the dev server / playwright harness)

Run: `python3 run_tests.py ui --playwright-only`
Expected: PASS (the seven-card execution-detail assertions).

- [ ] **Step 5: Commit**
```bash
git add tests/unit/test_observable_traceability_regressions.py tests/playwright/execution_detail_tabs.spec.ts
git commit -m "test(ui): extend observable-traceability + execution-detail specs to 7 extractors"
```

---

## Task 12: Quickstart presets (9 files) + sibling embedded-prompt re-sync

**Files:**
- Modify: 9 files in `config/presets/AgentConfigs/quickstart/`
- Test: `tests/config/test_network_indicator_wiring.py` (add `TestPresetFiles`)

- [ ] **Step 1: Add the preset-coverage test** (append to wiring test, mirrors the scheduledtasks pattern)

```python
class TestPresetFiles:
    def test_presets_have_network_indicators(self):
        import json
        from pathlib import Path
        d = _REPO / "config" / "presets" / "AgentConfigs" / "quickstart"
        files = list(d.glob("*.json"))
        assert files
        for f in files:
            data = json.loads(f.read_text())
            assert "NetworkIndicatorExtract" in data, f"missing in {f.name}"
            sec = data["NetworkIndicatorExtract"]
            assert sec.get("Model"), f"empty Model in {f.name}"
            assert sec.get("Prompt", {}).get("prompt"), f"empty Prompt.prompt in {f.name}"
            assert "QAEnabled" not in sec and "QA" not in sec, f"QA keys must be absent in {f.name}"
```

- [ ] **Step 2: Run -- expect failure**

Run: `python3 run_tests.py unit --paths "tests/config/test_network_indicator_wiring.py::TestPresetFiles"`
Expected: FAIL.

- [ ] **Step 3: Add the agent block to all 9 presets via script** (populates `Prompt.prompt` from disk; copies each preset's existing ScheduledTasksExtract Provider/Model so the model tier matches that preset):

```python
import json, glob
with open("src/prompts/NetworkIndicatorExtract") as f:
    extract_prompt = f.read().strip()
for path in glob.glob("config/presets/AgentConfigs/quickstart/*.json"):
    with open(path) as f:
        data = json.load(f)
    tmpl = data.get("ScheduledTasksExtract", {})  # match this preset's provider/model tier
    data["NetworkIndicatorExtract"] = {
        "Enabled": True,
        "Provider": tmpl.get("Provider", ""),
        "Model": tmpl.get("Model", ""),
        "Temperature": 0.0,
        "TopP": 0.9,
        "Prompt": {"prompt": extract_prompt, "instructions": ""},
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
print("presets updated")
```

- [ ] **Step 4: Re-sync the 6 sibling prompts' embedded copies** (Task 2 edited the disk prompts; presets embed a stale copy):

```python
import json, glob
AGENTS = ["CmdlineExtract","ProcTreeExtract","RegistryExtract","ServicesExtract","ScheduledTasksExtract","HuntQueriesExtract"]
src = {a: open(f"src/prompts/{a}").read().strip() for a in AGENTS}
for path in glob.glob("config/presets/AgentConfigs/quickstart/*.json"):
    with open(path) as f:
        data = json.load(f)
    for a in AGENTS:
        if a in data and "Prompt" in data[a]:
            data[a]["Prompt"]["prompt"] = src[a]
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
print("sibling prompts re-synced")
```

- [ ] **Step 5: Run the preset test + a full-load sanity check**

Run: `python3 run_tests.py unit --paths "tests/config/test_network_indicator_wiring.py::TestPresetFiles"`
Expected: PASS. Then verify one preset loads + flattens:
```bash
python3 -c "import json; from src.config.workflow_config_loader import load_workflow_config; d=json.load(open('config/presets/AgentConfigs/quickstart/Quickstart-LMStudio-Qwen3.json')); c=load_workflow_config(d); f=c.flatten_for_llm_service(); assert f['NetworkIndicatorExtract_model']; print('preset load OK:', f['NetworkIndicatorExtract_model'])"
```
Expected: `preset load OK: <model>`

- [ ] **Step 6: Commit**
```bash
git add config/presets/AgentConfigs/quickstart/ tests/config/test_network_indicator_wiring.py
git commit -m "feat(presets): add NetworkIndicatorExtract to 9 quickstart presets + re-sync sibling prompts"
```

---

## Task 13: Eval data (articles.json + eval_articles.yaml)

**Files:**
- Create: `config/eval_articles_data/network_indicators/articles.json`
- Modify: `config/eval_articles.yaml` (`subagents.network_indicators` list)
- Test: `tests/config/test_network_indicator_wiring.py` (add `TestEvalArticlesData`, mirroring the scheduledtasks version)

- [ ] **Step 1: Add the eval-data test** (append; mirror `TestEvalArticlesData` from `test_scheduledtasks_wiring.py` -- dir exists, articles.json parses as list with required fields `{url,title,content,expected_count}`, no dup URLs, yaml `subagents.network_indicators` non-empty, yaml<->json count + URL match).

- [ ] **Step 2: Run -- expect failure** (dir/yaml key missing).

Run: `python3 run_tests.py unit --paths "tests/config/test_network_indicator_wiring.py::TestEvalArticlesData"`
Expected: FAIL.

- [ ] **Step 3: Pick indicator-rich articles from the live DB** (abundant atomic substrate). Query for candidates:
```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper -c \
"SELECT a.id, a.title FROM articles a WHERE a.content ~* '(hxxp|[0-9]{1,3}\[\.\][0-9]{1,3}|user-agent|/gate\.php|duckdns|beacon)' ORDER BY a.created_at DESC LIMIT 25;"
```
Choose ~6-10 articles that contain explicit, attacker-attributed network indicators (skip ones that are pure prose / benign).

- [ ] **Step 4: Add the chosen URLs to `config/eval_articles.yaml`** under `subagents.network_indicators` (mirror the `scheduled_tasks` block shape: a list of `{url: ..., expected_count: N}` or whatever shape the existing entries use -- match exactly).

- [ ] **Step 5: Populate `articles.json` via the static fetch script**
```bash
python3 scripts/fetch_eval_articles_static.py
```
This writes `config/eval_articles_data/network_indicators/articles.json` from the yaml URLs. (If the script is subagent-scoped, pass the appropriate flag -- check `--help`.)

- [ ] **Step 6: Run the eval-data test**

Run: `python3 run_tests.py unit --paths "tests/config/test_network_indicator_wiring.py::TestEvalArticlesData"`
Expected: PASS (yaml<->json counts match).

- [ ] **Step 7: Commit**
```bash
git add config/eval_articles.yaml config/eval_articles_data/network_indicators/ tests/config/test_network_indicator_wiring.py
git commit -m "feat(eval): seed network_indicators eval articles + yaml contract"
```

---

## Task 14: Remaining config/contract test updates

**Files:**
- Modify: `tests/config/test_workflow_config_export.py` (UI-ordered fixture +section)
- Modify: `tests/config/test_workflow_config_import_export_fidelity.py` (6-field block, NO QA constants)
- Modify: `tests/config/test_backfill_sub_agents.py` (`BACKFILL_AGENTS` += agent)
- Modify: `tests/config/test_subagent_traceability_contract.py` (`MIGRATED_EXTRACT_AGENTS` += agent; NO QA)
- Modify: `tests/worker/test_test_agents_provider_resolution.py` (parametrize += agent)
- Modify: `tests/integration/test_lmstudio_minimal_e2e.py` (`disabled_agents` += agent, ~line 189)

- [ ] **Step 1: Make each edit** (all are "add `NetworkIndicatorExtract`/`network_indicators` to a list/fixture", no QA fields):
  - `test_workflow_config_export.py`: add a `NetworkIndicatorExtract` section to the UI-ordered preset fixture with the 6 required keys (Enabled/Provider/Model/Temperature/TopP/Prompt).
  - `test_workflow_config_import_export_fidelity.py`: add a 6-field `NetworkIndicatorExtract` block to `_full_ui_ordered_preset` plus a `FIDELITY_NETWORK_INDICATOR_ENABLED = True` constant. Add NO `*_QA_ENABLED` constant and NO QA keys.
  - `test_backfill_sub_agents.py`: append `"NetworkIndicatorExtract"` to `BACKFILL_AGENTS`.
  - `test_subagent_traceability_contract.py`: append `"NetworkIndicatorExtract"` to `MIGRATED_EXTRACT_AGENTS` (its json_example uses `count`). Add nothing QA-related (no `MIGRATED_QA_AGENTS`, no `base_for_qa`).
  - `test_test_agents_provider_resolution.py`: add `"NetworkIndicatorExtract"` to the `@pytest.mark.parametrize` agent list.
  - `test_lmstudio_minimal_e2e.py`: append `"NetworkIndicatorExtract"` to the `disabled_agents` list (~line 189).

- [ ] **Step 2: Run the full config suite + the QA-deprecation guard**

Run:
```bash
python3 run_tests.py unit --paths tests/config/
python3 run_tests.py unit --paths tests/config/test_qa_full_deprecation.py
```
Expected: PASS (QA guard must stay green -- proves we added zero QA).

- [ ] **Step 3: Commit**
```bash
git add tests/config/test_workflow_config_export.py tests/config/test_workflow_config_import_export_fidelity.py tests/config/test_backfill_sub_agents.py tests/config/test_subagent_traceability_contract.py tests/worker/test_test_agents_provider_resolution.py tests/integration/test_lmstudio_minimal_e2e.py
git commit -m "test: extend config/contract/provider/e2e suites to NetworkIndicatorExtract (7th, no QA)"
```

---

## Task 15: Full verification + browser check

**Files:** none (verification only)

- [ ] **Step 1: Restart containers** (`.py` edits require it)
```bash
docker restart cti_web cti_worker cti_workflow_worker cti_scheduler
```

- [ ] **Step 2: Run the broad suites**
```bash
python3 run_tests.py unit --paths tests/config/ tests/unit/
python3 run_tests.py api
```
Expected: PASS.

- [ ] **Step 3: Preset backward-compat** -- import a preset with the `NetworkIndicatorExtract` block removed; confirm clean import + agent defaults to disabled:
```bash
python3 -c "import json,copy; from src.config.workflow_config_loader import load_workflow_config; d=json.load(open('config/presets/AgentConfigs/quickstart/Quickstart-LMStudio-Qwen3.json')); d.pop('NetworkIndicatorExtract',None); c=load_workflow_config(d); print('backward-compat OK; disabled:', 'NetworkIndicatorExtract' in c.Execution.ExtractAgentSettings.DisabledAgents or 'NetworkIndicatorExtract' not in c.Agents)"
```
Expected: `backward-compat OK; disabled: True`

- [ ] **Step 4: Browser verification** at http://127.0.0.1:8001/workflow#config (hard-reload to bust JS cache):
  - Workflow Overview shows 7 sub-agents.
  - Selected Models panel lists NetworkIndicatorExtract with provider/model.
  - Expand ExtractAgent -> NetworkIndicatorExtract panel shows provider dropdown, model dropdown (LMStudio dropdown populates when LMStudio selected), temperature, top_p, prompt editor, Test button. NO QA toggle.
  - No console errors mentioning NetworkIndicatorExtract.

- [ ] **Step 5: Test button** -- click "Test NetworkIndicatorExtract" with a known indicator-rich article; confirm it uses the configured provider (not an ExtractAgent fallback) and returns `network_indicators` items with verbatim `value`s.

- [ ] **Step 6: Final status** -- confirm working tree clean and summarize PASS.

---

## Self-Review (completed during planning)

**Spec coverage:** Every spec section maps to a task -- identifiers (T1,T4), schema (T4), prompt + siblings (T1,T2), llm_service simple/normalization (T5), engine (T6), sigma/eval-bundle/lmstudio (T7), routes incl. workflow_config (T8), UI incl. locked guard + observable sync (T9,T10,T11), presets + sibling re-sync (T12), eval data incl. the eval_articles.yaml addendum (T13), all listed tests (T3,T4,T5,T6,T8,T9,T11,T12,T13,T14), verification + QA-guard (T14,T15). No gaps.

**Placeholder scan:** No TBD/TODO. Two explicit implementer-judgment notes (the llm_service normalizer method name in T5, and behavior-vs-substring API tests in T8) are flagged as "pick ONE and make it concrete" rather than left vague.

**Type/name consistency:** `NetworkIndicatorExtract` (agent), `network_indicators` (alias/array/result_key/eval-dir), `networkindicatorextract` (prefix), `'\u{1F310}'`/`&#x1F310;` (icon) used identically across all tasks. Render entry uses `order: 7` consistently (T9, T10). Migrate count `9 -> 10` (T4). Locked render count `6 -> 7` (T9).
