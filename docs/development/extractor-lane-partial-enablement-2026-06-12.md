# Extractor Lanes Under Partial Agent Enablement — Design & Decision

**Status:** RATIFIED 2026-06-12 — principle adopted, Cmdline guard approved, and the
guard generalized to a **Complete-Artifact Rule** across all four agents (operator ruling,
§9). Execution: **Registry pilot first, then reassess** before Services / ScheduledTasks /
Cmdline.
**Date:** 2026-06-12.
**Scope:** the six ExtractAgent sub-agents (CmdlineExtract, ProcTreeExtract,
RegistryExtract, ServicesExtract, ScheduledTasksExtract, HuntQueriesExtract).
**Drives:** up to four contract edits + four eval-fixture re-audits, each its own
score-comparability era boundary. **No contract is edited by this doc** — it is the
plan and the rationale the edits will cite.

---

## 1. The problem

Every lane exclusion in the extractor fleet was written assuming **all siblings run**.
A rule of the form "don't extract X, sibling Y owns it" silently carries a second
clause — "…and Y will catch it." That clause is true only when Y is enabled.

Deployments routinely enable a **subset** of agents, driven by which telemetry a SIEM
actually has. An enterprise with command-line logging but no EDR may enable only
CmdlineExtract; another may run CmdlineExtract + HuntQueriesExtract and nothing else.
Under any such subset, a deference rule whose owning sibling is **disabled** stops being
a clean handoff and becomes a **coverage hole** — the artifact is extracted by nobody.

