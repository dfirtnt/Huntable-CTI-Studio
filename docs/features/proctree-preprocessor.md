# ProcTree Attention Preprocessor

Optional preprocessor for the **ProcTreeExtract** sub-agent that surfaces high-likelihood
process lineage regions earlier in the LLM prompt. Improves extraction quality by focusing
attention on Sysmon fields, tree renderings, and spawn-pattern anchors before the full article.

## Overview

The preprocessor scans article text for regions likely to contain Windows parent/child process
creation relationships, then reorders the prompt so those snippets appear first. The LLM still
receives the full article; the goal is attention shaping, not content filtering.

**What it does:**

- Identifies lines matching Sysmon field anchors (`ParentImage`, `ParentCommandLine`, etc.)
- Matches tree-rendering glyphs (`└─`, `├─`, `->`, `-->`, `→`)
- Applies structural rules (two known `.exe` tokens + lineage keyword, PID/PPID pairs)
- Extracts snippets with surrounding context lines
- Prepends snippets to the prompt under `=== HIGH-LIKELIHOOD PROCESS TREE SNIPPETS ===`
- Appends full article under `=== FULL ARTICLE (REFERENCE ONLY) ===`

**What it does NOT do:**

- Assemble parent/child tuples (that is the LLM's job)
- Infer PIDs, scores, or confidence
- Modify `full_article` bytes (HARD CONTRACT -- see below)
- Touch other extractors' prompts or the cmdline preprocessor

## HARD CONTRACT

When `agent_name == "ProcTreeExtract"`, the preprocessor operates in **byte-preserving mode**:

- `full_article` is returned byte-for-byte identical to the input (newline boundaries only).
- Snippets are derived/normalized (stripped, context-joined) and are NOT byte-identical to
  the source -- this is intentional.
- Any change that alters `full_article` bytes is a **bug**, not a tuning issue.

## Configuration

| Setting | Location | Default |
|---------|----------|---------|
| `proc_tree_attention_preprocessor_enabled` | Workflow Config -> ProcTree Extract agent | `true` |

Toggle in the Workflow Config page under the ProcTree Extract agent panel.

## Anchor Types

### String Anchors (case-insensitive, high-specificity only)

Sysmon field names:

- `Process Create`, `ProcessCreate`, `ProcessCreated`
- `EventID 1`, `Event ID 1`
- `ParentImage`, `ParentCommandLine`, `ParentProcessName`, `ParentProcessId`, `ParentProcessGuid`

Arrow renderings: `->`, `-->`, `→`

Tree-drawing glyphs: `└─`, `├─`, `└──`, `├──`, `└>`

> String anchors are limited to high-specificity tokens (Sysmon field names, tree glyphs,
> arrows). Bare verbs like "spawn" or "child" are handled by regex anchors with `\b` guards
> to avoid the substring-anchor trap.

### Regex Anchors (P1-P8, case-insensitive)

| Pattern | Description |
|---------|-------------|
| **P1** | Lineage verb binding two tokens: `winword.exe spawned powershell.exe` |
| **P2** | Reverse direction: `X was spawned by Y` |
| **P3** | Parent/child label: `parent process:`, `child pid =` |
| **P4** | PID/PPID numeric: `ppid: 1234`, `process id = 5678` |
| **P5** | Injection/hollowing: `injected code into explorer.exe` |
| **P6** | Relational phrases: `child of svchost.exe`, `running under services.exe` |
| **P7** | Explicit `.exe -> .exe` arrow: `cmd.exe -> powershell.exe` |
| **P8** | Tree glyph + `.exe` at line start: `└── powershell.exe` |

P3, P4, P5, P7, P8 are **strong** anchors. P1, P2, P6 are **weak** and subject to
narrative suppression (see below).

### Structural Rules (T3-T5)

| Rule | Logic |
|------|-------|
| **T3** | Two *known* `.exe` tokens within 60 chars of each other AND a lineage keyword nearby (`spawn`, `launch`, `inject`, `lineage`, `tree`, etc.) |
| **T4** | Sysmon field block: `ParentImage` + `Image` on the same line, OR `ParentCommandLine` + `CommandLine` on the same line |
| **T5** | Two distinct PID/PPID numeric matches on the same line |

All structural rule matches are treated as **strong** anchors.

### Known Process Token List (T3)

T3 proximity matching requires at least two tokens from a hardcoded allow-list of
well-known Windows executables. Examples include:

`services.exe`, `lsass.exe`, `winlogon.exe`, `explorer.exe`, `svchost.exe`,
`cmd.exe`, `powershell.exe`, `pwsh.exe`, `wmic.exe`, `rundll32.exe`, `regsvr32.exe`,
`mshta.exe`, `cscript.exe`, `wscript.exe`, `certutil.exe`, `bitsadmin.exe`,
`schtasks.exe`, `winword.exe`, `excel.exe`, `outlook.exe`, `chrome.exe`, `msedge.exe`,
`psexec.exe`, and others.

## Narrative Suppression

Weak verb anchors (P1, P2, P6) are suppressed when the matched line has **none** of:

- A known `.exe` token from the T3 allow-list
- An arrow or tree-drawing glyph

This prevents generic sentences like *"the attacker launched a campaign"* from polluting
the snippet list.

## Long-Line Handling

For lines exceeding 500 characters (e.g., newline-poor input):

- **Match-window capture**: +/- 400 chars around each anchor match
- **Boundary expansion**: expanded to nearest newline boundary (byte-preserving mode) or
  sentence boundary (non-byte-preserving mode)
- **Overlap merging**: adjacent/overlapping windows are merged before extraction
- **Cross-line context**: the first window gets the previous and next lines prepended/appended

## Snippet Extraction Details

- **Short lines** (<= 500 chars): matching line +/- 1 adjacent line (context)
- **Tree-glyph lines**: +/- 2 adjacent lines to capture full tree block
- **Deduplication**: exact-string dedup, snippets returned in article order
- **`max_snippets` cap**: excess entries dropped from the **end** -- earliest matches
  (highest-signal) are preserved. Process lineage facts typically appear early in
  structured threat reports.

## Execution Visibility

When enabled, the preprocessor adds metadata to the ProcTree Extract agent conversation log:

- `attention_preprocessor_enabled`: `true`
- `attention_preprocessor_snippet_count`: number of high-likelihood snippets found

View in Workflow page -> execution detail -> ProcTree Extract agent log.

## Implementation

- **Module**: `src/services/proc_tree_attention_preprocessor.py`
- **Entry point**: `process(article_text, agent_name=None, max_snippets=None) -> dict`
- **Returns**: `{"high_likelihood_snippets": [...], "full_article": "..."}`
- **Integration**: `llm_service.py` calls the preprocessor when
  `agent_name == "ProcTreeExtract"` and `proc_tree_attention_preprocessor_enabled` is true

## Extending Anchors

Edit `src/services/proc_tree_attention_preprocessor.py`:

- **String anchors**: add to `STRING_ANCHORS_EXACT` -- **only high-specificity tokens**
  (Sysmon field names, glyphs, arrows). Do NOT add bare verbs here.
- **Regex anchors**: add to `PROC_TREE_REGEX_PATTERNS` with `\b` guards. Bare verbs like
  `spawn`, `child`, `parent` belong here.
- **Known process tokens**: add to `KNOWN_PROCESS_TOKENS` for T3 proximity matching.
- Pre-compile regexes at module load. Do not add scoring, weighting, or caps.

_Last updated: 2026-05-17_
