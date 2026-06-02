# CmdlineExtract Eval Audit — 2026-05-31

Read-only audit of the `cmdline` sub-agent eval fixtures against the live contract.
**No sinks were modified.** This document exists so the operator can adjudicate the
judgment calls before any write is applied.

## Sources

| Source | What it holds | Notes |
|---|---|---|
| **Contract** | `agentic_workflow_config` id=`4331`, version=`4236`, `is_active=true`, updated `2026-05-29` | Pulled `agent_prompts->'CmdlineExtract'` — operative rubric lives in the inner `system` field. |
| **xlsx canonical** | `HuntableCTI-Europa-ExtractionEvals-7.0.0.xlsx`, sheet `articles_table` | 15 rows with `HuntableType = CmdLine` — but only 10 URLs are in the cmdline fixture. 1 row is a duplicate (Blurring-the-Lines), 4 rows are not in the fixture. |
| **DB rows** | `subagent_evaluations` WHERE `subagent_name = 'cmdline'` | 1,702 historical rows; 10 distinct URLs. Latest-per-URL is dated `2026-05-28` from `workflow_config_version = 4223` — **one version behind the active 4236**. |
| **yaml** | `config/eval_articles.yaml` → `subagents.cmdline` | 10 entries, `(url, expected_count)` only. |
| **articles.json** | `config/eval_articles_data/cmdline/articles.json` | 10 entries: `url, title, content, expected_count`. |
| **ground_truth.json** | `config/eval_articles_data/cmdline/ground_truth.json` | 10 entries: `url, expected_items[]`. Two are intentional empty placeholders (`bitter-end`, `roningloader`). |

## Inter-sink drift snapshot (pre-extraction)

`yaml == articles.json.expected_count` on all 10. `ground_truth.json` item-count matches that on 8/10 (placeholders excepted).

`xlsx Count` and `DB expected_count` are the **stale pair** — they hold the pre-curation values on 5 rows even though the curated lists have moved. `xlsx GroundTruth` is its own animal: partially populated, partially mis-sized (TeamCity Count=13 / GT_len=1; OneNote Count=24 / GT_len=2; Blurring Count=6 / GT_len=2 — and Blurring appears in xlsx twice).

## Eval1 — count comparison

```
art  url-short                                        | mine | xlsx | DB | yaml | a.json | gt.json
 0.  ScreenConnect (levelblue)                        |   1  |   2  |  1 |   1  |    1   |    1
 1.  DarkCloud (fortinet)                             |   1  |   2  |  2 |   2  |    2   |    2
 2.  UNC1549 (cloud.google)                           |   4  |   5  |  5 |   5  |    5   |    5
 3.  Bitter End (proofpoint)                          |  32  |   9  |  4 |   4  |    4   |    0*
 4.  TeamCity (fortinet)                              |  14  |  13  | 13 |  12  |   12   |   12
 5.  OneNote (dfir)                                   |  19  |  24  | 22 |  23  |   23   |   23
 6.  Blurring (dfir)                                  |   7  |   6  |  6 |   6  |    6   |    6
 7.  RONINGLOADER (elastic)                           |   2  |   3  |  2 |   2  |    2   |    0*
 8.  Commented Kill Chain (huntress)                  |  72  |  22  | 22 |  22  |   22   |   22
 9.  Bumblebee (dfir)                                 |   8  |   9  |  9 |   8  |    8   |    8
```

`*` = intentional empty placeholder.

## Self-inconsistency in agent output

Article 8 ("Commented Kill Chain") came back with `my_count = 71` and
`len(my_items) = 72`. Items list is the source of truth (72). The agent
miscounted by one in its own integer field.

## REVIEW items (operator to adjudicate)

Each entry below shows the disputed item, the relevant article excerpt
(verbatim, ~180 chars on each side), my agent's call, the ground_truth.json
position, and the **specific contract clause** each side is citing.

---

### REVIEW 1 — Article 1 (DarkCloud) — `powershell -w hidden -noprofile -ep bypass -c`

**Disputed item:** `powershell -w hidden -noprofile -ep bypass -c`

**Article excerpt** (`https://www.fortinet.com/blog/threat-research/unveiling-a-new-variant-of-the-darkcloud-campaign`):
> …It then creates a WScript.Shell object to run the decoded PowerShell code. Figure 3: Partial code of the JavaScript file. The cosmea variable holds a decoded string, **`powershell -w hidden -noprofile -ep bypass -c`**, while the effortless variable contains the decoded PowerShell code…

