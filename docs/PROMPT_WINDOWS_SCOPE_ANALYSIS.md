# Agent Prompt Analysis: Windows-Only Scope

## Current Multi-Platform References

### 1. Rank Agent (`lmstudio_sigma_ranking.txt`)
**Issues:**
- No platform-specific restrictions
- Generic scoring applies to all platforms

**Recommendation:** Add Windows-only focus

### 2. Rank Agent (`gpt4o_sigma_ranking.txt`)
**Issues:**
- Lines 9, 52-55, 73-77, 112-118, 132-138: References Linux, macOS, Cloud
- Line 112: "Structured Windows/Linux/macOS Event Mapping"
- Line 219-227: "Multi-Platform Coverage" section explicitly lists all platforms

**Recommendation:** Remove all non-Windows references

### 3. Extract Agent (`ExtractAgent`)
**Issues:**
- Lines 28-33: "platform_coverage" section lists:
  - Windows: Sysmon, Security Logs
  - Linux: auditd, Syslog
  - macOS: EndpointSecurity, Unified Logs
  - Cloud: AWS CloudTrail, Azure Activity Logs, GCP Audit Logs

**Recommendation:** Remove Linux, macOS, Cloud entries

### 4. Sigma Generation (`sigma_generation.txt`)
**Issues:**
- Line 18: "Use appropriate log sources (Windows Event Logs, Sysmon, Linux auditd, etc.)"
- Line 52: `product: <windows|linux|macos>`

**Recommendation:** Restrict to Windows only

### 5. Sigma System (`sigma_system.txt`)
**Issues:**
- Line 32: "Cross-platform attack techniques"

**Recommendation:** Change to "Windows-specific attack techniques"

## Recommended Changes

### Priority 1: Remove Multi-Platform Language

1. **Rank Agent (`gpt4o_sigma_ranking.txt`):**
   - Remove macOS, Linux, Cloud references from data sources
   - Change "Multi-Platform Coverage" to "Windows Platform Coverage"
   - Remove Category 1 references to macOS/Cloud CLI commands
   - Remove Category 2 references to macOS Endpoint Security
   - Remove Category 3 cloud references
   - Remove Category 4 Linux/macOS/Cloud event mappings
   - Remove Category 5 Linux/macOS/Cloud persistence mechanisms

2. **Extract Agent (`ExtractAgent`):**
   - Remove Linux, macOS, Cloud from `platform_coverage.valid_sources`
   - Keep only: "Windows: Sysmon, Security Logs"

3. **Sigma Generation (`sigma_generation.txt`):**
   - Change line 18 to: "Use appropriate Windows log sources (Windows Event Logs, Sysmon)"
   - Change line 52 to: `product: windows`

4. **Sigma System (`sigma_system.txt`):**
   - Change line 32 to: "Windows-specific attack techniques"

### Priority 2: Tighten Windows-Specific Language

1. **Emphasize Windows Event IDs:**
   - Sysmon Event IDs: 1, 3, 11, 12, 13, 19, 7045
   - Security Event IDs: 4688, 4697, 4698

2. **Focus on Windows-Specific Observables:**
   - Registry keys (HKCU, HKLM patterns)
   - Windows services (sc.exe, service creation)
   - Scheduled tasks (schtasks.exe, Task Scheduler)
   - Windows file paths (C:\Windows\*, %TEMP%, %APPDATA%)
   - Windows LOTL binaries (powershell.exe, cmd.exe, certutil.exe, bitsadmin.exe)

3. **Remove Cross-Platform Examples:**
   - No cron jobs (Linux)
   - No LaunchAgents/LaunchDaemons (macOS)
   - No Cloud API calls
   - No osascript (macOS)

### Priority 3: Update Scoring Criteria

1. **Category 1 (Process Command-Line):**
   - Remove: macOS osascript, launchctl, Cloud CLI commands
   - Focus: Windows binaries, PowerShell, cmd.exe, Windows-specific LOTL

2. **Category 2 (Parent-Child Process):**
   - Remove: macOS Endpoint Security references
   - Focus: Windows process chains, Sysmon parent-child relationships

3. **Category 4 (Event Mapping):**
   - Remove: Linux auditd, macOS unified logging, Cloud logs
   - Focus: Windows Security Event IDs, Sysmon Event IDs

4. **Category 5 (Persistence):**
   - Remove: Linux systemd/cron, macOS LaunchAgents, Cloud IAM
   - Focus: Windows Registry, Scheduled Tasks, Windows Services

## Specific File Changes Needed

### `src/prompts/gpt4o_sigma_ranking.txt`
- Lines 52-55: Remove macOS/Cloud from Category 1
- Lines 73-77: Remove macOS from Category 2
- Lines 112-118: Change to "Windows Event Mapping" only
- Lines 132-138: Remove Linux/macOS/Cloud from Category 5
- Lines 219-227: Replace with Windows-only data sources

### `src/prompts/ExtractAgent`
- Lines 28-33: Remove Linux, macOS, Cloud from `platform_coverage`

### `src/prompts/sigma_generation.txt`
- Line 18: Change to Windows-only log sources
- Line 52: Change to `product: windows`

### `src/prompts/sigma_system.txt`
- Line 32: Change to Windows-specific techniques

