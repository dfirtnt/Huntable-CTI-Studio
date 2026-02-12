# Cmdline Attention Preprocessor

Optional preprocessor for the **CmdlineExtract** sub-agent that surfaces high-likelihood command-line regions earlier in the LLM prompt. Improves extraction quality by focusing attention on LOLBAS-aligned anchors and structural patterns before the full article.

## Overview

The preprocessor scans article text for regions likely to contain Windows command-line observables, then reorders the prompt so those snippets appear first. The LLM still receives the full article; the goal is attention shaping, not content filtering.

**What it does:**
- Identifies lines matching LOLBAS-aligned anchors (powershell, rundll32, certutil, etc.)
- Applies structural rules (.exe + args, quoted paths, Windows paths)
- Extracts snippets with surrounding context
- Prepends snippets to the prompt under `=== HIGH-LIKELIHOOD COMMAND SNIPPETS ===`
- Appends full article under `=== FULL ARTICLE (REFERENCE ONLY) ===`

**What it does NOT do:**
- Extract or validate command lines
- Modify original text
- Apply Sigma/EDR logic
- Score or rank commands

## Configuration

| Setting | Location | Default |
|---------|----------|---------|
| `cmdline_attention_preprocessor_enabled` | Workflow Config → Cmdline Extract agent | `true` |

Toggle in the Workflow Config page under the Cmdline Extract agent panel. The checkbox label is "Attention Preprocessor" or "Cmdline attention preprocessor enabled".

## Anchor Types

### String Anchors (case-insensitive)
Examples: `powershell`, `pwsh`, `rundll32`, `msiexec`, `certutil`, `bitsadmin`, `schtasks`, `netsh`, `mshta`, `cscript`, `wscript`, `forfiles`, `findstr`, `taskkill`, `tasklist`, `curl`, `wget`, `FromBase64String`, `DownloadString`, `Invoke-WebRequest`, `Invoke-Expression`, `IEX`, `New-Object`, `MemoryStream`, `Add-MpPreference`, `Set-MpPreference`, `.lnk`, `.iso`, `.vhd`, `C:\`, `D:\`, `%WINDIR%`, `%TEMP%`, `system32`, `syswow64`, `appdata`, `programdata`, and others aligned with LOLBAS tradecraft.

### Regex Anchors
- Registry keys: `hklm`, `hkcu`, `hkey_local_machine`, `hkey_current_user`
- Registry operations: `reg add`, `reg delete`, `reg query`, etc.
- CMD flags: `/c`, `/k`, `/?`
- PowerShell: `-encodedcommand`, `-enc`
- Rundll32 invocation shape: `rundll32.dll,Export`
- File extensions: `.lnk`, `.iso`, `.img`, `.vhd`, `.vhdx`

### Structural Rules
1. **.exe path + argument** — Quoted or unquoted `.exe` followed by at least one argument token
2. **Quoted .exe + non-punctuation** — `"path\to\tool.exe" verb`
3. **.exe + bare verb** — `tool.exe verb args`
4. **Argument indicators** — `.exe` followed by `-`, `/`, `>`, `<`, `|`, etc.
5. **Two or more Windows paths** — `C:\...` and `D:\...` in same line

## Long-Line Handling

For lines exceeding 500 characters (e.g., newline-poor input):
- **Match-window capture**: ±350 chars around each anchor match
- **Sentence-boundary expansion**: Snippets expanded to nearest sentence boundaries
- Prevents one-snippet-per-article collapse when input has few newlines

## Execution Visibility

When enabled, the preprocessor adds metadata to the Extract Agent conversation log:
- `enabled`: `true`
- `snippet_count`: Number of high-likelihood snippets found

View in Workflow page → execution detail → Extract Agent log.

## Implementation

- **Module**: `src/services/cmdline_attention_preprocessor.py`
- **Entry point**: `process(article_text: str) -> dict`
- **Returns**: `{"high_likelihood_snippets": [...], "full_article": "..."}`
- **Integration**: `llm_service.py` calls preprocessor when `agent_name == "CmdlineExtract"` and `attention_preprocessor_enabled` is true

## Extending Anchors

To add anchors, edit `cmdline_attention_preprocessor.py`:
- **String anchors**: Add to `STRING_ANCHORS` for case-insensitive literal match
- **Regex anchors**: Add pattern to `REGEX_ANCHOR_PATTERNS` (pre-compiled at module load)

Keep anchors aligned with LOLBAS tradecraft. Do not add scoring, weighting, or caps.