**My agent:** REJECTED. Reasoning: "`-c` flag has no inline command payload (decoded PS is appended at runtime), fails fidelity/confidence."

**ground_truth.json:** ACCEPTED.

**Contract clauses in play:**
- Positive scope #3 requires "at least one argument, switch/flag, parameter, pipeline, redirection, or chain." This string has FOUR switches (`-w`, `-noprofile`, `-ep`, `-c`).
- Detection-relevance gate: Sysmon EID 1 / 4688 CommandLine — these exact flags ARE the high-signal detection IOC (`-w hidden -noprofile -ep bypass`).
- Fidelity: "Preserve EXACTLY as written" — the article shows this verbatim as the value of a JS variable that gets passed to `WScript.Shell.Run`.

**Recommendation:** gt is right. **My agent was over-strict.** Accept the gt item; correct my count from 1 → 2.

---

### REVIEW 2 — Article 2 (UNC1549) — `ssh.exe` with `[Username]`/`[IP Address]` placeholders

**Disputed item:** `C:\windows\system32\openssh\ssh.exe[Username]@[IP Address] -p 443 -o ServerAliveInterval=60 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null`

**Article excerpt** (`https://cloud.google.com/blog/topics/threat-intelligence/analysis-of-unc1549-ttps-targeting-aerospace-defense`):
> …object auditing being disabled. **`C:\windows\system32\openssh\ssh.exe[Username]@[IP Address] -p 443 -o ServerAliveInterval=60 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/n…`**

**My agent:** REJECTED. Reasoning: "contains `[Username]` and `[IP Address]` which are placeholders (not the allowed `[REDACTED]` sentinel), failing closed."

**ground_truth.json:** ACCEPTED.

**Contract clauses in play:**
- Negative scope: "Placeholders: `<command>`, `{payload}`, `$(...)`. (Allowed: `[REDACTED]`, defanged indicators hxxp://, [.])"
- Strict reading: `[Username]` and `[IP Address]` are bracketed redaction markers, NOT on the allowed list (only the literal token `[REDACTED]` is).
- Lenient reading: they are clearly redaction markers of the same family as `[REDACTED]`; rejecting them throws away genuine telemetry-derived attacker commands.

**Recommendation:** **REVIEW NEEDED — contract ambiguity.** If the operator wants `[Username]`/`[IP Address]` etc. treated as equivalent to `[REDACTED]`, the contract should be amended to say so explicitly and gt is then correct. If not, the contract is correct and gt should be pruned. Either way, the source of disagreement is the contract, not the article.

---

### REVIEW 3 — Article 4 (TeamCity) — missing `ntdsutil` and two `schtasks.exe /run` entries

**Disputed items (in gt, missed by me):**
1. `ntdsutil.exe 'ac i ntds' 'ifm' 'create full C:\tempp' q q`
2. `schtasks.exe /run /tn "\Microsoft\Windows\DefenderUPDService"`
3. `schtasks.exe /run /tn "\Microsoft\Windows\IISUpdateService"`

**Article excerpts** (`https://www.fortinet.com/blog/threat-research/teamcity-intrusion-saga-apt29-suspected-exploiting-cve-2023-42793`):

> …tried to dump active directory credentials using the Windows utility 'ntdsutil.exe' on the host HOST_2_SVR. They tried to dump credentials using the following command: **`ntdsutil.exe 'ac i ntds' 'ifm' 'create full C:\tempp' q q`**…

> …the actor attempted to execute the newly created task using the following command, again executed through the TeamCity RCE vulnerability on the HOST_1_TEAMCITY: **`schtasks.exe /run /tn "\Microsoft\Windows\DefenderUPDService"`**…

**My agent:** MISSED all three. Notes mention "skipped 'cmd.exe /c C:\…' wrappers" but no explicit reason for dropping these.

**ground_truth.json:** ACCEPTED all three.

**Contract clauses in play:**
- Positive scope #2/#3: `ntdsutil.exe` is a LOLBin with quoted arguments — valid. `schtasks.exe /run /tn "<path>"` has flag + parameter — valid.
- Dedup rule: `schtasks /run /tn DefenderUPDService` is a textually distinct command from the earlier `schtasks /create /tn DefenderUPDService` and should be a separate entry. Same for `IISUpdateService`.
- No anti-rule applies.

**Recommendation:** gt is right. **My agent missed these.** Add three items; correct my count from 14 → 17 (subject to also resolving the echo split below).

