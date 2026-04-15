# Extractor Agent Prompt Standard

Version: 1.1
Last Updated: 2026-04-15
Applies To: All ExtractAgent sub-agents (CmdLine, ProcTree, Registry, Services, HuntQueries, future extractors)

---

## Purpose

This document defines the mandatory structure, design principles, and quality gates for all extraction agent prompts in the Huntable CTI pipeline.

Every new or revised extractor prompt MUST comply with this standard. Use this as a template when building new extractors and as a checklist when reviewing existing ones.

---

## Code-level requirements

The Huntable pipeline code (`llm_service.py`) enforces specific prompt structure at runtime. Prompts that don't meet these requirements will either hard-fail or produce schema conflicts. All extractor prompts MUST comply.

### 1. System prompt is mandatory

- The code validates that a `system` role message exists before calling the LLM.
- Missing system prompt = PreprocessInvariantError = hard abort (no retries).
- The entire extraction prompt (ROLE through FINAL REMINDER) goes in the system message.

### 2. Instructions key is mandatory

- The `instructions` field is injected as the CRITICAL footer or into `{instructions}` in the user template.
- Without it, the model gets only "Output valid JSON only." -- no schema, no field rules, no JSON enforcement.
- The instructions key MUST contain: output schema, field rules, and JSON-only enforcement.

### 3. Traceability fields are mandatory (all sub-extract agents)

- The code auto-appends a traceability block to every user prompt requiring: `value`, `source_evidence`, `extraction_justification`, `confidence_score`.
- Your `json_example` MUST already include these four fields.
- If `json_example` omits them, the model receives conflicting schema instructions (your example says one thing, the appended block says another).
- `source_evidence` and `extraction_justification` are not cosmetic -- the QA agent uses them for factuality checks. Without them, QA flags outputs as potentially hallucinated.

### 4. json_example must match output schema

- The `json_example` in prompt config is the schema contract.
- It must include every field from your OUTPUT SCHEMA section, plus the four traceability fields.
- Do NOT rely on the model to infer fields not shown in `json_example`.

### 5. User message scaffold is code-owned

- The user message (Title/URL/Content headers + instructions footer) is hardcoded in `llm_service.py`, not authored in presets.
- Preset authors do NOT write or edit `user_template`.
- The runtime assembles the user message from the article content, title, URL, and the `instructions` config key.
- The INPUT CONTRACT section (section 4) documents the design intent for how article content reaches the model, but the actual assembly is code-owned.

---

## Design principles (non-negotiable)

1. **FAIL-CLOSED**: When uncertain, EXCLUDE. No artifact is better than a wrong artifact.
2. **PRECISION OVER RECALL**: It is always better to miss a true artifact than to include a fabricated, inferred, or uncertain one.
3. **EDR OBSERVABILITY OVERRIDES COMPLETENESS**: Only extract what can drive detection. If an artifact is technically present but has no telemetry or detection engineering value, skip it.
4. **LITERAL EXTRACTION ONLY**: No inference. No reconstruction. No synthesis. No normalization. If it isn't explicitly in the text, it doesn't exist.
5. **SIBLING AGENTS OWN THEIR LANES**: Each extractor has a defined scope. Never extract artifacts that belong to another extractor. Boundaries must be explicitly declared.
6. **HYPOTHETICAL AND DEFENSIVE CONTENT IS EXCLUDED**: "Attackers could use...", "defenders should monitor...", hardening guidance, and speculative references are not observed behavior. Skip them.
7. **RAW TELEMETRY IS VALID; SOURCE CODE IS NOT**: Sysmon logs, EDR events, and raw telemetry ARE extraction sources. Malware source code (C, Python, Go, etc.) is NOT -- it shows how malware works internally, not what defenders observe.
8. **IOC APPENDICES ARE VALID**: Indicators of Compromise tables and appendices at the end of articles are valid extraction sources. Apply all other rules normally.
9. **OBFUSCATED CONTENT IS PRESERVED AS-IS**: Do not decode, deobfuscate, or clean up extracted artifacts. Extract exactly as written.

---

## Mandatory prompt structure

Every extractor prompt MUST include the following 16 sections in this order. Sections may be renamed for clarity but the content requirement is fixed.

### 1. ROLE BLOCK

Purpose: One-line identity statement + extraction philosophy.

