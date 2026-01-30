# CmdlineExtract Prompt Comparison: Best Eval Configs vs Current

## Best scores (nMAE, ≥10 completed articles)

| Config version | nMAE     | Completed | Perfect |
|----------------|----------|-----------|---------|
| **v7689**      | **0.2653** | 14      | 4       |
| v1305          | 0.2857   | 17        | 5       |
| current (v7917) | ~0.41 (in-session) | 14 | 3–5     |

## Structural differences

### v7689 (best nMAE 0.2653) — ~4k chars

- **Shorter, rule-first**: Numbered sections 0–5 (Anti-Reconstruction, Enumeration Exclusion, Multi-Line Exclusion, Positive Allowances, Final Self-Check, Output Format).
- **Framing**: "fail-closed extraction task", "When uncertain, EXCLUDE silently", "Any violation invalidates the output."
- **Model in prompt**: Explicit "Model / Sampling Constraints (MANDATORY) temperature: 0.0 top_p: 0.7".
- **Multi-line**: **Excludes** multi-line and wrapped commands: "Exclude if: The command spans multiple lines; continuation characters are implied (^, `); any visual reconstruction would be required."
- **Anti-reconstruction**: "NEVER extract commands that require: Joining multiple lines; Combining fields; Inferring missing arguments."
- **Enumeration exclusion**: "You MUST NOT extract from inline lists, bulleted lists, 'such as' lists…"
- **Final self-check**: "Before outputting each command: 1. I can highlight the EXACT command on ONE line. 2. … 4. NO joining, trimming, or interpretation was required. If ANY check fails → REMOVE."
- **Final reminder**: "Your task is ONLY to extract what is explicitly and literally printed. When uncertain → EXCLUDE."
- **No** long SPACE INVARIANT / CMD.EXE & CHAINING / POWERSHELL / EXPLICIT EXCLUSIONS blocks.

### v1305 (second best 0.2857) — ~7k chars

- **Anti-reconstruction first**: "0. Anti-Reconstruction Rules" with **concrete FORBIDDEN examples** (e.g. "Process: cmd.exe Arguments: /c whoami" → do not reconstruct).
- **Single-line**: "SINGLE, CONTIGUOUS LINE (no newlines)".
- **"All constraints must be followed exactly."**
- **Do NOT infer, reconstruct, join, or invent any part.**
- Has some "continuation" wording but no long MULTI-LINE & CONTINUATION HANDLING section that **instructs joining**.

### Current (v7917) — ~7.2k chars

