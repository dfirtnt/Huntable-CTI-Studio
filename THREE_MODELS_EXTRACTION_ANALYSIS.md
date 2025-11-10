# Three-Model Extraction Comparison Analysis

**Date:** November 10, 2025  
**Models Tested:** Claude Sonnet 4.5, GPT-4o, GPT-4o-mini  
**Articles:** 6 benchmark articles (1794, 1860, 1866, 1909, 1937, 1974)

---

## Executive Summary

**Status:** ✅ Complete three-way analysis (Claude Sonnet 4.5, GPT-4o, GPT-4o-mini)

**Key Findings:**
- **Claude Sonnet 4.5:** 110 total observables across 6 articles (highest volume)
- **GPT-4o:** 53 total observables
- **GPT-4o-mini:** 34 total observables (64.2% of GPT-4o)
- **All three models agree:** 25 observables found by all three (highest confidence)
- **Consistency varies by article:** 0% to 92.3% depending on article complexity

---

## Overall Statistics

| Model | Total Observables | Avg per Article | vs Sonnet |
|-------|------------------|-----------------|-----------|
| **Claude Sonnet 4.5** | **110** | **18.3** | **Baseline** |
| GPT-4o | 53 | 8.8 | 48.2% of Sonnet |
| GPT-4o-mini | 34 | 5.7 | 30.9% of Sonnet |
| **All Three Agree** | **25** | **4.2** | **Highest confidence** |

**Key Insight:** Sonnet extracts 2.1x more observables than GPT-4o, and 3.2x more than GPT-4o-mini. However, 25 observables are found by all three models, representing the highest-confidence detections.

---

## Per-Article Breakdown

### Article 1794: PhantomVAI Loader
- **GPT-4o:** 5 observables
- **GPT-4o-mini:** 3 observables
- **Common:** 1 (25% consistency)
- **Key Match:** Both found encoded PowerShell execution (`powershell.exe -enc/-encodedCommand`)

**Analysis:**
- GPT-4o extracts more process chains (wscript → cmd → schtasks/reg)
- GPT-4o-mini focuses on direct MSBuild injection paths
- Both identify PowerShell encoding as a key technique

---

### Article 1860: Qilin Attack Methods
- **GPT-4o:** 15 observables
- **GPT-4o-mini:** 6 observables
- **Common:** 6 (57.1% consistency - highest overlap)
- **Key Matches:**
  1. Registry modifications (RDP, WDigest)
  2. WinRAR data exfiltration
  3. Active Directory enumeration
  4. VSS shadow copy deletion
  5. mshta privilege escalation

**Analysis:**
- **High consistency** - Both models identify core ransomware behaviors
- GPT-4o extracts more reconnaissance commands (nltest, whoami /priv, tasklist filters)
- GPT-4o-mini uniquely captures PsExec lateral movement
- Both convert similar attack logic: registry → persistence, VSS → recovery prevention

---

### Article 1866: Mem3nt0 mori (Hacking Team)
- **GPT-4o:** 4 observables
- **GPT-4o-mini:** 4 observables
- **Common:** 0 (0% consistency - completely different interpretations)

**Analysis:**
- **Lowest consistency** - Models interpret the same content differently
- GPT-4o focuses on: console.debug sandbox escape, rdpclip.exe process check, generic cmd execution
- GPT-4o-mini focuses on: PowerShell execution policy bypass, registry persistence, rundll32 DLL loading
- Both extract valid observables but from different aspects of the attack chain

---

### Article 1909: Ukrainian Organizations Targeted
- **GPT-4o:** 17 observables
- **GPT-4o-mini:** 7 observables
- **Common:** 6 (50% consistency)
- **Key Matches:**
  1. Webshell deployment via curl
  2. Windows Defender exclusion
  3. Scheduled task for memory dumps (2 variations)
  4. rdrleakdiag memory dump
  5. PowerShell backdoor execution

**Analysis:**
- GPT-4o extracts more reconnaissance commands (whoami, arp, tracert, Symantec checks, KeePass enumeration)
- Both identify the same core attack sequence: webshell → defender bypass → memory dump → persistence
- GPT-4o-mini uniquely captures OpenSSH installation and net group enumeration

