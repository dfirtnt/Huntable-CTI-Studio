# OS Detection Agent Benchmark Test Results

This document records benchmark test results for various language models evaluating OS detection performance (determining which operating system described behaviors target).

## Test Methodology

**Test Articles:** 6 articles (IDs: 1974, 1909, 1866, 1860, 1937, 1794)

**Runs per Model:** 1 run per article (temperature=0, top_p=1 = deterministic)

**Evaluation Metrics:**
- **JSON Validity:** Percentage of runs that produce valid JSON
- **Valid Label:** Percentage of runs that produce a valid OS label (Windows, Linux, MacOS, or multiple)
- **Label Consistency:** Consistency of OS labels across runs (for same article)
- **Accuracy:** Manual validation against ground truth (to be determined)

**Output Format Expected:**
```json
{
  "operating_system": "Windows" | "Linux" | "MacOS" | "multiple"
}
```

---

## Test Results

| Article | Model | OS Label | Valid Label | JSON Valid |
|---------|-------|---------|-------------|------------|
| 1974 | TBD | | | |
| 1909 | TBD | | | |
| 1866 | TBD | | | |
| 1860 | TBD | | | |
| 1937 | TBD | | | |
| 1794 | TBD | | | |

---

## Models Tested

### Local Models (LMStudio)
- `meta-llama-3.1-8b-instruct`
- `codellama-7b-instruct`
- `qwen/qwen2.5-coder-32b`
- `qwen2-7b-instruct`
- `deepseek-r1-qwen3-8b`
- `llama-3-13b-instruct`
- `mistral-7b-instruct-v0.3`
- `qwen2.5-14b-coder`
- `mixtral-8x7b-instruct`
- `gpt-oss-20b`
- `nous-hermes-2-mistral-7b-dpo`

### Cloud Models
- `GPT-4o` (OpenAI)
- `GPT-4o-mini` (OpenAI)
- `Claude Sonnet 4.5` (Anthropic)

### Special Models
- `CTI-BERT` (HuggingFace: ibm-research/CTI-BERT - embedding-based similarity classification)
- `SEC-BERT` (HuggingFace: e3b/security-bert or similar - embedding-based similarity classification)

---

## Evaluation Criteria

### 1. JSON Compliance (Critical)
- **Required:** Valid JSON output that can be parsed
- **Required Field:** `operating_system` must be present
- **Failure Mode:** Invalid JSON or missing field = unusable

### 2. Label Validity (Critical)
- **Required:** `operating_system` must be one of: "Windows", "Linux", "MacOS", or "multiple"
- **Failure Mode:** Invalid label = unusable

### 3. Consistency
- **Metric:** Same OS label across multiple runs (when applicable)
- **Lower variance = better reliability**

### 4. Accuracy (Manual Validation)
- **Ground Truth:** Manual review of articles to determine correct OS
- **Metric:** Percentage of correct OS detections
- **To be populated after manual validation**

---

## Decision Rules

The OS detection agent uses the following indicators:

### Windows Indicators
- Windows-specific commands (powershell.exe, cmd.exe, wmic.exe, reg.exe, schtasks.exe)
- Windows registry paths (HKCU, HKLM, HKEY_*)
- Windows file paths (C:\, %APPDATA%, %TEMP%, %SYSTEMROOT%)
- Windows Event IDs (4688, 4697, 4698, Sysmon events)
- Windows services, scheduled tasks, WMI
- .exe, .dll, .bat, .ps1 file extensions in context

### Linux Indicators
- Linux commands (bash, sh, systemd, cron, apt, yum, systemctl)
- Linux file paths (/etc/, /var/, /tmp/, /home/, /usr/bin/)
- Linux package managers (apt, yum, dpkg, rpm)
- Linux init systems (systemd, init.d, upstart)
- .sh, .deb, .rpm file extensions in context

### MacOS Indicators
- macOS-specific commands (osascript, launchctl, plutil, defaults)
- macOS file paths (/Library/, ~/Library/, /Applications/, /System/)
- macOS package formats (.pkg, .dmg, .app)
- macOS launch agents/daemons (LaunchAgents, LaunchDaemons)

### Multiple Indicators
- Behaviors that work across multiple platforms
- Cross-platform tools or techniques
- Multiple OS-specific indicators present
- Platform-agnostic attacks (web-based, network-level)

---

## Next Steps

1. Run benchmarks across all models
2. Populate benchmark results in this document
3. Perform manual validation to establish ground truth
4. Calculate accuracy metrics
5. Generate final recommendations