- **Long instructions**: CORE MISSION, GLOBAL OUTPUT RULES, DEFINITION: VALID COMMAND LINE (A–E), CMD.EXE & CHAINING, POWERSHELL RULES, **MULTI-LINE & CONTINUATION HANDLING** (join lines with ^ and `), EXPLICIT EXCLUSIONS, FINAL VALIDATION.
- **In-session addition**: "Extract ONLY the exact character string as it appears. Do not output inferred, reconstructed, or alternative phrasings." (helped nMAE to ~0.41.)
- **Multi-line policy**: **Allows** joining: "Lines ending with ^ → remove ^ and join with next line… Multi-line CommandLine fields → join with single spaces."
- Same final as v1305: "Only extract what you can copy-paste from ONE LINE."

## Variations tried in-session

| Version | Change | Result |
|---------|--------|--------|
| v7914   | "Output each command once; count MUST equal length of cmdline_items" | nMAE **worse** (0.66) |
| v7915   | "Extract ONLY exact character string… Do not output inferred, reconstructed, or alternative phrasings" | nMAE **better** (0.41) |
| v7916   | "Rescan code blocks and multi-line CommandLine… include every verbatim command" | nMAE **worse** (0.58); reverted |
| v7917   | Reverted to v7915-style (literal-only) | Same prompt as v7915 |

## Insights

1. **v7689’s strict multi-line policy (exclude, don’t join)** may reduce over-extraction and boundary errors. Current prompt **instructs joining** multi-line CommandLine/Sysmon fields, which can encourage reconstruction and wrong counts.
2. **Shorter, rule-first structure** (v7689) may focus the model better than the long validity-definition blocks in current.
3. **Anti-reconstruction as section 0** with explicit "NEVER join/combine/infer" and **concrete FORBIDDEN examples** (v1305) aligns with best behavior.
4. **Final self-check** ("I can highlight the EXACT command on ONE line"; "NO joining or interpretation was required") before output matches v7689’s best score.
5. **"fail-closed" / "EXCLUDE silently"** and **explicit temperature/top_p in prompt** (v7689) may reinforce determinism.
6. **Literal-only wording** (current v7915) helped but is not enough on its own; **multi-line policy** and **anti-reconstruction ordering** differentiate the best configs.

## Recommendations to improve current prompt

1. **Option A — Adopt v7689’s CmdlineExtract prompt**: Replace current CmdlineExtract prompt with v7689’s (shorter, exclude multi-line, final self-check). Re-run evals and compare nMAE.
2. **Option B — Merge best elements into current**:
   - Add **Anti-Reconstruction as first numbered section** (no joining, no combining fields, no inferring) and 1–2 **concrete FORBIDDEN examples** (v1305 style).
   - **Relax or remove** the current "MULTI-LINE & CONTINUATION HANDLING" that instructs joining; replace with "If the command spans multiple lines or requires joining → EXCLUDE" (v7689 style).
   - Add **Mandatory Final Self-Check** before output: "I can highlight the EXACT command on ONE line; NO joining or interpretation was required. If ANY check fails → REMOVE."
   - Add **"fail-closed"** and **"When uncertain, EXCLUDE silently"** (v7689).
   - Optionally add **Model / Sampling in prompt**: "temperature: 0.0, top_p: 0.7" (v7689).
3. **Do not**: Re-add "count MUST equal length of cmdline_items" (hurt in v7914) or broad "rescan and include every verbatim command" (hurt in v7916).

---

## Bundle inspection (v7927 — best in 10-run tuning, nMAE 0.4286)

**Standard practice:** After every run, read at least one under- and one over-extraction bundle before proposing the next change.

### Under-extraction example (exec 5011: expected 9, actual 8 — bing/akira article)

- **Article snippet:** Contains wbadmin, psql, cmd/rundll32, ssh, and a long chained discovery line.
- **Model output:** 8 cmdline_items including wbadmin (two phrasings: one with escaped quotes, one without), psql, rundll32, net user, net group, ssh (with redacted host), and one merged discovery line.
- **Likely cause:** One command missed (e.g. a distinct literal line) or model merged/dropped one; possible duplicate wbadmin reduced effective distinct count. Under-extraction here is mild (8 vs 9).

### Over-extraction example (exec 5007: expected 13, actual 20 — teamcity article)

- **Model output:** 20 items including e.g. `cmd.exe "/c whoami"` and `cmd.exe /c whoami`, `cmd.exe "/c ipconfig /all"` and discovery-style commands (whoami, ipconfig, hostname, tasklist, netstat, net user) in multiple phrasings.
- **Likely cause:** (1) **Same command in multiple phrasings** — e.g. quoted vs unquoted `/c whoami`. (2) **Enumeration/list extraction** — generic discovery commands (whoami, ipconfig, net user) may be from “commands included: …” style lists rather than single literal lines. (3) Tool names with args (AnyDesk.exe --get-id) as separate items.
- **Prompt implications:** Strengthen “output each distinct command once; do not list the same command in multiple phrasings (e.g. quoted vs unquoted).” Strengthen “do not extract from inline lists, bulleted lists, or ‘such as’ / ‘including’ enumerations.”


---

## Tweak applied (option 3 — small prompt edits at temp 0)

**Baseline:** v7689-style prompt + temp 0 → nMAE 0.3061 (user-reported).

**Edit:** One sentence added to CmdlineExtract instructions (before "Output ONLY the JSON object." or at end): "Output each distinct command exactly once; do not list the same command in multiple phrasings (e.g. quoted vs unquoted). Do not extract from inline lists, bulleted lists, or such as / including enumerations."

**Script:** scripts/apply_cmdline_prompt_tweak_and_eval.py — GET config, apply edit, PUT, run cmdline eval, wait, print nMAE. Run with app + Celery up: .venv/bin/python3 scripts/apply_cmdline_prompt_tweak_and_eval.py [--base-url URL]
