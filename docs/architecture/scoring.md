# Threat Hunting Scoring

The threat hunting scorer assigns a 0-100 numeric score to each ingested article
based on keyword pattern matching. Scores drive filtering and sorting: articles
below the configured `ranking_threshold` (default 6.0) are suppressed from the
working queue.

Scores are derived from a keyword model trained on 319 labeled articles
(97 high-signal, 222 low-signal). The scorer runs automatically at ingestion
time; scores are stored in article metadata and exposed via the API.

The scorer also feeds the ML content filter
([`src/utils/content_filter.py`](../../src/utils/content_filter.py)):
92 perfect-discriminator patterns are shared between systems, and any chunk
matching a perfect discriminator is excluded from LLM-based classification,
reducing API calls.

## Keyword Categories

### Perfect Discriminators

Appeared exclusively in high-signal training articles. Each match contributes to
the 75-point Perfect score bucket (see [Scoring Formula](#scoring-formula) below).

- **Process names**: `rundll32`, `msiexec`, `svchost`, `lsass.exe`
- **Registry references**: `hklm`, `appdata`, `programdata`, `WINDIR`
- **Command execution**: `iex`, `wmic`, `powershell.exe`
- **File types**: `.lnk`, `.iso`
- **Technical patterns**: `MZ`, `-accepteula`, `wintmp`
- **Path patterns**: `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`

### Supporting Discriminators

Provide corroborating signal; contribute to the 5-point Good score bucket.

- **Windows paths**: `c:\windows\`
- **Script extensions**: `.bat`, `.ps1`
- **Detection patterns**: `==`, `[.]`, `-->`
- **Registry patterns**: `currentversion`
- **Event log patterns**: `EventCode`

### LOLBAS Executables

239 Windows binaries commonly abused in attacks. Contribute to the 10-point
LOLBAS score bucket. Examples:

- **System tools**: `certutil.exe`, `cmd.exe`, `reg.exe`, `schtasks.exe`
- **Network tools**: `bitsadmin.exe`, `ftp.exe`, `netsh.exe`, `wmic.exe`
- **Script engines**: `cscript.exe`, `mshta.exe`, `wscript.exe`
- **Installers**: `msiexec.exe`, `regsvr32.exe`, `rundll32.exe`
- **File ops**: `forfiles.exe`, `explorer.exe`, `ieexec.exe`

Full list: [`src/utils/content.py`](../../src/utils/content.py) `LOLBAS_EXECUTABLES`

## Scoring Formula

Each category uses a geometric series with 50% diminishing returns
(`score = max * (1 - 0.5^n)`). This prevents a single keyword-dense article
from saturating any one bucket.

```
Perfect discriminators  75.0 pts max  (92 patterns)
LOLBAS executables      10.0 pts max  (239 patterns)
Intelligence indicators 10.0 pts max  (56 patterns)
Supporting indicators    5.0 pts max  (89 patterns)
Negative indicators     -penalty      (25 patterns, linear: min(12.5, n x 6.0))

Final = max(0.0, min(100.0, perfect + good + lolbas + intelligence - negative))
```

**Perfect discriminators** (75 pts max):
`rundll32`, `comspec`, `msiexec`, `wmic`, `iex`, `findstr`,
`hklm`, `appdata`, `programdata`, `powershell.exe`, `wbem`,
`.lnk`, `D:\`, `.iso`, `<Command>`, `MZ`,
`svchost`, `-accepteula`, `lsass.exe`, `WINDIR`, `wintmp`,
`\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`, `Defender query`

Cmd.exe obfuscation regex patterns (sampled): `%VAR:~0,4%`, `!VAR!`,
`cmd /V:ON`, `s^e^t`, `c^a^l^l`

**LOLBAS executables** (10 pts max): 239 patterns; examples above.

**Intelligence indicators** (10 pts max):
`APT`, `threat actor`, `campaign`, `ransomware`,
`FIN`, `TA`, `UNC`, `Lazarus`, `Carbanak`,
`breach`, `compromise`, `in the wild`, `active campaign`

**Supporting indicators** (5 pts max):
`temp`, `==`, `c:\windows\`, `Event ID`, `.bat`, `.ps1`,
`pipe`, `::`, `[.]`, `-->`, `currentversion`, `EventCode`

**Negative indicators** (up to -12.5 pts):
Educational and marketing content: `what is`, `how to`, `best practices`,
`free trial`

## Article Metadata

[`src/core/processor.py`](../../src/core/processor.py) calculates scores during
ingestion and stores them in article metadata.
[`src/utils/content.py`](../../src/utils/content.py) `ThreatHuntingScorer` exposes:

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

_Last updated: 2026-05-01_
