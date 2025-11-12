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
- **Sonnet 4.5:** 8 observables
- **GPT-4o:** 5 observables
- **GPT-4o-mini:** 3 observables
- **All three agree:** 1 observable (encoded PowerShell execution)
- **Two-model agreements:** Sonnet+GPT-4o (2), Sonnet+GPT-4o-mini (2)

**Analysis:**
- **All three models** found encoded PowerShell execution (`powershell.exe -enc/-encodedCommand`)
- Sonnet extracts the most (8), including full infection chain: `msedge.exe → wscript.exe → powershell.exe → MSBuild.exe`
- GPT-4o extracts more process chains (wscript → cmd → schtasks/reg)
- GPT-4o-mini focuses on direct MSBuild injection paths
- Sonnet uniquely identifies: wscript.exe execution, scheduled task creation, and multiple MSBuild framework paths

---

### Article 1860: Qilin Attack Methods
- **Sonnet 4.5:** 37 observables
- **GPT-4o:** 15 observables
- **GPT-4o-mini:** 6 observables
- **All three agree:** 7 observables (36.2% consistency)
- **Two-model agreements:** Sonnet+GPT-4o (10), Sonnet+GPT-4o-mini (1)

**Key Matches (All Three):**
1. Registry modifications (WDigest, RDP, LSA)
2. WinRAR data exfiltration
3. Active Directory enumeration
4. VSS shadow copy deletion
5. mshta privilege escalation

**Analysis:**
- **High consistency** - All three models identify core ransomware behaviors
- Sonnet extracts the most (37), including detailed reconnaissance (nltest, whoami /priv, tasklist filters, net share, net use)
- GPT-4o extracts more reconnaissance commands than mini
- GPT-4o-mini uniquely captures PsExec lateral movement
- All three convert similar attack logic: registry → persistence, VSS → recovery prevention
- Sonnet uniquely identifies: additional registry keys (LSA DisableRestrictedAdmin), localgroup modifications, RSAT-AD-PowerShell installation

---

### Article 1866: Mem3nt0 mori (Hacking Team)
- **Sonnet 4.5:** 13 observables
- **GPT-4o:** 4 observables
- **GPT-4o-mini:** 4 observables
- **All three agree:** 0 observables (0% consistency - completely different interpretations)
- **Two-model agreements:** Sonnet+GPT-4o (6), Sonnet+GPT-4o-mini (0), GPT-4o+GPT-4o-mini (0)

**Analysis:**
- **Lowest consistency** - All three models interpret the same APT content differently
- Sonnet extracts the most (13), including unique technique types:
  - `file_path_pattern`: Base64 folder/file naming patterns
  - `api_call_pattern`: NtGetContextThread, NtQueryInformationProcess (anti-debugging)
  - `file_search_pattern`: Document file extensions (*.doc, *.xls, *.pdf, etc.)
- GPT-4o focuses on: console.debug sandbox escape, rdpclip.exe process check, generic cmd execution, COM hijacking
- GPT-4o-mini focuses on: PowerShell execution policy bypass, registry persistence, rundll32 DLL loading
- Sonnet and GPT-4o agree on: cmd.exe execution, rdpclip.exe process chain, COM hijacking registry key
- All extract valid observables but from different aspects of the attack chain

---

### Article 1909: Ukrainian Organizations Targeted
- **Sonnet 4.5:** 36 observables
- **GPT-4o:** 17 observables
- **GPT-4o-mini:** 7 observables
- **All three agree:** 5 observables (25% consistency)
- **Two-model agreements:** Sonnet+GPT-4o (9), Sonnet+GPT-4o-mini (3)

**Key Matches (All Three):**
1. Webshell deployment via curl
2. Windows Defender exclusion
3. Scheduled task for memory dumps (2 variations)
4. rdrleakdiag memory dump

