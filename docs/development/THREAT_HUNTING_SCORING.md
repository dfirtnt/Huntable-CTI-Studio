# Enhanced Threat Hunting Scoring Mechanism

## Overview

Based on the analysis of Windows malware keywords across 319 articles (97 Chosen, 222 Rejected), I've implemented an enhanced scoring mechanism that automatically identifies high-quality threat hunting and malware analysis content.

## Key Findings

### Perfect Discriminators (100% Chosen, 0% others)
These keywords appear **exclusively** in "Chosen" content:

- **Process Names**: `rundll32`, `msiexec`, `svchost`, `lsass.exe`
- **Registry References**: `hklm`, `appdata`, `programdata`, `WINDIR`
- **Command Execution**: `iex`, `wmic`, `powershell.exe`
- **File Types**: `.lnk`, `.iso`
- **Technical Patterns**: `MZ`, `-accepteula`, `wintmp`
- **Path Patterns**: `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`

### Good Discriminators (High Chosen ratio)
These keywords have >90% correlation with "Chosen" content:

- **Windows Paths**: `c:\windows\` (98.1% Chosen)
- **File Extensions**: `.bat` (97.1% Chosen), `.ps1` (94.4% Chosen)
- **Technical Patterns**: `==` (94% Chosen), `[.]` (96.7% Chosen), `-->` (detection engineering focus)
- **Registry Patterns**: `currentversion` (detection engineering focus)
- **Event Log Patterns**: `EventCode` (detection engineering focus)

### LOLBAS Executables (97.1% Chosen ratio)
Living Off the Land Binaries and Scripts - 68 Chosen, 2 Rejected:

- **System Tools**: `certutil.exe`, `cmd.exe`, `reg.exe`, `schtasks.exe`
- **Network Tools**: `bitsadmin.exe`, `ftp.exe`, `netsh.exe`, `wmic.exe`
- **Script Engines**: `cscript.exe`, `mshta.exe`, `wscript.exe`
- **Installation Tools**: `msiexec.exe`, `regsvr32.exe`, `rundll32.exe`
- **File Operations**: `forfiles.exe`, `explorer.exe`, `ieexec.exe`
- **And 150+ more legitimate Windows executables commonly abused by threat actors**


## Implementation

### New Components

1. **`ThreatHuntingScorer` Class** (`src/utils/content.py`)
   - `score_threat_hunting_content()`: Main scoring function with logarithmic bucket system
   - `_keyword_matches()`: Advanced regex-based keyword detection including obfuscation patterns
   - Logarithmic scoring with diminishing returns for realistic score distribution

2. **Enhanced Metadata** (`src/core/processor.py`)
   - Automatically calculates threat hunting scores during article processing
   - Stores results in article metadata

3. **Prefilter Protection** (`src/utils/content_filter.py`)
   - Synchronized with scoring system to protect perfect discriminators from filtering
   - Supports regex patterns for command line obfuscation techniques
   - Ensures high-value content is never filtered out before GPT analysis

### Logarithmic Bucket Scoring System

The system uses logarithmic buckets with diminishing returns to provide realistic score distributions:

```
Perfect Score = min(15 × log(matches + 1), 30.0)     # 30 points max
LOLBAS Score = min(10 × log(matches + 1), 20.0)       # 20 points max  
Intelligence Score = min(8 × log(matches + 1), 20.0) # 20 points max
Good Score = min(5 × log(matches + 1), 10.0)          # 10 points max
Negative Penalty = min(3 × log(matches + 1), 10.0)   # -10 points max

Final Score = max(0.0, min(100.0, perfect + good + lolbas + intelligence - negative))
```

**Perfect Discriminators** (30 points max):
- `rundll32`, `comspec`, `msiexec`, `wmic`, `iex`, `findstr`
- `hklm`, `appdata`, `programdata`, `powershell.exe`, `wbem`
- `EventID`, `.lnk`, `D:\`, `.iso`, `<Command>`, `MZ`
- `svchost`, `-accepteula`, `lsass.exe`, `WINDIR`, `wintmp`
- `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`, `Defender query`
- **Cmd.exe obfuscation regex patterns**: `%VAR:~0,4%`, `!VAR!`, `cmd /V:ON`, `s^e^t`, `c^a^l^l`

**LOLBAS Executables** (20 points max):
- 150+ legitimate Windows executables commonly abused by threat actors
- Examples: `certutil.exe`, `cmd.exe`, `reg.exe`, `schtasks.exe`, `wmic.exe`
- High correlation with threat hunting content (97.1% Chosen ratio)

**Intelligence Indicators** (20 points max):
- Real threat activity: `APT`, `threat actor`, `campaign`, `ransomware`
- Specific threat groups: `FIN`, `TA`, `UNC`, `Lazarus`, `Carbanak`
- Real incidents: `breach`, `compromise`, `in the wild`, `active campaign`

**Good Discriminators** (10 points max):
- `temp`, `==`, `c:\windows\`, `Event ID`, `.bat`, `.ps1`
- `pipe`, `::`, `[.]`, `-->`, `currentversion`, `EventCode`

**Negative Indicators** (-10 points max):
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

**Score Distribution** (1,508 articles):
- **0-19**: 801 articles (53.1%) - Low threat hunting value
- **20-39**: 479 articles (31.8%) - Moderate value  
- **40-59**: 135 articles (9.0%) - Good value
- **60-79**: 93 articles (6.2%) - High value
- **80-100**: 0 articles (0%) - No articles reach highest tier

**Score Range**: 0.0 - 79.2
**Average Score**: 21.2

## Usage Examples

### High-Quality Threat Hunting Content
**Score: 79.2/100**
- Contains multiple perfect keywords (`rundll32`, `wmic`, `hklm`)
- High technical depth with CVE references, registry paths
- Excellent for threat hunters and detection engineers

### LOLBAS-Focused Malware Analysis
**Score: 78.4/100**
- Multiple LOLBAS executables (`certutil.exe`, `cmd.exe`, `regsvr32.exe`)
- Excellent technical depth with command examples
- Perfect for detection engineering and threat hunting

### General Security News
**Score: 0/100**
- No technical keywords found
- No technical depth indicators
- Limited value for threat hunting

### Technical Malware Analysis
**Score: 77.9/100**
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

## Future Enhancements

1. **Machine Learning**: Train models on keyword patterns
2. **Dynamic Keywords**: Update keyword lists based on new analysis
3. **Source-Specific Scoring**: Different weights for different sources
4. **Temporal Analysis**: Track keyword evolution over time
5. **Custom Keywords**: Allow users to define their own keyword sets
6. **Additional Regex Patterns**: Expand cmd.exe obfuscation detection
