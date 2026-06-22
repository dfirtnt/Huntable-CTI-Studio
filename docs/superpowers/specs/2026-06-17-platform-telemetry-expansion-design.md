# Platform Telemetry Expansion -- Design Spec

- Date: 2026-06-17 (reworked 2026-06-19 for goal-mode execution)
- Status: Approved for build — executing via `/goal`. Operator decisions captured. A
  build agent is already mid-flight on phase one, so this goal is **convergent**: it
  describes the verified end-state and drives existing progress to green, not a restart.
- Branch: europa-dev

---

## 0. Goal-mode execution contract (run via `/goal`)

Phase one is executed with Claude Code's `/goal` — an autonomous turn-loop that keeps
working until a completion condition is met.

### 0.1 The one constraint that shapes everything

`/goal` loops turns until a **separate fast evaluator model** judges the condition met.
The evaluator **reads only this conversation transcript** — it runs no tools, opens no
files, and cannot see a browser. Two consequences govern the entire spec:

- **Evidence must be printed, not asserted.** "I added platform routing" proves
  nothing to the evaluator. A pasted `run_tests.py` summary showing the platform tests
  PASSED is proof. The build agent must run the acceptance suite and print its output
  every turn.
- **UI acceptance must be a test, not a look.** The platform badge and capability
  matrix are invisible to the evaluator. They count as done only when a Playwright spec
  asserts them and prints green. Browser-level verification is still required for the
  human reviewer (repo policy), but it is **not** how the goal confirms done.

### 0.2 The goal condition (paste verbatim into `/goal`)

```text
/goal Phase-one Platform Telemetry Expansion is DONE when the agent has, in THIS
conversation, printed passing output for ALL of the following with no failures:

(1) `.venv/bin/python run_tests.py --paths tests/workflows/test_platform_telemetry_phase_one.py --output-format quiet`
exits 0 with every test PASSED. That module asserts the phase-one product contract:
Linux-only executions skip the Windows-only extractors (RegistryExtract, ServicesExtract,
ScheduledTasksExtract) with a structured record carrying reason_code, supported_platforms,
detected_platforms; every observable carries a non-null platform in
{windows,linux,macos,cross_platform,unknown}; Linux process/cmdline evidence generates
backend-neutral Sigma with an explicit logsource plus platform and generation_basis
metadata; mixed Windows/Linux articles produce separate per-platform/logsource rule
groups; macOS-only articles generate NO macOS Sigma; every generated rule passes pySigma
validation (valid YAML, non-empty detection selection, >=1 observable) and Linux
process_creation rules use no Windows-only fields.

(2) `.venv/bin/python run_tests.py ui --area workflow` prints all Playwright specs green,
including a spec asserting the Linux/platform badge renders in the shared review queue,
a spec asserting the read-only platform capability matrix renders in Workflow Config, and
the renamed Platform Detection spec (formerly agent_config_os_detection.spec.ts).

(3) `.venv/bin/python run_tests.py regression --output-format quiet` shows no new failures
versus baseline — no drop in huntability/ranking scores, no break to legacy execution API
serializers.

GUARDRAILS — the goal is NOT met if any were violated: do not mutate eval-article DB rows
or config/eval_articles_data fixtures; do not rename or generalize the Windows artifact
taxonomy; if any src/prompts/*.txt changed, the 9 config/presets/AgentConfigs/quickstart/*.json
files were updated to match; schema/model changes (src/config/workflow_config_schema.py,
src/database/models.py) ship with a migration and backward-compatible serializers; no
historical executions were backfilled; test output was never piped through `| tail`.

Read docs/superpowers/specs/2026-06-17-platform-telemetry-expansion-design.md for full
detail. Print the actual test summaries each turn so this condition can be confirmed. If
blocked on an operator decision (e.g. whether a conditionally-in-scope extractor is ready)
or any destructive step, STOP and surface it instead of guessing. Otherwise stop after 25
turns.
```

### 0.3 Definition of Done — the acceptance suite the agent runs each turn

All proof points collapse into one Python acceptance module plus the `workflow`
Playwright project, so a single command sequence demonstrates the whole contract:

