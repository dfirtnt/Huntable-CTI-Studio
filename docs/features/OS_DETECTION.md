# OS Detection System

Automated operating system detection for threat intelligence articles using embedding-based classification with LLM fallback.

## Overview

The OS Detection system identifies the target operating system(s) mentioned in threat intelligence articles. This enables:
- **Workflow Filtering**: Agentic workflow continues only for Windows-focused articles
- **Targeted Analysis**: Focus SIGMA rule generation on relevant OS-specific techniques
- **Content Classification**: Categorize articles by operating system for better organization

## Architecture

### Detection Methods

1. **Keyword-Based Detection** (Tier 1)
   - Fast initial classification using keyword pattern matching
   - Checks article content for OS-specific terms (e.g., Windows registry paths, PowerShell commands, Linux paths)
   - This is the fastest detection method and handles clear-cut cases before invoking ML models

2. **Embedding-Based Classification** (Primary)
   - Uses CTI-BERT or SEC-BERT embeddings
   - RandomForest or LogisticRegression classifier
   - Trained on OS-specific indicator texts
   - High confidence threshold (>0.8) for single OS detection

2. **LLM Fallback** (Secondary)
   - Mistral-7B-Instruct-v0.3 via LMStudio
   - Used when embedding confidence is low
   - Provides reasoning for OS detection

### OS Labels

- **Windows**: PowerShell, registry, Event IDs, Windows paths
- **Linux**: bash, systemd, package managers, Linux paths
- **MacOS**: osascript, launchctl, macOS paths
- **multiple**: Multiple operating systems detected
- **Unknown**: Unable to determine OS

## Integration

### Agentic Workflow

OS Detection is integrated as **Step 0** (first) in the agentic workflow:

```
0. OS Detection ← Windows only continues; non-Windows terminates
1. Junk Filter
2. LLM Ranking
3. Extract Agent
4. Generate SIGMA
5. Similarity Search
6. Promote to Queue
```

**Workflow Behavior:**
- If Windows detected: Workflow continues to extraction
- If non-Windows detected: Workflow terminates gracefully with `TERMINATION_REASON_NON_WINDOWS_OS` (actual code string: `non_windows_os_detected`)
- If multiple OS detected: Workflow continues (may include Windows)

### API Integration

OS Detection is available via:
- **Workflow Execution**: Automatic during agentic workflow
- **Manual Testing**: `test_os_detection_manual.py` script

## Configuration

### Environment Variables

```bash
# Embedding model selection
OS_DETECTION_MODEL=ibm-research/CTI-BERT  # or nlpaueb/sec-bert-base

# Classifier type
OS_DETECTION_CLASSIFIER=random_forest  # or logistic_regression

# LLM fallback
LMSTUDIO_API_URL=http://host.docker.internal:1234/v1
LMSTUDIO_MODEL=mistralai/mistral-7b-instruct-v0.3
```

### Model Selection

**Embedding Models:**
- `ibm-research/CTI-BERT`: Optimized for cybersecurity content (default)
- `nlpaueb/sec-bert-base`: Security-focused embeddings

**Classifier Types:**
- `random_forest`: Better for complex patterns (default)
- `logistic_regression`: Faster, simpler model

## Usage

### Manual Testing

```bash
python test_os_detection_manual.py --article-id 1937
```

### Programmatic Usage

```python
from src.services.os_detection_service import OSDetectionService

service = OSDetectionService(
    model_name="ibm-research/CTI-BERT",
    classifier_type="random_forest"
)

result = service.detect_os(article_content)
# Returns: {"os": "Windows", "confidence": 0.95, "method": "embedding"}
```

### Workflow Integration

OS Detection runs automatically during agentic workflow execution. Results are stored in:
- `agentic_workflow_executions.os_detection_result` (JSONB)
- `agentic_workflow_executions.detected_os` (string)

## Technical Details

### Similarity Logic

**High Confidence (>0.8):**
- Prefer top OS unless gap to second is < 0.5%
- Prevents false "multiple" classifications when one OS is clearly dominant

**Low Confidence (≤0.8):**
- Falls back to LLM for reasoning
- LLM provides final OS determination with explanation

### OS Indicators

The system uses OS-specific indicator texts for embedding comparison:

**Windows:**
- PowerShell, cmd.exe, wmic.exe, reg.exe
- Registry paths (HKCU, HKLM, HKEY)
- Windows file paths (C:\, %APPDATA%, %TEMP%)
- Event IDs (4688, 4697, 4698, Sysmon)
- Windows services, scheduled tasks, WMI

**Linux:**
- bash, sh, systemd, cron
- Package managers (apt, yum, dpkg, rpm)
- Linux file paths (/etc/, /var/, /tmp/)
- Init systems (systemd, init.d, upstart)

**MacOS:**
- osascript, launchctl, plutil, defaults
- macOS file paths (/Library/, ~/Library/, /Applications/)
- Package formats (.pkg, .dmg, .app)
- LaunchAgents, LaunchDaemons

## Performance

- **Embedding Detection**: ~100-200ms per article
- **LLM Fallback**: ~2-5 seconds per article
- **GPU Acceleration**: Automatic if CUDA available
- **Model Loading**: Lazy loading on first use

## Troubleshooting

### Low Confidence Scores

If confidence scores are consistently low:
1. Check embedding model is loaded correctly
2. Verify classifier model exists at `models/os_detection_classifier.pkl`
3. Retrain classifier with more training data

### LLM Fallback Not Working

If LLM fallback fails:
1. Verify LMStudio is running: `curl http://localhost:1234/v1/models`
2. Check model is loaded: Mistral-7B-Instruct-v0.3
3. Verify API URL in environment variables

### False Positives

If OS detection is incorrect:
1. Review OS indicator texts in `os_detection_service.py`
2. Add more training examples for problematic cases
3. Adjust confidence thresholds in workflow configuration

## Related Documentation

- **Workflow Configuration**: See workflow_config.py in src/web/routes/
- **OS Detection Service**: See os_detection_service.py in src/services/

