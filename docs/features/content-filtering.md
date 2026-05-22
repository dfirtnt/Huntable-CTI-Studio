# Content Filtering

The content filtering system removes non-huntable chunks from article content
before the text reaches the configured LLM. It runs as a pre-processing step in
the agentic workflow; the chunk debug interface exposes per-chunk decisions for
inspection and annotation.

## Architecture

The system uses a hybrid approach combining:

1. **Perfect discriminator protection** — chunks containing any of the 92
   threat-hunting keyword patterns are always preserved, regardless of ML score
2. **Pattern-based filters** — fast, deterministic matching against huntable
   and not-huntable pattern sets
3. **ML classification** — RandomForest trained on annotated chunk samples,
   using 20 features per chunk (v3 extractor; see Feature Extractor Versions
   below)

```
Article Content
      |
Chunking (1000 chars, 200 overlap) — overlap-only tail chunks suppressed
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
Chunks whose entire content already appears in the previous chunk's tail
(overlap-only tail chunks) are suppressed.

### Step 2: Pattern Analysis

Each chunk is analyzed against:
- **Huntable patterns:** `powershell\.exe.*-encodedCommand`, `invoke-webrequest.*-uri`, etc.
- **Not huntable patterns:** `acknowledgement|gratitude`, `contact.*mandiant`, etc.

### Step 3: ML Classification

The ML model extracts 20 features (v3 extractor) and classifies each chunk.
Chunks are kept when:
- They contain a perfect discriminator (always preserved), or
- ML confidence exceeds the configured threshold (default 0.7), or
- Pattern match analysis indicates huntable content

The `feature_version` used at inference is auto-detected from a JSON sidecar
at `<model_path>.meta.json`. Models trained before sidecars existed fall back
to v1 (the historic default). The active model in production is v3.

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
**Features:** 20 per chunk (v3 extractor — see below)  
**Model path:** `models/content_filter.pkl`  
**Featurizer metadata:** `models/content_filter.pkl.meta.json`

### Feature Extractor Versions

Three extractor versions exist; the active one is determined at training time
and recorded in the sidecar at `<model_path>.meta.json` so `load_model()` can
re-align `feature_version` correctly when the pkl is loaded later.

| Version | Count | Status | Notes |
|---|---|---|---|
| **v3** | **20** | **Production (2026-05-21+)** | Aligned with ExtractAgent sub-agent contracts: cmdline, registry, proc-tree, services, scheduled-tasks, hunt-queries. Adds explicit negative detectors (YARA, Suricata, beacon configs, atomic-IOC density, educational/hypothetical phrases, MITRE-only TTP tables). Drops standalone `ip_count`/`url_count` (misleading neutral signals) and length-leakage features (`sentence_count`, `avg_word_length`). |
| v2 | 19 | Legacy | Cleanup of v1: dropped length leakage and train/serve skew. Still missing structural detectors for SIGMA/YARA bodies and registry paths. |
| v1 | 27 | Legacy | Original featurizer. Has length-leakage features and treats atomic IOCs as positive signals. Used by pre-2026-05-21 model versions. |

To opt a script into a specific version, pass `feature_version="v3"` when
constructing `ContentFilter` (see `scripts/seed_model.py` and
`scripts/retrain_with_feedback.py`). At inference time, the sidecar overrides
the constructor default to match the on-disk model.

### v3 Feature Categories (current)

| Category | Features |
|---|---|
| Extractor signals (positive) | `cmdline_artifact_count`, `registry_hive_path_count`, `process_lineage_count`, `service_artifact_count`, `scheduled_task_count`, `hunt_query_count` |
| Negative content | `yara_rule_indicator`, `suricata_rule_indicator`, `beacon_config_indicator`, `hash_count`, `atomic_ioc_density`, `educational_phrase_count`, `mitre_ttp_only_density`, `marketing_term_count` |
| Discriminators | `perfect_pattern_count` (noisy 2-char matches stripped), `attacker_placed_path_count`, `technical_term_count`, `has_code_blocks` |
| Aggregates | `cmdline_density`, `extractor_signal_strength` |

## Chunk Debugger

Use `/api/articles/{article_id}/chunk-debug` to inspect per-chunk
classification decisions and collect annotation feedback. This is the primary
interface for identifying why a chunk was dropped and for curating training data
to improve the model.

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
  `scripts/retrain_with_feedback.py`


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
> When no chunks survive the filter (`is_huntable=False`), the pipeline
> terminates immediately with status `no_huntable_content` — no LLM calls
> are made.

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

The ML model is **not trained automatically** on a fresh install or restore.
Run the seed script once to create `models/content_filter.pkl` from the bundled
eval article fixtures:

```bash
python3 scripts/seed_model.py
# then restart the server so the new model is picked up
```

The seed model provides a usable baseline. With the v3 extractor and a
balanced ~1,000-row training set, F1 on Huntable lands around 0.89 on the
240-row curated eval set; the prior v1 baseline was F1 ≈ 0.69.

### Defining "Huntable" for Your Use Case

"Huntable" is a subjective label that reflects your team's priorities. The
default training data treats **behavioral techniques** as huntable (command
lines, process trees, registry modifications, persistence, lateral movement)
and **atomic indicators** (IPs, domains, hashes, CVEs) as not huntable.

Your organisation may define it differently. The model learns whatever labeling
you provide — if you change the definition, rebuild the eval set at
`outputs/evaluation_data/eval_set.csv` to match, otherwise accuracy scores will
appear to degrade against the old ground truth:

```bash
# After annotating chunks with your labeling convention:
python3 scripts/prepare_eval_set.py
# Writes to outputs/evaluation_data/eval_set.csv
```


### Retraining

**From UI feedback (recommended):**
```bash
python3 scripts/retrain_with_feedback.py
docker-compose restart web
```

**From a manual CSV** (columns: `highlighted_text`, `classification`):

Pass the CSV as the `--original` argument to `retrain_with_feedback.py`:
```bash
python3 scripts/retrain_with_feedback.py --original your_training_data.csv
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

**Model not found / "ML model not available" in UI:**
```
Error: [Errno 2] No such file or directory: 'models/content_filter.pkl'
```
Seed the model from the bundled fixtures, then restart the server:
```bash
python3 scripts/seed_model.py
docker-compose restart web
```

**Model fails to load:**
- Check file exists: `ls models/content_filter.pkl`
- Check scikit-learn: `python3 -c "import sklearn; print(sklearn.__version__)"`
- Check logs: `docker-compose logs web | grep -i model`

**Too aggressive filtering (> 90% content removed):**
- Lower confidence threshold (0.5 instead of 0.7)
- Increase chunk size (1000 instead of 400)
- Review pattern rules in `src/utils/content_filter.py`

**Technical content removed incorrectly:**
- Verify the content contains a perfect discriminator keyword (always
  preserved regardless of ML score)
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
features = filter_system.extract_features_v3(text)
```


_Last updated: 2026-05-21_
_Last reviewed: 2026-05-22_