---

### REVIEW 4 — Article 4 (TeamCity) — five `echo` IOC commands I split, gt collapsed

**Disputed items (I added 5, gt has none of them):**
1. `echo 167043640 > C:/Windows/Temp/0`
2. `echo 2W1EVQsV5piPbyW6FSsNC8D7irR`
3. `echo 2W28BTpkdCjcRPQNkSF5qFCphlG`
4. `echo 2W2GZqAg8k6ipgBTcHyK5wABDSW`
5. `echo 9fW99pdqfpXU21zd`

**Article excerpt:**
> …Command line: `cmd.exe /c whoami` 212[.]113[.]106[.]100 Command line: `cmd.exe /c systeminfo` 212[.]113[.]106[.]100 Command line: `cmd.exe /c net user` 212[.]113[.]106[.]100 Command line: **`cmd.exe /c "echo 167043640 > C:/Windows/Temp/0"`** 43[.]248[.]34[.]77 Command line: **`echo 2W1EVQsV5piPbyW6FSsNC8D7irR`** 103[.]89[.]13[.]15…

**My agent:** ACCEPTED. Reasoning: "Dedup'd two identical 'echo 2W28BTpk...' entries (different remote IPs, same command). Skipped 'cmd.exe /c …' wrappers." Treated as 5 textually distinct attacker invocations from a telemetry table.

**ground_truth.json:** REJECTED all five.

**Contract clauses in play:**
- Dedup rule: "Unique key = exact character-for-character match of the extracted command string. Near-duplicates (e.g., different arguments) are preserved as separate entries." → favours my read.
- Positive scope #3 ("non-trivial invocation"): `echo <literal>` with one argument is non-trivial — but **bare `echo <opaque-token>` with no redirection has weak detection-engineering value**.
- Detection-relevance gate: an `echo` with a 20-char random string and no redirect IS observable via Sysmon EID 1 but **the rule would only fire on the literal random token**, which is per-incident IOC noise, not behavioural detection.

**Recommendation:** **REVIEW — a legitimate judgment call.** If the eval is rule-pattern oriented, gt's collapse is right; if it is literal-command oriented, my split is right. The contract doesn't resolve this directly — it gives the dedup rule (favours me) and the EDR-observability gate (favours gt). **My read is tighter to the literal contract text**; gt's read is tighter to the *spirit* of "EDR observability overrides completeness." The first `echo 167043640 > …` with redirection is the strongest case for inclusion regardless.

---

### REVIEW 5 — Article 5 (OneNote) — missing `mkdir` and `echo … | AnyDesk --set-password`

**Disputed items (in gt, missed by me):**
1. `mkdir "C:\ProgramData\Any"`
2. `echo btc1000qwe123 | C:\ProgramData\Any\AnyDesk.exe --set-password`

**Article excerpt** (`https://thedfirreport.com/2024/04/01/from-onenote-to-ransomnote-an-ice-cold-intrusion/`):
> …the copied PowerShell script was executed on multiple systems to facilitate the deployment of AnyDesk using the following commands:
> **`mkdir "C:\ProgramData\Any"`**
> # Download AnyDesk
> $clnt = new-object System.Net.WebClient
> …
> cmd.exe /c C:\ProgramData\AnyDesk.exe --install C:\ProgramData\Any --start-with-win --silent
>
> **`cmd.exe /c echo btc1000qwe123 | C:\ProgramData\Any\AnyDesk.exe --set-password`**

**My agent:** MISSED both. No explicit reason in notes.

**ground_truth.json:** ACCEPTED both.

**Contract clauses in play:**
- `mkdir "C:\ProgramData\Any"` — built-in with quoted path argument → positive scope #2/#3 satisfied.
- `echo btc1000qwe123 | C:\ProgramData\Any\AnyDesk.exe --set-password` — chain via pipe `|`, both components non-trivial → positive scope #3 satisfied (after cmd.exe /c wrapper strip).
- No anti-rule applies.