```bash
# 1. Product-contract assertions (create/extend this module)
.venv/bin/python run_tests.py --paths tests/workflows/test_platform_telemetry_phase_one.py --output-format quiet
# 2. UI acceptance (badge + capability matrix + renamed Platform Detection spec)
.venv/bin/python run_tests.py ui --area workflow
# 3. No regressions (scores, legacy serializers)
.venv/bin/python run_tests.py regression --output-format quiet
```

Print the final summary lines from each command. Never pipe through `| tail` — it hides
progress and starves the evaluator of the very output it judges.

### 0.4 Guardrails — the goal is unmet if any are violated

| Guardrail | Why |
|---|---|
| Never mutate eval-article DB rows or `config/eval_articles_data` fixtures. | Ground truth is forward-only; pipeline fixes never chase GT. |
| Do not rename/generalize the Windows artifact taxonomy. | Phase-one boundary is capability metadata + skip reasons (§4). |
| If any `src/prompts/*.txt` changed, update the 9 `config/presets/AgentConfigs/quickstart/*.json` (3 distinct variants). | Editing prompts alone silently desyncs the presets. |
| `src/config/workflow_config_schema.py` and `src/database/models.py` are contracts — change deliberately, ship a migration, keep serializers backward-compatible. | New executions only; legacy rows must still deserialize (§8). |
| No backfill/migration of historical executions. | Explicit out-of-scope (§2). |
| Huntability/ranking scores must not drop. | Platform support is additive (§2); the regression suite guards this. |

### 0.5 Bound and stop conditions

- **Turn bound:** `stop after 25 turns` caps runaway loops.
- **Hard stop on judgment calls:** if blocked on an operator decision — e.g. whether
  NetworkIndicatorExtract / HuntQueries confidence is good enough to pull a
  conditionally-in-scope item (§2) into this run — or on any destructive/irreversible
  step, the agent stops and surfaces it rather than guessing.
- **Resume:** if the session ends with the goal active, `--resume`/`--continue` carries
  the condition over (the turn counter resets).

---

## 1. Goal

Expand the agentic workflow from Windows-only routing to platform-aware telemetry
coverage, with Linux host command/process telemetry as the first generation-capable
non-Windows slice.

The primary product outcome is **broader telemetry coverage visibility**. Phase one
should make platform handling explicit in each workflow execution, run only extractors
that are capable for the detected platform evidence, and generate reviewable Sigma
rules for supported Linux command/process telemetry.

---

## 2. Phase-one scope

### In scope

- Rename the workflow concept from **OS Detection** to **Platform Detection** in docs
  and UI copy where this behavior is described.
- Change platform handling from a hard Windows gate to capability-based routing.
- Detect and preserve multiple platforms per article, including mixed Windows/Linux
  articles.
- Require every observable to carry a `platform` value from this controlled set:
  - `windows`
  - `linux`
  - `macos`
  - `cross_platform`
  - `unknown`
- Add first-class telemetry metadata to each observable:
  - `telemetry_category`
  - `telemetry_confidence`
  - `logsource_hint`
  - `platform_confidence`
  - `platform_rationale`
- Enable Linux Sigma generation for:
  - command lines
  - process execution metadata
  - parent/child process lineage
- Generate separate Sigma rules per platform/logsource group for mixed-platform
  articles.
- Use backend-neutral Sigma output first, with explicit logsource declarations.
- Keep Linux-generated rules in the same review queue as Windows rules, with a
  platform badge.
- Store structured extractor skip/capability reasons and render them in the workflow
  trace.
- Show a read-only platform capability matrix in Workflow Config.
- Expose platform fields through existing execution/review APIs.
- Preserve existing huntability/ranking score behavior; platform support does not
  lower article quality scores.

### Conditionally in scope

- Network observables may participate in Linux Sigma generation if the network
  observable feature is ready and each item carries platform/logsource confidence.
- HuntQueries may participate in Sigma generation only when backend and target
  telemetry are clear.
