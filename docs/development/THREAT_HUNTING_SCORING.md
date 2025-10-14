# Enhanced Threat Hunting Scoring Mechanism

## Overview

Based on the analysis of Windows malware keywords across 319 articles (97 Chosen, 222 Rejected), I've implemented an enhanced scoring mechanism that automatically identifies high-quality threat hunting and malware analysis content.

**Integration with ML Content Filtering:** The hunt scoring system is now fully integrated with the ML content filtering system, providing enhanced accuracy and cost optimization through shared threat hunting keywords and confidence scoring.

## Key Findings

### Perfect Discriminators (100% Chosen, 0% others)
These keywords appear **exclusively** in "Chosen" content:

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
- **And 40+ more legitimate Windows executables commonly abused by threat actors**


## Implementation

### New Components

1. **`ThreatHuntingScorer` Class** (`src/utils/content.py`)
   - `score_threat_hunting_content()`: Main scoring function with logarithmic bucket system
   - `_keyword_matches()`: Advanced regex-based keyword detection including obfuscation patterns
   - Logarithmic scoring with diminishing returns for realistic score distribution

2. **Enhanced Metadata** (`src/core/processor.py`)
   - Automatically calculates threat hunting scores during article processing
   - Stores results in article metadata

3. **ML Content Filtering Integration** (`src/utils/content_filter.py`)
   - **Full integration** with hunt scoring system for enhanced accuracy
   - **103 perfect discriminators** shared between systems
   - **Hunt score as ML feature** for improved classification confidence
   - **Confidence enhancement** through hunt score integration
   - **Perfect discriminator protection** - chunks containing threat hunting keywords are never filtered
   - **Cross-platform coverage** (Windows, macOS, Linux patterns)
   - **Cost optimization** with 20-80% reduction in GPT-4o API costs

### Logarithmic Bucket Scoring System

The system uses logarithmic buckets with diminishing returns to provide realistic score distributions:

```
Perfect Score = min(35 × log(matches + 1), 75.0)     # 75 points max (dominant weight)
LOLBAS Score = min(5 × log(matches + 1), 10.0)       # 10 points max  
Intelligence Score = min(4 × log(matches + 1), 10.0) # 10 points max
Good Score = min(2.5 × log(matches + 1), 5.0)        # 5 points max
Negative Penalty = min(3 × log(matches + 1), 10.0)   # -10 points max

Final Score = max(0.0, min(100.0, perfect + good + lolbas + intelligence - negative))
```

**Perfect Discriminators** (75 points max, 103 patterns):
- `rundll32`, `comspec`, `msiexec`, `wmic`, `iex`, `findstr`
- `hklm`, `appdata`, `programdata`, `powershell.exe`, `wbem`
- `.lnk`, `D:\`, `.iso`, `<Command>`, `MZ`
- `svchost`, `-accepteula`, `lsass.exe`, `WINDIR`, `wintmp`
- `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`, `Defender query`
- **Cmd.exe obfuscation regex patterns**: `%VAR:~0,4%`, `!VAR!`, `cmd /V:ON`, `s^e^t`, `c^a^l^l`

**LOLBAS Executables** (10 points max, 64 patterns):
- 64 legitimate Windows executables commonly abused by threat actors
- Examples: `certutil.exe`, `cmd.exe`, `reg.exe`, `schtasks.exe`, `wmic.exe`
- Practical attack techniques with high technical value

**Intelligence Indicators** (10 points max, 45 patterns):
- Real threat activity: `APT`, `threat actor`, `campaign`, `ransomware`
- Specific threat groups: `FIN`, `TA`, `UNC`, `Lazarus`, `Carbanak`
- Real incidents: `breach`, `compromise`, `in the wild`, `active campaign`

**Good Discriminators** (5 points max, 77 patterns):
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

## Future Enhancements

1. **Machine Learning**: Train models on keyword patterns
2. **Dynamic Keywords**: Update keyword lists based on new analysis
3. **Source-Specific Scoring**: Different weights for different sources
4. **Temporal Analysis**: Track keyword evolution over time
5. **Custom Keywords**: Allow users to define their own keyword sets
6. **Additional Regex Patterns**: Expand cmd.exe obfuscation detection