**Recommendation:** gt is right. **My agent missed these.** Add both; correct my count from 19 → 21. (Still 2 short of gt's 23 — the residual delta is two `cd` commands my agent skipped as low-value, which is contract-defensible: bare `cd <path>` has weak detection signal.)

---

### REVIEW 6 — Article 6 (Blurring the Lines) — WinRAR with `<redacted>` markers

**Disputed item (I added, gt does not have):**
`"C:\Program Files\WinRAR\WinRAR.exe" x -iext -ow -ver -imon1   "F:\Shares\<redacted>\<redacted>\<redacted>.zip"`

**Article excerpt** (`https://thedfirreport.com/2025/09/08/blurring-the-lines-intrusion-shows-connection-with-three-major-ransomware-gangs/`):
> Where zipped files were found, these were opened using WinRAR:
> **`"C:\Program Files\WinRAR\WinRAR.exe" x -iext -ow -ver -imon1   "F:\Shares\<redacted>\<redacted>\<redacted>.zip" F:\Shares\<redacted>\<redacted>\<…`**

**My agent:** ACCEPTED. Reasoning: "Included WinRAR command with `<redacted>` angle-bracket markers treating them as redaction tokens equivalent to allowed `[REDACTED]`, not as `<command>` placeholders."

**ground_truth.json:** REJECTED.

**Contract clauses in play:**
- Negative scope: "Placeholders: `<command>`, `{payload}`, `$(...)`. (Allowed: `[REDACTED]`, defanged hxxp://, [.])"
- Angle-bracket-wrapped lowercase content matches the `<command>` placeholder pattern character-for-character. `[REDACTED]` (uppercase, square brackets) is the only allowed sentinel.

**Recommendation:** gt is right. **My agent was lenient.** Drop the item; correct my count from 7 → 6. *(Same operator decision as REVIEW 2 applies — if the contract is amended to treat all bracketed redaction markers as equivalent, both this item and the ssh.exe item flip.)*

---

### REVIEW 7 — Article 8 (Commented Kill Chain) — 50-item expansion (22 → 72)

**Disputed items:** I added 50 entries on top of gt's 22, all from a single ransomware loader's command catalog. Sample (first 10 of 50):

```
reg add "HKLM\Software\Policies\Microsoft\Windows Defender" /v "DisableAntiSpyware" /t REG_DWORD /d "1" /f
reg add "HKLM\Software\Policies\Microsoft\Windows Defender" /v "DisableAntiVirus" /t REG_DWORD /d "1" /f
reg add "HKLM\Software\Policies\Microsoft\Windows Defender\MpEngine" /v "MpEnablePus" /t REG_DWORD /d "0" /f
reg add "HKLM\Software\Policies\Microsoft\Windows Defender\Real-Time Protection" /v "DisableIOAVProtection" /t …
reg add "HKLM\Software\Policies\Microsoft\Windows Defender\SpyNet" /v "DisableBlockAtFirstSeen" /t REG_DWORD /…
reg add "HKLM\System\CurrentControlSet\Services\SecurityHealthService" /v "Start" /t REG_DWORD /d "4" /f
reg add "HKLM\System\CurrentControlSet\Services\WdBoot" /v "Start" /t REG_DWORD /d "4" /f
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v "SecurityHealth" /f
sc delete SecurityHealthService
sc delete WdBoot
```

**My agent:** ACCEPTED 72 distinct strings. Reasoning: article is a deliberately-commented ransomware playbook in `cmd`/`powershell` form, mostly single-line `reg`/`sc`/`bcdedit`/`taskkill` invocations.

**ground_truth.json:** Has 22.

**Contract clauses in play:**
- Positive scope: each entry is a literal single-line `reg.exe` / `sc.exe` / `bcdedit.exe` invocation with non-trivial arguments and clear EDR observability.
- Cross-extractor boundary: "A `reg.exe` command is yours; RegistryExtract pulls the key/value." → reg lines belong to CmdlineExtract.
- Cross-extractor boundary: "An sc.exe / New-Service / net start command is yours; ServicesExtract pulls the service artifact." → sc lines belong to CmdlineExtract.
- No anti-rule applies.

**Recommendation:** **REVIEW — likely my agent is correct on the contract**, but the magnitude warrants human eyes. The gt list of 22 looks like a curated subset rather than a contract-driven rejection. If the operator confirms the article body genuinely contains 72 distinct attacker command strings, gt should be expanded to match. Possible middle ground: keep distinct-key (`reg add` for distinct value-names) but collapse near-identical `sc delete Wd*` into a representative subset — this would NOT be contract-correct under the literal dedup rule, but matches gt's intent.

Note also: agent's own `count` field said 71 while `len(items)` was 72 — an off-by-one in the agent's self-report, not in the items list.

---

### REVIEW 8 — Article 9 (Bumblebee) — `wbadmin` variant added & `whoami /groups` dropped

**Disputed item A (I added):** `wbadmin start backup -backuptarget:\\127.0.0.1\C$\ProgramData\ -include:"C:\windows\NTDS\ntds.dit,C:\windows\system32\co…`

**Article excerpt:**
> psql.exe -U postgres --csv -d VeeamBackup … FROM credentials" **Monitor wbadmin abuse for NTDS.dit/Hive dumping** : **`wbadmin start backup -backuptarget:\\127.0.0.1\C$\ProgramData\ -include:"C:\windows\NTDS\ntds.dit,…`**

**My agent:** ACCEPTED.

**ground_truth.json:** REJECTED.

**Contract clause:** Negative scope explicitly says: "Defensive guidance or hardening recommendations." The phrase "Monitor wbadmin abuse for NTDS.dit/Hive dumping" is **detection-engineering guidance prose**, not attacker telemetry. The `wbadmin` string is presented as the pattern-to-monitor, not as an observed command.

**Recommendation:** gt is right. **My agent was wrong** — failed to recognize the defensive-guidance framing. Drop the item.

**Disputed item B (gt has, I dropped):** `whoami /groups`

**Article excerpt:**
> The threat actor then initiated internal reconnaissance using built-in Windows utilities, including systeminfo, nltest /dclist:, **`whoami /groups`**, and net group domain admins /dom.

**My agent:** DROPPED.

**ground_truth.json:** ACCEPTED.

**Contract clauses in play:**
- Positive scope #3: `/groups` IS a switch — satisfies "at least one switch/flag."
- Context rule (anti-overcautious-rejection): "Surrounding prose, lists, captions, logs, tables, or narrative DO NOT invalidate a command. If the command text itself is literal, complete, and single-line, it is eligible regardless of how it is introduced (e.g., 'such as', 'including', discovery descriptions)."

**Recommendation:** gt is right. **My agent was over-strict** — exactly the case the anti-overcautious-rejection rule was written for.

**Net effect on art 9:** drop wbadmin, add whoami /groups, count stays at 8 but item set changes.

---

## Sink-staleness summary

| Sink | Status | Action it needs |
|---|---|---|
| `xlsx` Count | Pre-curation values on 5 rows; 1 duplicate row; 4 rows are for URLs not in the cmdline fixture | Align Count with `yaml`/`articles.json` on the 10 fixture URLs; either drop the 5 non-fixture rows or move them to a separate sheet |
| `xlsx` GroundTruth | Partially populated; mismatched len-vs-Count on 3 rows | Repopulate from `ground_truth.json` for the 10 fixture URLs |
| `DB` `expected_count` | Holds pre-curation values on 5 rows even though `expected_items` was updated | Re-evaluate cmdline subagent under config v4236; new rows will land with the curated counts |
| `DB` `expected_items` | Mostly aligned with `ground_truth.json` | No write needed; will refresh on next eval run |
| `yaml` | Internally consistent | No action |
| `articles.json` `expected_count` | Internally consistent with yaml and ground_truth.json items-len | No action |
| `ground_truth.json` | 2 intentional empty placeholders awaiting curation | Populate `bitter-end` and `roningloader` (REVIEW items 3 and 7 not above — they are non-judgment-call placeholder populations: my counts 32 and 2 respectively) |

## Final adjudication checklist for the operator

1. **REVIEW 1** (DarkCloud bare `powershell -c`) — accept gt or not?
2. **REVIEW 2** (UNC1549 `[Username]` ssh) — amend contract to widen redaction allowlist, or prune gt?
3. **REVIEW 3** (TeamCity ntdsutil + 2× schtasks /run) — likely just add to my extraction; gt is right.
4. **REVIEW 4** (TeamCity 5 echo IOC commands) — keep my split (contract-literal) or accept gt's collapse (EDR-spirit)?
5. **REVIEW 5** (OneNote mkdir + AnyDesk pipe) — likely just add to my extraction; gt is right.
6. **REVIEW 6** (Blurring WinRAR `<redacted>`) — drop unless REVIEW 2 contract amendment goes through.
7. **REVIEW 7** (Commented Kill Chain 22 → 72) — confirm gt was a curated subset, then expand; or keep gt's selectivity by explicit operator policy.
8. **REVIEW 8** (Bumblebee `wbadmin` add / `whoami /groups` drop) — gt is right on both; my agent had both wrong.

Once adjudicated, the operator can pick a write target (xlsx / yaml / articles.json+ground_truth.json / DB) and the audit will apply only the approved deltas.
