# Workflow Config Comparison: v1643 vs v1729

## Summary
**v1643** performed better on Hunt Query evals than **v1729**.

## Key Differences

### 1. HuntQueriesExtract Prompt (CRITICAL DIFFERENCE)

#### v1643 Prompt Characteristics
- **Length**: 5605 chars
- **Style**: Highly prescriptive, verbose, with extensive constraints
- **Key Features**:
  - Opens with "# Critical Instruction" with hard-stop warnings
  - Explicit anti-inference rules: "You are NOT a helpful assistant"
  - Mandatory verification question before extraction
  - More detailed platform-specific gates with specific schema indicators
  - Extensive exclusion rules and fail-safes
  - Multiple "NON-NEGOTIABLE" and "MANDATORY" markers

#### v1729 Prompt Characteristics
- **Length**: 5045 chars (560 chars shorter)
- **Style**: More structured, concise, cleaner formatting
- **Key Features**:
  - Opens with simple "ROLE" section
  - Uses `/no_think` directive
  - Cleaner section headers with `========================` separators
  - More concise platform gates
  - Less prescriptive language overall

#### Specific Prompt Differences

**v1643 Opening:**
```
# Critical Instruction
***Read fully. Follow all constraints exactly. Any violation invalidates the output.***

- You are NOT a helpful assistant.
- You do NOT infer, reconstruct, normalize, or repair detection logic.
- Your only task is to extract literal, verbatim detection artifacts from the article text.
- When uncertain, EXCLUDE the candidate silently.
- This is a pure extraction task. /no_think
```

**v1729 Opening:**
```
ROLE
You are a strict cyber threat intelligence detection-artifact extraction agent.

/no_think
```

**Platform Gate Differences:**

v1643 has more restrictive gates:
- Microsoft Defender: Requires specific schema fields (DeviceProcessEvents, DeviceNetworkEvents, ProcessCommandLine, InitiatingProcessCommandLine)
- SentinelOne: Requires EventType with specific values
- More explicit exclusion rules

v1729 has broader gates:
- Microsoft Defender: Includes more table types (DeviceFileEvents, DeviceRegistryEvents, DeviceImageLoadEvents, DeviceLogonEvents, DeviceEvents, EmailEvents, IdentityLogonEvents, AlertInfo, AlertEvidence)
- SentinelOne: Requires AT LEAST TWO of multiple fields (EventType, CommandLine, SrcProcName, TgtProcName, ObjectType, AgentUuid, SiteName)
- Splunk: More flexible with index=, sourcetype=, and pipe operators
- Elastic: More field options

### 2. QA_ENABLED Configuration

| Agent | v1643 | v1729 | Status |
|-------|-------|-------|--------|
| ProcTreeExtract | `True` | `False` | ❌ **DIFFERENT** |

**Impact**: v1643 has QA enabled for ProcTreeExtract, which may provide additional validation/feedback loops that improve extraction quality.

### 3. Scalar Configuration Fields

| Field | v1643 | v1729 | Status |
|-------|-------|-------|--------|
| min_hunt_score | `97.0` | `97.0` | ✅ Same |
| ranking_threshold | `6.0` | `6.0` | ✅ Same |
| similarity_threshold | `0.5` | `0.5` | ✅ Same |
| junk_filter_threshold | `0.8` | `0.8` | ✅ Same |
| auto_trigger_hunt_score_threshold | `60.0` | `60.0` | ✅ Same |
| sigma_fallback_enabled | `false` | `false` | ✅ Same |
| rank_agent_enabled | `true` | `true` | ✅ Same |
| qa_max_retries | `3` | `3` | ✅ Same |

### 4. Agent Models

✅ **Identical** - No differences in agent model configurations.

## Root Cause Analysis

### Most Likely Causes of Performance Degradation in v1729:

1. **HuntQueriesExtract Prompt Simplification** (HIGHEST PRIORITY)
   - v1729 removed the highly prescriptive "# Critical Instruction" section
   - Less emphasis on anti-inference rules
   - Broader platform gates may allow false positives
   - Shorter prompt may lose important extraction constraints

2. **QA Disabled for ProcTreeExtract**
   - v1643: `ProcTreeExtract` QA enabled = `True`
   - v1729: `ProcTreeExtract` QA enabled = `False`
   - QA feedback loops may improve extraction quality through iterative refinement

3. **Platform Gate Changes**
   - v1729's broader gates (especially SentinelOne requiring "AT LEAST TWO" fields) may be less restrictive
   - More Microsoft Defender table types in v1729 may increase false positives
   - Less restrictive Splunk/Elastic gates may allow non-query artifacts

## Recommendations

1. **Revert HuntQueriesExtract prompt to v1643 version** (highest priority)
   - Restore "# Critical Instruction" section
   - Restore explicit anti-inference rules
   - Use v1643's more restrictive platform gates

2. **Re-enable QA for ProcTreeExtract**
   - Set `qa_enabled.ProcTreeExtract = True`

3. **Test incrementally**
   - Change one variable at a time to isolate the issue
   - Monitor Hunt Query eval metrics after each change
