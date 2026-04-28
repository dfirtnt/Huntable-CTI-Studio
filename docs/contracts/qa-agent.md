# QA Agent Contract

Version: 1.0
Last Updated: 2026-04-18
Applies To: All QA variants (RankAgentQA, CmdLineQA, ProcTreeQA, HuntQueriesQA, RegistryQA, ServicesQA, generic QAAgent)

---

## Purpose

This document defines the mandatory structure, configuration, and runtime behavior for all QA (Quality Assurance) agents in the Huntable CTI pipeline.

QA agents validate the outputs of base agents (Rank, Extract sub-agents) for compliance, factuality, and completeness. Every QA prompt and configuration MUST comply with this standard.

---

## Code-level requirements

The Huntable pipeline code (`qa_agent_service.py`) enforces specific prompt structure and configuration at runtime. Prompts that don't meet these requirements will either hard-fail or produce schema conflicts. All QA prompts MUST comply.

### 1. Prompt structure keys are mandatory

QA prompts stored in the workflow config MUST contain these keys:

- **`role` or `system`**: REQUIRED. The system prompt / persona statement for the QA agent.
  - Missing = ValueError with message about empty system message.
  - The system message is assembled from `role` (or `system`) + `objective`.

- **`objective`**: REQUIRED. The evaluation objective statement (appended to role/system).
  - Can be empty string but the key must exist in the JSON structure.

- **`evaluation_criteria`**: REQUIRED. A list (array) of evaluation criteria strings.
  - Used to build the evaluation prompt that is shown to the model.
  - Must be a valid JSON array; empty array is allowed but not useful.
  - Each criterion is a string describing one validation rule.

### 2. Prompt location in config

QA prompts are stored under `agent_prompts` in the workflow config with key name mapping:

- **Generic QAAgent prompt**: stored as `agent_prompts["QAAgent"]`
  - Fallback prompt when no agent-specific QA prompt exists
  - Must be a JSON string (can be nested JSON-in-JSON)

- **Agent-specific QA prompts**: stored as `agent_prompts["{AgentName}QA"]`
  - Example: `agent_prompts["RankAgentQA"]` for Rank Agent QA
  - Example: `agent_prompts["CmdLineQA"]` for CmdLine Extract QA
  - Not currently implemented; reserved for future per-agent customization

### 3. Evaluation output format is mandatory

The QA model MUST return a JSON object with these fields:

```json
{
  "summary": "Brief summary of overall quality (1-3 sentences)",
  "issues": [
    {
      "type": "compliance | factuality | formatting",
      "description": "short explanation of the issue",
      "location": "line number or section reference, if applicable",
      "severity": "low | medium | high"
    }
  ],
  "verdict": "pass | needs_revision | critical_failure"
}
```

**Required fields:**

- **`summary`**: REQUIRED. String describing the overall evaluation result.
- **`issues`**: REQUIRED. Array of issue objects (can be empty if no issues).
- **`verdict`**: REQUIRED. Enum: `pass`, `needs_revision`, or `critical_failure`.

**Issue object fields:**

- **`type`**: REQUIRED. Must be one of: `compliance`, `factuality`, `formatting`.
- **`description`**: REQUIRED. Concise explanation of the issue.
- **`location`**: OPTIONAL. Reference to where the issue appears (line, field, section).
- **`severity`**: REQUIRED. Must be one of: `low`, `medium`, `high`.

### 4. Configuration requirements (workflow_config_schema.py)

QA behavior is controlled by the `QA` configuration object:

```json
{
  "QA": {
    "Enabled": {
      "RankAgent": true,
      "CmdlineExtract": false,
      "ProcTreeExtract": false,
      "HuntQueriesExtract": false,
      "RegistryExtract": false,
      "ServicesExtract": false,
      "ScheduledTasksExtract": false
    },
    "MaxRetries": 5
  }
}
```

**`QA.Enabled` (dict[str, bool])**

- Keys must match base agent names exactly (e.g., "RankAgent", "CmdlineExtract")
- True = run QA validation + retry loop on failure
- False = skip QA for this agent
- If a base agent is missing from this dict, defaults to False (QA disabled)

**`QA.MaxRetries` (int, default 5)**

- Maximum number of retries after QA validation failure
- On final failure: fall back to last valid output or terminate with error
- Applies per-agent based on agent-specific QA enablement

### 5. Per-agent LLM configuration (optional override)

Each QA agent can override its provider, model, temperature, and top_p:

Configuration keys in `agent_models`:

- **Provider override**: `{AgentName}QA_provider` (e.g., `RankAgentQA_provider`)
  - Default: ExtractAgent provider (from `ExtractAgent_provider`)
  - Fallback: llm_service.provider_extract

