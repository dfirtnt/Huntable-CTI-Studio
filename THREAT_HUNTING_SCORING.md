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

### Good Discriminators (High Chosen ratio)
These keywords have >90% correlation with "Chosen" content:

- **Windows Paths**: `c:\windows\` (98.1% Chosen)
- **File Extensions**: `.bat` (97.1% Chosen), `.ps1` (94.4% Chosen)
- **Technical Patterns**: `==` (94% Chosen), `[.]` (96.7% Chosen)

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
   - `score_threat_hunting_content()`: Main scoring function
   - `_keyword_matches()`: Regex-based keyword detection
   - `_calculate_technical_depth()`: Technical depth analysis

2. **Enhanced Metadata** (`src/core/processor.py`)
   - Automatically calculates threat hunting scores during article processing
   - Stores results in article metadata

### Scoring Algorithm

```
Threat Hunting Score = Perfect Keywords × 15 + Good Keywords × 8 + LOLBAS × 12 + Technical Depth (max 30)
```

**Perfect Keywords** (15 points each):
- `rundll32`, `comspec`, `msiexec`, `wmic`, `iex`, `findstr`
- `hklm`, `appdata`, `programdata`, `powershell.exe`, `wbem`
- `EventID`, `.lnk`, `D:\`, `.iso`, `<Command>`, `MZ`
- `svchost`, `-accepteula`, `lsass.exe`, `WINDIR`, `wintmp`

**Good Keywords** (8 points each):
- `temp`, `==`, `c:\windows\`, `Event ID`, `.bat`, `.ps1`
- `pipe`, `::`, `[.]`

**LOLBAS Executables** (12 points each):
- 150+ legitimate Windows executables commonly abused by threat actors
- Examples: `certutil.exe`, `cmd.exe`, `reg.exe`, `schtasks.exe`, `wmic.exe`
- High correlation with threat hunting content (97.1% Chosen ratio)

**Technical Depth** (up to 30 points):
- CVE references, hex values, registry paths
- Windows paths, executable files, IP addresses
- Hash values, code blocks, technical terms

### Metadata Fields Added

Each article now includes:
- `threat_hunting_score`: Overall score (0-100)
- `perfect_keyword_matches`: List of perfect keywords found
- `good_keyword_matches`: List of good keywords found
- `lolbas_matches`: List of LOLBAS executables found
- `keyword_density`: Keywords per 1000 words
- `technical_depth_score`: Technical depth component (0-30)

## Usage Examples

### High-Quality Threat Hunting Content
**Score: 100/100**
- Contains multiple perfect keywords (`rundll32`, `wmic`, `hklm`)
- High technical depth with CVE references, registry paths
- Excellent for threat hunters and detection engineers

### LOLBAS-Focused Malware Analysis
**Score: 100/100**
- Multiple LOLBAS executables (`certutil.exe`, `cmd.exe`, `regsvr32.exe`)
- High keyword density (129.03 per 1000 words)
- Excellent technical depth with command examples
- Perfect for detection engineering and threat hunting

### General Security News
**Score: 0/100**
- No technical keywords found
- No technical depth indicators
- Limited value for threat hunting

### Technical Malware Analysis
**Score: 100/100**
- Multiple perfect keywords (`rundll32`, `iex`, `lsass.exe`)
- High keyword density (158.73 per 1000 words)
- Excellent technical depth with code blocks and indicators

## Benefits

1. **Automatic Quality Assessment**: No manual review needed
2. **Data-Driven**: Based on actual article classification analysis
3. **Technical Focus**: Identifies content with actionable technical details
4. **Scalable**: Works automatically for all incoming articles
5. **Transparent**: Clear scoring breakdown and keyword matches

## Integration

The scoring mechanism is fully integrated into the article processing pipeline:
- Runs automatically during article ingestion
- Stores results in article metadata
- Available via API and web interface
- Can be used for filtering and sorting

## Future Enhancements

1. **Machine Learning**: Train models on keyword patterns
2. **Dynamic Keywords**: Update keyword lists based on new analysis
3. **Source-Specific Scoring**: Different weights for different sources
4. **Temporal Analysis**: Track keyword evolution over time
5. **Custom Keywords**: Allow users to define their own keyword sets