- `unknown` and `cross_platform` observables may generate standalone backend-neutral
  Sigma only when detection intent, telemetry category, field mapping, and explicit
  Sigma logsource are clear.

### Out of scope for phase one

- Linux persistence artifacts such as cron, systemd timers, SSH authorized keys,
  shell profile modification, PAM/sudoers edits, or similar persistence surfaces.
- macOS Sigma generation.
- Cloud/SaaS audit telemetry generation.
- Cross-platform behavior-family deduplication.
- Historical backfill/migration of old workflow executions.
- Aggregate reporting/dashboard metrics. Per-execution UI visibility is sufficient
  for phase one.
- A supportability status enum. Use structured skip/capability reasons instead.

---

## 3. Platform routing behavior

Platform Detection returns platform context, not a binary pass/fail gate.

Expected behavior:

- Windows-only articles continue through the current Windows-capable path.
- Linux-only articles run Linux-capable extractors and skip Windows-only extractors
  with structured skip reasons.
- Mixed Windows/Linux articles run applicable extractors for each platform and group
  generated rules by platform/logsource.
- macOS-only articles may extract/display platform-agnostic huntables, but do not
  generate macOS Sigma in phase one.
- Unsupported-only articles still create completed workflow executions with visible
  skip/capability reasons. They should not disappear silently.
- Platform assignment is observable-scoped. Article-level platform detection informs
  routing, but an individual observable's platform and telemetry metadata control
  rule-generation eligibility.

The execution trace should make expected skips explicit. Example:

```text
RegistryExtract skipped: extractor supports windows only; detected evidence platform linux.
```

Structured skip/capability records should use a stable shape:

```json
{
  "extractor": "RegistryExtract",
  "status": "skipped",
  "reason_code": "unsupported_platform",
  "reason": "Extractor supports windows only; detected evidence platform linux.",
  "supported_platforms": ["windows"],
  "detected_platforms": ["linux"],
  "telemetry_categories": ["registry"]
}
```

Use `reason_code` for UI/reporting logic and `reason` for human trace display.

Routing has three separate stages:

1. Evidence classification: identify platform, telemetry category, and confidence for
   extracted evidence.
2. Extractor capability filtering: run only extractors whose declared capabilities can
   handle the detected evidence family.
3. Rule-generation eligibility: generate Sigma only when the observable group has a
   supported telemetry category, explicit logsource, and sufficient platform/logsource
   confidence.

Do not treat "extractor supports linux" as proof that Linux evidence exists in the
article. Capability is about what the extractor can handle; evidence classification is
about what the article actually contains.

---

## 4. Extractor capability model

Phase one should keep the existing Extract Agent flow and add capability metadata
instead of creating a separate Linux workflow.

Initial capability intent:

| Extractor | Phase-one capability intent |
|---|---|
| CmdlineExtract | Platform-aware; supports Windows/Linux/macOS tagging where evidence is clear. |
| ProcTreeExtract | Platform-aware; supports Windows/Linux/macOS tagging where evidence is clear. |
| NetworkIndicatorExtract | Platform-aware or cross-platform if implemented with platform/logsource confidence. |
| HuntQueriesExtract | Backend/query-language aware; not OS-first. |
| RegistryExtract | Windows only. |
| ServicesExtract | Windows only in phase one. |
| ScheduledTasksExtract | Windows only in phase one. |

Do not rename or generalize the Windows-specific artifact taxonomy in phase one.
Capability metadata and skip reasons are the boundary. Generalized future taxonomy
should wait until Linux persistence/service-manager artifacts are actually designed.

---

## 5. Observable platform contract

Every observable must include platform and telemetry metadata. The platform value may
be `unknown`, but it must not be missing.

Use:

- `windows`, `linux`, or `macos` when the source evidence clearly implies an OS.
- `cross_platform` for genuinely OS-neutral observables, such as some network
  indicators or backend-neutral hunt queries.
- `unknown` when the observable is useful but platform assignment is not supported
  by the article evidence.

Required routing fields:

