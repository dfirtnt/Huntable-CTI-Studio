# SigmaGenerate -- Prompt Contract v1.0

Version: 1.0
Last Updated: 2026-05-12
Applies To: Sigma rule generation agent (sigma_generate_multi, sigma_generation, and all future variants)

---

## Purpose

This document defines the mandatory structure, design principles, and quality gates for all
Sigma rule generation prompts in the Huntable CTI pipeline.

Every new or revised generation prompt MUST comply with this contract. Use it as a template
when building new generator variants and as a checklist when reviewing existing ones.

---

## Code-level requirements

The pipeline drives rule generation from `SigmaGenerationAgent` (or equivalent service). Prompts
that do not meet these requirements will either hard-fail validation or produce rules that pass
pySIGMA parsing but fail downstream enrichment or ranking.

1. **System prompt is mandatory.** The entire contract (ROLE through VERIFICATION CHECKLIST)
   goes in the system message.

2. **Instructions key governs output contract.** The `instructions` field (OUTPUT SCHEMA through
   FINAL REMINDER) is injected as the CRITICAL footer. Without it the model receives no YAML
   structure constraints, no required-fields list, and no `observables_used` enforcement.

3. **`observables_used` is a required non-standard field.** Every emitted rule MUST carry
   `observables_used: [<indices>]` referencing the exact observable indices that informed its
   detection logic. The pipeline reads this field for traceability. Absence = traceability
   failure.

4. **Output is raw YAML, not JSON.** The pipeline parses the model response directly as
   YAML via pySIGMA. Any narrative text before or within the YAML causes a parse error.

5. **UUID enforcement is code-validated.** The pipeline rejects rules with duplicate or missing
   `id` values. Every rule needs a freshly generated UUIDv4.

---

## Design principles (non-negotiable)

1. **BEHAVIORAL DETECTION OVER IOC MATCHING**: Rules must detect the behavior, not the exact
   artifact. Infrastructure indicators (IPs, hashes, domains) are only valid when they
   materially increase precision against the specific behavior.

2. **RESILIENCE OVER BREVITY**: A rule that survives argument reordering, whitespace variation,
   and case changes is worth more than a shorter rule that breaks on the first evasion.

3. **SPLIT BY BEHAVIOR**: One distinct TTP = one rule. Collapsing multiple tactics into a
   single detection obscures signal and increases false positive risk.

4. **OBSERVABLE GROUNDING**: Every detection element must trace back to a specific observable.
   Do not infer behaviors, paths, or registry keys not supported by the provided observables.

5. **GENERIC LOGSOURCES**: Rules must work across vendors. No EventIDs, no sysmon hardcoding,
   no SIEM-specific field names in logsource.

6. **PRECISE SEVERITY**: Level reflects actual behavior risk. Do not default everything to high.

---

## Mandatory prompt structure

Every generator prompt MUST include the following sections in this order.

### 1. SYSTEM PROMPT

Purpose: Short persona + hard output constraint. This is the `system` message in the API call,
separate from the main prompt file (which is the user message).

Required elements:
- "Sigma rule generation expert"
- "production-ready, behaviorally meaningful Sigma rules"
- "grounded strictly in the provided observables"
- Output format constraint: "Output ONLY valid YAML starting with `title:`. Use exact 2-space
  indentation. No markdown, no explanations, no code fences."