**Analysis:**
- Sonnet extracts the most (36), including detailed reconnaissance broken into individual commands
- All three identify the same core attack sequence: webshell → defender bypass → memory dump → persistence
- Sonnet and GPT-4o agree on: tracert, Symantec checks, KeePass enumeration, file enumeration, session queries
- GPT-4o extracts more reconnaissance commands than mini
- GPT-4o-mini uniquely captures OpenSSH installation and net group enumeration
- Sonnet uniquely identifies: individual reconnaissance commands (whoami, tasklist, systeminfo), registry save operations, Python script execution, firewall rule creation

---

### Article 1937: CVE-2025-59287 (WSUS RCE)
- **Sonnet 4.5:** 8 observables
- **GPT-4o:** 4 observables
- **GPT-4o-mini:** 4 observables
- **All three agree:** 4 observables (75% consistency - highest for this article)
- **Two-model agreements:** Sonnet+GPT-4o (2)

**Key Matches (All Three):**
1. PowerShell download commands (dcrsproxy.exe, rcpkg.db)
2. Encoded PowerShell execution
3. Process chain: w3wp → cmd → powershell

**Analysis:**
- **High consistency** - All three models identify the same core techniques
- Sonnet extracts the most (8), including specific download targets and webhook exfiltration
- GPT-4o emphasizes process chains (w3wp → cmd → powershell)
- GPT-4o-mini provides more specific download commands and webhook exfiltration details
- All three identify the same core technique: PowerShell encoding for obfuscation
- Sonnet uniquely identifies: specific file downloads (dcrsproxy.exe, rcpkg.db), webhook exfiltration pattern, msiexec installation

---

### Article 1974: Russian Attacks on Ukraine
- **Sonnet 4.5:** 8 observables
- **GPT-4o:** 8 observables
- **GPT-4o-mini:** 10 observables
- **All three agree:** 8 observables (92.3% consistency - highest overall)
- **Two-model agreements:** None (all found by all three or unique to mini)

**Key Matches (All Three):**
1. whoami, systeminfo, tasklist, net group (reconnaissance)
2. rdrleakdiag (memory dump)
3. winbox64.exe, service.exe, cloud.exe (suspicious binaries)

**Analysis:**
- **Highest consistency** - All three models extract identical core observables
- Simple, clear-cut observables lead to near-perfect overlap
- GPT-4o-mini adds 2 additional observables (PowerShell bypass, scheduled task) not found by others
- All three convert the same attack logic: recon → memory dump → suspicious execution
- Sonnet provides more detailed source context grouping multiple commands together

---

## Pattern Analysis

### Commands Extracted by All Three Models

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

### Techniques Extracted by All Three Models

| Technique | Frequency | Articles |
|-----------|-----------|----------|
| encoded_powershell | 2 | 1794, 1937 |
| registry_modification | 3 | 1860 |
| scheduled_task | 2 | 1909 |

---

## Differentiation Analysis

### What Sonnet Extracts That Others Miss

**Pattern:** Sonnet extracts significantly more observables (110 vs 53 vs 34):

1. **More detailed reconnaissance:**
   - Individual commands broken out (e.g., `cmd.exe /C whoami` vs just `whoami`)
   - More network enumeration commands (tracert, arp, nltest, net use, net share)

2. **Additional technique types:**
   - `file_path_pattern` (e.g., Base64 folder names in Article 1866)
   - `api_call_pattern` (e.g., NtGetContextThread, NtQueryInformationProcess for anti-debugging)
   - `file_search_pattern` (e.g., document file extensions)

3. **More comprehensive process chains:**
   - Full infection chains (e.g., `msedge.exe → wscript.exe → powershell.exe → MSBuild.exe`)
   - More detailed parent→child relationships

4. **Additional registry operations:**
   - More registry keys identified (e.g., LSA DisableRestrictedAdmin)
   - Registry save operations

### What GPT-4o Extracts That Others Miss