Required elements:

- What the agent extracts (one sentence)
- "LITERAL TEXT EXTRACTOR" declaration
- Core principle: "EDR observability overrides completeness"

Template:

> You extract [ARTIFACT TYPE] from threat intelligence articles.
> You are a LITERAL TEXT EXTRACTOR. You do NOT infer, reconstruct, or synthesize [artifacts].
> EDR observability overrides completeness. Only extract what can drive detection.

Boundary: ROLE is a persona statement (who the agent is), NOT a place for task instructions. Do NOT include:

- Model-specific directives (`/no_think`, model target notes)
- Task instructions ("Do NOT reason, explain, infer")
- Output formatting rules ("Output valid JSON")

Those belong in INSTRUCTIONS (sections 13-16). A well-written ROLE should still make sense if the agent were given a different task (e.g., reviewing someone else's extraction instead of producing one).

### 2. PURPOSE

Purpose: Why this extractor exists and what downstream system consumes its output.

Required elements:

- What the extracted data feeds (e.g., Sigma rule generation, behavioral detection)
- Relevant Sigma logsource categories or detection telemetry types

### 3. ARCHITECTURE CONTEXT

Purpose: Declare sibling agents and boundary rules to prevent overlap.

Required elements:

- "You are a sub-agent of ExtractAgent."
- List ALL sibling extractors by name (CmdLineExtract, ProcTreeExtract, RegistryExtract, ServicesExtract, HuntQueriesExtract, plus any future agents)
- Explicit "Do NOT extract" rules for each sibling's scope
- Any "You MAY extract" carve-outs where scopes partially overlap (e.g., RegistryExtract may extract the key from a reg.exe command, but not the command itself)

When adding a new extractor:

- Update ALL existing extractor prompts to list the new sibling
- Define boundary rules in both directions

### 4. INPUT CONTRACT

Purpose: Define the sole source of truth and prohibit external data.

Required elements (use verbatim):

- A single article provided as `{article_content}`
- Treat as plain text. Do NOT interpret HTML, Markdown, or rendering semantics.
- Extract ONLY from the provided text. Do NOT use prior knowledge or memory.
- Do NOT fetch, browse, or access any URLs.

### 5. POSITIVE EXTRACTION SCOPE

Purpose: Define what TO extract.

Required elements:

- Artifact types with structural requirements (e.g., "must start with `HKLM\`" or "must contain executable AND arguments")
- List of VALID SOURCES to extract from:
    - Narrative/analysis text describing observed attacker behavior
    - Raw telemetry and event logs
    - Commands (extract the relevant artifact, not the command itself if owned by CmdLineExtract)
    - Tables, figures, and inline code
    - IOC tables and appendices

### 6. NEGATIVE EXTRACTION SCOPE

Purpose: Define what NOT to extract. Explicit exclusions prevent the most common failure modes.

Required categories (include all that apply):

- Generic/vague references without specifics
- Partial or incomplete artifacts
- Shorthand or aliases without full form (if applicable)
- Artifacts inside malware source code
- Artifacts inside detection logic owned by HuntQueriesExtract (if applicable)
- Artifacts inside YARA rules
- Generic references without specific instances
- API calls (extract the artifact, not the API)
- Hypothetical or speculative references ("attackers could use...", "it is possible to...")
- Defensive guidance or hardening recommendations not tied to observed attacker behavior
- Artifacts inferred from malware family knowledge rather than explicitly stated
- Sibling agent artifacts (restate briefly)

### 7. DETECTION RELEVANCE GATE

Purpose: Every artifact must have clear detection engineering value.

Required elements:

- List applicable telemetry sources (e.g., Sysmon EventIDs, EDR capabilities, Windows Security logs)
- Rule: "If an artifact is technically present but has no detection engineering value, SKIP."

### 8. FIDELITY REQUIREMENTS

Purpose: Preserve artifacts exactly as written.

Required rules (use verbatim where applicable):

- Reproduce exactly as written. Do NOT normalize.
- Preserve original casing, abbreviations, and formatting.
- Do NOT expand abbreviations.
- Preserve obfuscated or encoded content exactly.

### 9. MULTI-LINE HANDLING

Purpose: Define how to handle artifacts split across multiple lines.

Required rules (use verbatim):

- If an artifact is split across multiple lines but clearly contiguous, reconstruct ONLY by direct concatenation of adjacent lines.
- Do NOT insert missing characters.
- If reconstruction is ambiguous -> SKIP.

### 10. COUNT SEMANTICS

Purpose: Define what constitutes a unique item vs a duplicate.

Required elements:

- Define the unique key (e.g., "each unique combination of (key + value_name + value_data) = ONE item")
- Rule for same artifact with different values = multiple entries
- Rule for same artifact mentioned multiple times with identical values = ONE entry
- Rule for same artifact in different attack phases

### 11. EDGE CASES

Purpose: Handle known ambiguous scenarios with explicit rules rather than leaving them to model judgment.

Required approach:

- List each edge case with a concrete example
- Show what TO extract and what NOT to extract
- Reference which sibling agent owns the excluded portion

### 12. VERIFICATION CHECKLIST

Purpose: Pre-output self-check. Forces the model to validate each extraction before including it.

Format: Checkbox list with one question per line.

Required checks (minimum):

- [ ] Is the artifact explicitly present in the text?
- [ ] Does it meet structural validity requirements?
- [ ] Is the source valid (not source code, detection logic, or defensive guidance)?
- [ ] Does it have detection engineering value?
- [ ] Can I point to the exact source_evidence?
- [ ] Is it NOT owned by a sibling extractor?
- [ ] Are all four traceability fields populated (value, source_evidence, extraction_justification, confidence_score)?

Add artifact-specific checks as needed.

### 13. OUTPUT SCHEMA

Purpose: Define the exact JSON output format.

Required elements:

- "Respond with ONLY valid JSON. No prose, no markdown, no code fences, no explanations."
- Concrete example with realistic field values (not placeholder types)
- Array of items + integer count field
- MUST include traceability fields in the example (see Section 14)

### 14. FIELD RULES

Purpose: Define each field's requirements.

Required for each field:

- REQUIRED or optional
- Data type and allowed values (if enumerated)
- Omission behavior for optional fields ("Omit field if not present" -- not null, not empty string)

**Traceability fields (mandatory -- all extractors):**

These four fields MUST appear on every extracted item. They are required by the pipeline code and consumed by the QA agent for factuality checks.

- **value**: REQUIRED. The extracted artifact itself (the primary content). Map this to whatever your artifact's main field is (e.g., for CmdLine this is the command line; for Registry this is the key path). If your schema uses a different primary field name (key, query_text, etc.), ALSO include value as a duplicate or alias.
- **source_evidence**: REQUIRED. The exact excerpt from the article that contains or directly supports the artifact. This is the QA agent's ground truth for factuality verification.
- **extraction_justification**: REQUIRED. One sentence explaining WHY this artifact was extracted -- what makes it a valid, detection-relevant artifact rather than noise. Used by QA to assess extraction reasoning.
- **confidence_score**: REQUIRED. Float between 0.0 and 1.0.
    - 1.0 = artifact is unambiguously explicit, complete, and detection-relevant
    - 0.7-0.9 = artifact is present but has minor ambiguity (e.g., operation type not stated, partial context)
    - 0.5-0.6 = artifact is present but requires some interpretation
    - Below 0.5 = do NOT extract (fail-closed principle applies)

**Domain-specific fields:** Define all additional fields specific to the artifact type.

**json_example alignment:** The `json_example` in your prompt config MUST include every field defined here, including all four traceability fields.

### 15. FAIL-SAFE / EMPTY OUTPUT

Purpose: Define exact output when no artifacts qualify.

Required: Show the literal JSON to return.

Example: `{"registry_artifacts": [], "count": 0}`

### 16. FINAL REMINDER

Purpose: Restate core principle + top failure modes in 4-6 one-line rules.

Required elements:

- Restate "Precision over recall" and/or "EDR observability overrides completeness"
- 3-5 specific failure modes as short imperative sentences (e.g., "If the article says 'the Run key' without a full path, SKIP.")
- End with: "When in doubt, OMIT."

---

## Prompt config alignment

This section maps the prompt standard to the Huntable pipeline's prompt config keys (stored in JSON, parsed at runtime by `llm_service.py`).

| Prompt Standard Section | Config Key | Notes |
|---|---|---|
| Sections 1-12 (ROLE through VERIFICATION CHECKLIST) | `system` (or `role`) | This is the system message. Must be present or pipeline hard-fails. |
| Sections 13-16 (OUTPUT SCHEMA through FINAL REMINDER) | `instructions` | Injected as CRITICAL footer. Must contain schema + field rules + JSON enforcement. |
| Output example | `json_example` | Must include ALL fields from Section 14 including traceability fields. Must match the output schema exactly. |
| Schema description (legacy) | `output_format` | Used only if `json_example` is absent. Describes the JSON schema in prose. |
| User message scaffold | CODE-OWNED (`llm_service.py`) | The Title/URL/Content scaffold and instructions footer are hardcoded in the runtime. Not authored in presets. Preset authors control the system message and instructions content; the runtime controls how they are assembled into the user message. |

---

## Prompt review checklist

Use this when reviewing any extractor prompt (new or revised):

### Structure

- [ ] All 16 mandatory sections present?
- [ ] Sections in correct order?
- [ ] ROLE block includes "LITERAL TEXT EXTRACTOR" and core principle?
- [ ] ROLE block is persona only (no model directives, no task instructions)?
- [ ] Architecture context lists ALL current sibling agents?
- [ ] Input contract uses standard verbatim language?

### Code alignment

- [ ] System prompt content maps to `system`/`role` config key?
- [ ] `instructions` config key contains output schema + field rules + JSON enforcement?
- [ ] `json_example` includes ALL output fields including traceability fields?
- [ ] `json_example` matches output schema exactly (no field mismatches)?
- [ ] User message scaffold is code-owned (no `user_template` in preset)?
- [ ] Traceability fields (value, source_evidence, extraction_justification, confidence_score) present in output schema, field rules, AND `json_example`?

### Boundaries

- [ ] Sibling agent boundaries explicitly declared?
- [ ] Boundary rules stated in both directions (what to extract AND what not to)?
- [ ] Overlap carve-outs documented where scopes touch?

### Exclusions

- [ ] Hypothetical/speculative content excluded?
- [ ] Defensive guidance excluded?
- [ ] Malware source code excluded?
- [ ] Detection logic owned by HuntQueriesExtract excluded (if applicable)?
- [ ] YARA rules excluded?
- [ ] Inferred-from-family-knowledge excluded?

### Quality gates

- [ ] Detection relevance gate present?
- [ ] Structural validity requirements defined?
- [ ] Multi-line handling rules present?
- [ ] Count semantics defined?
- [ ] Verification checklist present with minimum required checks?

### Output

- [ ] JSON-only output instruction present?
- [ ] Concrete example with realistic values?
- [ ] source_evidence field REQUIRED (traceability)?
- [ ] extraction_justification field REQUIRED (traceability)?
- [ ] confidence_score field REQUIRED (traceability)?
- [ ] Fail-safe empty output defined with literal JSON?
- [ ] Field rules specify REQUIRED vs optional for every field?
- [ ] Optional fields use "omit" behavior (not null)?

### Fidelity

- [ ] No-normalization rule present?
- [ ] Preserve-casing rule present?
- [ ] Preserve-obfuscation rule present?
- [ ] No-expansion rule present (if applicable)?
- [ ] Multi-line concatenation rule present?

### Final

- [ ] Final reminder restates core principle?
- [ ] Top failure modes listed as short imperatives?
- [ ] Ends with "When in doubt, OMIT"?

---

## Maintenance rules

1. **When adding a new extractor agent:**
    - Build its prompt using this standard
    - Update ALL existing extractor prompts to add the new sibling to their Architecture Context block
    - Define boundary rules in both the new and existing prompts
    - Verify `json_example` includes traceability fields

2. **When a prompt is revised after eval failures:**
    - Add the failure pattern to the Edge Cases section
    - Add a corresponding check to the Verification Checklist
    - If the failure was a boundary issue, update sibling prompts too
    - If the failure was a schema issue, verify `json_example` alignment

3. **Version tracking:**
    - Every prompt should include a version identifier
    - Track prompt versions alongside model versions in eval results
    - When a prompt change improves eval scores, note what changed and why

4. **Periodic review:**
    - Review all extractor prompts together when adding a new sibling
    - Ensure terminology, field names, and design patterns remain consistent
    - Check that the fleet's combined coverage has no gaps or overlaps
    - Verify all `json_examples` still match the pipeline's traceability requirements