- YAML quoting reminder: "If title or description contains special YAML characters
  (? : [ ] { } | & * # @ `), wrap the value in double quotes."
- observables_used enforcement: "When observables are provided, every rule MUST include
  `observables_used: [indices]`. Never omit this field."

Keep this short (3-6 sentences). It is the system message that every provider receives.
The full generation strategy lives in the user message (sections 2-12 and the output contract).

Note: if no system prompt is configured in the workflow, the pipeline falls back to the
hardcoded default in `_call_provider_for_sigma`. Any configured system prompt REPLACES that
default entirely -- it does not append to it.

### 2. PURPOSE

Purpose: Why this generator exists, what feeds it, what it feeds.

Required elements:
- Upstream: "receives structured observables from the CTI extraction pipeline"
- Downstream: "output feeds pySIGMA validation, the ranking agent, and the detection library"
- Goal: detection durability, low false positives, Sigma best practices

### 3. ARCHITECTURE CONTEXT

Purpose: Declare the pipeline position and input provenance.

Required elements:
- "Receives pre-extracted observables from ExtractAgent sub-agents"
- List observable types consumed: CmdlineExtract, ProcTreeExtract, RegistryExtract,
  ServicesExtract, ScheduledTasksExtract, HuntQueriesExtract
- Explicit note: "Do NOT re-extract raw indicators from article content; observables are
  already structured. Your job is to generate rules FROM them, not to re-parse the article."

### 4. INPUT CONTRACT

Purpose: Define the exact inputs available to the model.

Required elements (use verbatim where applicable):
- Article metadata: title, source URL
- Article content (optional, for context only -- not for re-extraction)
- Structured observables list with 0-based indices
- "Treat observables as the authoritative behavioral evidence. Article content provides
  context; observables are ground truth."

### 5. POSITIVE GENERATION SCOPE

Purpose: Define what behaviors to generate rules for.

Required elements:
- Behavior types eligible for rule generation:
  - PowerShell / scripting engine execution
  - Ingress tool transfer / download cradles
  - Persistence (registry, scheduled tasks, services)
  - Credential dumping
  - Suspicious parent-child execution chains
  - Defense evasion (AMSI bypass, AV disablement, LOLBin abuse)
  - Lateral movement
  - Data exfiltration
  - Network activity (C2, staging)
- Rule: "If observables represent a distinct behavior, generate a rule for it."

### 6. NEGATIVE GENERATION SCOPE

Purpose: Define what NOT to generate rules for.

Required elements:
- Single atomic IOCs without behavioral context (bare IPs, hashes, domains, filenames alone)
- Behaviors with insufficient observable support (ambiguous or fragmentary)
- Overly noisy detections (would fire on most endpoints)
- Behaviors indistinguishable from normal administrative activity without additional context
- "If the observable supports only an IOC match and no behavioral signal, SKIP the rule."

### 7. RULE SPLITTING LOGIC

Purpose: Enforce one-behavior-per-rule discipline.

Required elements:
- Mandatory: if observables span distinct behaviors, generate separate rules
- Splitting criteria (by behavior type):
  - PowerShell execution
  - Ingress tool transfer
  - Persistence via registry
  - Credential dumping
  - curl-based / certutil-based staging
  - Data exfiltration
  - Suspicious parent-child execution chains
- Prohibited: collapsing multiple tactics into one rule "unless they are inseparable"
- Definition of "inseparable": the behaviors only occur together and detecting either alone
  would be meaningless (rare; document explicitly when applied)

### 8. LOGSOURCE RULES

Purpose: Enforce generic, cross-vendor logsources.

Required elements:
- Always prefer `category` over `service`.
- Canonical category examples:
  - Process execution: `category: process_creation`, `product: windows`
  - Registry persistence: `category: registry_event`, `product: windows`
  - File creation: `category: file_event`, `product: windows`
  - Network: `category: network_connection`, `product: windows`
  - PowerShell: `category: ps_script` or `category: ps_classic_script`
  - WMI: `category: wmi_event`
- PROHIBITED in logsource:
  - `EventID` (any value)
  - `service: sysmon`
  - SIEM-specific field names
  - Vendor-specific product versions

### 9. DETECTION CONSTRUCTION RULES

Purpose: Enforce behavioral operators over brittle IOC matching.

Required elements:
- Prohibited: full-string equality matching on CommandLine for multi-component commands
- Required operator preference:
  - Multi-parameter command lines: `CommandLine|contains|all:`
  - Partial IOC anchoring: `CommandLine|contains:`
  - Executable focus: `Image|endswith:`
- Modifier usage:
  - `|contains` -- substring match
  - `|all` -- all substrings must be present (AND semantics)
  - `|endswith` -- suffix match (use for Image paths)
  - `|startswith` -- prefix match
  - `|re` -- regex only if wildcard modifiers are insufficient
- Rule: "Never overuse regex. Prefer modifier combinations."
- Infrastructure indicators (IPs, domains): include only when they materially increase
  detection precision beyond pure behavioral matching.

### 10. DETECTION RESILIENCE REQUIREMENTS

Purpose: Rules must survive realistic evasion attempts.

Required elements:
- Detection must survive:
  - Argument reordering
  - Whitespace variation
  - Case differences (use `|contains` not `=` for CommandLine)
  - Additional benign flags inserted between target args
  - Quote style changes
- Rule: "If your rule would break under minor formatting changes, redesign it."
- When `CommandLine|contains|all:` is used, test mentally that each element is independently
  necessary and that together they cannot be triggered by common benign activity.

### 11. ATT&CK TAGGING RULES

Purpose: Accurate, behavior-grounded ATT&CK mapping.

Required elements:
- Always map both tactic AND technique (never tactic alone, never technique alone without tactic)
- Required tag format: `attack.<tactic>` and `attack.t<technique>[.<subtechnique>]`
- Canonical examples:
  - PowerShell execution: `attack.execution`, `attack.t1059.001`
  - Download cradle: `attack.command_and_control`, `attack.t1105`
  - Registry Run key persistence: `attack.persistence`, `attack.t1547.001`
  - Credential dumping via reg save: `attack.credential_access`, `attack.t1003.002`
  - Scheduled task persistence: `attack.persistence`, `attack.t1053.005`
  - AMSI bypass: `attack.defense_evasion`, `attack.t1562.001`
- Prohibited: guessing a technique without observable support. Map based on actual behavior.

### 12. VERIFICATION CHECKLIST

Purpose: Pre-output self-check on every generated rule.

Format: Checkbox list, one question per line.

Required checks:
- [ ] Does the rule target a specific behavior, not just a bare IOC?
- [ ] Is the logsource a generic category (no EventID, no sysmon, no vendor-specific)?
- [ ] Does detection use behavioral operators (`|contains|all`, `|endswith`) not full-string equality?
- [ ] Would the detection survive argument reordering, whitespace variation, and case differences?
- [ ] Is a fresh UUIDv4 assigned to `id`?
- [ ] Are ALL required fields present: title, id, status, description, tags, author, date, level, logsource, detection, falsepositives, condition, observables_used?
- [ ] Does `observables_used` contain only indices that directly informed the detection logic?
- [ ] Are ATT&CK tags accurate and evidence-grounded (both tactic AND technique)?
- [ ] Are falsepositives realistic (not "None" or "Unknown")?
- [ ] Is `level` calibrated to actual behavior risk (not defaulted to high)?
- [ ] Does the rule description start with "Detects"?
- [ ] Are YAML special characters in title/description wrapped in double quotes?

---

## INSTRUCTIONS (output contract -- everything below is the `instructions` payload)

### OUTPUT SCHEMA

Output ONLY valid YAML.
Start with `title:`.
Use exact 2-space indentation.
No markdown, no explanations, no prose, no code fences.
Multiple rules separated by `---`.

Every rule MUST follow this structure:

```yaml
title: <descriptive title; wrap in double quotes if it contains : ? [ ] { } | & * # @ `>
id: <freshly generated UUIDv4>
status: experimental
description: "Detects <specific behavior>"
tags:
  - attack.<tactic>
  - attack.t<technique>
author: "Automated CTI Pipeline"
date: YYYY/MM/DD
references:
  - <article_url>
logsource:
  category: <generic_category>
  product: <windows|linux|macos>
detection:
  <selection_name>:
    <FieldName|modifier>:
      - <value>
  condition: <selection_name>
falsepositives:
  - <realistic scenario>
level: <low|medium|high|critical>
observables_used: [<0-based indices>]
```

### FIELD RULES

**Required on every rule (no exceptions):**

- **title**: Descriptive, specific. If value contains `? : [ ] { } | & * # @ \`` wrap in double quotes.
- **id**: Valid UUIDv4. Never null, empty, placeholder, or reused.
- **status**: Always `experimental`.
- **description**: REQUIRED. Must start with "Detects". One sentence. Quote if special chars present.
- **tags**: REQUIRED. At minimum one tactic tag AND one technique tag. Both must be evidence-grounded.
- **author**: Always `"Automated CTI Pipeline"`.
- **date**: YYYY/MM/DD format. Use today's date.
- **logsource**: REQUIRED. Must use `category` (generic). Never hardcode `EventID` or `service: sysmon`.
- **detection**: REQUIRED. At minimum one selection block + condition.
- **falsepositives**: REQUIRED. List with at least one realistic scenario. Never "None", "Unknown", or empty.
- **level**: REQUIRED. Calibrated to behavior:
  - `critical`: Clear malicious credential dumping, known-malicious infrastructure execution
  - `high`: Suspicious download cradle, registry persistence
  - `medium`: Reconnaissance commands, process discovery
  - `low`: Weak contextual signals, generic LOLBin invocations with minimal indicators
- **condition**: REQUIRED. References defined selection names.
- **observables_used**: REQUIRED. 0-based index list referencing observables that directly
  informed detection logic. Use `[]` only if the rule is derived purely from article context
  with no structured observables.

**Optional fields (omit entirely if not applicable):**

- **references**: Include article URL when available. Omit field if no URL provided.

### ESCAPING RULES

Follow Sigma backslash convention:
- Windows paths: single backslash (`\path\to\file`) -- do NOT double-escape.
- Only double-escape if the YAML parser would otherwise interpret the backslash as an escape sequence.
- Do not escape single backslashes unnecessarily.

### FAIL-SAFE / EMPTY OUTPUT

If no observable is sufficient to generate a safe, non-noisy rule, output nothing.
An empty response is correct behavior. Do NOT generate placeholder or speculative rules.

Conditions that require an empty output:
- All observables are bare IOCs with no behavioral context
- Behavior is ambiguous and detection would be excessively noisy
- Observable data is insufficient to construct a resilient detection

### FINAL REMINDER

Behavioral detection over IOC matching.
Split by behavior: one TTP, one rule.
If the only signal is a bare IP, hash, or filename, SKIP the rule.
If the detection would break under minor whitespace or reordering changes, redesign it.
If the falsepositives field would be "None" or "Unknown", reconsider the rule -- it is probably too narrow or too broad.
If `observables_used` would be empty because you invented detection elements, STOP -- do not invent.
When in doubt, generate nothing.

---

## Config key alignment

The sigma generation prompt wiring differs from the extractor agents. There is no
`instructions` config key. The prompt file is the entire user message.

| Content | Where it lives | Notes |
|---|---|---|
| Section 1 (SYSTEM PROMPT) | `sigma_system_prompt` parameter | Short system message. Configured in workflow config or falls back to hardcoded default in `_call_provider_for_sigma`. Replaces the default entirely -- does not append. |
| Sections 2-12 (PURPOSE through VERIFICATION CHECKLIST) + INSTRUCTIONS | Prompt `.txt` file (user message) | The full strategy + output contract. Formatted by `format_prompt_async` with template vars, then passed as the user message to the API. |
| `{title}`, `{source}`, `{url}`, `{content}` | CODE-OWNED template vars | Injected by `sigma_generation_service.py` at call time. Prompt authors write the placeholder, not the values. |
| `{observables_section}` | CODE-OWNED, built by `_build_observables_section()` | Pre-formatted observable list with `observables_used` enforcement appended. If the template does not include `{observables_section}`, the service appends it automatically after formatting. |

**No `instructions` key exists for sigma generation.** Unlike the extractors, the entire
prompt (strategy + output contract) is one flat string in the user message. The system message
is a separate short config param (`sigma_system_prompt`), not a section of the prompt file.

---

## Model adaptation

This section defines how to adjust the contract for each model class supported by the pipeline.
The **invariant core** (design principles, rule splitting logic, logsource rules, detection
construction rules, output schema, field rules) never changes. Only the structural and
behavioral overlays listed below change.

### Model classes

| Class | Examples | Prompt file convention |
|---|---|---|
| Local (LM Studio) | Qwen, Mistral, Llama, Phi | `sigma_generation_local.txt` |
| Claude standard | claude-sonnet-4-5, claude-opus | `sigma_generation_claude.txt` |
| Claude extended thinking | claude-sonnet-4-5 with thinking budget | `sigma_generation_claude_thinking.txt` |
| OpenAI instruction | gpt-4o, gpt-4.1 | `sigma_generation_openai.txt` |
| OpenAI reasoning | o1, o3, o4, o4-mini, gpt-5.x | `sigma_generation_openai_reasoning.txt` |

---

### Local (LM Studio)

**What to do:**

- Shorten system prompt aggressively. Local models lose instruction fidelity past ~800 tokens.
- Replace multi-sentence rules with single-line imperatives.
- Collapse sections 7-10 (rule splitting, logsource, detection construction, resilience) into
  a single flat bulleted list of the 8-10 most critical rules.
- Repeat the output format directive at least twice: once at the top of the system prompt and
  once immediately before the input block.
- Include a short concrete YAML example inline in the instructions. Local models anchor
  heavily on examples; abstract field descriptions alone are unreliable.
- Keep the verification checklist to 5 items maximum.

**What to add:**

```
CRITICAL: Output ONLY raw YAML starting with `title:`. No text before it. No code fences.
No explanations. If you include any text before `title:`, the output will be rejected.
```

Repeat this block verbatim at the very end of the user message as well.

**What to drop:**

- Architecture Context section (no value for local models)
- Variant guidance, review checklists, maintenance rules
- Multi-paragraph principle explanations -- keep only the rule itself

**Temperature:** Use 0.1 or lower. Local models hallucinate structure at higher temperatures.

---

### Claude standard (no extended thinking)

**What to do:** Use the full contract as written. Claude handles multi-section system prompts
reliably and follows hierarchical structure without repetition.

**What to add:** None required.

**What to drop:** Nothing -- full contract applies.

**Note on system prompt:** The system message is the `sigma_system_prompt` config param, not
a section of the prompt file. Keep it to the short persona + output constraint from Section 1.
The full strategy and output contract stay in the prompt file (user message).

**Temperature:** 0.2-0.4 for generation. Lower = more consistent field coverage.

---

### Claude extended thinking

**What to do:**

- Condense sections 7-10 (rule splitting, logsource, detection construction, resilience) to
  principle statements only. The model reasons through application internally; verbose
  step-by-step guidance in those sections is redundant and wastes context.
- Keep the full output schema and field rules -- the model still needs to know the exact
  required fields and format.
- The `observables_used` index mapping benefits most from thinking mode; keep that requirement
  fully detailed.

**What to add at the top of the system prompt:**

```
Do not include chain-of-thought, reasoning steps, or thinking content in your response.
Output ONLY the YAML rule(s). Your thinking happens internally and must not appear in output.
```

**What to drop:** None of the invariant core. Only the step-by-step elaborations in the
strategy sections can be shortened to one-line principles.

**Temperature:** Extended thinking models typically use temperature=1 (API requirement).
The pipeline handles this via `clamp_temperature_for_provider`.

---

### OpenAI instruction (gpt-4o, gpt-4.1)

**What to do:** Use the full contract. These models handle multi-section system prompts well.

**What to add:** None required beyond the base contract.

**What to note:** The pipeline already uses `max_completion_tokens` for gpt-4.1 (not
`max_tokens`). No prompt change needed -- this is handled by `llm_service.py`.

**Temperature:** 0.2-0.3.

---

### OpenAI reasoning (o1, o3, o4, o4-mini, gpt-5.x)

**What to do:**

- Keep the system prompt lean. Reasoning models think internally; long strategy sections
  (7-10) create noise. Condense to principle-level rules only, same approach as Claude thinking.
- The output contract (sections 13+) must remain complete -- reasoning models still need
  explicit required-field lists and format rules.
- Do NOT use "think step by step", "reason carefully", or similar CoT elicitation language.
  These models reason by default; the directive is redundant and can cause the model to
  surface its reasoning in the output.

**What to add at the top of the system prompt:**

```
Do not include reasoning, chain-of-thought, or scratchpad content in your response.
Output ONLY the YAML rule(s) starting with `title:`.
```

**What to drop:**

- The step-by-step elaborations in sections 7-10 (keep the rule, drop the explanation)
- Any "reason carefully about" language

**What to note:** The pipeline detects reasoning models via `model_supports_variable_temperature`
and omits `temperature` from the API call. No prompt change needed for that.

---

### Adaptation decision table

| Prompt element | Local | Claude std | Claude thinking | OpenAI instruction | OpenAI reasoning |
|---|---|---|---|---|---|
| Full multi-section system prompt | Simplify | Full | Full | Full | Condense |
| Strategy sections 7-10 detail | Flatten to bullets | Full | Principles only | Full | Principles only |
| "Do not show reasoning" directive | n/a | n/a | REQUIRED | n/a | REQUIRED |
| Output format repetition | 2x minimum | 1x | 1x | 1x | 1x |
| Inline YAML example | REQUIRED | Optional | Optional | Optional | Optional |
| Verification checklist length | 5 max | Full | Full | Full | Full |
| `observables_used` detail | Abbreviated | Full | Full | Full | Full |
| Architecture Context section | Drop | Keep | Keep | Keep | Keep |

---

## Variant guidance (behavior scope)

When creating a specialized variant of this contract (e.g., a Linux-only generator, a
cloud-telemetry generator, or a low-noise-only variant):

1. Keep ROLE unchanged -- it is a persona, not a scope statement.
2. Narrow POSITIVE GENERATION SCOPE to the intended behavior types.
3. Update LOGSOURCE RULES if targeting a non-Windows platform.
4. Update DETECTION CONSTRUCTION RULES if the platform uses different field names.
5. Keep VERIFICATION CHECKLIST, OUTPUT SCHEMA, FIELD RULES, and FINAL REMINDER intact.
6. Bump version and date in the file header.

---

## Prompt review checklist

Use when reviewing any generator prompt (new or revised):

### Structure
- [ ] All mandatory sections present?
- [ ] ROLE block is persona only (no output rules, no task-specific strategy)?
- [ ] Architecture context names all ExtractAgent siblings?
- [ ] Input contract defines the observables as ground truth?

### Code alignment
- [ ] Section 1 (system prompt) is short -- persona + output constraint only?
- [ ] Full strategy + output contract is in the prompt file (user message), not the system prompt?
- [ ] `observables_used` enforcement present in both the system prompt (Section 1) and the output contract?
- [ ] Input variable placeholders (`{title}`, `{url}`, `{content}`, `{observables_section}`) present in prompt file?
- [ ] No `instructions` config key referenced -- sigma uses flat user message, not extractor split?

### Detection quality gates
- [ ] Logsource rules prohibit EventIDs and vendor-specific service values?
- [ ] Detection construction rules mandate behavioral operators?
- [ ] Resilience requirements explicitly listed?
- [ ] Rule splitting logic defined by behavior type?

### Output contract
- [ ] YAML-only output instruction present?
- [ ] All required Sigma fields enumerated with their rules?
- [ ] `observables_used` declared as REQUIRED with index semantics?
- [ ] Level calibration table present (not "default to high")?
- [ ] Falsepositives "None"/"Unknown" explicitly prohibited?
- [ ] UUID enforcement stated?
- [ ] Fail-safe (empty output) conditions defined?
- [ ] Final reminder ends with "generate nothing" not "omit"?

---

_Last updated: 2026-05-12_