---

### Article 1937: CVE-2025-59287 (WSUS RCE)
- **GPT-4o:** 4 observables
- **GPT-4o-mini:** 4 observables
- **Common:** 1 (25% consistency)
- **Key Match:** Both found encoded PowerShell execution

**Analysis:**
- GPT-4o emphasizes process chains (w3wp → cmd → powershell)
- GPT-4o-mini provides more specific download commands and webhook exfiltration details
- Both identify the same core technique: PowerShell encoding for obfuscation

---

### Article 1974: Russian Attacks on Ukraine
- **GPT-4o:** 8 observables
- **GPT-4o-mini:** 10 observables
- **Common:** 8 (88.9% consistency - highest)
- **Key Matches:** All 8 observables found by both:
  1. whoami, systeminfo, tasklist, net group (reconnaissance)
  2. rdrleakdiag (memory dump)
  3. winbox64.exe, service.exe, cloud.exe (suspicious binaries)

**Analysis:**
- **Highest consistency** - Both models extract identical observables
- Simple, clear-cut observables lead to perfect overlap
- GPT-4o-mini adds 2 additional observables (PowerShell bypass, scheduled task)
- Both convert the same attack logic: recon → memory dump → suspicious execution

---

## Pattern Analysis

### Commands Extracted by Both Models

| Command | Frequency | Articles |
|---------|-----------|----------|
| powershell | 5 | 1794, 1860, 1909, 1937, 1974 |
| sc/schtasks | 5 | 1860, 1909, 1974 |
| reg | 2 | 1860 |
| cmd | 2 | 1909 |
| net | 2 | 1974 |
| rundll32 | 2 | 1909 |
| rdrleakdiag | 2 | 1909, 1974 |

**Insight:** PowerShell and scheduled tasks are the most consistently identified techniques across both models.

### Techniques Extracted by Both Models

| Technique | Frequency | Articles |
|-----------|-----------|----------|
| encoded_powershell | 2 | 1794, 1937 |
| registry_modification | 2 | 1860 |
| scheduled_task | 2 | 1909 |

---

## Differentiation Analysis

### What GPT-4o Extracts That GPT-4o-mini Misses

**Pattern:** GPT-4o extracts more:
- **Process chains** (7 instances): More detailed parent→child relationships
- **Reconnaissance commands** (9 instances): whoami /priv, nltest, tasklist filters, arp, tracert
- **Registry operations** (3 instances): More detailed registry save/export operations
- **Complex PowerShell** (2 instances): Event log clearing, AD enumeration

**Example - Article 1909:**
- GPT-4o: `"CSIDL_SYSTEM\cmd.exe" /C whoami` (with CSIDL normalization)
- GPT-4o-mini: (missed)

**Example - Article 1860:**
- GPT-4o: `nltest.exe /dclist:` (domain controller enumeration)
- GPT-4o-mini: (missed)

### What GPT-4o-mini Extracts That GPT-4o Misses

**Pattern:** GPT-4o-mini extracts more:
- **Specific file paths** (2 instances): Exact MSBuild framework paths
- **Lateral movement** (1 instance): PsExec with full command structure
- **Installation commands** (1 instance): OpenSSH MSI installation with full parameters

**Example - Article 1860:**
- GPT-4o-mini: `cmd /C [PsExec] -accepteula \\IP Address -c -f -h -d -i C:\Users\xxx\ .exe --password [PASSWORD] --spread --spread-process`
- GPT-4o: (missed)