- **Model override**: `{AgentName}QA` (e.g., `RankAgentQA`)
  - Default: ExtractAgent model (from llm_service.model_extract)
  - Special case: RankAgent QA can use `RankAgent_provider` if `RankAgentQA_provider` is absent

- **Temperature override**: `{AgentName}QA_temperature` (e.g., `RankAgentQA_temperature`)
  - Default: 0.1 (low temperature for deterministic evaluation)
  - Recommended: 0.0 - 0.3 (QA should be conservative)

- **TopP override**: `{AgentName}QA_top_p` (e.g., `RankAgentQA_top_p`)
  - Default: 0.9
  - Recommended: 0.9 - 1.0

---

## Design principles (non-negotiable)

1. **FAIL-CLOSED**: When uncertain about quality, recommend revision. No uncertain pass-through.
2. **FACTUALITY FIRST**: Verify that agent output is grounded in the article content. No hallucinations.
3. **COMPLIANCE CHECKING**: Validate that output format matches the agent's schema contract.
4. **EVIDENCE REQUIREMENT**: All issues MUST be tied to specific evidence (line, excerpt, field).
5. **CONSTRUCTIVE FEEDBACK**: Issue descriptions should be actionable, not vague.
6. **NO OVER-SPECIFICATION**: Do not require formatting perfection; focus on correctness and completeness.

---

## Mandatory prompt structure

Every QA agent prompt MUST include the following sections. Sections may be renamed for clarity but content requirements are fixed.

### 1. ROLE BLOCK

Purpose: One-line identity statement + QA philosophy.

Required elements:

- What the agent validates (base agent name + output type)
- QA philosophy (e.g., "You verify correctness, not cosmetics")

Template:

> You are the Quality Assurance validator for the [BASE_AGENT] Agent.
> You verify that [BASE_AGENT] outputs are compliant, factually grounded, and complete.
> Your role is to catch errors early, not to over-specify formatting.

### 2. OBJECTIVE

Purpose: What the QA agent is evaluating and why.

Required elements:

- What is being validated (e.g., "extracted artifacts", "relevance scores")
- Why validation matters (e.g., "to prevent hallucinations", "to ensure schema compliance")
- What happens on failure (retry or fall-back)

### 3. EVALUATION CONTEXT

Purpose: Define the inputs the QA agent receives.

Required elements (use verbatim):

- You receive: **Article Content** (the source article from which the agent operated)
- You receive: **Agent Prompt** (the instructions given to the base agent)
- You receive: **Agent Output** (the structured output the base agent produced)
- You have access to: **Evaluation Criteria** (explicit rules for validation)

### 4. EVALUATION CRITERIA

Purpose: Define what TO check.

**This section is code-populated from the `evaluation_criteria` list in config.** Provide concrete checks such as:

- Factuality: "Is each item grounded in article content (can you cite source_evidence)?"
- Compliance: "Does the output match the required JSON schema?"
- Completeness: "Are there obvious artifacts or items the agent missed?"
- Logical consistency: "Does the output contradict the article or the prompt intent?"

Each criterion MUST be:

- Specific (not "Is it good?")
- Verifiable against the three inputs (article, prompt, output)
- Actionable (the model can point to evidence)

### 5. ISSUE SEVERITY RUBRIC

Purpose: Define how to classify issues.

Required:

- **Low severity**: Minor formatting, cosmetic style, non-critical field omission
  - Example: "Field capitalization inconsistent with schema"
  - Recommendation: pass or needs_revision depending on verdict weight

- **Medium severity**: Schema non-compliance, missing optional fields, factuality ambiguity
  - Example: "An extracted item references content not in the article"
  - Recommendation: needs_revision

- **High severity**: Schema violation, hallucination, incomplete output when completeness is critical
  - Example: "Structured output is not valid JSON"
  - Recommendation: critical_failure

### 6. VERDICT GUIDANCE

Purpose: Define when each verdict applies.

**PASS:**

- Output matches the schema
- All items are factually grounded in article content
- No logical contradictions
- Completeness is reasonable given article scope
- Can proceed to next pipeline step

**NEEDS_REVISION:**

- One or more medium-severity issues exist
- Re-prompt the base agent with QA feedback (up to MaxRetries times)
- If all retries exhausted: fall back to last valid output or terminate

**CRITICAL_FAILURE:**

- One or more high-severity issues exist
- Output cannot be trusted downstream
- Do NOT retry; escalate or fail the workflow execution

### 7. OUTPUT FORMAT (MANDATORY)

Purpose: Enforce the JSON structure the pipeline expects.

Required (use verbatim):

> Respond ONLY with valid JSON. No prose, markdown, code fences, or explanations.
>
> Use this format:
> ```json
> {
>   "summary": "Brief 1-3 sentence summary of quality",
>   "issues": [
>     {
>       "type": "compliance | factuality | formatting",
>       "description": "short explanation",
>       "location": "optional line/field reference",
>       "severity": "low | medium | high"
>     }
>   ],
>   "verdict": "pass | needs_revision | critical_failure"
> }
> ```