| Field | Purpose |
|---|---|
| `platform` | Observable-scoped OS/platform assignment. |
| `platform_confidence` | Confidence in the platform assignment. |
| `platform_rationale` | Short reason for the assignment, based on source evidence. |
| `telemetry_category` | Detection telemetry family, such as `process_creation`, `network_connection`, `registry`, or `hunt_query`. |
| `telemetry_confidence` | Confidence that the observable maps to that telemetry family. |
| `logsource_hint` | Sigma logsource hint or explicit backend/logsource target when known. |

Attribution rules:

- Do not infer `linux` from generic commands like `curl`, `ssh`, `python`, or `bash`
  unless the article evidence supports Linux context.
- Prefer `unknown` when a command or artifact appears on multiple platforms and the
  surrounding evidence does not disambiguate it.
- Prefer `cross_platform` only when the detection target is genuinely OS-neutral and
  the telemetry category/logsource remains meaningful without choosing an OS.
- In mixed articles, observable-level platform metadata wins over article-level
  `primary_platform`.
- If a Linux article contains a Windows artifact such as `C:\Windows\Temp\foo.exe`,
  that observable should be tagged `windows` when the evidence supports it.
- WSL/container cases should not be forced into a pure OS bucket. Use `unknown` or
  the host platform with rationale until a future `execution_environment` dimension
  is designed.

Future work may add an `execution_environment` field for containers, WSL, Kubernetes,
and similar contexts. It is not required in phase one.

---

## 6. Sigma generation contract

Phase-one Linux Sigma generation targets backend-neutral Sigma first. Backend-neutral
does not mean logsource-vague: every generated rule must declare an explicit Sigma
logsource.

For command/process telemetry, the default target is Linux process creation-style
Sigma. The implementation should not prematurely encode Sysmon for Linux, auditd,
Elastic, Splunk CIM, CrowdStrike, or Defender assumptions unless the source evidence
or HuntQuery target clearly requires it.

Sigma generation is driven by telemetry category and logsource eligibility. Platform
is a constraint, not the primary abstraction. For phase one:

- `telemetry_category=process_creation` with `platform=linux` may generate Linux
  process creation-style Sigma when the command/process evidence is explicit.
- `cross_platform` and `unknown` observables may generate standalone Sigma only when
  `telemetry_category`, field mapping, and `logsource_hint` are clear.
- A generated rule must carry metadata that identifies the generation basis, such as
  `generation_basis: process_creation_generic`, and the detection readiness, such as
  `detection_readiness: generic`.
- `detection_readiness=generic` means the rule is valid portable Sigma intent, not a
  guarantee that every backend can compile or deploy it unchanged.

Generation-basis, detection-readiness, platform, and telemetry metadata should be
stored in the rule metadata/review-queue record, not forced into pySigma-validated
rule YAML. If any temporary grounding fields are emitted in YAML for LLM prompting,
strip them before pySigma validation the same way `observables_used` is stripped
today.

Mixed-platform articles generate separate rules per platform/logsource group. A single
combined Windows/Linux Sigma rule is not phase-one behavior.

Do not generate duplicate platform-specific rules from generic evidence. If an
observable's platform confidence is low, either keep it for display or generate a
standalone backend-neutral rule only when the telemetry category/logsource is explicit.

Similarity/deduplication should remain platform-aware by default. Windows, Linux, and
macOS process rules should not be treated as the same canonical class unless a future
behavior-family dedupe layer is explicitly designed.

---

## 7. Review queue and UI behavior

Linux-generated rules enter the same review queue as Windows rules.

Phase-one review UI adds a platform badge only. Do not add platform/logsource filters
in phase one unless a later UI task explicitly expands the scope.

Generated Sigma rule titles should not be force-prefixed with platform text. Platform
belongs in metadata and UI badges unless a title would otherwise be ambiguous.

Workflow Config should show a read-only platform capability matrix. Do not add
operator toggles per platform/extractor in phase one.

In goal-mode (§0), both the platform badge and the capability matrix count as delivered
only when a Playwright spec asserts them and prints green — the evaluator cannot see a
browser. As part of the OS Detection → Platform Detection rename, the existing
`tests/playwright/agent_config_os_detection.spec.ts` is renamed/retargeted to the
Platform Detection spec and must keep passing.