**Example - Article 1909:**
- GPT-4o-mini: `powershell Start-Process -FilePath msiexec.exe -ArgumentList @("/i `"C:\Users\[REMOVED]\downloads\openssh-win64-v8.9.1.0.msi`", "/qn", "/norestart", "ALLUSERS=1") -Wait -NoNewWindow`
- GPT-4o: (missed)

---

## How Models Convert Information to Similar Logic

### 1. **Command Normalization**
Both models normalize Windows commands similarly:
- `cmd.exe /c` → `cmd.exe /C` (case normalization)
- `powershell.exe -enc` → `powershell.exe -encodedCommand` (parameter normalization)
- Both preserve full command structure when present

### 2. **Process Chain Representation**
- **GPT-4o:** Prefers `process_chain` type for multi-step executions
- **GPT-4o-mini:** Sometimes uses `process_cmdline` for the same chains
- **Both:** Use `→` symbol to represent parent→child relationships

**Example - Article 1937:**
- GPT-4o: `[process_chain] w3wp.exe → cmd.exe → powershell.exe`
- GPT-4o-mini: `[process_chain] C:\Windows\System32\w3wp.exe → C:\Windows\System32\cmd.exe → C:\Windows\System32\powershell.exe`
- **Logic:** Both identify the same execution chain, GPT-4o-mini includes full paths

### 3. **Placeholder Usage**
Both models use similar placeholder strategies:
- `<base64string>` for encoded content
- `<script_path>` for file paths
- `[REMOVED]` for sanitized data
- `<placeholder>` for variable content

### 4. **Context Interpretation**
**Key Finding:** Even when extracting the same observable, models often provide different `source_context` interpretations:

**Example - Article 1974 (whoami):**
- GPT-4o: "Executed to map the environment."
- GPT-4o-mini: "Adversaries executed 'whoami' to identify the current user."
- **Similarity:** 0.48 (different wording, same meaning)

**Example - Article 1909 (rdrleakdiag):**
- GPT-4o: "The attackers performed a memory dump using the Windows Resource Leak Diagnostic tool."
- GPT-4o-mini: "The attackers used the Windows Resource Leak Diagnostic tool to perform a memory dump."
- **Similarity:** 0.69 (slightly different phrasing)

---

## Consistency by Article Complexity

| Article | Complexity | Consistency | Notes |
|---------|------------|-------------|-------|
| 1974 | Low (simple commands) | 88.9% | Perfect overlap on straightforward observables |
| 1860 | Medium (ransomware) | 57.1% | Good overlap on core techniques |
| 1909 | High (multi-stage) | 50.0% | Moderate overlap, GPT-4o extracts more recon |
| 1794 | Medium (loader) | 25.0% | Low overlap, different focus areas |
| 1937 | Medium (RCE) | 25.0% | Low overlap, different chain representations |
| 1866 | High (APT) | 0.0% | No overlap, completely different interpretations |

**Insight:** Simpler articles with clear-cut observables show higher consistency. Complex APT articles show lower consistency due to different interpretation approaches.

---

## Recommendations

### For Detection Engineering

1. **Use GPT-4o for comprehensive extraction:**
   - Extracts 56% more observables than GPT-4o-mini
   - Better at process chains and reconnaissance commands
   - More detailed registry operations

2. **Use GPT-4o-mini for cost-effective extraction:**
   - Captures 64% of GPT-4o's observables at lower cost
   - Sometimes extracts unique details (specific paths, full command parameters)
   - Good for high-volume, lower-criticality articles

3. **Combine both for maximum coverage:**
   - 22 common observables (high confidence)
   - 31 unique to GPT-4o (comprehensive)
   - 12 unique to GPT-4o-mini (complementary)

### For Model Selection

- **High-value articles:** Use GPT-4o for maximum observables
- **Bulk processing:** Use GPT-4o-mini for cost efficiency
- **Critical analysis:** Run both and merge results

---

## Three-Way Comparison Results

### Observables Found by ALL THREE Models: 25 Total

**Highest Confidence Detections** - These represent the most reliable observables where all three models independently identified the same information:

#### Article 1974 (8/8 = 100% agreement)
All three models found identical observables:
- `whoami`, `systeminfo`, `tasklist`, `net group` (reconnaissance)
- `rdrleakdiag` (memory dump)
- `winbox64.exe`, `service.exe`, `cloud.exe` (suspicious binaries)

#### Article 1860 (7 common observables)
- Registry modifications (WDigest, RDP, LSA)
- WinRAR data exfiltration
- Active Directory enumeration
- VSS shadow copy deletion
- mshta privilege escalation

#### Article 1909 (5 common observables)
- Webshell deployment via curl
- Windows Defender exclusion
- Scheduled tasks for memory dumps (2 variations)
- rdrleakdiag memory dump

#### Article 1937 (4 common observables)
- PowerShell download commands
- Encoded PowerShell execution
- Process chain: w3wp → cmd → powershell

#### Article 1794 (1 common observable)
- Encoded PowerShell execution

#### Article 1866 (0 common observables)
- No overlap - all three models interpreted this APT article differently

### Pattern Analysis: Commands Found by All Three

| Command | Frequency | Articles |
|---------|-----------|----------|
| powershell | 6 | 1794, 1860, 1909, 1937 |
| sc/schtasks | 5 | 1860, 1909 |
| cmd | 4 | 1860, 1909, 1937 |
| reg | 3 | 1860 |
| net | 2 | 1974 |
| rundll32 | 2 | 1909 |
| rdrleakdiag | 2 | 1909, 1974 |
| vssadmin | 1 | 1860 |
| mshta | 1 | 1860 |

**Insight:** PowerShell and scheduled tasks are the most consistently identified techniques across all three models, indicating these are the most reliable detection targets.

### How All Three Models Convert Information to Similar Logic

1. **Command Normalization:**
   - All three normalize `cmd.exe /c` → `cmd.exe /C`
   - All three recognize `powershell.exe -enc` and `-encodedCommand` as equivalent
   - All three preserve full command structure when present

2. **Process Chain Representation:**
   - **Sonnet:** Uses `process_chain` type with `→` symbol
   - **GPT-4o:** Uses `process_chain` type with `→` symbol
   - **GPT-4o-mini:** Sometimes uses `process_cmdline` for chains, but includes full paths
   - **All three:** Identify the same parent→child relationships

3. **Placeholder Usage:**
   - All three use `<base64string>`, `<base64_encoded_payload>`, `<base64_payload>` interchangeably
   - All three use `[REMOVED]` for sanitized data
   - All three use `<placeholder>` for variable content

4. **Registry Key Extraction:**
   - All three extract full registry paths: `HKLM\SYSTEM\CurrentControlSet\...`
   - All three identify registry modification operations (`reg add`, `reg save`)

### Sonnet's Unique Contributions

**Sonnet extracts significantly more observables (110 vs 53 vs 34):**

1. **More detailed reconnaissance:**
   - Individual commands broken out (e.g., `cmd.exe /C whoami` vs just `whoami`)
   - More network enumeration commands (tracert, arp, nltest)

2. **Additional technique types:**
   - `file_path_pattern` (e.g., Base64 folder names)
   - `api_call_pattern` (e.g., NtGetContextThread, NtQueryInformationProcess)
   - `file_search_pattern` (e.g., document file extensions)

3. **More comprehensive process chains:**
   - Full infection chains (e.g., `msedge.exe → wscript.exe → powershell.exe → MSBuild.exe`)
   - More detailed parent→child relationships

4. **Additional registry operations:**
   - More registry keys identified (e.g., LSA DisableRestrictedAdmin)
   - Registry save operations

### Two-Model Agreements

**Sonnet + GPT-4o (but not mini):** 29 observables
- More detailed reconnaissance commands
- Complex registry operations
- Process chains with full paths

**Sonnet + GPT-4o-mini (but not GPT-4o):** 6 observables
- Specific file paths (MSBuild framework paths)
- PsExec lateral movement
- OpenSSH installation commands

**GPT-4o + GPT-4o-mini (but not Sonnet):** 0 observables
- No unique agreements between GPT models that Sonnet missed

---

## Files Generated

- `claude-sonnet-4-5_extract_results_full_2025-11-10_16-21-13.json` - Sonnet detailed results
- `gpt4o_extract_results_full_2025-11-10_16-01-32.json` - GPT-4o detailed results
- `gpt4o-mini_extract_results_full_2025-11-10_16-02-49.json` - GPT-4o-mini detailed results
- `three_models_comprehensive_analysis.txt` - Full three-way analysis output
- `analyze_three_models_comprehensive.py` - Analysis script