**Concrete instance (the motivating case).** In the TeamCity article
(`art-08`, Fortinet CVE-2023-42793), the richest command lines live *inside the
threat-hunting query bodies* — e.g. the `cmd.exe` invocation
`/C "chcp 65001 > NUL & netstat -afn -p TCP"`. A CmdlineExtract-only deployment reading
that article extracts **none** of them today, because of
`cmdline-extract.md:110` ("Commands that appear ONLY inside a Sigma rule, KQL/SPL/EQL/XQL
query, or other detection logic → SKIP"). The command-line shop — the single most common
partial configuration — is precisely the one that loses command lines.

---

## 2. Why this is on the table now

The ProcTreeExtract eval-fixture audit (2026-06-12, commits `b8094541` and `1eca173c`)
removed ProcTree's "appears only inside detection logic" deference and opened detection /
hunting / mitigation prose **and** rule/query field conditions as valid lineage sources.
That fixed the gap for process pairs — and made ProcTree the **lone agent** in the fleet
that mines detection logic for its artifact. This doc decides whether to propagate that
move, and — because the propagation is *not* uniform — pins exactly how the one hard
agent (Cmdline) should behave.

---

## 3. Framework: three buckets of exclusion

Not every exclusion is a gap-maker. Sort each one:

1. **Type-discipline** — "do not emit another agent's artifact *type*." (ProcTree must
   not emit command strings; Registry must not emit lineage pairs.)
   Enablement-independent. **Always keep.** Disabling a sibling never makes this agent
   the right tool to emit that other type.

2. **Validity** — "this is not a real instance of *my* type." (Injection is not process
   creation; a bare `whoami` is not a non-trivial command.)
   Enablement-independent. **Always keep.**

3. **Deference** — "I *could* faithfully emit my type here, but I skip because sibling Y
   owns this *region*." **The only gap-making bucket.**

**The test for bucket 3:** *if Y is disabled, does a faithful instance of MY artifact
type vanish?* If yes, it is deference, and it is costing coverage.

---

## 4. The invariant that makes de-laning safe

The reason "let every agent extract its own type from everywhere" cannot cause
cross-agent double-counting: **all six output types are disjoint.**

| Agent | Output key | Artifact (primary field) | Sigma logsource consumer |
|---|---|---|---|
| CmdlineExtract | `commands` | command-line string | `process_creation` (CommandLine) |
| ProcTreeExtract | `process_lineage` | parent→child pair | `process_creation` (Parent/Image) |
| RegistryExtract | `registry_artifacts` | hive-rooted key/value/op | `registry_event` |
| ServicesExtract | `windows_services` | service_name / image_path | `service_creation` |
| ScheduledTasksExtract | `scheduled_tasks` | task identity / schedule | `scheduled_task` |
| HuntQueriesExtract | `queries` | finished rule/query text | (is itself the detection) |

No two agents can emit the same record — different primary fields, different downstream
logsource. Therefore:

- **Cross-agent collision is impossible.** "Extract your type everywhere" never produces
  a duplicate across agents.
- **Within-agent restatement** (the same artifact stated twice in one article) is handled
  by each agent's own COUNT SEMANTICS dedup — already in every contract.
- **Enablement becomes compositional:** the enabled set determines which *types* you get;
  you can never lose a faithful artifact *within* an enabled type.

**Residual to name, not a bug:** one source span can now yield several records of
*different* types. A `reg.exe add HKLM\…\Run /v X /d Y` line inside a Sigma rule yields a
Cmdline record (the command, if literal), a Registry record (the key/value), and a
HuntQueries record (the rule). That is **multi-faceted extraction**, not duplication —
three artifacts for three detection-engineering consumers. Expect total record volume to
rise under full enablement; it is not double-counting.

---

## 5. The gap is one rule pattern, in four places

Auditing all six contracts against §3, the gap-making deference reduces to a **single
repeated pattern** plus its defensive-guidance twin:

> "*&lt;my artifact&gt;* that appears **ONLY inside** a Sigma rule / KQL / SPL / EQL / XQL
> query / other detection logic → SKIP (HuntQueriesExtract)."
> …and "Defensive guidance / 'defenders should monitor' references → SKIP."

Everything else is safe and stays:

- **Facet carve-outs between structured extractors are NOT deference — keep them all.**
  Cmdline owns the `reg.exe` / `sc.exe` / `schtasks.exe` command *line*; Registry /
  Services / ScheduledTasks pull their typed token *out of* that same line
  (`cmdline-extract.md:39-42`, `registry-extract.md:38-39`, `services-extract.md:36-40`,
  `scheduled-tasks-extract.md:43-45`). Each agent extracts a **different facet**. Disable
  one and the other still fires; the lost facet is always "you disabled the agent that
  owns that type," never "an enabled agent declined its own type." Safe under every
  subset. No change.

- **HuntQueriesExtract is the region owner, not a deferrer — no change.** It owns
  "FINISHED DETECTION LOGIC ONLY" (`huntquery-extract.md:45`). Its boundary already
  anticipates parallel sibling extraction: "If an article contains both a narrative IOC
  (owned by a sibling) and a Sigma/KQL rule that references it, you extract only the rule;
  the sibling extracts the IOC independently" (`:46-47`). De-laning the siblings extends
  that same model to the only-inside-a-rule case — it is aligned with HuntQueries, not in
  tension with it.

---

## 6. Per-agent classification

| Agent | Deference rule (line-cited) | Artifact shape | How detection logic stores it | Faithful? | Action |
|---|---|---|---|---|---|
| **ProcTree** | *(removed 2026-06-12)* | pair = two atomic tokens | `ParentImage` + `Image` field values | **Faithful** | **DONE** (reference pattern) |
| **Registry** | `registry-extract.md:75`, `:81`; defensive `:78-79` | atomic token (hive-rooted path) | `TargetObject` value — *often a hive-less suffix* | Faithful only when full | **Remove deference + light complete-artifact guard** (§7.3) |
| **Services** | `services-extract.md:85`; defensive `:88` | atomic tokens (service_name / image_path) | `ServiceName` / `ImagePath` value — *sometimes partial* | Faithful only when full | **Remove deference + light complete-artifact guard** (§7.3) |
| **ScheduledTasks** | `scheduled-tasks-extract.md:40` | atomic token (task name/path) | `TaskName` value | Faithful only when full | **Remove deference + light complete-artifact guard** (§7.3) |
| **Cmdline** | `cmdline-extract.md:110`; boundary `:37` | **free-form composite string** | `CommandLine|contains:` / `|re:` **predicates over fragments** | Lossy by default | **Remove deference + heavy guard** (§7.2) |
| **HuntQueries** | — (region owner) | the rule itself | n/a | n/a | **No change** |

**Correction to an earlier framing (operator ruling, 2026-06-12).** The three structured
siblings are *not* purely mechanical "open the region." Their artifact is an atomic token,
but detection logic frequently stores only a **suffix or fragment** of it —
`TargetObject|endswith: '\CurrentVersion\Run'` carries a hive-less tail, and Registry's
positive scope **requires** a hive root. So all four de-laned agents obey the same
**Complete-Artifact Rule** (§7); they differ only in weight. The structured three are
*light* — their existing positive scope (hive-rooted key, full `service_name`/`ImagePath`,
full task path) already rejects most fragments, so the guard is largely automatic. Cmdline
is *heavy* — its artifact has no single "complete" shape, so the guard must be explicit.

---

## 7. The Complete-Artifact Rule

One rule governs every agent that extracts from a detection-logic region:

> **When an artifact appears inside a Sigma rule / KQL / SPL / EQL / XQL / vendor query, it
> is extractable only if the matched value is the COMPLETE artifact as your positive scope
> defines it — a full hive-rooted key, a full `service_name` / `ImagePath`, a full task
> path, a full literal command line — never a suffix, substring, or predicate fragment.**

Two signals disclose completeness: the **matching operator** (exact-match carries the whole
value; `contains`/`re`/`endswith` carry a fragment) and the **value shape** (does the
matched string, on its own, satisfy your positive scope?). The rule is uniform; the *weight*
differs by artifact:

- **Light (structured three).** Registry/Services/ScheduledTasks already require a complete
  token in positive scope (Registry demands a hive root; Services demands a full
  `service_name`/`image_path`; ScheduledTasks a full task path). A hive-less `endswith`
  suffix or partial name **self-rejects against the existing positive scope** — the guard is
  mostly automatic, needing only a one-line "the matched value must be the full
  hive-rooted/complete token, not a suffix" note (§7.3).
- **Heavy (Cmdline).** A command line has no single canonical "complete" shape and is stored
  in detection logic almost entirely as fragments, so the guard must be spelled out (§7.2).

### 7.1 Why Cmdline is the heavy instance

Every other extractor's artifact is an **atomic token**; the command line is a
**free-form composite string**. That single structural fact changes how detection logic
represents it:

- `ParentImage|endswith: '\rundll32.exe'` — the image name survives the match as the
  identifying token. A **copy**.
- `TargetObject|endswith: '\Run\Evil'` — the registry path survives. A copy.
- `CommandLine|contains: 'wsuspool'` — the command does **not** survive. `wsuspool` is a
  sliver. Emitting "the command" would require inventing the rest — **inference**, which
  the LITERAL-TEXT-EXTRACTOR principle forbids.

A path or image name is short and self-identifying, so a partial-match operator still
captures the whole token. A command line is unbounded and ordered, so detection logic
never stores it by value — it stores **predicates over fragments**. So for the structured
four, "mine the rule body" copies the artifact; for Cmdline it reconstructs one.

### 7.2 The Cmdline guard (heavy instance)

> **A command appearing inside detection logic is extractable only if the matched value is
> the command itself — a verbatim, single-line invocation that independently satisfies
> CmdlineExtract POSITIVE SCOPE — not a predicate over the command.**

This is decided by two signals, in order:

**(a) Operator/modifier — primary signal. The operator discloses fidelity.**

| Verdict | Sigma | KQL (Defender/Sentinel) | SPL (Splunk) |
|---|---|---|---|
| **Faithful → eligible** | default match, `|equals` | `==`, `=~` | exact `=` / explicit full match |
| **Fragment → SKIP** | `|contains`, `|contains|all`, `|startswith`, `|endswith`, `|re`, `|windash` | `contains`, `has`, `hasprefix`, `matches regex`, `startswith`, `endswith` | `*wildcard*`, `like`, `rex` |

An exact-match operator asserts "the full command line equals this string," so the string
**is** the observed command. A fragment operator asserts "the command line contains/looks
like this," so the value is a discriminator, not the command.

**(b) Value-shape — fallback when the operator is ambiguous.** Vendor-blog queries
(e.g. Fortinet's `Type: ("Process Creation") AND Target.Process.CommandLine: ("…")`) do
not always expose a clean Sigma modifier. When operator semantics are unclear, fall back
to: **does the matched string, on its own, satisfy CmdlineExtract positive scope?** —
recognized first token + ≥1 non-trivial component, single physical line, no `…`
truncation, no placeholder. If yes → extract; if it is a keyword / substring / regex →
skip.

### 7.3 The structured three (light instance)

Registry, Services, and ScheduledTasks need no elaborate operator table — their **existing
positive scope is the complete-artifact gate.** The de-laning edit is "open the
detection-logic region," and the guard is one clarifying sentence per agent:

- **Registry** — extract a key from a rule only when the matched value is a **full
  hive-rooted path** (`HKLM\…`, `HKCU\…`). A `TargetObject|endswith: '\…\Run'` suffix lacks
  a hive root and already **fails** `registry-extract.md` positive scope (line 52) → SKIP,
  no new rule required. Value data / value name extractable only when literally present in
  the matched value, not implied by the field name.
- **Services** — extract only a **full `service_name` or `image_path`**, satisfying the
  existing Gate 2. A `ServiceName|contains: 'Mal'` fragment fails Gate 2 → SKIP.
- **ScheduledTasks** — extract only a **full task name/path** (the existing positive scope).
  A partial `TaskName|contains:` fragment → SKIP.

So for the structured three the audit work is mostly: (1) delete the deference + defensive
bullets, (2) add the one-line "matched value must be the complete token" note, (3) re-audit
GT — expecting a **modest** delta, since clean exact-match rules carrying full tokens are
less common than fragment conditions. The pilot (§8) measures exactly this.

### 7.4 This is not a new philosophy — it is an existing line, applied to query bodies

CmdlineExtract already draws exactly this distinction:

- Positive scope rule 1: "Appears verbatim, character-for-character, on ONE physical line.
  **Not assembled from multiple locations, fields, or representations.**"
  (`cmdline-extract.md:57-58`)
- Negative scope / edge case: `ARGV: ["cmd.exe","/c","whoami"]` → INVALID,
  "**representation, not a command line**." (`cmdline-extract.md:113`, `:169`)

A `CommandLine|contains:` condition is a **representation/predicate** in a field — the same
category as an ARGV array. The guard simply names that detection-logic field conditions
are representations unless the matched value is a literal full command. No new principle;
the existing literal-vs-representation boundary, extended to the detection-logic region.

### 7.5 Worked examples (from the audited corpus)

| Agent | Verbatim in query body | Verdict | Why |
|---|---|---|---|
| Cmdline · TeamCity `art-08` | `Target.Process.CommandLine: ("\/C \"chcp 65001 \> NUL & netstat \-afn \-p TCP\"")` | **EXTRACT** → `chcp 65001 > NUL & netstat -afn -p TCP` | Matched value is a full literal command chain (post-wrapper); `netstat -afn` is non-trivial. Passes positive scope on its own. |
| Cmdline · TeamCity `art-08` | `Source.Process.CommandLine: ("\"AclNumsInvertHost.dll\", AclNumsInvertHost")` | **SKIP** | A `rundll32` argument fragment — no recognized first-token execution component; fails positive scope. A sliver, not a command. |
| Cmdline · WSUS `art-05` | `ParentCommandLine|contains: 'wsuspool'` (embedded Sigma) | **SKIP** | Fragment operator; `wsuspool` is a discriminator substring, not a command. |
| Registry · illustrative | `TargetObject: 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\Evil'` (exact-match) | **EXTRACT** | Full hive-rooted key as the matched value; satisfies Registry positive scope. |
| Registry · illustrative | `TargetObject|endswith: '\CurrentVersion\Run'` | **SKIP** | Hive-less suffix; fails Registry's hive-root requirement (`registry-extract.md:52`) — the existing positive scope is the guard. |

**Net effect on Cmdline ground truth:** small and high-precision. Full literal commands
embedded in query bodies (which today fall through the floor for a Cmdline-only shop) are
recovered; the noisy `contains`/regex fragments stay excluded. The guard *raises* recall
for the most common solo configuration without lowering precision.

---

## 8. Costs & rollout

- **Four spec changes = four score-comparability era boundaries.** Registry, Services,
  ScheduledTasks, Cmdline each get a contract edit + dropin mirror + CHANGELOG era marker
  + a full eval-fixture-audit re-run (blind extraction → adjudication → 5-sink sync →
  seed/preset propagation), exactly as ProcTree had today. Budget one audit session each.
- **Sequencing — Registry pilot first (ruled 2026-06-12).** Run RegistryExtract as a
  single end-to-end proof of the pattern (de-lane its contract with the §7.3 light guard,
  then a full eval-fixture re-audit), **measure the real GT delta and effort, and reassess**
  before committing to Services → ScheduledTasks → **Cmdline last** (the §7.2 heavy guard
  needs careful GT adjudication of every query-body candidate). The pilot also empirically
  answers "how often do detection rules carry a full token vs a fragment?" — the open
  question behind the structured-three recall estimate.
- **Full-enablement volume rises** via multi-facet extraction (§4 residual). Not
  double-counting; name it in each CHANGELOG so the increase is not read as a regression.
- **No config-conditional prompts.** Enablement-independence is achieved *by
  construction* (each agent extracts its type everywhere), never by making a prompt branch
  on which siblings are enabled. The agent cannot reliably see the enabled set, and
  config-conditional behavior would destroy score comparability (same agent, different
  output per deployment).

---

## 9. Decisions (ruled 2026-06-12)

1. **Principle — RATIFIED.** Each agent extracts its own artifact type faithfully from
   everywhere it appears, including detection-logic regions; lanes are type-discipline +
   validity only. Partial enablement is gap-free by construction.
2. **Cmdline guard — APPROVED as written (§7.2).** Operator-discloses-fidelity primary,
   value-shape fallback for ambiguous-operator vendor queries, anchored on the existing
   "representation, not a command line" rule.
3. **Generalization — RULED.** The guard is not Cmdline-only; it is the **Complete-Artifact
   Rule (§7)** applied by all four de-laned agents. The structured three carry the *light*
   instance (their positive scope already gates completeness); Cmdline the *heavy* instance.
   This corrected the draft's "three mechanical siblings" framing.
4. **Execution — Registry pilot first (§8).** Ratify now, run RegistryExtract end-to-end,
   reassess before the rest.
5. **Volume — ACCEPTED** with a per-era CHANGELOG callout so the multi-facet increase
   (§4 residual) is never read as a regression.

Carried into the Registry pilot to confirm per-candidate: how often live detection rules
store a full hive-rooted key vs a hive-less suffix (the structured-three recall driver);
and whether ScheduledTasks carries a defensive-guidance twin to remove (confirm exact line
in its NEGATIVE SCOPE during its audit).

---

## Appendix — the ProcTree precedent (already shipped)

What this doc proposes to generalize was executed for ProcTreeExtract on 2026-06-12:

- `b8094541` — telemetry-block carve-out, verb-list expansion, objective-only relevance
  gate. Added a STRUCTURED TELEMETRY EXTRACTION section.
- `1eca173c` — detection-logic + defensive-guidance sources opened; rule/query field
  conditions (`Source.Process.Name` + `Target.Process.File.Name`, `ParentImage` + `Image`)
  recognized as faithful pair evidence; hunt-query-dedup and distributive-child-list edge
  cases.
- `8a6025ca`, `56187ae5` — the eval ground-truth re-audited under the new spec
  (10 articles, 9 → 20 pairs), all five sinks synced.
- `0fbf9887` — seed + 9 quickstart presets propagated.

ProcTree is the faithful-structured case done end to end. Registry / Services /
ScheduledTasks are the same move; Cmdline is the same move **plus the §7 guard**.