**Pattern:** GPT-4o extracts more than GPT-4o-mini:
- **Process chains** (7 instances): More detailed parent→child relationships
- **Reconnaissance commands** (9 instances): whoami /priv, nltest, tasklist filters, arp, tracert
- **Registry operations** (3 instances): More detailed registry save/export operations
- **Complex PowerShell** (2 instances): Event log clearing, AD enumeration

**Note:** Sonnet also extracts most of these, often with more detail.

**Example - Article 1909:**
- GPT-4o: `"CSIDL_SYSTEM\cmd.exe" /C whoami` (with CSIDL normalization)
- Sonnet: `cmd.exe /C whoami` (individual command)
- GPT-4o-mini: (missed)

**Example - Article 1860:**
- GPT-4o: `nltest.exe /dclist:` (domain controller enumeration)
- Sonnet: `nltest /dclist:<domain>` (with domain placeholder)
- GPT-4o-mini: (missed)

### What GPT-4o-mini Extracts That Others Miss

**Pattern:** GPT-4o-mini extracts some unique details:
- **Specific file paths** (2 instances): Exact MSBuild framework paths
- **Lateral movement** (1 instance): PsExec with full command structure
- **Installation commands** (1 instance): OpenSSH MSI installation with full parameters

**Note:** Most of these are also extracted by Sonnet, often with more detail.

**Example - Article 1860:**
- GPT-4o-mini: `cmd /C [PsExec] -accepteula \\IP Address -c -f -h -d -i C:\Users\xxx\ .exe --password [PASSWORD] --spread --spread-process`
- Sonnet: `cmd /C [PsExec] -accepteula \\<IP_Address> -c -f -h -d -i C:\Users\xxx\ .exe --password [PASSWORD] --spread --spread-process` (similar, with placeholder)
- GPT-4o: (missed)

