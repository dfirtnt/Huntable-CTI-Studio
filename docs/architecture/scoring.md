# Enhanced Threat Hunting Scoring Mechanism

## Overview

Based on the analysis of Windows malware keywords across 319 historical training samples (97 high-signal, 222 low-signal). This scoring mechanism automatically identifies high-quality threat hunting and malware analysis content.

**Integration with ML Content Filtering:** The hunt scoring system is now fully integrated with the ML content filtering system, providing enhanced accuracy and cost optimization through shared threat hunting keywords and confidence scoring.

## Key Findings

### Perfect Discriminators (100% precision in the historical high-signal subset)
These keywords appeared **exclusively** in the high-signal subset of training data:

- **Process Names**: `rundll32`, `msiexec`, `svchost`, `lsass.exe`
- **Registry References**: `hklm`, `appdata`, `programdata`, `WINDIR`
- **Command Execution**: `iex`, `wmic`, `powershell.exe`
- **File Types**: `.lnk`, `.iso`
- **Technical Patterns**: `MZ`, `-accepteula`, `wintmp`
- **Path Patterns**: `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`

### Good Discriminators (Supporting technical content)
These keywords provide supporting technical context:

- **Windows Paths**: `c:\windows\` (high technical value)
- **File Extensions**: `.bat`, `.ps1` (high technical value)
- **Technical Patterns**: `==`, `[.]`, `-->` (detection engineering focus)
- **Registry Patterns**: `currentversion` (detection engineering focus)
- **Event Log Patterns**: `EventCode` (detection engineering focus)

### LOLBAS Executables (High technical value)
Living Off the Land Binaries and Scripts - High technical value:

- **System Tools**: `certutil.exe`, `cmd.exe`, `reg.exe`, `schtasks.exe`
- **Network Tools**: `bitsadmin.exe`, `ftp.exe`, `netsh.exe`, `wmic.exe`
- **Script Engines**: `cscript.exe`, `mshta.exe`, `wscript.exe`
- **Installation Tools**: `msiexec.exe`, `regsvr32.exe`, `rundll32.exe`
- **File Operations**: `forfiles.exe`, `explorer.exe`, `ieexec.exe`
- **And 220+ more legitimate Windows executables commonly abused by threat actors**


## Implementation

### New Components

1. **`ThreatHuntingScorer` Class** (`src/utils/content.py`)
   - `score_threat_hunting_content()`: Main scoring function with geometric series scoring
   - `_keyword_matches()`: Advanced regex-based keyword detection including obfuscation patterns
   - Geometric series with 50% diminishing returns for realistic score distribution

2. **Enhanced Metadata** (`src/core/processor.py`)
   - Automatically calculates threat hunting scores during article processing
   - Stores results in article metadata

3. **ML Content Filtering Integration** (`src/utils/content_filter.py`)
   - **Full integration** with hunt scoring system for enhanced accuracy
   - **92 perfect discriminators** shared between systems
   - **Hunt score as ML feature** for improved classification confidence
   - **Confidence enhancement** through hunt score integration
   - **Perfect discriminator protection** - chunks containing threat hunting keywords are never filtered
   - **Cross-platform coverage** (Windows, macOS, Linux patterns)
   - **Cost optimization** with 20-80% reduction in GPT-4o API costs

### Geometric Series Scoring System

The system uses a geometric series with 50% diminishing returns. Each successive match adds 50% of the previous increment, so scores approach but never reach the category maximum:

```
Formula: score = max_points × (1 - 0.5^n)  where n = number of matches

Perfect Score → 75.0 points max  (dominant weight for technical depth)
LOLBAS Score  → 10.0 points max  (practical attack techniques)
Intelligence  → 10.0 points max  (core threat intelligence value)
Good Score    →  5.0 points max  (supporting technical content)
Negative      → min(12.5, matches × 6.0) linear penalty

