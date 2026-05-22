# ML Model Feature Definitions

Definitions for all 20 features used by the v3 content-filter model (`extract_features_v3()` in `src/utils/content_filter.py`). v1 (27 features) and v2 (19 features) are legacy; do not use as reference for the current model.


## Overview

The content filter runs a **RandomForestClassifier** trained and inferred against a fixed 20-feature vector produced by `extract_features_v3()`. Features are positional — the RF's `feature_importances_` array maps 1:1 to the dict returned by `extract_features_v3()` in declaration order.

**Feature version auto-detection:** `load_model()` reads `<model_path>.meta.json` and sets `feature_version` automatically. Do not pass `feature_version` manually at inference unless you are testing a specific version.

**Eval metrics (v3):** F1 ≈ 0.89 on a 240-row curated eval set (Huntable corpus).


**Legacy versions:**
- v1 (`extract_features()`) — 27 features; deprecated; legacy pkl files with no `.meta.json` sidecar default to v1.
- v2 (`extract_features_v2()`) — 19 features; intermediate cleanup; not in active use.

---

## v3 Feature Reference

Features are grouped by role. Within each group, the declaration order in `extract_features_v3()` is the contract.

### Extractor Signals (positive indicators)

These six features ask "would an ExtractAgent sub-agent emit an artifact from this chunk?" Higher values push the chunk toward Huntable.

---

#### `cmdline_artifact_count`

Count of command-line invocation patterns.

**Detection:** `_V3_CMDLINE` regex — matches `<exe> /<flag>`, `powershell -<flag>`, `cmd /c`, and common LOLBAS tools (`reg`, `sc`, `net`, `wmic`, `certutil`, `bitsadmin`, `schtasks`, `mshta`, `rundll32`, `regsvr32`) followed by an argument.

**Examples:**
- `powershell.exe -EncodedCommand AAAA==`
- `schtasks.exe /create /tn Updater`
- `reg add HKLM\...\Run /v evil`

---

#### `registry_hive_path_count`

Count of hive-rooted registry path references.

