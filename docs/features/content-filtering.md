# Content Filtering

The content filtering system reduces LLM API costs by removing non-huntable
chunks from article content before it is sent to the configured model. It runs
as a pre-processing step in the agentic workflow and is also available via the
chunk debug interface for inspection and model improvement.

## Architecture

The system uses a hybrid approach combining:

1. **Perfect discriminator protection** — chunks containing any of the 92
   threat-hunting keyword patterns are always preserved, regardless of ML score
2. **Pattern-based filters** — fast, deterministic matching against huntable
   and not-huntable pattern sets
3. **ML classification** — RandomForest trained on annotated chunk samples,
   using 27 features per chunk

```
Article Content
      |
Chunking (1000 chars, 200 overlap)
      |
Hunt Scoring + Pattern Analysis + ML Classification
      |
Filtered Content (huntable chunks only)
      |
LLM
```

## How It Works

### Step 1: Content Chunking

```python
chunks = chunk_content(content, chunk_size=1000, overlap=200)
# Example: 2,500 char article -> 4 overlapping chunks
```

When a sentence boundary pulls the chunk end back, the next chunk starts at
most at `end - overlap` and always moves forward by at least one character.
This keeps chunks tightly overlapping without gaps.

### Step 2: Pattern Analysis

Each chunk is analyzed against:
- **Huntable patterns:** `powershell\.exe.*-encodedCommand`, `invoke-webrequest.*-uri`, etc.
- **Not huntable patterns:** `acknowledgement|gratitude`, `contact.*mandiant`, etc.

### Step 3: ML Classification

The ML model extracts 27 base features and classifies each chunk. Chunks are
kept when:
- They contain a perfect discriminator (always preserved), or
- ML confidence exceeds the configured threshold (default 0.7), or
- Pattern match analysis indicates huntable content

### Step 4: Content Reconstruction

Only kept chunks are reassembled and sent to the LLM.

## Pattern Filters

Pattern categories come from the Hunt Scoring keyword system in
`src/utils/content.py` (see [Scoring](../architecture/scoring.md) for current
counts).

### Huntable Patterns

**Perfect Discriminators (92 patterns):**
- Process names: `rundll32`, `msiexec`, `svchost`, `lsass.exe`, `powershell.exe`
- Registry references: `hklm`, `appdata`, `programdata`, `WINDIR`, `wbem`
- Command execution: `iex`, `wmic`, `comspec`, `findstr`
- File types: `.lnk`, `.iso`, `MZ`, `-accepteula`
- Path patterns: `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`
- Technical patterns: `xor`, `tcp://`, `CN=`, `-ComObject`, `Base64`

**Good Discriminators (89 patterns):**
- Windows paths, script extensions (`.bat`, `.ps1`), attack techniques
  (`mimikatz`, `kerberoast`, `psexec`), cloud/network terms

**LOLBAS Executables (239 patterns):**
- Windows binaries commonly abused in attacks; see `src/utils/content.py`

**Intelligence Indicators (56 patterns):**
- Threat groups, campaign terms, IOC/TTP vocabulary

### Not Huntable Patterns (25 patterns)

Educational and marketing content: `what is`, `how to`, `best practices`,
`free trial`, `contact us`, `learn more`, `blog post`, `webinar`, etc.

## Machine Learning Model

**Algorithm:** RandomForestClassifier  
**Features:** 27 per chunk in the fitted model (31 in debug output only)  
**Model path:** `models/content_filter.pkl`

### Feature Categories

| Category | Features |
|---|---|
| Pattern-based | `huntable_pattern_count`, `not_huntable_pattern_count`, `huntable_pattern_ratio`, `not_huntable_pattern_ratio` |
| Text characteristics | `char_count`, `word_count`, `sentence_count`, `avg_word_length` |
| Technical content | `command_count`, `url_count`, `ip_count`, `file_path_count`, `process_count`, `cve_count`, `technical_term_count` |
| Quality indicators | `marketing_term_count`, `acknowledgment_count`, `marketing_term_ratio`, `technical_term_ratio` |
| Structural | `has_code_blocks`, `has_commands`, `has_urls`, `has_file_paths` |
| Hunt score bins | `hunt_score`, `hunt_score_high`, `hunt_score_medium`, `hunt_score_low` — populated only when callers pass `hunt_score` into `extract_features()`; the current training path does not supply this value, so the fitted model does not learn from these bins |

## Chunk Debugger

The chunk debug interface at `/api/articles/{article_id}/chunk-debug` lets
analysts inspect per-chunk classification decisions and collect feedback for
model improvement.

### Safeguards and Controls

Large articles can generate hundreds of chunks. The debugger balances
responsiveness with completeness:

- **Initial analysis pass**: processes up to `CHUNK_DEBUG_MAX_CHUNKS` (default
  150) using `CHUNK_DEBUG_CONCURRENCY` workers (default 4) with a per-chunk
  timeout of `CHUNK_DEBUG_CHUNK_TIMEOUT` (default 12s). A partial-analysis
  banner appears when the cap is reached.
- **Finish Full Analysis**: click the inline button to re-run with
  `full_analysis=true`. `CHUNK_DEBUG_FULL_CONCURRENCY` and
  `CHUNK_DEBUG_FULL_TIMEOUT` override the initial values if set.
- **Processing summary**: every response includes `processing_summary`
  (processed count, total count, remaining, concurrency, timeout, full-analysis
  flag) so operators can audit coverage.
- **Confidence band filter**: isolate chunks with confidence between 40% and
  60% for quicker review of borderline decisions.