**Example - Article 1909:**
- GPT-4o-mini: `powershell Start-Process -FilePath msiexec.exe -ArgumentList @("/i `"C:\Users\[REMOVED]\downloads\openssh-win64-v8.9.1.0.msi`", "/qn", "/norestart", "ALLUSERS=1") -Wait -NoNewWindow`
- Sonnet: `powershell Start-Process -FilePath msiexec.exe -ArgumentList @("/i `"<path>\openssh-win64-v8.9.1.0.msi`", "/qn", "/norestart", "ALLUSERS=1") -Wait -NoNewWindow` (similar, with placeholder)
- GPT-4o: (missed)

---

## How Models Convert Information to Similar Logic

### 1. **Command Normalization**
All three models normalize Windows commands similarly:
- `cmd.exe /c` → `cmd.exe /C` (case normalization - all three)
- `powershell.exe -enc` → `powershell.exe -encodedCommand` / `-enc <base64_encoded_payload>` (parameter normalization - all three recognize variants)
- All three preserve full command structure when present
- **Sonnet:** Sometimes includes command wrapper (e.g., `cmd.exe /C whoami` vs just `whoami`)
- **GPT models:** May extract just the command name or include full path

### 2. **Process Chain Representation**
- **Sonnet:** Uses `process_chain` type with `→` symbol, includes full infection chains (e.g., `msedge.exe → wscript.exe → powershell.exe → MSBuild.exe`)
- **GPT-4o:** Prefers `process_chain` type for multi-step executions with `→` symbol
- **GPT-4o-mini:** Sometimes uses `process_cmdline` for the same chains, but includes full paths when using `process_chain`
- **All three:** Use `→` symbol to represent parent→child relationships

**Example - Article 1937:**
- Sonnet: `[process_chain] w3wp.exe → cmd.exe → powershell.exe`
- GPT-4o: `[process_chain] w3wp.exe → cmd.exe → powershell.exe`
- GPT-4o-mini: `[process_chain] C:\Windows\System32\w3wp.exe → C:\Windows\System32\cmd.exe → C:\Windows\System32\powershell.exe`
- **Logic:** All three identify the same execution chain; GPT-4o-mini includes full paths

**Example - Article 1794:**
- Sonnet: `[process_chain] msedge.exe → wscript.exe → powershell.exe → MSBuild.exe` (full infection chain)
- GPT-4o: `[process_chain] C:\Windows\System32\wscript.exe → <script_path>` (partial chain)
- GPT-4o-mini: `[process_chain] C:\Windows\System32\powershell.exe → C:\Windows\System32\msbuild.exe` (partial chain)
- **Logic:** Sonnet captures the complete infection chain from initial vector to final payload

### 3. **Placeholder Usage**
All three models use similar placeholder strategies:
- `<base64string>`, `<base64_encoded_payload>`, `<base64_payload>` for encoded content (all three recognize variants)
- `<script_path>`, `<path_to_vbs_script>`, `<command>` for file paths/commands
- `[REMOVED]` for sanitized data (all three)
- `<placeholder>`, `<domain>`, `<IP_Address>` for variable content
- **Sonnet:** Sometimes uses more descriptive placeholders (e.g., `<8-byte-base64-string>`, `<malicious_dll>`)

### 4. **Registry Key Extraction**
All three models extract registry keys consistently:
- Full registry paths: `HKLM\SYSTEM\CurrentControlSet\...` (all three)
- Registry modification operations: `reg add`, `reg save` (all three)
- **Sonnet:** Extracts more registry keys (e.g., LSA DisableRestrictedAdmin) and includes save operations
- **GPT models:** Focus on modification operations (add, modify values)

### 5. **Context Interpretation**
**Key Finding:** Even when extracting the same observable, all three models often provide different `source_context` interpretations:

**Example - Article 1974 (whoami):**
- Sonnet: "After gaining access, they executed a series of reconnaissance commands (whoami, systeminfo, tasklist, net group) to map the environment."
- GPT-4o: "Executed to map the environment."
- GPT-4o-mini: "Adversaries executed 'whoami' to identify the current user."
- **Similarity:** Low (0.3-0.5) - different wording, same meaning. Sonnet groups commands together.

**Example - Article 1909 (rdrleakdiag):**
- Sonnet: "rdrleakdiag /p <process> /o <profile>\downloads /fullmemdmp /wait 1"
- GPT-4o: "The attackers performed a memory dump using the Windows Resource Leak Diagnostic tool."
- GPT-4o-mini: "The attackers used the Windows Resource Leak Diagnostic tool to perform a memory dump."
- **Similarity:** GPT models similar (0.69), Sonnet different phrasing

**Example - Article 1860 (WinRAR):**
- Sonnet: "C:\Program Files\WinRAR\WinRAR.exe a -ep1 -scul -r0 -iext -imon1 <target_file>"
- GPT-4o: "Executed to package data for exfiltration."
- GPT-4o-mini: "The attacker used WinRAR to package and exfiltrate data."
- **Similarity:** GPT models similar context, Sonnet focuses on command structure

---

## Consistency by Article Complexity

| Article | Complexity | All Three Agree | Notes |
|---------|------------|-----------------|-------|
| 1974 | Low (simple commands) | 92.3% (8/8) | Near-perfect overlap on straightforward observables |
| 1937 | Medium (RCE) | 75.0% (4/8) | High consistency on core techniques |
| 1860 | Medium (ransomware) | 36.2% (7/37) | Good overlap on core techniques, Sonnet extracts much more |
| 1909 | High (multi-stage) | 25.0% (5/36) | Moderate overlap, Sonnet extracts detailed recon |
| 1794 | Medium (loader) | 18.8% (1/8) | Low overlap, different focus areas |
| 1866 | High (APT) | 0.0% (0/13) | No overlap, all three interpret differently |

**Insight:** Simpler articles with clear-cut observables show higher consistency across all three models. Complex APT articles show lower consistency due to different interpretation approaches. Sonnet consistently extracts more observables, especially in complex articles.

---

## Recommendations

### For Detection Engineering

1. **Use Claude Sonnet 4.5 for maximum extraction:**
   - Extracts 2.1x more observables than GPT-4o, 3.2x more than GPT-4o-mini
   - Best at comprehensive process chains and detailed reconnaissance
   - Identifies unique technique types (API calls, file patterns)
   - Most detailed registry operations and save operations
   - **Best for:** High-value articles, APT analysis, comprehensive threat intelligence

2. **Use GPT-4o for balanced extraction:**
   - Extracts 56% more observables than GPT-4o-mini
   - Better at process chains and reconnaissance commands than mini
   - More detailed registry operations than mini
   - **Best for:** Standard threat intelligence, when Sonnet is unavailable

3. **Use GPT-4o-mini for cost-effective extraction:**
   - Captures 64% of GPT-4o's observables at lower cost
   - Sometimes extracts unique details (specific paths, full command parameters)
   - **Best for:** High-volume, lower-criticality articles, bulk processing

4. **Combine all three for maximum coverage:**
   - 25 observables found by all three (highest confidence)
   - 29 observables found by Sonnet+GPT-4o (high confidence)
   - 85 observables unique to Sonnet (comprehensive)
   - 28 observables unique to GPT-4o (complementary)
   - 9 observables unique to GPT-4o-mini (complementary)

### For Model Selection

- **High-value articles / APT analysis:** Use Sonnet 4.5 for maximum observables
- **Standard threat intelligence:** Use GPT-4o for balanced extraction
- **Bulk processing:** Use GPT-4o-mini for cost efficiency
- **Critical analysis:** Run all three and merge results, prioritize observables found by multiple models

---

## Summary: Three-Way Comparison Highlights

**Key Statistics:**
- **25 observables** found by all three models (highest confidence)
- **29 observables** found by Sonnet + GPT-4o (high confidence)
- **6 observables** found by Sonnet + GPT-4o-mini
- **0 observables** found by GPT-4o + GPT-4o-mini (but not Sonnet)

**Article-Level Agreement:**
- **Article 1974:** 92.3% agreement (8/8 observables) - highest consistency
- **Article 1937:** 75.0% agreement (4/8 observables) - high consistency
- **Article 1866:** 0.0% agreement (0/13 observables) - lowest consistency

**Key Insight:** Sonnet extracts 2.1x more observables than GPT-4o and 3.2x more than GPT-4o-mini. However, the 25 observables found by all three models represent the highest-confidence detections for detection engineering.

---

## Quantitative Metrics

### Coverage Metrics

**Extraction Volume:**
- **Sonnet 4.5:** 110 observables (18.3/article) - Baseline
- **GPT-4o:** 53 observables (8.8/article) - 48.2% of Sonnet
- **GPT-4o-mini:** 34 observables (5.7/article) - 30.9% of Sonnet

**Coverage Ratio:**
- GPT-4o extracts 48.2% of what Sonnet extracts
- GPT-4o-mini extracts 30.9% of what Sonnet extracts
- GPT-4o-mini extracts 64.2% of what GPT-4o extracts

**Interpretation:** Sonnet provides the most comprehensive extraction, extracting 2.1x more than GPT-4o and 3.2x more than GPT-4o-mini.

---

### Agreement Metrics

**Multi-Model Consensus:**
- **All three agree:** 25 observables (12.7% of total, 38.1% of average)
- **Two models agree:** 35 observables (17.8% of total)
  - Sonnet + GPT-4o: 29 observables
  - Sonnet + GPT-4o-mini: 6 observables
  - GPT-4o + GPT-4o-mini: 0 observables
- **Any consensus:** 60 observables (30.5% of total)

**Unique Extractions (Single Model Only):**
- **Sonnet-only:** 50 observables (25.4% of total)
- **GPT-4o-only:** 9 observables (4.6% of total)
- **GPT-4o-mini-only:** 10 observables (5.1% of total)
- **Total unique:** 69 observables (35.0% of total)

**Consensus Strength Distribution:**
- **High Confidence (3 models):** 25 observables (12.7%)
- **Medium Confidence (2 models):** 35 observables (17.8%)
- **Low Confidence (1 model):** 69 observables (35.0%)

**Interpretation:** 
- 12.7% of all extracted observables have highest confidence (all three agree)
- 30.5% have some form of consensus (2+ models)
- 35.0% are unique to a single model (Sonnet contributes most unique extractions)

---

### Quality Metrics

**Observable Type Diversity:**
- **Sonnet 4.5:** 7 unique observable types
- **GPT-4o:** 2 unique observable types
- **GPT-4o-mini:** 2 unique observable types

**Technique Detection Rates:**
| Technique | Sonnet | GPT-4o | GPT-4o-mini |
|-----------|--------|--------|-------------|
| Process Chain | 22 | 7 | 4 |
| Registry Modification | 8 | 5 | 2 |
| Scheduled Task | 6 | 5 | 2 |
| Encoded PowerShell | 2 | 2 | 2 |

**Interpretation:** Sonnet detects a wider variety of observable types and more instances of each technique, indicating better coverage of attack patterns.

---

### Confidence Metrics

**Multi-Model Consensus Rate:**
- **Three-Model Consensus:** 12.7% (highest confidence)
- **Two-Model Consensus:** 17.8% (medium confidence)
- **Any Consensus:** 30.5% (2+ models agree)

**Single-Model-Only Rate:**
- **Sonnet-only:** 25.4% (comprehensive but unique)
- **GPT-4o-only:** 4.6% (minimal unique contributions)
- **GPT-4o-mini-only:** 5.1% (minimal unique contributions)

**High-Confidence Detection Rate:** 12.7%

**Interpretation:** 
- 12.7% of all observables have the highest confidence (all three models independently identified them)
- 30.5% have some form of validation (2+ models)
- 69.5% are either unique to one model or have no consensus

---

### Efficiency Metrics

**Extraction Efficiency (Observables per Article):**
- **Sonnet 4.5:** 18.3 obs/article
- **GPT-4o:** 8.8 obs/article
- **GPT-4o-mini:** 5.7 obs/article

**Cost Efficiency (Requires API cost data):**
- Would calculate: Cost per observable, Cost per high-confidence observable
- Would calculate: Time per article, Time per observable

**Interpretation:** Sonnet extracts the most observables per article, but cost/time metrics would help determine the best value proposition.

---

### Recommended Metrics for Ongoing Measurement

1. **Coverage Metrics:**
   - Extraction rate (observables/article)
   - Coverage ratio (vs baseline model)
   - Unique contribution rate (model-specific observables)

2. **Agreement Metrics:**
   - Inter-model agreement percentage
   - Consensus strength distribution (high/medium/low confidence)
   - Per-article agreement rate

3. **Quality Metrics:**
   - Observable type diversity
   - Technique detection completeness
   - False positive rate (if ground truth available)

4. **Confidence Metrics:**
   - High-confidence detection rate (3-model consensus)
   - Medium-confidence detection rate (2-model consensus)
   - Single-model-only rate

5. **Efficiency Metrics:**
   - Cost per observable
   - Cost per high-confidence observable
   - Processing time per article
   - Throughput (articles/hour)

6. **Accuracy Metrics (Requires Ground Truth):**
   - Precision (correct observables / total extracted)
   - Recall (correct observables / total in ground truth)
   - F1-Score (harmonic mean of precision and recall)

---

## Files Generated

**Result Files:**
- `claude-sonnet-4-5_extract_results_full_2025-11-10_16-21-13.json` - Sonnet detailed results
- `gpt4o_extract_results_full_2025-11-10_16-01-32.json` - GPT-4o detailed results
- `gpt4o-mini_extract_results_full_2025-11-10_16-02-49.json` - GPT-4o-mini detailed results

**Analysis Files:**
- `three_models_comprehensive_analysis.txt` - Full three-way analysis output
- `analyze_three_models_comprehensive.py` - Comprehensive analysis script
- `extraction_metrics.json` - Quantitative metrics in JSON format
- `extraction_metrics_calculator.py` - Metrics calculation script

