# Platform Telemetry Expansion -- Design Spec

- Date: 2026-06-17
- Status: Proposed (operator decisions captured; pending implementation plan)
- Branch: europa-dev

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

---

## 10. Deferred work and explicit follow-ups

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
