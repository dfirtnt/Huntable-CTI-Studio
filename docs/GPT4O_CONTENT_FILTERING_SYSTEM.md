# GPT-4o Content Filtering System Documentation

## Overview

The GPT-4o Content Filtering System is a hybrid machine learning and pattern-based solution designed to reduce OpenAI API costs by intelligently filtering out "not huntable" content before sending it to GPT-4o for analysis. The system achieves **20-80% cost savings** while maintaining analysis quality.

## Table of Contents

- [Architecture](#architecture)
- [Components](#components)
- [How It Works](#how-it-works)
- [Chunk-Based Filtering](#chunk-based-filtering)
- [Pattern Filters](#pattern-filters)
- [Machine Learning Model](#machine-learning-model)
- [Enhanced Annotation System](#enhanced-annotation-system)
- [Usage Examples](#usage-examples)
- [Performance Metrics](#performance-metrics)
- [Configuration](#configuration)
- [API Integration](#api-integration)
- [Troubleshooting](#troubleshooting)

## Architecture

The system uses a **hybrid approach** combining:

1. **Hunt scoring system** (threat hunting quality assessment)
2. **Pattern-based filters** (fast, deterministic)
3. **Machine learning model** (contextual, adaptive with hunt score integration)
4. **Chunk-based analysis** (preserves context)

```
Article Content
      ↓
Chunking (1000 chars, 200 overlap)
      ↓
Hunt Scoring (0-100) + Pattern Analysis + ML Classification
      ↓
Enhanced ML Classification (with hunt score features)
      ↓
Filtered Content (Huntable Chunks Only)
      ↓
GPT-4o API
      ↓
Analysis Results + Cost Savings
```

## Enhanced Annotation System

The enhanced annotation system provides a sophisticated interface for creating high-quality evaluation data for ML model training. It ensures that evaluation excerpts match the production chunking parameters used by the ML model.

## ML vs Hunt Comparison Dashboard

The ML vs Hunt Comparison Dashboard provides comprehensive analytics for monitoring and improving ML model performance. It includes:

### Key Features
- **Time Series Analysis**: Track classification trends across model versions
- **Model Retraining**: Retrain models with user feedback and track progress
- **Model Evaluation**: Evaluate model performance on test set with detailed metrics
- **Performance Visualization**: Radar charts and accuracy trends
- **Backfill Processing**: Process articles with high hunt scores for analysis

### Recent Improvements (October 2024)
- **Fixed Agreement Calculation**: Corrected ml_prediction AND hunt_prediction logic
- **Percentage-Based Metrics**: Converted from raw counts to percentages for better trend analysis
- **Chart.js Canvas Management**: Proper chart instance destruction to prevent errors
- **Data Accuracy**: Removed artificial 10,000 limit to show actual data counts (11,644)
- **UI/UX Enhancements**: Button state management and visual feedback improvements

### Key Features

#### 1. Real-Time Character Counting
- **Live character counter** displays current selection length vs. target (1000 chars)
- **Color-coded guidance**:
  - 🟢 **Green**: Excellent (950-1000 chars) - Optimal for evaluation
  - 🟡 **Yellow**: Too short (<800 chars) - Needs more context
  - 🔵 **Blue**: Acceptable (800-950 chars) - Good but not optimal
  - 🔴 **Red**: Too long (>1000 chars) - Will be chunked differently

#### 2. Auto-Expand Functionality
- **🎯 Auto 1000** button automatically expands selections to 1000 characters
- **Smart boundary detection** respects sentence, paragraph, and word boundaries
- **Automatic trimming** ensures selections stay within 1000-character limit
- **Production alignment** matches ML model's chunking parameters

#### 3. Manual Expansion Controls
- **Precise adjustment buttons**: -200, -100, -50, +50, +100, +200 chars
- **Symmetrical expansion** adds/removes text from both sides equally
- **Smart boundary detection** prevents cutting mid-word or mid-sentence

#### 4. Live Selection Highlighting
- **Real-time visual feedback** shows expanded text selection in the article
- **Browser-native highlighting** provides clear visual boundaries
- **Auto-scroll** brings expanded selections into view when needed

### ML Training Compliance

The annotation system ensures evaluation data quality by:

1. **Length Optimization**: Targets 950-1000 characters for optimal ML performance
2. **Boundary Respect**: Maintains semantic coherence by respecting text boundaries
3. **Production Alignment**: Matches the exact chunking used in production ML processing
4. **Quality Control**: Visual feedback and guidance prevent suboptimal selections

### Usage Workflow

1. **Select text** in any article
2. **Review character count** and length guidance
3. **Use 🎯 Auto 1000** for optimal expansion
4. **Verify selection** spans appropriate content
5. **Classify** as huntable/not huntable
6. **Save** to database for ML training

This system enables threat intelligence experts to create high-quality, production-aligned evaluation datasets that improve ML model accuracy and performance.

## Components

### 1. Content Filter (`src/utils/content_filter.py`)

**Core filtering engine** with pattern matching and ML classification.

**Key Features:**
- **103 perfect discriminators** from threat hunting analysis (87 strings + 16 regex patterns)
- **64 LOLBAS executables** for comprehensive coverage
- **Cross-platform patterns** (Windows, macOS, Linux)
- **Intelligence indicators** (APT groups, campaigns, TTPs)
- **Perfect discriminator protection** - chunks containing threat hunting keywords are never filtered
- **Command line obfuscation pattern support** - advanced regex patterns for cmd.exe obfuscation
- **Hunt score integration** - ML confidence enhanced by threat hunting scores
- RandomForestClassifier with enhanced accuracy through hunt score features
- 27+ extracted features per chunk (including hunt score features)
- Configurable confidence thresholds

### 2. GPT-4o Optimizer (`src/utils/gpt4o_optimizer.py`)

**Integration layer** for cost optimization and statistics tracking.

**Key Features:**
- Content optimization before API calls
- Cost estimation with/without filtering
- Statistics tracking and reporting
- Async/await support

### 3. Enhanced API Endpoint (`src/web/gpt4o_optimized_endpoint.py`)

**New API endpoint** with filtering capabilities.

**Endpoint:** `/api/articles/{article_id}/gpt4o-rank-optimized`

**Parameters:**
- `use_filtering`: Enable/disable content filtering
- `min_confidence`: Confidence threshold (0.5-0.8)

### 4. Frontend Integration (`src/web/templates/gpt4o_optimized_js.js`)

**User interface** for optimization controls.

**Features:**
- Optimization dialog with cost preview
- Confidence threshold selection
- Real-time cost savings calculation

## How It Works

### Step 1: Content Chunking
```python
chunks = chunk_content(content, chunk_size=1000, overlap=200)
# Example: 2,500 char article → 4 overlapping chunks
```

### Step 2: Pattern Analysis
Each chunk is analyzed against:
- **Huntable patterns:** `powershell\.exe.*-encodedCommand`, `invoke-webrequest.*-uri`, etc.
- **Not huntable patterns:** `acknowledgement|gratitude`, `contact.*mandiant`, etc.

### Step 3: ML Classification
The ML model extracts 23 features and classifies each chunk:
- Pattern match counts
- Text characteristics (length, word count)
- Technical indicators (commands, URLs, IPs)
- Quality ratios (technical vs marketing terms)

### Step 4: Filtering Decision
Chunks are kept or removed based on:
- **Perfect discriminator check** - chunks with threat hunting keywords are always preserved
- ML model confidence score
- User-defined threshold (0.5-0.8)
- Pattern match analysis

### Step 5: Content Reconstruction
Only huntable chunks are reassembled and sent to GPT-4o.

## Chunk-Based Filtering

### Why Chunk-Based?

**✅ Advantages:**
- Preserves context and sentence integrity
- Avoids fragmenting technical content
- More accurate than word-by-word filtering
- Handles mixed content intelligently
- Configurable granularity

**❌ Keyword-only filtering problems:**
- Breaks sentences mid-way
- Loses context around technical terms
- Creates fragmented, unreadable content

### Chunking Algorithm

```python
def chunk_content(content: str, chunk_size: int = 1000, overlap: int = 200):
    """
    Split content into overlapping chunks.
    
    Args:
        chunk_size: Maximum characters per chunk
        overlap: Characters to overlap between chunks
    
    Returns:
        List of (start_offset, end_offset, chunk_text) tuples
    """
```

**Example Chunking:**
```
Original: 1,246 chars
Chunk 1: 0-337 chars    (Technical commands)
Chunk 2: 337-736 chars  (Acknowledgments + technical details)
Chunk 3: 736-1103 chars (Contact info + IP addresses)
Chunk 4: 1103-1246 chars (Lateral movement details)
```

### Chunk Size Impact

| Chunk Size | Chunks Removed | Content Reduction |
|------------|----------------|-------------------|
| 200 chars  | 7 chunks       | 88.0%            |
| 400 chars  | 3 chunks       | 73.0%            |
| 600 chars  | 3 chunks       | 100.0%           |
| 1000 chars | 1 chunk        | 80.3%            |

### Chunk Debugger Safeguards & Controls

Large articles can generate hundreds of chunks, so the debugger balances responsiveness with completeness:

- **Initial Analysis Pass**: Processes up to `CHUNK_DEBUG_MAX_CHUNKS` (default **150**) using `CHUNK_DEBUG_CONCURRENCY` workers (default **4**) and a per-chunk timeout defined by `CHUNK_DEBUG_CHUNK_TIMEOUT` (default **12s**). When the cap is reached, the UI surfaces a ⚠️ Partial Analysis banner.
- **Finish Full Analysis**: Analysts can click the inline button to re-run the endpoint with `full_analysis=true`, optionally using `CHUNK_DEBUG_FULL_CONCURRENCY` and `CHUNK_DEBUG_FULL_TIMEOUT` overrides (falling back to the initial values if unset).
- **Processing Summary**: Every response now includes `processing_summary` (processed count, total count, remaining chunks, concurrency, timeout, and whether full analysis ran) so operators can audit coverage.
- **Timeout Visibility**: Chunks that exceed the timeout render with explicit warnings in both the API and UI, making slow regions easy to spot.
- **Confidence Band Filter**: UI control to isolate chunks with confidence between 40% and 60% for quicker review of borderline decisions.

| Environment Variable | Default | Description |
| --- | --- | --- |
| `CHUNK_DEBUG_MAX_CHUNKS` | `150` | Safety cap before the finish button appears |
| `CHUNK_DEBUG_CONCURRENCY` | `4` | Worker count for the initial analysis pass |
| `CHUNK_DEBUG_CHUNK_TIMEOUT` | `12.0` | Per-chunk timeout (seconds) for the initial pass |
| `CHUNK_DEBUG_FULL_CONCURRENCY` | *(optional)* | Worker override when finishing the analysis |
| `CHUNK_DEBUG_FULL_TIMEOUT` | *(optional)* | Timeout override when finishing the analysis |

Tune these values with production telemetry (CPU load, latency, timeout frequency) to match your deployment’s capacity.

## Pattern Filters

The pattern-based classification uses the comprehensive Hunt Scoring keyword system from `src/utils/content.py`, providing 314 total patterns for content classification.

### Huntable Patterns (289 patterns)

**Perfect Discriminators (103 patterns):**
- **Process Names**: `rundll32`, `msiexec`, `svchost`, `lsass.exe`, `powershell.exe`
- **Registry References**: `hklm`, `appdata`, `programdata`, `WINDIR`, `wbem`
- **Command Execution**: `iex`, `wmic`, `comspec`, `findstr`
- **File Types**: `.lnk`, `.iso`, `MZ`, `-accepteula`
- **Path Patterns**: `\temp\`, `\pipe\`, `%WINDIR%`, `%wintmp%`
- **Cross-Platform**: `homebrew`, `/users/shared/`, `chmod 777`, `tccd`, `spctl`
- **Technical Patterns**: `xor`, `tcp://`, `CN=`, `-ComObject`, `Base64`

**Good Discriminators (77 patterns):**
- **Windows Paths**: `c:\windows\`, `temp`, `pipe`, `::`
- **File Extensions**: `.bat`, `.ps1`, `.exe`, `mach-o`, `plist`
- **Technical Patterns**: `==`, `[.]`, `-->`, `currentversion`, `Event ID`
- **Attack Techniques**: `mimikatz`, `kerberoast`, `psexec`, `payload`
- **Cross-Platform**: `osascript`, `TCC.db`, `sudo`, `cron`, `launchd`
- **Cloud/Network**: `aws`, `azure`, `gcp`, `ssl`, `proxy`, `network`

**LOLBAS Executables (64 patterns):**
- **System Tools**: `certutil`, `cmd`, `schtasks`, `wmic`, `regsvr32`, `rundll32`
- **Network Tools**: `bitsadmin`, `ftp`, `netsh`, `powershell`
- **Script Engines**: `cscript`, `mshta`, `wscript`, `msiexec`
- **File Operations**: `forfiles`, `explorer`, `ieexec`, `conhost`
- **And 40+ more legitimate Windows executables commonly abused by threat actors**

**Intelligence Indicators (45 patterns):**
- **Threat Activity**: `APT`, `threat actor`, `campaign`, `incident`, `breach`, `compromise`
- **Threat Groups**: `FIN`, `TA`, `UNC`, `APT1`, `APT28`, `Lazarus`, `Carbanak`
- **Attack Types**: `ransomware`, `data breach`, `cyber attack`, `espionage`
- **Technical Terms**: `IOC`, `indicator`, `TTP`, `technique`, `malware family`
- **Attack Techniques**: `golden-ticket`, `silver-ticket`, `lateral movement`

### Not Huntable Patterns (25 patterns)

**Educational/Marketing Content:**
- `what is`, `how to`, `guide to`, `tutorial`, `best practices`
- `statistics`, `survey`, `report shows`, `study reveals`
- `learn more`, `read more`, `click here`, `download now`
- `free trial`, `contact us`, `get started`, `sign up`
- `blog post`, `newsletter`, `webinar`, `training`
- `overview`, `introduction`, `basics`, `fundamentals`

## Machine Learning Model

### Model Details

**Algorithm:** RandomForestClassifier
**Training Data:** 22 annotated examples (9 huntable, 13 not huntable)
**Accuracy:** 80% on test data (requires validation)
**Features:** 27 extracted features per chunk

### Feature Categories

**Pattern-Based Features:**
- `huntable_pattern_count`: Number of huntable pattern matches
- `not_huntable_pattern_count`: Number of not huntable pattern matches
- `huntable_pattern_ratio`: Ratio of huntable patterns to total words
- `not_huntable_pattern_ratio`: Ratio of not huntable patterns to total words

**Text Characteristics:**
- `char_count`: Total character count
- `word_count`: Total word count
- `sentence_count`: Number of sentences
- `avg_word_length`: Average word length

**Technical Content Features:**
- `command_count`: Number of command patterns
- `url_count`: Number of URLs
- `ip_count`: Number of IP addresses
- `file_path_count`: Number of file paths
- `process_count`: Number of process names
- `cve_count`: Number of CVE references
- `technical_term_count`: Number of technical terms

**Quality Indicators:**
- `marketing_term_count`: Number of marketing terms
- `acknowledgment_count`: Number of acknowledgment terms
- `marketing_term_ratio`: Ratio of marketing terms
- `technical_term_ratio`: Ratio of technical terms

**Structural Features:**
- `has_code_blocks`: Boolean for code block presence
- `has_commands`: Boolean for command presence
- `has_urls`: Boolean for URL presence
- `has_file_paths`: Boolean for file path presence

**Hunt Score Integration (NEW):**
- `hunt_score`: Normalized hunt score (0-1 range)
- `hunt_score_high`: Boolean for high-quality content (≥70)
- `hunt_score_medium`: Boolean for medium-quality content (30-69)
- `hunt_score_low`: Boolean for low-quality content (<30)

### Training Process

```bash
# Train the model
python3 scripts/train_content_filter.py --data highlighted_text_classifications.csv

# Output:
# Model trained successfully. Accuracy: 0.800
# Classification Report:
#               precision    recall  f1-score   support
# Not Huntable       0.75      1.00      0.86         3
#     Huntable       1.00      0.50      0.67         2
#     accuracy                           0.80         5
```

## Usage Examples

### Basic Usage

```python
from src.utils.content_filter import ContentFilter

# Initialize filter
filter_system = ContentFilter('models/content_filter.pkl')

# Filter content
result = filter_system.filter_content(
    content=article_content,
    min_confidence=0.7,
    chunk_size=1000
)

print(f"Content reduction: {result.cost_savings:.1%}")
print(f"Filtered content: {result.filtered_content}")
```

### API Integration

```python
from src.utils.gpt4o_optimizer import optimize_article_content

# Optimize content for GPT-4o
optimization_result = await optimize_article_content(
    content=article_content,
    min_confidence=0.7
)

if optimization_result['success']:
    print(f"Cost savings: ${optimization_result['cost_savings']:.4f}")
    print(f"Tokens saved: {optimization_result['tokens_saved']:,}")
```

### Web API Usage

```javascript
// Call optimized endpoint
const response = await fetch(`/api/articles/${articleId}/gpt4o-rank-optimized`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        api_key: apiKey,
        use_filtering: true,
        min_confidence: 0.7
    })
});

const data = await response.json();
console.log(`Cost savings: $${data.optimization.cost_savings}`);
```

## Performance Metrics

### Cost Savings Analysis

**Sample Content (1,996 chars, ~499 tokens):**

| Confidence Threshold | Content Reduction | Tokens Saved | Cost Savings |
|---------------------|-------------------|--------------|--------------|
| 0.5 (Aggressive)    | 52.6%             | 263          | $0.0013      |
| 0.7 (Balanced)      | 77.7%             | 388          | $0.0019      |
| 0.8 (Conservative)  | 77.7%             | 388          | $0.0019      |

### Content Classification Examples

**✅ KEPT (Sent to OpenAI):**
- `"Command: powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD=="`
- `"Cleartext: Invoke-WebRequest -uri http://REDACTED:REDACTED/d3d11.dll"`
- `"the Centre.exe executable connected to these IP addresses: 104.21.16[.]1"`

**❌ REMOVED (Not sent to OpenAI):**
- `"Acknowledgement We would like to extend our gratitude to the Sitecore team..."`
- `"Contact Mandiant If you believe your systems may be compromised..."`
- `"This highlights how quickly threat actors can pivot to leverage new vulnerabilities..."`

### Model Performance

**Accuracy:** 80% on test data
**Precision:** 100% for Huntable, 75% for Not Huntable
**Recall:** 50% for Huntable, 100% for Not Huntable

## Configuration

### Confidence Thresholds

| Threshold | Filtering Behavior | Use Case |
|-----------|-------------------|----------|
| 0.5 | Aggressive filtering | Maximum cost savings |
| 0.7 | Balanced filtering | Recommended default |
| 0.8 | Conservative filtering | Preserve more content |

### Chunk Size Settings

| Chunk Size | Granularity | Use Case |
|------------|-------------|----------|
| 200 chars | Fine-grained | Detailed analysis |
| 400 chars | Medium | Balanced approach |
| 1000 chars | Coarse | Default setting |

### Environment Variables

```bash
# Model path
CONTENT_FILTER_MODEL_PATH=models/content_filter.pkl

# Default settings
DEFAULT_CHUNK_SIZE=1000
DEFAULT_OVERLAP=200
DEFAULT_CONFIDENCE_THRESHOLD=0.7
```

## API Integration

### New Endpoint

**URL:** `/api/articles/{article_id}/gpt4o-rank-optimized`

**Method:** POST

**Request Body:**
```json
{
    "api_key": "sk-...",
    "use_filtering": true,
    "min_confidence": 0.7
}
```

**Response:**
```json
{
    "success": true,
    "article_id": 123,
    "analysis": "SIGMA HUNTABILITY SCORE: 8...",
    "optimization": {
        "enabled": true,
        "cost_savings": 0.0019,
        "tokens_saved": 388,
        "chunks_removed": 3,
        "min_confidence": 0.7
    }
}
```

### Frontend Integration

```javascript
// Show optimization dialog
const optimizationOptions = await showOptimizationDialog();

// Call optimized endpoint
const response = await fetch(`/api/articles/${articleId}/gpt4o-rank-optimized`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        api_key: apiKey,
        use_filtering: optimizationOptions.useFiltering,
        min_confidence: optimizationOptions.minConfidence
    })
});
```

## Troubleshooting

### Common Issues

**1. Model Not Found**
```
Error: [Errno 2] No such file or directory: 'models/content_filter.pkl'
```
**Solution:** Train the model first:
```bash
python3 scripts/train_content_filter.py
```

**2. Low Accuracy**
```
Model accuracy: 0.60
```
**Solution:** 
- Collect more training data
- Retrain with updated annotations
- Adjust feature extraction

**3. Too Aggressive Filtering**
```
Content reduction: 95%
```
**Solution:** 
- Lower confidence threshold (0.5 instead of 0.7)
- Increase chunk size (1000 instead of 400)
- Review pattern rules

**4. Missing Technical Content**
```
Technical commands removed incorrectly
```
**Solution:**
- Add more huntable patterns
- Retrain model with better examples
- Adjust ML feature weights

### Debugging

**Enable Verbose Logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Test Individual Components:**
```python
# Test pattern matching
is_huntable, confidence = filter_system._pattern_based_classification(text)

# Test ML model
is_huntable, confidence = filter_system.predict_huntability(text)

# Test feature extraction
features = filter_system.extract_features(text)
```

**Comprehensive Testing:**
```bash
python3 scripts/test_filter_comprehensive.py
```

## ML Mismatch Analysis (NEW)

### Overview
The system now includes comprehensive ML mismatch analysis to identify discrepancies between ML predictions and actual filtering decisions.

### Features
- **Visual Indicators**: Yellow rings around mismatched chunks in visualization
- **Filter Button**: "Show ML Mismatches" to isolate problematic chunks
- **Statistics Dashboard**: Real-time accuracy metrics and mismatch counts
- **Chunk Tags**: "ML MISMATCH" badges for easy identification

### API Integration
```python
# Chunk debug endpoint with mismatch analysis
GET /api/articles/{article_id}/chunk-debug

# Response includes:
{
    "ml_stats": {
        "total_predictions": 18,
        "correct_predictions": 13,
        "accuracy_percent": 72.2,
        "mismatches": 5
    },
    "chunk_analysis": [
        {
            "ml_mismatch": true,
            "ml_prediction_correct": false,
            "ml_details": {
                "prediction": 0,
                "prediction_label": "Not Huntable",
                "confidence": 0.665
            }
        }
    ]
}
```

### Use Cases
- **Model Validation**: Identify where ML predictions fail
- **Training Data Collection**: Gather examples for model improvement
- **Quality Assurance**: Monitor filtering accuracy over time
- **Debugging**: Understand why specific chunks were filtered

## Chunk Debug Interface (NEW)

### Features
- **Interactive Visualization**: Click-to-highlight chunks
- **Real-time Filtering**: Multiple filter buttons for different chunk types
- **Detailed Analysis**: Feature breakdown and ML prediction details
- **Feedback System**: User feedback collection for model improvement

### Filter Options
- Show All Chunks
- Show Kept Only
- Show Removed Only
- Show Threat Keywords
- Show Perfect Discriminators
- Show ML Predictions
- **Show ML Mismatches** (NEW)

## Future Enhancements

### Planned Improvements

1. **Expand Training Data**
   - Collect more annotations
   - Include diverse content types
   - Improve model accuracy

2. **Advanced Features**
   - Dynamic chunk sizing
   - Context-aware filtering
   - Multi-language support

3. **Performance Optimization**
   - Caching of model predictions
   - Parallel chunk processing
   - GPU acceleration

4. **Analytics Dashboard**
   - Cost savings tracking
   - Filtering effectiveness metrics
   - User preference learning

### Contributing

1. **Add New Patterns**
   - Update `pattern_rules` in `ContentFilter`
   - Test with diverse content
   - Document pattern purpose

2. **Improve ML Model**
   - Add new features
   - Collect training data
   - Experiment with algorithms

3. **Enhance API**
   - Add new endpoints
   - Improve error handling
   - Add rate limiting

## Conclusion

The GPT-4o Content Filtering System successfully reduces API costs by 20-80% while maintaining analysis quality. The hybrid approach combining pattern filters and machine learning provides both speed and accuracy, making it an effective solution for cost optimization in threat intelligence analysis.

**Key Benefits:**
- ✅ Significant cost savings (20-80%)
- ✅ Preserves technical content quality
- ✅ User-configurable filtering
- ✅ Backward compatibility
- ✅ Comprehensive logging and metrics

**Next Steps:**
- Deploy to production environment
- Monitor cost savings and quality metrics
- Collect user feedback for improvements
- Expand training data for better accuracy