### 8. TRACEABILITY NOTE

Purpose: Remind QA to use source_evidence fields when present.

Required:

- If the base agent output includes `source_evidence` fields, use them to verify factuality.
- Compare `source_evidence` directly to article content.
- If `source_evidence` does not match the article, mark as factuality issue with high severity.

### 9. EDGE CASES

Purpose: Define how to handle ambiguous scenarios.

Include any known pitfalls for this specific agent's domain:

- Example (for ExtractAgent QA): "If the agent extracted the same artifact twice with different confidence scores, treat as duplicate unless context differs."
- Example (for RankAgent QA): "If the score contradicts the provided ranking reasoning, flag as logical inconsistency."

### 10. FINAL REMINDER

Purpose: Restate core principle + top failure modes.

Required elements:

- Restate "Factuality first" and/or "Fail-closed"
- 3-5 specific failure modes as imperative sentences
- End with: "When in doubt, recommend revision."

---

## Prompt config alignment

This section maps the prompt standard to the Huntable pipeline's prompt config keys.

| Prompt Standard Section | Config Key | Notes |
|---|---|---|
| Sections 1-9 (ROLE through EDGE CASES) | `role` or `system` | System message. Must be present or pipeline hard-fails. |
| Section 2 (OBJECTIVE) | `objective` | Appended to role/system to form complete system prompt. |
| Section 4 (EVALUATION CRITERIA) | `evaluation_criteria` | Array of strings. Injected into user prompt. |
| Section 7 (OUTPUT FORMAT) | Part of `role` or `system` | Must include the JSON format requirement. |

---

## Example: RankAgentQA Minimal Config

```json
{
  "agent_prompts": {
    "QAAgent": {
      "role": "You are the Quality Assurance validator for the Rank Agent. You verify that extracted relevance scores are justified and compliant with the scoring rubric.",
      "objective": "Validate that Rank Agent outputs follow the 1-10 scoring scale, are grounded in article content, and include clear reasoning.",
      "evaluation_criteria": [
        "Is the score justified by article content (not assumed)?",
        "Does the score fall in the correct band (1-3, 4-6, 7-10)?",
        "Are atomic IOCs excluded per the Rank Agent contract?",
        "Is the reasoning consistent with the scoring?"
      ]
    }
  },
  "QA": {
    "Enabled": {
      "RankAgent": true
    },
    "MaxRetries": 3
  }
}
```

---

## Runtime behavior

### QA Evaluation Loop

1. Base agent (e.g., RankAgent) produces output
2. QA service (`qa_agent_service.py`) calls QAAgent with:
   - Article content (truncated to 10k chars)
   - Original agent prompt (truncated to 5k chars)
   - Agent output (JSON stringified)
   - Evaluation criteria from config

3. QA model returns verdict JSON
4. Pipeline processes verdict:
   - **pass**: promote output to next step
   - **needs_revision**: re-prompt base agent with QA feedback (retry up to MaxRetries)
   - **critical_failure**: fail execution

5. On final failure (retries exhausted):
   - Fall back to last valid output, OR
   - Terminate with error (depends on downstreamError handling)

### Timeout & Failure Handling

- QA evaluation LLM call timeout: 300 seconds
- If QA call fails: treat as critical_failure (no fallback)
- If QA prompt is malformed: ValueError with message about empty system prompt

---

## Testing & Verification

QA agents are verified via:

- Unit tests: prompt loading, config parsing, evaluation JSON schema validation
- Integration tests: end-to-end evaluation loop with mock articles and agent outputs
- Manual tests: test each QA agent with a real article and known base agent output

Test location: `tests/services/test_qa_agent_service.py`

---

## Frequently Asked Questions

**Q: Can I use a different LLM for QA than for the base agent?**
A: Yes. Override the model in agent_models via `{AgentName}QA` key. Provider can be overridden via `{AgentName}QA_provider`.

**Q: What if the evaluation_criteria list is empty?**
A: The user message will show "Evaluation Criteria: " with no bullet points. This is allowed but not recommended; the model will default to common sense evaluation.

**Q: Can I disable QA for a specific agent?**
A: Yes. Set `QA.Enabled["{AgentName}"] = false` to skip QA and bypass retries.

**Q: What if a base agent isn't in QA.Enabled?**
A: Default is false; QA is skipped for that agent.

**Q: What happens if the QA model's verdict is malformed JSON?**
A: The pipeline will attempt to parse it. If parsing fails, the evaluation is treated as critical_failure.

---

## Final Note

QA agents are the final safeguard before outputs enter downstream systems. Invest time in clear, specific evaluation criteria and evidence-based reasoning. A well-designed QA prompt prevents hallucinations and schema violations from propagating through the pipeline.
