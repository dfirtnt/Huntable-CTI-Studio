# SIGMA Huntability Ranking (v2C‑R)

**Goal:** Score cyber blogs (1–10) for *Sigma rule potential* — only structured log data counts (no payloads, hashes, or binaries).  
**Platforms:** Windows (Sysmon/Security), Linux (auditd), macOS (Endpoint Security), Cloud (CloudTrail/Azure/GCP Audit).  

**Instruction:** Respond strictly using the provided Output Template. No prose before or after.  
Normalize total (A–F sum ÷ 1.3) to produce final 1–10 Huntability Score.  

---

### A. Process Creation (0–4)
*IDs:* Sysmon 1, Sec 4688, auditd EXECVE  
*Look for:* Parent→child paths, exact CLI args, multiple examples, cloud CLI commands.  
**Score:** 0 none | 1 vague | 2 partial | 3 detailed 1–2 cases | 4 multiple complete chains.  

---

### B. Persistence / System Mods (0–3)
*IDs:* Sysmon 12/13/19 | Sec 4697–4702 | System 7045  
*Look for:* Registry keys, services, tasks, LaunchAgents, cloud IAM changes.  
**Score:** 0 none | 1 generic | 2 specific but incomplete | 3 full paths / API calls.  

---

### C. Network / File Telemetry (0–2)
*IDs:* Sysmon 3/7/11/22, DNS 3008  
*Look for:* Dest IP/port, DNS pattern, file create/mod with process.  
**Score:** 0 absent | 1 mention only | 2 clear pattern usable in rule.  

---

### D. Log Correlation (0–2)
*Look for:* Cross‑source chains (proc + net + reg, endpoint + cloud).  
**Score:** 0 single log | 1 weak | 2 clear multi‑log sequence.  

---

### E. Field Structure / Value Modifiers (0–1)
Recognizes `|contains`, `|all`, `|re`, `|base64offset` logic.  
**Score:** 0 none | 1 explicit field/modifier pattern.  

---

### F. Condition Readiness (0–1)
Shows AND/OR logic usable as `condition:` in Sigma.  
**Score:** 0 isolated events | 1 expressed relationship.  

---

### Scoring Bands
1–2 strategic | 3–4 weak | 5–6 moderate | 7–8 strong | 9–10 rule‑ready.  

---

### Output Template
```
SIGMA HUNTABILITY SCORE: [1–10]
A Process: [x] …  
B Persistence: [x] …  
C Network/File: [x] …  
D Correlation: [x] …  
E Modifiers: [x] …  
F Condition: [x] …
Observables: [field names / Event IDs]  
Required Logs: [channels + sources]  
Feasibility: [immediate / needs mapping]
```

---

**Schema Refs:** Generic logsource model (Patzke 2018), Value Modifiers (2019), Rule Creation Guide (SigmaHQ 2022), Win_Event_Map v1 (2025).