---

## 8. API behavior

Expose platform and telemetry routing fields through existing workflow execution and
review APIs. Do not add a platform-specific endpoint unless the existing payloads
become too heavy.

Existing executions are not migrated or backfilled. Platform fields apply to new
workflow executions only. API serializers must remain backward-compatible with legacy
executions where these fields are absent.

---

## 9. Acceptance bar

The operator-selected minimum release bar for phase one fixtures is:

- no crashes
- valid generated Sigma YAML

This is intentionally a low wiring bar. The implementation should still add lightweight
product-contract assertions where cheap, especially:

- Linux-only executions skip Windows-only extractors with structured reasons.
- Linux-generated rules carry Linux/platform metadata.
- Mixed Windows/Linux executions generate per-platform/logsource groups.
- macOS-only executions do not generate macOS Sigma.
- Generated rules contain at least one extracted observable.
- Generated rules contain an explicit logsource.
- Generated rules contain platform metadata and generation-basis metadata.
- Generated rules contain a non-empty detection selection.
- Linux rules do not use Windows-only fields when the telemetry category is Linux
  process creation.

The fixture set should cover at least:

- Linux-only command/process article.
- Mixed Windows/Linux article.
- macOS-only article.
- Ambiguous-platform command/process evidence.
- Network observable article, if NetworkIndicatorExtract is ready.
- HuntQuery article with clear backend and target telemetry.
- Linux persistence article where persistence artifacts are deferred/skipped.

### 9.1 How the bar is proven in goal-mode

Because the `/goal` evaluator confirms "done" only from printed transcript output (§0.1),
every assertion above lives in the acceptance suite of §0.3 and is proven by a pasted
test summary — not by description:

- The product-contract bullets (Linux skips Windows-only extractors with structured
  reasons; Linux rules carry platform metadata; mixed articles split per
  platform/logsource; macOS generates no Sigma; rules have logsource + observable +
  non-empty selection + no Windows-only fields on Linux process_creation) →
  `tests/workflows/test_platform_telemetry_phase_one.py`, one test per bullet.
- "No crashes / valid generated Sigma YAML" → the same module drives each fixture
  end-to-end and runs every emitted rule through pySigma validation.
- Badge + capability matrix render → the `workflow` Playwright project (§7).
- No score regression / legacy serializers intact → `run_tests.py regression`.

The fixture set below seeds that module. Conditional fixtures (network, HuntQuery) are
included only if their extractor is confirmed ready this run; if not, the agent stops and
surfaces the decision per §0.5 rather than silently dropping the fixture.

---

## 10. Deferred work and explicit follow-ups

Phase-one follow-ups are tracked in
`docs/superpowers/specs/2026-06-19-platform-telemetry-followups.md`.

Create tracked backlog/TODO items during phase-one implementation for:

- Linux persistence extraction: cron, systemd timers, SSH authorized keys, shell
  profiles, PAM/sudoers, and related artifacts.
- macOS Sigma generation.
- Cross-platform behavior-family similarity/deduplication.
- Review of whether shared CmdlineExtract/ProcTreeExtract quality is sufficient after
  enough Linux rules have been reviewed.
- Backend-specific Sigma tuning for Sysmon for Linux, auditd, Elastic, Splunk,
  CrowdStrike, Defender, or osquery if customer demand requires it.
- Platform/logsource filters in the review queue.
- Aggregate platform coverage reporting, if per-execution visibility proves
  insufficient.

Recommended promotion criteria for future refactors:

- After a meaningful sample of reviewed Linux-generated rules, evaluate whether the
  shared command/process extractors need Linux-specific prompts or separate agents.
- If Linux false-positive/edit rate is materially worse than Windows, split the
  relevant extractor prompt or agent.
- If many Linux articles contain deferred persistence artifacts, prioritize the Linux
  persistence extractor before broadening to another platform.
- If reviewers repeatedly mark Windows/Linux rules as behaviorally equivalent, design
  a separate behavior-family dedupe layer instead of weakening platform-specific
  canonical classes.