Final Score = max(0.0, min(100.0, perfect + good + lolbas + intelligence - negative))
```

**Perfect Discriminators** (75 points max, 92 patterns):
- `rundll32`, `comspec`, `msiexec`, `wmic`, `iex`, `findstr`
- `hklm`, `appdata`, `programdata`, `powershell.exe`, `wbem`
- `.lnk`, `D:\`, `.iso`, `<Command>`, `MZ`
- `svchost`, `-accepteula`, `lsass.exe`, `WINDIR`, `wintmp`
- `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`, `Defender query`
- **Cmd.exe obfuscation regex patterns**: `%VAR:~0,4%`, `!VAR!`, `cmd /V:ON`, `s^e^t`, `c^a^l^l`

**LOLBAS Executables** (10 points max, 239 patterns):
- 239 legitimate Windows executables commonly abused by threat actors
- Examples: `certutil.exe`, `cmd.exe`, `reg.exe`, `schtasks.exe`, `wmic.exe`
- Practical attack techniques with high technical value

**Intelligence Indicators** (10 points max, 56 patterns):
- Real threat activity: `APT`, `threat actor`, `campaign`, `ransomware`
- Specific threat groups: `FIN`, `TA`, `UNC`, `Lazarus`, `Carbanak`
- Real incidents: `breach`, `compromise`, `in the wild`, `active campaign`

**Good Discriminators** (5 points max, 89 patterns):
- `temp`, `==`, `c:\windows\`, `Event ID`, `.bat`, `.ps1`
- `pipe`, `::`, `[.]`, `-->`, `currentversion`, `EventCode`

**Negative Indicators** (-10 points max, 25 patterns):
- Educational/marketing content: `what is`, `how to`, `best practices`, `free trial`

### Metadata Fields Added

Each article now includes:
- `threat_hunting_score`: Overall score (0-100)
- `perfect_keyword_matches`: List of perfect keywords found
- `good_keyword_matches`: List of good keywords found
- `lolbas_matches`: List of LOLBAS executables found
- `intelligence_matches`: List of intelligence indicators found
- `negative_matches`: List of negative indicators found

## Current Performance

**Score Distribution** (754 articles):
- **0-19**: 730 articles (96.8%) - Low threat hunting value
- **20-39**: 12 articles (1.6%) - Moderate value  
- **40-59**: 8 articles (1.1%) - Good value
- **60-79**: 3 articles (0.4%) - High value
- **80-100**: 0 articles (0%) - No articles reach highest tier

**Score Range**: 0.0 - 67.5
**Average Score**: 4.0

## Usage Examples

### High-Quality Threat Hunting Content
**Score: 67.5/100** (Current maximum)
- Contains multiple perfect keywords (`rundll32`, `wmic`, `hklm`)
- High technical depth with CVE references, registry paths
- Excellent for threat hunters and detection engineers

### LOLBAS-Focused Malware Analysis
**Score: 63.6/100**
- Multiple LOLBAS executables (`certutil.exe`, `cmd.exe`, `regsvr32.exe`)
- Excellent technical depth with command examples
- Perfect for detection engineering and threat hunting

### General Security News
**Score: 0/100**
- No technical keywords found
- No technical depth indicators
- Limited value for threat hunting

### Technical Malware Analysis
**Score: 63.5/100**
- Multiple perfect keywords (`rundll32`, `iex`, `lsass.exe`)
- Excellent technical depth with code blocks and indicators

## Benefits

1. **Automatic Quality Assessment**: No manual review needed
2. **Data-Driven**: Based on actual article classification analysis
3. **Technical Focus**: Identifies content with actionable technical details
4. **Scalable**: Works automatically for all incoming articles
5. **Transparent**: Clear scoring breakdown and keyword matches
6. **Regex Support**: Advanced cmd.exe obfuscation pattern detection

## Integration

The scoring mechanism is fully integrated into the article processing pipeline:
- Runs automatically during article ingestion
- Stores results in article metadata
- Available via API and web interface
- Can be used for filtering and sorting
- Supports regex patterns for advanced threat techniques

<!--stackedit_data:
eyJoaXN0b3J5IjpbNzI5ODQ0NzddfQ==
-->