| Environment Variable | Default | Description |
|---|---|---|
| `CHUNK_DEBUG_MAX_CHUNKS` | `150` | Safety cap before finish button appears |
| `CHUNK_DEBUG_CONCURRENCY` | `4` | Worker count for initial pass |
| `CHUNK_DEBUG_CHUNK_TIMEOUT` | `12.0` | Per-chunk timeout (seconds), initial pass |
| `CHUNK_DEBUG_FULL_CONCURRENCY` | *(optional)* | Worker override for full analysis |
| `CHUNK_DEBUG_FULL_TIMEOUT` | *(optional)* | Timeout override for full analysis |

### ML Mismatch Analysis

The chunk debug response includes `ml_stats` for identifying where ML
predictions diverge from actual filtering decisions:

```json
{
  "ml_stats": {
    "total_predictions": 18,
    "correct_predictions": 13,
    "accuracy_percent": 72.2,
    "mismatches": 5
  }
}
```

Mismatched chunks are tagged `"ml_mismatch": true` in `chunk_analysis` for
easy identification. Use the "Show ML Mismatches" filter button in the UI to
isolate them.

### Annotation System

The annotation interface ensures evaluation data matches production chunking:

- **Auto 1000** button expands selections to 1000 characters with smart
  sentence/word boundary detection
- **Manual adjustment controls**: -200, -100, -50, +50, +100, +200 chars
- **Live character counter** with color-coded guidance (green 950-1000,
  yellow < 800, blue 800-950, red > 1000)
- Annotations are stored in `article_annotations` and exported via
  `scripts/export_highlights.py`

## Configuration

### Confidence Thresholds

| Threshold | Behavior | Use Case |
|---|---|---|
| 0.5 | Aggressive filtering | Maximum cost savings |
| 0.7 | Balanced filtering | Recommended default |
| 0.8 | Conservative filtering | Preserve more content |

> **Note**: The standalone content filtering threshold defaults to 0.7. The
> agentic workflow's Junk Filter step uses a separate threshold defaulting to
> 0.8, configurable via `junk_filter_threshold` in workflow configuration.

### Environment Variables

```bash
CONTENT_FILTER_MODEL_PATH=models/content_filter.pkl
DEFAULT_CHUNK_SIZE=1000
DEFAULT_OVERLAP=200
DEFAULT_CONFIDENCE_THRESHOLD=0.7
```

## API

### Optimized Rank Endpoint

**`POST /api/articles/{article_id}/llm-rank-optimized`**

```json
{
  "api_key": "sk-...",
  "use_filtering": true,
  "min_confidence": 0.7
}
```

Response:
```json
{
  "success": true,
  "article_id": 123,
  "analysis": "Sigma huntability score: 8...",
  "optimization": {
    "enabled": true,
    "cost_savings": 0.0019,
    "tokens_saved": 388,
    "chunks_removed": 3,
    "min_confidence": 0.7
  }
}
```

## ML Model Setup

The ML model is **automatically trained during `./setup.sh`**. No manual
configuration is required for initial setup.

### Defining "Huntable" for Your Use Case

"Huntable" is a subjective label that reflects your team's priorities. The
default training data treats **behavioral techniques** as huntable (command
lines, process trees, registry modifications, persistence, lateral movement)
and **atomic indicators** (IPs, domains, hashes, CVEs) as not huntable.

Your organisation may define it differently. The model learns whatever labeling
you provide — but if you change the definition, you must also rebuild the eval
set at `outputs/evaluation_data/eval_set.csv` to match, otherwise accuracy
scores will appear to degrade against the old ground truth:

```bash
# After annotating chunks with your labeling convention:
python3 scripts/export_annotations_for_eval.py
# Writes to outputs/evaluation_data/eval_set.csv
```

### Retraining

**From UI feedback (recommended):**
```bash
python3 scripts/retrain_with_feedback.py
docker-compose restart web
```

**From exported annotations:**
```bash
python3 scripts/export_highlights.py highlighted_text_classifications.csv
python3 scripts/train_content_filter.py --data highlighted_text_classifications.csv
```

**From manual CSV** (columns: `highlighted_text`, `classification`):
```bash
python3 scripts/train_content_filter.py --data your_training_data.csv
```

### Verification

```bash
ls -lh models/content_filter.pkl

python3 -c "
from src.utils.content_filter import ContentFilter
cf = ContentFilter()
cf.load_model()
print('Model loaded' if cf.model else 'Model failed to load')
"
```

## Troubleshooting

**Model not found:**
```
Error: [Errno 2] No such file or directory: 'models/content_filter.pkl'
```
Run `python3 scripts/train_content_filter.py` to train from default data, or
`./setup.sh` to run full setup.

**"ML model not available" in UI after setup:**
Re-run: `python3 scripts/train_content_filter.py --data models/default_content_filter_training_data.csv`

**Model fails to load:**
- Check file exists: `ls models/content_filter.pkl`
- Check scikit-learn: `python3 -c "import sklearn; print(sklearn.__version__)"`
- Check logs: `docker-compose logs web | grep -i model`

**Too aggressive filtering (> 90% content removed):**
- Lower confidence threshold (0.5 instead of 0.7)
- Increase chunk size (1000 instead of 400)
- Review pattern rules in `src/utils/content_filter.py`

**Technical content removed incorrectly:**
- Verify the content contains a perfect discriminator keyword (these are
  always preserved regardless of ML score)
- Add more huntable patterns and retrain

**Enable verbose logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Test individual components:**
```python
is_huntable, confidence = filter_system._pattern_based_classification(text)
is_huntable, confidence = filter_system.predict_huntability(text)
features = filter_system.extract_features(text)
```

_Last updated: 2026-05-01_
