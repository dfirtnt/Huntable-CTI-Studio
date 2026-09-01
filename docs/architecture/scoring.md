# Threat Hunting Scoring

The threat hunting scorer assigns a 0-100 numeric score to each ingested article
based on keyword pattern matching. Scores drive filtering, sorting, and workflow
auto-triggering: an article's score must be strictly **above** the configurable
`auto_trigger_hunt_score_threshold` for ingestion to auto-trigger the agentic
workflow. The default is **100**, which sits above the 99.9 score ceiling (see
[Scoring Formula](#scoring-formula)), so **nothing auto-processes by default** —
auto-triggering is opt-in, activated only when a user consciously lowers the
threshold in Settings → Workflow. (The separate `ranking_threshold`, default 6.0,
applies to the LLM RankAgent's 0-10 score inside the workflow, not to this keyword
score.)

Scores are derived from a keyword model trained on 319 labeled articles
(97 high-signal, 222 low-signal). The scorer runs automatically at ingestion
time; scores are stored in article metadata and exposed via the API.

The scorer also feeds the ML content filter
(`src/utils/content_filter.py`):
114 perfect-discriminator patterns are shared between systems, and any chunk
matching a perfect discriminator is excluded from LLM-based classification,
reducing API calls.

## Keyword Categories

### Perfect Discriminators

Appeared exclusively in high-signal training articles. Each match contributes to
the 75-point Perfect score bucket (see [Scoring Formula](#scoring-formula) below).

- **Process names**: `rundll32.exe`, `msiexec.exe`, `svchost.exe`, `lsass.exe`
- **Registry references**: `hklm`, `appdata`, `programdata`, `WINDIR`
- **Command execution**: `iex`, `wmic.exe`, `powershell.exe`
- **File types**: `.lnk`, `.iso`
- **Technical patterns**: `MZ`, `-accepteula`, `wintmp`
- **Path patterns**: `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`
- **Non-Windows (macOS/Linux)**: `osascript`, `do shell script`, `launchctl`, `LaunchAgents`,
  `.plist`, `xattr`, `TCC.db`, `dscl`, `xmrig`, `memfd_create`, `chattr +i`, `base64 -d`,
  `chmod 777` (calibrated 2026-06-21 — high-fidelity carriers that let genuinely-huntable
  non-Windows articles clear the gate; generic admin tokens stay good-tier)

### Supporting Discriminators

Provide corroborating signal; contribute to the 5-point Good score bucket.

- **Windows paths**: `c:\windows\`
- **Script extensions**: `.bat`, `.ps1`
- **Detection patterns**: `==`, `[.]`, `-->`
- **Registry patterns**: `currentversion`
- **Event log patterns**: `Event ID`

### LOLBAS Executables

239 Windows binaries commonly abused in attacks. Contribute to the 10-point
LOLBAS score bucket. Examples:

- **System tools**: `certutil.exe`, `cmd.exe`, `reg.exe`, `schtasks.exe`
- **Network tools**: `bitsadmin.exe`, `ftp.exe`, `netsh.exe`, `wmic.exe`
- **Script engines**: `cscript.exe`, `mshta.exe`, `scriptrunner.exe`
- **Installers**: `installutil.exe`, `regsvr32.exe`, `rundll32.exe`
- **File ops**: `forfiles.exe`, `explorer.exe`, `ieexec.exe`

Full list: `config/keyword_registry.yaml` (tier: `lolbas`), exposed as
`HUNT_SCORING_KEYWORDS["lolbas_executables"]` in `src/utils/content.py`

## Scoring Formula

Each category uses a geometric series with 50% diminishing returns
(`score = max * (1 - 0.5^n)`). This prevents a single keyword-dense article
from saturating any one bucket.

```text
Perfect discriminators  75.0 pts max  (114 patterns)
LOLBAS executables      10.0 pts max  (239 patterns)
Intelligence indicators 10.0 pts max  (56 patterns)
Supporting indicators    5.0 pts max  (94 patterns, key: good_discriminators)
Negative indicators     15.0 pts max  (25 patterns, geometric: 15.0 * (1 - 0.5^n))

Final = max(0.0, min(99.9, perfect + good + lolbas + intelligence - negative))
```

**Perfect discriminators** (75 pts max; sampled from the 114 patterns):
`rundll32.exe`, `comspec`, `msiexec.exe`, `wmic.exe`, `iex`, `findstr.exe`,
`hklm`, `appdata`, `programdata`, `powershell.exe`, `wbem`,
`.lnk`, `D:\`, `.iso`, `<Command>`, `MZ`,
`svchost.exe`, `-accepteula`, `lsass.exe`, `WINDIR`, `wintmp`,
`\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`, `Defender query`

Cmd.exe obfuscation regex patterns (sampled): `%VAR:~0,4%`, `!VAR!`,
`cmd /V:ON`, `s^e^t`, `c^a^l^l`

**LOLBAS executables** (10 pts max): 239 patterns; examples above.

**Intelligence indicators** (10 pts max; sampled from the 56 patterns):
`APT`, `threat actor`, `campaign`, `ransomware`,
`FIN`, `TA`, `UNC`, `Lazarus`, `Carbanak`,
`breach`, `compromise`, `in the wild`, `active campaign`

**Supporting indicators** (5 pts max; sampled from the 94 patterns):
`temp`, `==`, `c:\windows\`, `Event ID`, `.bat`, `.ps1`,
`pipe`, `::`, `[.]`, `-->`, `currentversion`

**Negative indicators** (up to -15 pts, geometric like the positive buckets):
Educational and marketing content: `what is`, `how to`, `best practices`,
`free trial`

## Article Metadata

`src/core/processor.py` calculates scores during
ingestion and stores them in article metadata.
`src/utils/content.py` `ThreatHuntingScorer` exposes:

- `score_threat_hunting_content()` -- main scoring entry point
- `_keyword_matches()` -- regex-based keyword detection, including obfuscation patterns

Each article record carries:

| Field | Type | Description |
|---|---|---|
| `threat_hunting_score` | float 0-100 | Overall score |
| `perfect_keyword_matches` | list | Perfect-discriminator keywords found |
| `good_keyword_matches` | list | Supporting-discriminator keywords found |
| `lolbas_matches` | list | LOLBAS executables found |
| `intelligence_matches` | list | Intelligence-indicator keywords found |
| `negative_matches` | list | Negative-indicator keywords found |

Scores are available via the articles API and displayed in the web interface.

## Score Distribution

> **Note:** Distribution below reflects a snapshot of 754 articles at the time
> this document was written. Current distribution will differ.

| Range | Count | % | Label |
|---|---|---|---|
| 0-19 | 730 | 96.8% | Low threat hunting value |
| 20-39 | 12 | 1.6% | Moderate value |
| 40-59 | 8 | 1.1% | Good value |
| 60-79 | 3 | 0.4% | High value |
| 80-100 | 0 | 0% | Not yet observed |

Score range observed: 0.0-67.5. Mean: 4.0.

## Scored Article Examples

**Score 67.5/100** (highest observed at time of writing)
Contains `rundll32`, `wmic`, `hklm`; includes CVE references and registry paths.

**Score 63.6/100**
Contains `certutil.exe`, `cmd.exe`, `regsvr32.exe`; command-line examples present.

**Score 63.5/100**
Contains `rundll32`, `iex`, `lsass.exe`; code blocks and host-based indicators.

**Score 0/100**
No recognized keywords; no technical depth indicators.

_Last updated: 2026-07-17_
_Last reviewed: 2026-09-01_
