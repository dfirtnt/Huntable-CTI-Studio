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
- `SEC-BERT` (HuggingFace: nlpaueb/sec-bert-base - embedding-based similarity classification)

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

## Similarity Detection Logic

The embedding-based detection (CTI-BERT, SEC-BERT) uses cosine similarity between article content and OS-specific indicator embeddings. The decision logic is:

1. **High Confidence (>0.8 similarity)**: Prefer the top OS unless the gap to second place is < 0.5% (0.005)
   - If gap ≥ 0.5%: Return the top OS (clear winner)
   - If gap < 0.5%: Check if multiple OSes are within 0.5% of the top score
     - If multiple OSes are close: Return "multiple"
     - Otherwise: Return the top OS

2. **Medium-High Confidence (0.75-0.8 similarity)**: 
   - If gap to second > 2%: Return the top OS
   - If gap < 2% and multiple OSes > 0.75: Return "multiple"
   - Otherwise: Return the top OS

3. **Medium Confidence (0.6-0.75 similarity)**: Return the top OS

4. **Low Confidence (<0.6 similarity)**: Return "Unknown"

**Example:**
- Windows: 84.9%, MacOS: 84.1%, Linux: 83.1%
- Gap: 0.8% (84.9% - 84.1%)
- Since gap (0.8%) > 0.5% threshold: Returns "Windows"

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

## Implementation Details

### Embedding Models
- **CTI-BERT**: `ibm-research/CTI-BERT` - Domain-specific BERT model for cybersecurity threat intelligence
- **SEC-BERT**: `nlpaueb/sec-bert-base` - Security-focused BERT model for financial/security documents

### Detection Methods
1. **Classifier** (if trained): Uses RandomForest or LogisticRegression on CTI-BERT/SEC-BERT embeddings
2. **Similarity-based** (fallback): Cosine similarity between article embeddings and OS indicator embeddings
3. **LLM Fallback** (low confidence): Uses configured LLM (default: Mistral-7B-Instruct-v0.3) for inference

### Configuration
- Embedding model selection: Configurable via workflow config page
- Fallback LLM model: Configurable via workflow config page
- Classifier path: `models/os_detection_classifier.pkl` (if trained)

## Next Steps

1. Run benchmarks across all models
2. Populate benchmark results in this document
3. Perform manual validation to establish ground truth
4. Calculate accuracy metrics
5. Generate final recommendations
6. Train classifier model on labeled CTI data