**Detection:** `_V3_REGISTRY_HIVE` regex — matches `HKLM\`, `HKCU\`, `HKU\`, `HKCR\`, `HKCC\`, and their long-form equivalents, followed by at least one path component.

**Why this matters:** A hive-rooted path with subkeys is a strong positive signal unique to tradecraft documentation and hunt queries. Generic registry-key text (just "HKLM") is not sufficient.

---

#### `process_lineage_count`

Count of parent-child process relationship indicators.

**Detection:** `_V3_LINEAGE` regex — matches Unicode arrows (`→`), ASCII arrows (`->`), phrases like `spawned by`, `parent process`, `child process`, and patterns of the form `<exe.exe> spawning <exe.exe>`.

---

#### `service_artifact_count`

Count of Windows service manipulation patterns.

**Detection:** `_V3_SERVICE` regex — matches `sc.exe create|delete|config|start|stop|description` and PowerShell service cmdlets (`New-Service`, `Set-Service`, `Stop-Service`, `Remove-Service`, `Start-Service`).

---

#### `scheduled_task_count`

Count of scheduled task creation/manipulation patterns.

**Detection:** `_V3_SCHEDULED_TASK` regex — matches `schtasks.exe /create|change|delete|run|query`, PowerShell task cmdlets (`Register-ScheduledTask`, `New-ScheduledTask`, `Unregister-ScheduledTask`), and XML task definition markers (`<Triggers>`, `<Actions>`, `<Principals>`).

---

#### `hunt_query_count`

Count of hunt-query language markers (Sigma YAML or KQL/SPL pipe expressions).

**Detection:** Sum of two sub-counts:
- **Sigma markers:** any of `title:`, `logsource:`, `detection:`, `selection:`, `condition:`, `falsepositives:` found in the lowercased text.
- **KQL/SPL markers:** any of `| where`, `| project`, `| summarize`, `| extend`, `| join`, table names (`deviceprocessevents`, `devicenetworkevents`, `devicefileevents`, `securityevent`), or field/keyword patterns (`eventcode=`, `source=`, `index=`, `event_simplename`).

---

### Negative Content Indicators

These eight features fire on content that superficially looks technical but is explicitly excluded from ExtractAgent scope: rule formats, atomic IOC lists, educational prose, and marketing copy.

---

#### `yara_rule_indicator`

Binary (0.0 / 1.0). Fires when the chunk contains a YARA rule body.

**Detection:** Two paths — either `_V3_YARA_RULE` matches a `rule <name> { strings:` block, or `_V3_YARA_STRINGS` finds two or more `$x = "..." fullword ascii` / `condition: uint` patterns.

---

#### `suricata_rule_indicator`

Binary (0.0 / 1.0). Fires when the chunk contains a Suricata/Snort rule signature.

**Detection:** `_V3_SURICATA` regex — matches `alert <proto> ... msg:` and Emerging Threats signature identifiers (`ET MALWARE`, `ET POLICY`, `ET SCAN`, etc.).

---

#### `beacon_config_indicator`

Binary (0.0 / 1.0). Fires when the chunk contains three or more Cobalt Strike beacon configuration keys.

**Detection:** `_V3_BEACON_CONFIG` regex over keys from `V3_BEACON_CONFIG_KEYS`: `beacontype`, `sleeptime`, `jitter`, `maxgetsize`, `spawnto`, `polling`, `maxdns`, `watermark`, `license_id`, `kill_date`, `cfg_caution`. Threshold is ≥ 3 matches.

---

#### `hash_count`

Count of cryptographic hash strings (MD5, SHA-1, SHA-256).

**Detection:** `_V3_HASH` regex — matches 32-, 40-, and 64-character lowercase hex strings with word boundaries.

**Note:** Hash-heavy chunks are atomic IOC lists, not hunt content. This is a negative signal.

---

#### `atomic_ioc_density`

Density of atomic IOC tokens per word: `(hash_count + ipv4_count + defanged_domain_count) / word_count`.

**Sub-detectors:**
- `_V3_IPV4` — IPv4 address pattern (`\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}`)
- `_V3_DEFANGED_DOMAIN` — defanged domain notation (`word[.]tld`)

High density indicates an IOC table or feed output rather than hunt-ready content.

---

#### `educational_phrase_count`

Count of hedging or explanatory phrases that signal non-operational, educational content.

**Detection:** Substring match over `V3_EDUCATIONAL_PHRASES`. Includes: `could be used`, `may employ`, `is used to`, `can be used`, `attackers could`, `threat actors may`, `defenders should`, `best practice`, `we recommend`, `how to`, `what is`, `in this blog`, `we will demonstrate`, `throughout this blog`, and similar.

---

#### `mitre_ttp_only_density`

MITRE technique reference density, counted only when no command-line artifacts are present.

**Calculation:** `(mitre_count / word_count) if cmdline_artifact_count == 0 else 0.0`

**Detection:** `_V3_MITRE` regex — `T\d{4}(\.\d{1,3})?` (e.g., `T1059.001`).

**Rationale:** A pure TTP table with no supporting command-line content is not extractable by CmdlineExtract or the other sub-agents. Chunks that mix TTP references with actual commands score 0 here.

---

#### `marketing_term_count`

Count of marketing and CTA phrases from `V2_MARKETING_TERMS` (~30 terms).

**Detection:** Substring match over `V2_MARKETING_TERMS`. Includes: `demo`, `free trial`, `book a demo`, `managed service`, `webinar`, `white paper`, `sign up`, `subscribe`, `contact sales`, `schedule a call`, `leverage`, `empower`, `streamline`, `transform your`, `our solution`, `case study`, `testimonial`, and similar.

---

### Discriminators

These four features are cross-cutting signals that help the model distinguish technically rich chunks from superficially similar noise.

---

#### `perfect_pattern_count`

Count of perfect-discriminator keyword matches, with noisy short patterns excluded.

**Detection:** Iterates `HUNT_SCORING_KEYWORDS["perfect_discriminators"]` (92 patterns), skipping `V3_NOISY_PERFECT_DISCRIMINATORS` = `{"MZ", "C:\\", "D:\\"}`. Remaining patterns are matched case-insensitively against the raw text via `re.escape()`.


**Pattern categories:**
- Windows executables: `rundll32.exe`, `msiexec.exe`, `svchost.exe`, `lsass.exe`, `wscript.exe`, `conhost.exe`, `winlogon.exe`
- Registry/environment: `hklm`, `appdata`, `programdata`, `WINDIR`, `wintmp`, `\\temp\\`, `\\pipe\\`
- Command execution: `powershell.exe`, `wmic.exe`, `iex`, `findstr.exe`, `reg.exe`
- PowerShell techniques: `FromBase64String`, `MemoryStream`, `DownloadString`, `invoke-mimikatz`, `invoke-shellcode`
- KQL Advanced Hunting tables: `DeviceProcessEvents`, `DeviceNetworkEvents`, `DeviceEvents`, `EmailEvents`, `InitiatingProcessCommandLine`, `ProcessCommandLine`
- Falcon EDR fields: `ProcessRollup2`, `event_simpleName`, `ImageFileName`, `ParentBaseFileName`, `SHA256HashData`, `ScriptContent`, `RegistryOperation`
- SentinelOne: `EventType = Process`, `EventType = File`, `EventType = Registry`, `EventType = Network`, `EventType = ScheduledTask`
- Splunk CIM: `Endpoint.Processes`, `Endpoint.Registry`, `Endpoint.Filesystem`
- Elastic Security: `logs-endpoint.events.process`, `logs-endpoint.events.file`, `logs-endpoint.events.registry`

---

#### `attacker_placed_path_count`

Count of attacker-staged filesystem paths — locations adversaries commonly use for staging, distinct from generic Windows paths.

**Detection:** `_V3_ATTACKER_PATH` regex. Matches:
- `C:\Users\Public\<file>`
- `C:\ProgramData\<CustomDir>\<file>` (at least 3 chars in the custom dir name)
- `C:\Windows\Temp\<file>`
- Environment-variable forms: `%PUBLIC%\...`, `%PROGRAMDATA%\...`, `%TEMP%\...`, `%AppData%\<AppName>`
- Unix staging: `/tmp/<file>`, `~/Library/LaunchAgents/<file>`

---

#### `technical_term_count`

Count of security and tradecraft vocabulary matches from `V2_TECHNICAL_TERMS` (~50 terms).

**Detection:** Substring match over `V2_TECHNICAL_TERMS`. Covers: original v1 terms (`dll`, `exe`, `payload`, `backdoor`, `shell`, `exploit`, `vulnerability`, `malware`) plus tradecraft (`persistence`, `privesc`, `lateral movement`, `exfiltration`, `ransomware`, `dropper`, `loader`, `stager`, `implant`, `rootkit`), C2/network (`beacon`, `c2`, `command and control`, `reverse shell`), system artifacts (`registry key`, `scheduled task`, `mutex`, `process injection`, `dll injection`), credential terms (`lsass`, `mimikatz`, `kerberos`, `ntlm`, `credential dump`), indicators (`ioc`, `ttp`, `observable`), and cryptographic/forensic terms (`sha256`, `sha1`, `md5`, `base64`, `obfuscat`, `encoded payload`).

---

#### `has_code_blocks`

Binary (0.0 / 1.0). Fires on markdown code blocks or inline code spans.

**Detection:** `re.search(r"```|`[^`]+`", text)`

---

### Density / Aggregates

---

#### `cmdline_density`

Command-line artifact density per word: `cmdline_artifact_count / word_count`.

`word_count` is clamped to a minimum of 1 to prevent division by zero.

---

#### `extractor_signal_strength`

Sum of all six extractor signal counts:

```
cmdline_artifact_count + registry_hive_path_count + process_lineage_count
+ service_artifact_count + scheduled_task_count + hunt_query_count
```

This is the primary aggregate positive signal. The RF uses it as a length-normalized proxy for overall extractability.

---

## Feature Version Compatibility

| Version | Feature count | Extractor function | Status |
|---|---|---|---|
| v1 | 27 | `extract_features()` | Legacy; default for pkl files with no `.meta.json` sidecar |
| v2 | 19 | `extract_features_v2()` | Legacy; intermediate cleanup |
| v3 | 20 | `extract_features_v3()` | **Production** |

`load_model()` reads `<model_path>.meta.json` and sets `self.feature_version` automatically. Training (`train_model()`) writes this sidecar. A missing sidecar means a legacy v1 pkl; `load_model()` logs a warning and defaults to `"v1"`.


---

## Model Training Reference

| Parameter | Value |
|---|---|
| Algorithm | RandomForestClassifier |
| `n_estimators` | 100 |
| `max_depth` | 10 |
| `class_weight` | balanced |
| `random_state` | 42 |
| Train/test split | 80/20, stratified |
| Eval F1 (Huntable class, v3) | ≈ 0.89 |
| Eval dataset | 240-row curated Huntable corpus |


Feature importances are learned from training data; call `model.feature_importances_` on a trained instance to inspect the current ranking.

---

## Pattern Matching Implementation

`extract_features_v3()` uses pre-compiled class-level regexes (named `_V3_*`) to avoid per-call compilation overhead. The vocabulary lists (`V2_TECHNICAL_TERMS`, `V2_MARKETING_TERMS`, `V3_EDUCATIONAL_PHRASES`, `V3_BEACON_CONFIG_KEYS`) are tuples defined at class level and iterated with `in` (substring) or `re.search(re.escape(p), ...)` matching depending on the feature.

`HUNT_SCORING_KEYWORDS["perfect_discriminators"]` is imported from `src/utils/content.py` and shared by both the keyword-scoring system and the v3 extractor. Changes to that list affect both systems.

_Last updated: 2026-05-15_
_Last reviewed: 2026-05-22_
